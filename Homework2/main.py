import os
import shlex
import signal


# os gives me the process-related functions like fork(), execvp(), waitpid(), chdir(), and kill()
# shlex lets me split command input properly even when the user has quotes
# signal gives me constants like SIGTERM that I can send to a process


class Job:
    def __init__(self, pid, command):
        # pid is the actual operating system process id
        self.pid = pid

        # keep the command so I can show it again with jobs
        self.command = command

        # every new background job starts off running
        self.status = "Running"


# my own job numbers like [1], [2], [3] point to Job objects here
jobs = {}

# keep increasing this whenever I create a new background job
next_job_id = 1


def reap_jobs():
    # keep checking until there are no more finished children to collect
    while True:
        try:
            # -1 means check any child process
            # WNOHANG makes sure I check without freezing the shell
            pid, status = os.waitpid(-1, os.WNOHANG)

            # pid == 0 means I still have children, but none finished yet
            if pid == 0:
                break

            # find which job belongs to the pid that just finished
            for job_id, job in jobs.items():
                if job.pid == pid:
                    job.status = "Done"
                    break

        # this happens when there are no child processes left to wait for
        except ChildProcessError:
            break


def show_jobs():
    # show all the background jobs I am currently tracking
    for job_id, job in jobs.items():
        print(f"[{job_id}]  {job.status:<10} {job.command}")


def foreground_job(job_id):
    # make sure the job number actually exists first
    if job_id not in jobs:
        print(f"fg: {job_id}: no such job")
        return

    job = jobs[job_id]

    print(job.command)

    try:
        # now I actually want to wait because this job is being brought to the foreground
        os.waitpid(job.pid, 0)

    # if it was somehow already reaped, there is nothing else to wait for
    except ChildProcessError:
        pass

    # once the foreground job is finished I don't need to track it anymore
    del jobs[job_id]


def kill_job(job_id):
    # first check that the shell knows about this job
    if job_id not in jobs:
        print(f"kill: {job_id}: no such job")
        return

    job = jobs[job_id]

    try:
        # SIGTERM tells the process to terminate
        os.kill(job.pid, signal.SIGTERM)

        # I still need to wait for the killed process so it doesn't become a zombie
        os.waitpid(job.pid, 0)

        print(f"[{job_id}]  Terminated  {job.command}")

    # process may have already ended before I tried to kill it
    except ProcessLookupError:
        pass

    # process may already have been reaped
    except ChildProcessError:
        pass

    # either way I no longer want this job in my jobs list
    del jobs[job_id]


def main():
    # I change this counter whenever I create a background job
    global next_job_id

    # keep the shell running until the user exits
    while True:

        # before showing another prompt, clean up any background processes that finished
        reap_jobs()

        try:
            line = input("myshell> ").strip()

        # Ctrl+D gives EOF, so I treat that like exiting the shell
        except EOFError:
            print()
            break

        # ignore empty input and just show another prompt
        if not line:
            continue

        try:
            # shlex handles quoted input correctly
            # example: echo "hello world" keeps "hello world" as one argument
            args = shlex.split(line)

        # can happen if the user has something like an unfinished quote
        except ValueError as e:
            print(f"myshell: {e}")
            continue

        if not args:
            continue


        background = False

        # a trailing & means I should run the command in the background
        if args[-1] == "&":
            background = True

            # & is shell syntax, the actual program should not receive it as an argument
            args.pop()

        if not args:
            continue


        # rebuild the command as text so I can display it later in jobs
        command = " ".join(args)


        # built-in commands have to be handled by my shell itself

        if args[0] == "exit":
            break


        elif args[0] == "cd":

            # if no directory was given, go back to the user's home directory
            path = args[1] if len(args) > 1 else os.environ.get("HOME", "/")

            try:
                # cd has to change the directory of this shell process itself
                # doing this in a child would not change the parent's directory
                os.chdir(path)

            except OSError as e:
                print(f"cd: {e}")

            continue


        elif args[0] == "jobs":

            # just print the jobs I have saved in the dictionary
            show_jobs()
            continue


        elif args[0] == "fg":

            # fg needs a job number like fg 1
            if len(args) < 2:
                print("fg: missing job id")
                continue

            try:
                # convert the job id from input text into an integer
                job_id = int(args[1])

                foreground_job(job_id)

            except ValueError:
                print("fg: job id must be a number")

            continue


        elif args[0] == "kill":

            # same idea here, kill needs one of my shell's job ids
            if len(args) < 2:
                print("kill: missing job id")
                continue

            try:
                job_id = int(args[1])

                kill_job(job_id)

            except ValueError:
                print("kill: job id must be a number")

            continue


        # if it was not a built-in command, create a new child process
        # fork() duplicates the current process
        pid = os.fork()


        # fork() returns 0 inside the child process
        if pid == 0:

            try:
                # replace the child process with the program the user asked for
                # execvp also searches PATH so commands like ls and sleep work
                os.execvp(args[0], args)

            # execvp only comes back if something failed
            except FileNotFoundError:
                print(
                    f"myshell: {args[0]}: command not found",
                    flush=True
                )

                # stop this child so it does not accidentally continue running my shell loop
                os._exit(1)

            except PermissionError:
                print(
                    f"myshell: {args[0]}: permission denied",
                    flush=True
                )

                os._exit(1)


        # in the parent, fork() gives me the child's actual pid
        else:

            if background:

                # don't wait for background jobs
                # just save the process so I can track it later
                jobs[next_job_id] = Job(pid, command)

                print(f"[{next_job_id}] {pid} {command}")

                # next background job gets the next number
                next_job_id += 1

            else:

                try:
                    # foreground commands should block the shell until that child finishes
                    os.waitpid(pid, 0)

                # don't let Ctrl+C crash the whole Python shell
                except KeyboardInterrupt:
                    pass


# only run main() if I directly run this Python file
if __name__ == "__main__":
    main()