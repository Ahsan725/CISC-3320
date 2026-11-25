import argparse
import os
import sys

#the disk logic stays in the file, this file just deals with typed commands
from filesystem import FSError, FileSystem


#this is the text printed by help, it doesnt run any of the commands
HELP = """Commands:
  mkdir /path
  ls /path
  write /path text
  cat /path
  rm /path
  stat /path
  fsstat
  save [image_path]
  load [image_path]
  mkfs
  help
  quit
"""


def process_command(fs, line, image_path):
    #I split at most twice so spaces inside the text are kept
    words = line.split(None, 2)
    #an empty line should just give me another prompt
    if not words:
        return True
    #the first word is the command, whatever is left becomes its arguments
    command, *args = words
    #False tells the main loop to stop, saving happens there before the program exits
    if command in ("quit", "exit") and not args:
        return False
    try:
        if command == "help" and not args:
            print(HELP, end="")
        elif command == "mkdir" and len(args) == 1:
            fs.mkdir(args[0])
        elif command == "write" and 1 <= len(args) <= 2:
            #turn text into bytes here, leaving out the text creates an empty file
            fs.write(args[0], args[1].encode("utf-8") if len(args) == 2 else b"")
        elif command == "cat" and len(args) == 1:
            #send any pending text out before switching to raw byte output
            sys.stdout.flush()
            #I dont add a newline because cat should output only the file bytes
            sys.stdout.buffer.write(fs.read(args[0]))
            sys.stdout.buffer.flush()
        elif command == "ls" and len(args) == 1:
            #the file already marks directory names with a slash
            for name, size in fs.ls(args[0]):
                print(f"{name}   {size}")
        elif command == "rm" and len(args) == 1:
            fs.rm(args[0])
        elif command == "stat" and len(args) == 1:
            #stat describes one file or directory, including the blocks it owns
            s = fs.stat(args[0])
            print(f"inode {s['inode']}  {s['type']}  size {s['size']}  blocks {s['blocks']}"
                  f"  pointer block {s['indirect']}")
        elif command == "fsstat" and not args:
            #fsstat describes the entire disk instead of just one path
            s = fs.fsstat()
            print(f"inodes {s['inodes_used']}/64 used  {s['inodes_free']} free   "
                  f"data blocks {s['blocks_used']}/237 used  {s['blocks_free']} free   "
                  f"files {s['files']}  dirs {s['dirs']}")
        elif command == "save" and len(args) <= 1:
            #without a filename I use the same image chosen when starting the program
            fs.save(args[0] if args else image_path)
        elif command == "load" and len(args) <= 1:
            #loading replaces whats in memory, it doesnt change the default save filename
            fs.load(args[0] if args else image_path)
        elif command == "mkfs" and not args:
            #this clears the in-memory disk, so use it only when starting over
            fs.mkfs()
        else:
            print("error: unknown command or wrong arguments. Type 'help'.")
    except FSError as exc:
        #a bad command should print its error and let me keep using the file system
        print(f"error: {exc}")
    return True


def main():
    #argparse handles --help and lets me choose a different disk image
    parser = argparse.ArgumentParser(description="HW6 toy file system")
    parser.add_argument("--image", default="disk.img", help="disk image to load and save")
    args = parser.parse_args()
    #start blank, then load the previous disk if the image file is already there
    fs = FileSystem()
    if os.path.exists(args.image):
        try:
            fs.load(args.image)
        except FSError as exc:
            print(f"error: {exc}")
            #I ask before replacing an image that failed to load
            try:
                answer = input("Start with a reformatted disk? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                return
            #anything except an explicit yes leaves the bad image untouched
            if answer.lower() != "y":
                return

    #show prompts when typing, but keep them out of piped command output
    interactive = sys.stdin.isatty()
    if interactive:
        print("Toy file system. Type 'help'.")
    try:
        while True:
            try:
                #input removes the final newline, not the spaces within the command text
                line = input("fs> " if interactive else "")
            except (EOFError, KeyboardInterrupt):
                #ctrl d or ctrl c ends the loop and still reaches the save below
                if interactive:
                    print()
                break
            #quit returns False, other commands keep the loop going
            if not process_command(fs, line, args.image):
                break
    finally:
        #I save on exit including ctrl c so the next run can load the same disk
        try:
            fs.save(args.image)
        except FSError as exc:
            #make a failed save visible instead of pretending the session was saved
            print(f"error saving image: {exc}", file=sys.stderr)


#only open the command loop when running this file directly
if __name__ == "__main__":
    main()
