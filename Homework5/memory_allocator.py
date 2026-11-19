#this simulates a fixed size heap by tracking blocks without storing actual bytes
from dataclasses import dataclass
from typing import Optional


#I use this custom error when an operation cannot be completed
class AllocatorError(ValueError):
    pass


#each block tracks its starting address size and optional allocation name
@dataclass
class Block:
    start: int
    size: int
    name: Optional[str] = None

    @property
    def free(self) -> bool:
        #a block is free when it has no allocation name
        return self.name is None

    @property
    def end(self) -> int:
        #I calculate the exclusive ending address instead of storing it seperately
        return self.start + self.size





#this class manages allocation freeing and memory statistics
class MemoryAllocator:
    POLICIES = ("first", "best", "worst")

    def __init__(self, pool_size: int = 1000, policy: str = "first") -> None:
        #I validate the pool size and policy before creating any blocks
        if type(pool_size) is not int or pool_size <= 0:
            raise AllocatorError("pool size must be a positive integer")
        
        if policy not in self.POLICIES:
            raise AllocatorError("policy must be first, best, or worst")
        self.pool_size = pool_size
        self.policy = policy
        
        #start with one free block covering the entire pool
        self.blocks = [Block(0, pool_size)]
        
        #I remember freed names to tell a double free apart from an unknown name
        self.freed_names: set[str] = set()
        self.check_invariants()

    
    
    def set_policy(self, policy: str) -> None:
        #switch allocation strategies without changing existing memory blocks
        if policy not in self.POLICIES:
            raise AllocatorError("policy must be first, best, or worst")
        self.policy = policy



    def _choose_hole(self, size: int) -> Optional[int]:
        #find the indexes of free blocks large enough for this request
        candidates = [i for i, b in enumerate(self.blocks) if b.free and b.size >= size]
        
        if not candidates:
            return None
        if self.policy == "first":
            #first fit picks the earliest suitable block in address order
            return candidates[0]
        if self.policy == "best":
            #best fit picks the smallest suitable block using the lowest address for ties
            return min(candidates, key=lambda i: (self.blocks[i].size, self.blocks[i].start))
        #worst fit picks the largest hole and also uses the lowest address for ties
        return min(candidates, key=lambda i: (-self.blocks[i].size, self.blocks[i].start))




    def alloc(self, name: str, size: int) -> tuple[int, int]:
        #I reject invalid names sizes and names already in use before changing memory
        if not isinstance(name, str) or not name or name.isspace() or any(ch.isspace() for ch in name):
            raise AllocatorError("allocation name must be a nonempty word")
        if type(size) is not int or size <= 0:
            raise AllocatorError("allocation size must be a positive integer")
        if any(b.name == name for b in self.blocks):
            raise AllocatorError(f"name '{name}' is already allocated")

        #choose a free block based on the currently selected policy
        index = self._choose_hole(size)
        if index is None:
            #even if total free memory is enough the request fails without one large enough hole
            raise AllocatorError(f"out of memory: cannot allocate {size} bytes for '{name}'")

        hole = self.blocks[index]
        allocated = Block(hole.start, size, name)
        if hole.size == size:
            #an exact fit replaces the hole without creating an empty block
            self.blocks[index] = allocated
        else:
            #I split a larger hole into the allocated block and the unused remainder
            remainder = Block(hole.start + size, hole.size - size)
            self.blocks[index:index + 1] = [allocated, remainder]
        
        
        #reusing a freed name means it should no longer count as previously freed
        self.freed_names.discard(name)
        self.check_invariants()
        #return the half open address range where end is not included
        return allocated.start, allocated.end




    def free(self, name: str) -> tuple[int, int]:
        #find the block belonging to the requested allocation name
        index = next((i for i, b in enumerate(self.blocks) if b.name == name), None)
        if index is None:
            #I distinguish freeing the same name twice from freeing a name that never existed
            if name in self.freed_names:
                raise AllocatorError(f"double free: '{name}' was already freed")
            raise AllocatorError(f"unknown allocation: '{name}'")

        old = self.blocks[index]
        old_range = (old.start, old.end)
        #remove the name to turn this allocated block back into a free hole
        self.blocks[index] = Block(old.start, old.size)
        self.freed_names.add(name)

        #I merge with the free block on the left first and adjust the index after deleting
        if index > 0 and self.blocks[index - 1].free:
            self.blocks[index - 1].size += self.blocks[index].size
            del self.blocks[index]
            index -= 1
        
        #then merge with the right neighbor so adjacent holes become one larger hole
        if index + 1 < len(self.blocks) and self.blocks[index + 1].free:
            self.blocks[index].size += self.blocks[index + 1].size
            del self.blocks[index + 1]
        self.check_invariants()
        
        #return the original address range even if coalescing made the hole larger
        return old_range

    
    
    def stats(self) -> dict:
        #collect only free blocks to calculate remaining memory and fragmentation
        holes = [b for b in self.blocks if b.free]
        total_free = sum(b.size for b in holes)
        largest = max((b.size for b in holes), default=0)
        return {
            "pool": self.pool_size,
            "used": self.pool_size - total_free,
            "free": total_free,
            "holes": len(holes),
            "largest_hole": largest,
            #I use external fragmentation based on how much free memory is outside the largest hole
            "fragmentation_percent": 100 * (1 - largest / total_free) if total_free else 0.0,
        }

    def memory_map(self) -> str:
        
        #display every block in address order with its size and allocation status
        return "\n".join(
            f"[{b.start:>5}-{b.end:<5}) {b.size:>5} bytes  "
            + ("FREE" if b.free else f"USED {b.name}")
            for b in self.blocks
        )

    
    
    def free_list(self) -> str:
        
        #show only the free address ranges or none if the entire pool is allocated
        return " ".join(
            f"[{b.start}-{b.end})" for b in self.blocks if b.free
        ) or "(none)"

    
    
    def check_invariants(self) -> None:
        #I run these checks after changes to catch gaps overlaps and other memory mistakes
        address = 0
        names: set[str] = set()
        
        
        for i, block in enumerate(self.blocks):
            #every block must have a positive size and begin exactly where the previous one ended
            assert block.size > 0, "zero or negative block"
            assert block.start == address, "gap or overlap"
            #two neighboring free blocks should have already been merged
            assert not (i and self.blocks[i - 1].free and block.free), "adjacent free blocks not merged"
            if not block.free:
                #I make sure the same allocation name is never used by two active blocks
                assert block.name not in names, "duplicate allocated name"
                names.add(block.name)
            address = block.end
        
        
        #the blocks must cover the full pool and used plus free must equal its size
        assert address == self.pool_size, "total block sizes differ from pool size"
        s = self.stats()
        assert s["used"] + s["free"] == self.pool_size
