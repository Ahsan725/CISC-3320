# CISC 3320 HW3: Scheduler Simulator

## Files

- `simulator.py` — complete Python 3 simulator and command-line interface
- `sample.csv` — lecture's four-process workload
- `custom.csv` — additional original five-process workload, with staggered arrivals
- `comparison_report.txt` — output of all five algorithms on both workloads, including per-process metrics and Gantt timelines



## Input format

CSV with either `PID,arrival,burst,priority` or `PID,arrival,burst` (priority defaults to 0). Header optional. Nonnegative integer arrival times and positive integer burst times. Process IDs must be unique. Arbitrary arrival times are supported, including periods with no ready work.

## Design decisions

- **FCFS:** non-preemptive; order by arrival, then original CSV input order.
- **SJF:** non-preemptive; among arrived jobs select smallest burst, then earliest arrival, then input order.
- **Round Robin:** preemptive; default quantum=4; FIFO queue; newly arrived jobs enter the queue before re-adding the running job; finish exactly at the quantum boundary means do not requeue.
- **Priority:** non-preemptive; **smaller priority number means higher priority**; ties broken by earlier arrival and then input order. By default static priorities are used so the professor's lecture sample matches exactly. Optional aging `--aging 5` enables `effective_priority = base_priority - (wait_so_far // 5)` at each scheduling decision. This aging rule uses current ready waiting; since no preemption occurs in Priority scheduling, ready waiting before first execution equals current time minus arrival.
- **MLFQ:** three queues Q0/Q1/Q2, with default quantum sizes 4, 8, 16 respectively. New jobs join Q0; completing a full quantum without finishing demotes one level (remaining in bottom queue when already at bottom); higher-priority arrivals interrupt lower-priority work; periodic boost every 50 units returns all ready jobs to Q0; same-level order is FIFO. The boost counter uses absolute simulated time and is configurable via `--boost`.
- **I/O behavior:** the supplied lecture workload format contains only one total CPU burst and has **no I/O-event or blocking timestamps**. Therefore, no process voluntarily blocks for I/O in this simulation. The lecture's "I/O reward" rule (no demotion on early I/O block) is described conceptually but cannot be exercised without adding new input fields. Simulating fictitious I/O behavior would violate the specified input model.
- **Metrics:** turnaround = completion - arrival; response = first_start - arrival; waiting = turnaround - burst. The waiting shortcut assumes a CPU-only workload without separate I/O-blocking intervals.
- **Comparison:** each algorithm receives a fresh set of `SimProcess` objects, so updated `remaining_time`, `start_time`, and `completion_time` fields never contaminate another algorithm.

## Expected sample validation

| Algorithm | Average waiting | Average turnaround | Average response |
|---|---:|---:|---:|
| FCFS | 7.50 | 12.25 | 7.50 |
| SJF | 4.50 | 9.25 | 4.50 |
| Round Robin (q=4) | 8.50 | 13.25 | 5.00 |
| Priority (static) | 9.00 | 13.75 | 9.00 |
| MLFQ (4/8/16) | 8.50 | 13.25 | 5.00 |
