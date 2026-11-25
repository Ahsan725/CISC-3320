# CISC 3320 HW6

This is a small file system stored in a bytearray. filesystem.py handles the disk and cli.py handles the commands.

# Run

Use Python 3. No extra packages are needed.

Open a terminal in Homework6 and run python3 cli.py.

The program loads disk.img if it exists or starts with a fresh disk. It saves when I quit, press Ctrl+D or press Ctrl+C at the prompt. To use another image, run python3 cli.py --image other.img.

# Commands

mkdir /docs creates a directory.

write /docs/a.txt hello creates a file or replaces its contents. Text does not need quotes. Leaving out the text makes an empty file.

cat /docs/a.txt prints the contents without adding a newline.

ls /docs lists names and sizes. Directory names end with a slash.

rm /docs/a.txt deletes a file. Directories must be empty before removing them.

stat /docs/a.txt shows the inode, type, size and blocks.

fsstat shows used and free inodes and data blocks, plus file and directory counts.

save and load use the startup image filename. Either command can also take another filename, like save backup.img. Loading another image does not change where the program saves on exit.

mkfs clears the disk in memory. Saving or quitting afterwards replaces the image with that cleared disk.

help shows the commands. quit or exit closes the program.

# Design

I used the lecture layout: 256 blocks of 256 bytes and 64 inodes. Block 0 holds the superblock, blocks 1 and 2 hold the bitmaps, blocks 3–18 hold the inode table, and blocks 19–255 hold data.

Each inode has 10 direct pointers and one indirect pointer. The largest file is 18,944 bytes. Names can be up to 28 UTF-8 bytes. All persistent information stays inside the bytearray, and allocation uses first-fit.

Paths start with /. The command interface uses paths without spaces. Extra slashes and trailing slashes are ignored. Dot and dot-dot paths are not supported. Failed commands leave the disk unchanged. A corrupt image is reported, and the program asks before starting over.
