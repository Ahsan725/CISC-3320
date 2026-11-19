import argparse
from memory_allocator import AllocatorError, MemoryAllocator


#these are the commands I made available to the user
HELP = """Commands:
  alloc <name> <size>_____Allocate a named block
  free <name>_____Release a named block
  policy <first|best|worst>_____Change placement policy
  stats_____Show usage and external fragmentation
  map_____Show all blocks in address order
  help_____Show commands
  quit_____Exit
"""


def process_command(allocator: MemoryAllocator, line: str) -> bool:
    #this function processes one command and tells my main loop whether to continue
    words = line.split()

    #I skip empty inputs and lines starting with a hashtag
    if not words or words[0].startswith("#"):
        return True

    #seperate the command from the arguments provided
    command, *args = words

    #return false when the user wants to exit the program
    if command in ("quit", "exit") and not args:
        return False

    #display the help menu without modifying any memory
    if command == "help" and not args:
        print(HELP, end="")
        return True

    #I handle errors here so invalid commands dont crash my program
    try:
        if command == "alloc" and len(args) == 2:
            #convert the requested memory size into an integer
            try:
                size = int(args[1])
            except ValueError as exc:
                #I raise an error if the user enters a size that isnt an integer
                raise AllocatorError("size must be an integer") from exc

            #the allocator finds a free block and returns the addresses it used
            start, end = allocator.alloc(args[0], size)
            print(f"{args[0]}: {size} bytes at [{start}-{end})")

        elif command == "free" and len(args) == 1:
            #I free the named block so that memory becomes available again
            start, end = allocator.free(args[0])
            print(f"{args[0]} freed (previously [{start}-{end}))")

        elif command == "policy" and len(args) == 1:
            #change the allocation strategy between first fit best fit and worst fit
            allocator.set_policy(args[0])
            print(f"policy: {allocator.policy}-fit")

        elif command == "stats" and not args:
            #I retrieve the current memory statistics from my allocator
            s = allocator.stats()

            #display the pool size used memory free memory and number of holes
            print(f"pool {s['pool']}   used {s['used']}   free {s['free']}   holes {s['holes']}")

            #largest hole shows the biggest allocation that could currently fit
            print(f"largest hole {s['largest_hole']}   fragmentation {s['fragmentation_percent']:.1f}%")

            #I show the free list to see exactly where unused memory remains
            print(f"free list: {allocator.free_list()}")

        elif command == "map" and not args:
            #print every memory block in order so I can visualize the layout
            print(allocator.memory_map())

        else:
            #handle unknown commands or incorrect arguments
            print("ERROR: unknown command or wrong arguments. Type 'help'.")

    except AllocatorError as exc:
        #I print the error instead of letting the whole program crash
        print(f"ERROR: {exc}")

    #return true so my command loop keeps running
    return True


def main() -> None:
    #I use argparse to allow different settings when launching the program
    parser = argparse.ArgumentParser(description="HW5 simulated heap allocator")

    #the memory pool starts at 1000 bytes unless I specify another size
    parser.add_argument("--size", type=int, default=1000, help="pool size in bytes (default: 1000)")

    #only allow the three allocation policies supported by my program
    parser.add_argument("--policy", choices=MemoryAllocator.POLICIES, default="first")

    #I added script support so commands can also be loaded from a file
    parser.add_argument("--script", type=argparse.FileType("r"), help="read commands from a file")

    #read the arguments before initializing the allocator
    args = parser.parse_args()

    try:
        allocator = MemoryAllocator(args.size, args.policy)
    except AllocatorError as exc:
        #I stop execution if the user provides an invalid starting configuration
        parser.error(str(exc))

    #check whether a script file was provided
    if args.script is not None:
        with args.script as stream:
            #I process each line as if the user typed it into the terminal
            for line in stream:
                #skip displaying empty lines and comments from the script
                if line.strip() and not line.lstrip().startswith("#"):
                    print(f"alloc> {line.strip()}")

                #stop processing commands when quit is encountered
                if not process_command(allocator, line):
                    break

        #I return here to avoid starting interactive mode after the script finishes
        return

    #start the interactive terminal if no script was provided
    print(f"Memory allocator: {args.size} bytes, {args.policy}-fit. Type 'help'.")

    while True:
        try:
            #keep asking for commands until the user exits
            line = input("alloc> ")

        except (EOFError, KeyboardInterrupt):
            #I also allow exiting using ctrl d or ctrl c
            print()
            break

        #exit the loop if process_command returns false
        if not process_command(allocator, line):
            break


#I only call main when this file is executed directly
if __name__ == "__main__":
    main()
