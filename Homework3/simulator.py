#!/usr/bin/env python3
#Command-line flags let me switch workloads and algorithms without editing the script each time.
import argparse
import csv
#A deque makes sense here since I keep moving jobs from the front to the back.
from collections import deque
from dataclasses import dataclass
from pathlib import Path
#Keeping all process info together means I don't have to track separate arrays for timing and priority.
@dataclass
class SimProcess:
    pid: str
    arrival_time: int
    burst_time: int
    priority: int = 0
    remaining_time: int = 0
    start_time: int = None
    completion_time: int = None
    input_order: int = 0
    #Start remaining_time at the full burst, then reduce it as the CPU runs the process.
    def __post_init__(self):
        self.remaining_time = self.burst_time


def read_workload(path):
    processes = []
    #Keep track of IDs as I read them so duplicate processes don't sneak into the workload.
    seen = set()
    with open(path, newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        for line_no, row in enumerate(reader, 1):
            #Blank rows shouldn't cause an error if I add spacing to a CSV.
            if not row or not any(value.strip() for value in row):
                continue
            if row[0].lstrip().startswith('#'):
                continue
            row = [part.strip() for part in row]
            #A header is just a label, not a process, so skip it if the CSV has one.
            if row[0].lower() in ('pid', 'process') and len(row) >= 3:
                continue
            #Priority isn't needed for every algorithm, so let the fourth column be optional.
            if len(row) not in (3, 4):
                raise ValueError(f'Line {line_no}: expected PID,arrival,burst[,priority]')
            pid = row[0]
            if not pid or pid in seen:
                raise ValueError(f'Line {line_no}: missing or duplicate PID {pid!r}')
            try:
                arrival = int(row[1])
                burst = int(row[2])
                priority = int(row[3]) if len(row) == 4 else 0
            except ValueError as exc:
                raise ValueError(f'Line {line_no}: arrival, burst and priority must be integers') from exc
            #No process can arrive before time 0 or need zero/negative CPU time in this simulation.
            if arrival < 0 or burst <= 0:
                raise ValueError(f'Line {line_no}: arrival must be >= 0 and burst must be > 0')
            seen.add(pid)
            processes.append(SimProcess(pid, arrival, burst, priority, input_order=len(processes)))
    if not processes:
        raise ValueError('Workload is empty')
    return processes


#Each algorithm should get a fresh copy, otherwise earlier runs would change the results.
def fresh_copy(processes):
    #Recreating the objects resets everything that changed during a run. I still need the original inputs untouched.
    return [SimProcess(p.pid, p.arrival_time, p.burst_time, p.priority,
                       input_order=p.input_order) for p in processes]


def run_slice(p, now, duration, segments):
    #Catch bad slice lengths here so they don't silently corrupt the timeline.
    if duration <= 0 or p.remaining_time < duration:
        raise ValueError('Invalid CPU slice')
    if p.start_time is None:
        p.start_time = now  #Don't overwrite this when the process runs again; response time needs its very first start.
    end = now + duration
    #Save the start and end of each turn for the timeline, especially when a job runs multiple times.
    segments.append((p.pid, now, end))
    p.remaining_time -= duration
    #Only mark completion when there's no CPU time left, not after every slice.
    if p.remaining_time == 0:
        p.completion_time = end
    return end


def fcfs_schedule(processes, quantum=None):
    segments = []
    now = 0
    #Sort by arrival first. If jobs arrive together, I keep their original CSV order.
    for p in sorted(processes, key=lambda p: (p.arrival_time, p.input_order)):
        #Jump past idle time rather than pretending a process ran before it arrived.
        now = max(now, p.arrival_time)
        now = run_slice(p, now, p.remaining_time, segments)
    return segments


def sjf_schedule(processes, quantum=None):
    segments = []
    now = 0
    pending = processes[:]
    while pending:
        #Only look at jobs ready now. I can't pick a shorter job that hasn't arrived yet.
        ready = [p for p in pending if p.arrival_time <= now]
        if not ready:
            now = min(p.arrival_time for p in pending)
            ready = [p for p in pending if p.arrival_time <= now]
        #This is non-preemptive SJF, so once I pick the shortest ready job, it finishes its whole burst.
        p = min(ready, key=lambda p: (p.burst_time, p.arrival_time, p.input_order))
        pending.remove(p)
        now = run_slice(p, now, p.remaining_time, segments)
    return segments


def round_robin_schedule(processes, quantum=None):
    #Use 4 as the default quantum, but leave it adjustable when testing RR.
    q = 4 if quantum is None else quantum
    if q <= 0:
        raise ValueError('Round Robin quantum must be positive')
    segments = []
    now, next_idx = 0, 0
    pending = sorted(processes, key=lambda p: (p.arrival_time, p.input_order))
    #A ready queue keeps the turns fair; I don't want RR accidentally favoring one job.
    ready = deque()
    completed = 0
    while completed < len(pending):
        if not ready and next_idx < len(pending):
            now = max(now, pending[next_idx].arrival_time)
        while next_idx < len(pending) and pending[next_idx].arrival_time <= now:
            ready.append(pending[next_idx])
            next_idx += 1
        if not ready:
            continue
        #Run only up to the quantum, or less if the job finishes before that.
        p = ready.popleft()
        now = run_slice(p, now, min(q, p.remaining_time), segments)
        #Add anything that arrived during this slice before putting the unfinished job back. Otherwise it cuts in line.
        while next_idx < len(pending) and pending[next_idx].arrival_time <= now:
            ready.append(pending[next_idx])
            next_idx += 1
        #Not finished? Back of the line. Only count it as complete when its burst reaches zero.
        if p.remaining_time:
            ready.append(p)
        else:
            completed += 1
    return segments


def priority_schedule(processes, quantum=None, aging_interval=0):
    """Non-preemptive priority; smaller number means higher priority.
    Optional aging: effective = base - floor(ready_wait/aging_interval).
    Because selection is non-preemptive, aging changes priority at dispatch time.
    """
    #I can turn aging off with 0, but a negative interval wouldn't make sense.
    if aging_interval < 0:
        raise ValueError('Aging interval cannot be negative')
    segments = []
    now = 0
    pending = processes[:]
    while pending:
        ready = [p for p in pending if p.arrival_time <= now]
        if not ready:
            now = min(p.arrival_time for p in pending)
            ready = [p for p in pending if p.arrival_time <= now]
        #Recalculate when I choose the next job, since waiting can improve its effective priority.
        def key(p):
            #Lower number = higher priority, so subtract the aging bonus instead of adding it.
            effective = p.priority - ((now - p.arrival_time) // aging_interval if aging_interval else 0)
            return (effective, p.arrival_time, p.input_order)
        #This one is non-preemptive too; a new high-priority arrival waits for the current job to finish.
        p = min(ready, key=key)
        pending.remove(p)
        now = run_slice(p, now, p.remaining_time, segments)
    return segments


#Keep the timeline and queue-event history separate so I can show both without mixing their formats.
class MLFQTrace(list):
    def __init__(self):
        super().__init__()
        self.events = []


def mlfq_schedule(processes, quantum=None, boost_interval=50, quanta=(4, 8, 16)):
    """Three-level feedback scheduling, with periodic global priority boosts.
    Arrivals join Q0. Exhausting a queue's time quantum demotes to the next
    queue if not complete. A higher-priority arrival preempts a lower queue.
    No I/O events exist in the assigned workload format, so early blocking
    cannot occur
    """
    if not quanta or any(q <= 0 for q in quanta):
        raise ValueError('MLFQ quanta must be positive')
    if boost_interval < 0:
        raise ValueError('Boost interval cannot be negative')
    pending = sorted(processes, key=lambda p: (p.arrival_time, p.input_order))
    next_idx, completed, now = 0, 0, 0
    #Separate deques for each level. Q0 gets checked first because it's the highest priority.
    queues = [deque() for _ in quanta]
    result = MLFQTrace()
    #Setting boost to 0 means no periodic reset, hence None for the next boost time.
    next_boost = boost_interval if boost_interval else None
    #New arrivals always start at Q0, even if other jobs have already been demoted.
    def admit():
        nonlocal next_idx
        while next_idx < len(pending) and pending[next_idx].arrival_time <= now:
            queues[0].append(pending[next_idx])
            next_idx += 1
    while completed < len(pending):
        if not any(queues) and next_idx < len(pending):
            now = max(now, pending[next_idx].arrival_time)
        #The clock can jump during idle periods, so account for any boost times passed along the way.
        if next_boost is not None:
            while now >= next_boost:
                #Move waiting jobs back up periodically so lower queues don't get stuck forever.
                moved = [p for queue in queues for p in queue]
                queues = [deque(moved)] + [deque() for _ in quanta[1:]]
                result.events.append((next_boost, '-', 'BOOST', 'All ready jobs move to Q0'))
                next_boost += boost_interval
        admit()
        if not any(queues):
            continue
        #Look from Q0 downward. A job in a lower queue shouldn't run while a higher queue has work.
        level = next(i for i, queue in enumerate(queues) if queue)
        p = queues[level].popleft()
        #Cap the slice by both the current queue's quantum and the CPU time still needed.
        duration = min(p.remaining_time, quanta[level])
        #A new Q0 arrival should interrupt Q1/Q2 instead of waiting for their entire quantum.
        if level > 0 and next_idx < len(pending):
            duration = min(duration, max(1, pending[next_idx].arrival_time - now))
        #Stop at the boost boundary. I need to reshuffle priorities before letting anything keep running.
        if next_boost is not None:
            duration = min(duration, next_boost - now)
        start = now
        now = run_slice(p, now, duration, result)
        admit()
        #Only demote for using the whole quantum, not for getting interrupted early.
        full_slice = duration == quanta[level]
        if p.remaining_time == 0:
            completed += 1
            action = 'Finished'
        elif full_slice:
            #Using a whole quantum suggests a CPU-heavy job. Move it down, but never past the lowest queue.
            new_level = min(level + 1, len(quanta)-1)
            queues[new_level].append(p)
            action = f'Full quantum ({duration}), demoted to Q{new_level}' if new_level != level else f'Full quantum ({duration}), remains in Q{level}'
        else:
            #An interrupted job hasn't used a whole quantum, so leave it at the same level and put it first there.
            queues[level].appendleft(p)
            action = f'Interrupted after {duration} units'
        result.events.append((start, p.pid, f'Q{level}', action))
    return result


def metrics(processes):
    rows = []
    #Keep the report in CSV order so I can compare results even when execution order changes.
    for p in sorted(processes, key=lambda p: p.input_order):
        if p.start_time is None or p.completion_time is None:
            raise ValueError(f'Process {p.pid} did not finish')
        #Turnaround includes everything from when a job arrives until it finishes.
        tat = p.completion_time - p.arrival_time
        waiting = tat - p.burst_time  #Waiting = turnaround - burst here because I'm not modeling any separate I/O blocked time.
        #Response uses the first start, not all the times the job got scheduled again.
        response = p.start_time - p.arrival_time
        rows.append((p.pid, p.arrival_time, p.burst_time, p.priority,
                     p.start_time, p.completion_time, waiting, tat, response))
    averages = tuple(sum(row[i] for row in rows)/len(rows) for i in (6, 7, 8))
    return rows, averages


def fmt_table(headers, rows):
    contents = [tuple(str(x) for x in headers)] + [tuple(str(x) for x in row) for row in rows]
    #Make columns wide enough for the longest entry so the printed table stays readable.
    widths = [max(len(row[i]) for row in contents) for i in range(len(headers))]
    return '\n'.join('  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row))
                     for row in contents)


def run_algorithm(name, original, args):
    #Start from the same untouched workload for every algorithm, or the averages won't be comparable.
    processes = fresh_copy(original)
    methods = {'fcfs': fcfs_schedule, 'sjf': sjf_schedule, 'rr': round_robin_schedule,
               'priority': priority_schedule, 'mlfq': mlfq_schedule}
    #Pass only the settings each scheduler uses, rather than making every function handle every option.
    if name == 'rr':
        segments = methods[name](processes, args.quantum)
    elif name == 'priority':
        segments = methods[name](processes, aging_interval=args.aging)
    elif name == 'mlfq':
        segments = methods[name](processes, boost_interval=args.boost, quanta=tuple(args.mlfq_quanta))
    else:
        segments = methods[name](processes)
    rows, averages = metrics(processes)
    return segments, rows, averages


def detail(name, original, args):
    segments, rows, averages = run_algorithm(name, original, args)
    lines = [f'Algorithm: {name.upper()}', '']
    #A list of start-end intervals makes the actual execution order easier to verify.
    lines.append('Execution timeline: ' + ' | '.join(f'{pid}[{a}-{b}]' for pid, a, b in segments))
    lines.append('')
    cols = ['PID', 'Arrival', 'Burst', 'Priority', 'Start', 'Completion', 'Waiting', 'Turnaround', 'Response']
    lines.append(fmt_table(cols, rows))
    lines += ['', f'Average Waiting Time:    {averages[0]:.2f}',
              f'Average Turnaround Time: {averages[1]:.2f}',
              f'Average Response Time:   {averages[2]:.2f}']
    #MLFQ needs its extra queue/boost events shown, or it would be hard to explain why jobs moved.
    if name == 'mlfq':
        lines += ['', 'MLFQ events:', fmt_table(['Time', 'PID', 'Queue', 'Action'], segments.events)]
    return '\n'.join(lines)


def compare(original, args):
    names = ['fcfs', 'sjf', 'rr', 'priority', 'mlfq']
    labels = ['FCFS', 'SJF', f'Round Robin (q={args.quantum})',
              'Priority', f'MLFQ ({"/".join(map(str,args.mlfq_quanta))})']
    rows = []
    #Compare the averages side by side, with each scheduler starting from fresh process states.
    for name, label in zip(names, labels):
        _, _, avg = run_algorithm(name, original, args)
        rows.append((label, *(f'{v:.2f}' for v in avg)))
    return fmt_table(['Algorithm', 'Avg Waiting', 'Avg Turnaround', 'Avg Response'], rows)


def main():
    parser = argparse.ArgumentParser(description='CISC 3320 HW3: CPU scheduling simulator')
    parser.add_argument('--workload', required=True, type=Path, help='CSV: PID,arrival,burst,priority')
    #Choose one scheduler OR compare all. These flags shouldn't conflict.
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--algo', choices=['fcfs', 'sjf', 'rr', 'priority', 'mlfq'])
    group.add_argument('--compare', action='store_true')
    parser.add_argument('--quantum', type=int, default=4, help='Round Robin quantum (default 4)')
    parser.add_argument('--aging', type=int, default=0,
                        help='Priority aging interval (0 disables; use 5 to enable lecture formula)')
    parser.add_argument('--boost', type=int, default=50,
                        help='MLFQ priority boost interval (default 50, 0 disables)')
    parser.add_argument('--mlfq-quanta', type=int, nargs='+', default=[4, 8, 16],
                        help='MLFQ queue quantum sizes (default 4 8 16)')
    #Parse the CLI options first, then use them to decide what to run.
    args = parser.parse_args()
    try:
        original = read_workload(args.workload)
        #Catch bad quantum/aging/boost values now rather than trying to debug strange results later.
        if args.quantum <= 0 or args.aging < 0 or args.boost < 0 or any(q <= 0 for q in args.mlfq_quanta):
            parser.error('quantum and all queue quantums must be positive; aging and boost must be >= 0')
        print(compare(original, args) if args.compare else detail(args.algo, original, args))
    #Show a clear CLI error if the file is missing or the CSV values are invalid.
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
