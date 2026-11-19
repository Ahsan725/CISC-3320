# CISC 3320 HW5
## Files

- memory_allocator.py: reusable MemoryAllocator class and allocation logic.
- cli.py: interactive shell and script runner.
- README.md: setup, command reference, design and fragmentation formula.


## Run

From this directory:


python cli.py
python cli.py --size 2000 --policy best


Commands: alloc <name> <size>, free <name>, policy <first|best|worst>, stats, map, help, quit.

Example:

text
alloc> alloc A 200
A: 200 bytes at [0-200)
alloc> alloc B 300
B: 300 bytes at [200-500)
alloc> alloc C 150
C: 150 bytes at [500-650)
alloc> free B
B freed (previously [200-500))
alloc> stats
pool 1000   used 350   free 650   holes 2
largest hole 350   fragmentation 46.2%
free list: [200-500) [650-1000)


## Design decisions

**Representation:** One address-sorted list of Block(start, size, name) records. name=None denotes a free block. Every address belongs to exactly one block, and all ranges are **half-open**, [start, end), so end is not included. Data bytes themselves are not stored.

**Search:** The allocator filters free blocks with size >= request. First-fit selects the first sufficient hole in address order. Best-fit selects the smallest sufficient hole. Worst-fit selects the largest sufficient hole. Ties select the lowest starting address.

**Allocation and splitting:** Allocate at the beginning of the selected hole. An oversized hole is replaced with the allocated block followed by the remainder. An exact fit replaces the entire hole and creates no zero-size block.

**Free and coalescing:** Find the allocated name, replace its block with a free block, merge with any free block immediately before it, then merge with any free block immediately after it. Names may be reused after a successful free. A set of freed names distinguishes double free from never-allocated names.

**Validation:** Pool size and allocation sizes must be positive integers; allocation names must be nonempty single words and unique among live allocations. Invalid policy, duplicate name, unknown name, double free, and failed allocation produce an error without changing the pool. Failed alloc never reserves a name.

**Invariant:** Blocks have positive size, cover [0, pool_size) without gaps or overlaps, and never leave neighboring free blocks unmerged. Consequently used + free == pool_size. These checks run after every successful allocation and free.

## Statistics

- **Used:** sum of allocated block sizes.
- **Free:** sum of free block sizes.
- **Holes:** number of free blocks.
- **Largest hole:** maximum free block size, or 0 when none remain.
- **External fragmentation (%):** 100 * (1 - largest_hole / total_free) when total_free > 0; otherwise **0%** (no free space exists to fragment). This matches Lecture 10 slide 37.
- **Internal fragmentation:** 0 for this simulator, because block headers and alignment are **not** modeled. Both are optional lecture extensions.

## Testing

Test the allocator interactively with commands like alloc A 200, alloc B 300, free A, map, and stats. For the lecture trace, allocate A 200, B 300, C 150, D 100; free B and D; allocate E 280 and F 100; then try G 260. G should fail under all three policies.

## PyShell OS integration

Import the class from memory_allocator.py and call alloc, free, stats, or memory_map directly. These methods return data rather than print. Printing is isolated in cli.py. If a future PyShell OS runs jobs concurrently, protect access to the shared allocator with a lock; this toy implementation itself is not thread-safe.
