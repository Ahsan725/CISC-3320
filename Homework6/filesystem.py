#struct lets me turn numbers into fixed size records inside the disk
import struct
import threading

#this gives the command loop one kind of error to catch when a request fails
class FSError(ValueError):
    pass


class FileSystem:
    #each block is a 256 byte chunk of my pretend disk
    BLOCK_SIZE = 256
    #256 of those chunks gives me a 64 KB disk in total
    NUM_BLOCKS = 256
    #an inode is the record holding a file's type, size and block numbers
    NUM_INODES = 64
    #blocks 0 through 18 hold bookkeeping, file contents start at block 19
    DATA_START = 19
    #10 direct blocks plus 64 blocks reached through the indirect pointer
    MAX_SIZE = 74 * BLOCK_SIZE
    #type, size, 10 direct pointers, 1 indirect pointer and 15 padding bytes
    INODE = struct.Struct("<BI10II15x")
    #a directory entry connects a 28 byte name to a 4 byte inode number
    ENTRY = struct.Struct("<28sI")
    #these seven numbers describe the disk layout so it can be checked when loading
    SUPER = struct.Struct("<7I")

    def __init__(self, image_path=None):
        #only one operation should change the disk at a time when my shell shares it
        self.lock = threading.Lock()
        #the whole file system lives here, not in a seperate dictionary of files
        self.disk = bytearray(self.BLOCK_SIZE * self.NUM_BLOCKS)
        #no image means a fresh disk, otherwise pick up where the saved one left off
        if image_path is None:
            self.mkfs()
        else:
            self.load(image_path)

    def mkfs(self):
        with self.lock:
            #start over with every byte set to zero
            self.disk[:] = bytes(len(self.disk))
            #save the sizes followed by the starting blocks of the two bitmaps, inode table and data
            self.SUPER.pack_into(self.disk, 0, 256, 256, 64, 1, 2, 3, 19)
            #the bitmap uses 1 for used, so dont let file data take the metadata blocks
            for block in range(self.DATA_START):
                self.set_bit(2, block, True)
            #the first inode is root, and even an empty directory starts with one block
            root = self.alloc_inode()
            #type 2 means directory, with size zero because there are no entries yet
            self.put_inode(root, 2, 0, [self.alloc_block()], 0)

    def bit(self, bitmap, number):
        #divide by 8 to find the byte, then test just the bit for this inode or block
        return bool(self.disk[bitmap * 256 + number // 8] & (1 << (number % 8)))

    def set_bit(self, bitmap, number, used):
        #bitmap is a block number, so multiplying by 256 finds its starting byte
        offset = bitmap * 256 + number // 8
        #moving a single 1 left picks the bit I want without touching its neighbors
        mask = 1 << (number % 8)
        if used:
            #OR turns that bit on
            self.disk[offset] |= mask
        else:
            #AND with the inverted mask turns only that bit off
            self.disk[offset] &= ~mask

    def alloc_inode(self):
        #I scan from the beginning so a deleted inode gets reused first
        for number in range(self.NUM_INODES):
            if not self.bit(1, number):
                #reserve it before returning so the next allocation cant take it too
                self.set_bit(1, number, True)
                return number
        raise FSError("no free inodes")

    def alloc_block(self):
        #first fit again, but skip the blocks reserved for bookkeeping
        for number in range(self.DATA_START, self.NUM_BLOCKS):
            if not self.bit(2, number):
                self.set_bit(2, number, True)
                start = number * 256
                #clear old contents when reusing a block from a deleted file
                self.disk[start:start + 256] = bytes(256)
                return number
        raise FSError("disk full")

    def free_block(self, number):
        #clearing the bitmap bit makes this block available, no need to erase it here
        self.set_bit(2, number, False)

    def free_inode(self, number):
        #same idea for an inode, its old bytes stop mattering once the bit is cleared
        self.set_bit(1, number, False)

    def inode(self, number):
        #the table starts at block 3 and each inode takes 64 bytes
        return self.INODE.unpack_from(self.disk, 3 * 256 + number * 64)

    def put_inode(self, number, kind, size, blocks, indirect):
        #unused direct pointers stay zero so every inode keeps the same layout
        direct = blocks[:10] + [0] * (10 - len(blocks[:10]))
        #write the record back into the bytearray instead of storing it somewhere else
        self.INODE.pack_into(self.disk, 3 * 256 + number * 64,
                             kind, size, *direct, indirect)

    def blocks(self, inode):
        #I unpack pointers when I need them instead of keeping a second file table
        blocks = [b for b in inode[2:12] if b]
        #the last field points to a block of more pointers, not file contents itself
        if inode[12]:
            blocks.extend(b for b in struct.unpack_from("<64I", self.disk, inode[12] * 256) if b)
        return blocks

    def entries(self, number):
        #a directory stores names in its own data blocks just like a file stores bytes
        for block in self.blocks(self.inode(number)):
            #each 32 byte slot has room for one name and its inode number
            for offset in range(block * 256, (block + 1) * 256, 32):
                name, child = self.ENTRY.unpack_from(self.disk, offset)
                #a zero first byte means an empty slot, so skip those
                if name[0]:
                    #remove name padding and keep the slot's address for deleting later
                    yield name.rstrip(b"\0").decode("utf-8"), child, offset

    def parts(self, path):
        #all paths start at root, there isnt a current working directory in this version
        if not isinstance(path, str) or not path.startswith("/"):
            raise FSError("path must be absolute")
        #ignoring empty pieces makes /docs//a and /docs/a/ work the same way
        parts = [part for part in path.split("/") if part]
        for part in parts:
            #dot paths arent supported, and a zero byte would clash with name padding
            if part in (".", "..") or "\0" in part:
                raise FSError("invalid name")
            #the limit is bytes, a character like é can take more than one
            if len(part.encode("utf-8")) > 28:
                raise FSError("name too long (maximum 28 bytes)")
        return parts



    def lookup(self, parent, name):
        #look through one directory and return the inode and slot, or None if missing
        return next(((child, offset) for entry, child, offset in self.entries(parent)
                     if entry == name), None)

    def resolve(self, parts):
        #always start at inode 0, which is the root directory
        current = 0
        for name in parts:
            #cant keep walking down a path if the previous part was a regular file
            if self.inode(current)[0] != 2:
                raise FSError("not a directory")
            entry = self.lookup(current, name)
            if entry is None:
                raise FSError("not found")
            #this entry becomes the starting point for the next part of the path
            current = entry[0]
        return current

    def parent(self, path):
        parts = self.parts(path)
        #an empty list means root itself, and I must not overwrite or delete that
        if not parts:
            raise FSError("cannot replace or remove root")
        #for /docs/a.txt I need the existing /docs inode and the new name a.txt
        parent = self.resolve(parts[:-1])
        if self.inode(parent)[0] != 2:
            raise FSError("not a directory")
        return parent, parts[-1]




    def slot(self, parent):
        #find an empty directory entry, including holes left behind by rm
        for block in self.blocks(self.inode(parent)):
            for offset in range(block * 256, (block + 1) * 256, 32):
                if self.disk[offset] == 0:
                    return offset
        #no empty slots means the directory will need another block
        return None

    def capacity(self, blocks, new_inode=False):
        #check everything before changing the disk so a failed command leaves it alone
        if new_inode and all(self.bit(1, i) for i in range(64)):
            raise FSError("no free inodes")
        #only count data blocks, metadata is never available for file contents
        free = sum(not self.bit(2, b) for b in range(19, 256))
        if blocks > free:
            raise FSError("disk full")



    def add_entry(self, parent, name, child):
        slot = self.slot(parent)
        #eight entries fit in a block, the ninth needs another directory block
        if slot is None:
            inode = self.inode(parent)
            blocks = self.blocks(inode)
            block = self.alloc_block()
            blocks.append(block)
            self.put_inode(parent, 2, inode[1], blocks, 0)
            slot = block * 256
        #now connect the name to its inode so path lookup can actually find it
        self.ENTRY.pack_into(self.disk, slot, name.encode("utf-8"), child)
        inode = self.inode(parent)
        #I count occupied entries for directory size, even when deleted slots leave gaps
        self.put_inode(parent, 2, inode[1] + 32, self.blocks(inode), inode[12])

    def release(self, inode):
        #give back all the blocks containing the file or directory's actual data
        for block in self.blocks(inode):
            self.free_block(block)
        #dont forget the extra block that held pointers for a larger file
        if inode[12]:
            self.free_block(inode[12])

    def mkdir(self, path):
        with self.lock:
            #root already exists even though it doesnt have an entry in a parent
            if not self.parts(path):
                raise FSError("exists")
            parent, name = self.parent(path)
            if self.lookup(parent, name) is not None:
                raise FSError("exists")
            #need a block for the new directory and maybe another for its parent to grow
            self.capacity(1 + (self.slot(parent) is None), new_inode=True)
            number = self.alloc_inode()
            self.put_inode(number, 2, 0, [self.alloc_block()], 0)
            #having an inode alone isnt enough, its name must go in the parent too
            self.add_entry(parent, name, number)



    def write(self, path, data):
        with self.lock:
            #the file handles bytes, converting typed text happens in the CLI
            if not isinstance(data, bytes):
                raise FSError("write needs bytes")
            parent, name = self.parent(path)
            entry = self.lookup(parent, name)
            #a missing entry means create, an existing file means replace its contents
            old = self.inode(entry[0]) if entry is not None else None
            if old is not None and old[0] != 1:
                raise FSError("is a directory")
            if len(data) > self.MAX_SIZE:
                raise FSError("file too large")

            #round up because even one leftover byte needs a whole block
            count = (len(data) + 255) // 256
            #past ten content blocks I also need a block to hold indirect pointers
            needed = count + (count > 10)
            if old is not None:
                #I include the old blocks as available before freeing anything
                needed -= len(self.blocks(old)) + bool(old[12])
            else:
                #a new name might also fill up the parent's current directory blocks
                needed += self.slot(parent) is None
            self.capacity(needed, new_inode=old is None)




            if old is None:
                number = self.alloc_inode()
            else:
                number = entry[0]
                #space is confirmed now, so its safe to free the old contents
                self.release(old)
            blocks = [self.alloc_block() for _ in range(count)]
            indirect = self.alloc_block() if count > 10 else 0
            for i, block in enumerate(blocks):
                #copy one block-sized piece at a time, the last piece may be shorter
                chunk = data[i * 256:(i + 1) * 256]
                self.disk[block * 256:block * 256 + len(chunk)] = chunk
            if indirect:
                #the first ten pointers are in the inode, the rest go in this extra block
                pointers = blocks[10:] + [0] * (64 - len(blocks[10:]))
                struct.pack_into("<64I", self.disk, indirect * 256, *pointers)
            #record the real byte length so reading wont include padding at the end
            self.put_inode(number, 1, len(data), blocks, indirect)
            if old is None:
                self.add_entry(parent, name, number)






    def read(self, path):
        with self.lock:
            #turn the path into an inode before looking up its content blocks
            inode = self.inode(self.resolve(self.parts(path)))
            if inode[0] != 1:
                raise FSError("is a directory")
            #put the blocks back together in the same order they were written
            data = b"".join(self.disk[b * 256:(b + 1) * 256] for b in self.blocks(inode))
            #only return the stored size, not the unused zero bytes in the last block
            return data[:inode[1]]

    def rm(self, path):
        with self.lock:
            parent, name = self.parent(path)
            entry = self.lookup(parent, name)
            if entry is None:
                raise FSError("not found")
            number, offset = entry
            inode = self.inode(number)
            #deleting a directory with children would leave those files stranded
            if inode[0] == 2 and any(self.entries(number)):
                raise FSError("directory not empty")
            self.release(inode)
            self.free_inode(number)
            #zeroing the name's whole slot removes it from the parent directory
            self.disk[offset:offset + 32] = bytes(32)
            inode = self.inode(parent)
            #keep any extra parent blocks, just reduce the occupied entry count
            self.put_inode(parent, 2, inode[1] - 32, self.blocks(inode), inode[12])

    def ls(self, path):
        with self.lock:
            number = self.resolve(self.parts(path))
            if self.inode(number)[0] != 2:
                raise FSError("not a directory")
            #add a slash for directories so the caller can tell them apart from files
            return [(name + ("/" if self.inode(child)[0] == 2 else ""), self.inode(child)[1])
                    for name, child, _ in self.entries(number)]

    def stat(self, path):
        with self.lock:
            number = self.resolve(self.parts(path))
            inode = self.inode(number)
            #return details for the CLI to print, the file itself stays quiet
            return {"inode": number, "type": "file" if inode[0] == 1 else "directory",
                    "size": inode[1], "blocks": self.blocks(inode), "indirect": inode[12]}

    def fsstat(self):
        with self.lock:
            #only bitmap-marked inodes count, freed records may still have old bytes
            inodes = [self.inode(i) for i in range(64) if self.bit(1, i)]
            used = sum(self.bit(2, b) for b in range(19, 256))
            #these block counts include directories and pointer blocks but exclude metadata
            return {"inodes_used": len(inodes), "inodes_free": 64 - len(inodes),
                    "blocks_used": used, "blocks_free": 237 - used,
                    "files": sum(i[0] == 1 for i in inodes),
                    "dirs": sum(i[0] == 2 for i in inodes)}

    def check(self):
        #I compare actual ownership with both bitmaps to catch leaks and shared blocks
        assert len(self.disk) == 65536, "wrong image size"
        assert self.SUPER.unpack_from(self.disk) == (256, 256, 64, 1, 2, 3, 19), "bad superblock"
        #build the set of inodes the bitmap says are still in use
        used = {i for i in range(64) if self.bit(1, i)}
        assert 0 in used and self.inode(0)[0] == 2, "missing root"
        #metadata must stay marked used even though no file points to it
        reachable = set(range(19))
        children = set()
        
        
        for number in used:
            inode = self.inode(number)
            assert inode[0] in (1, 2), "invalid inode type"
            blocks = self.blocks(inode)
            assert 0 <= inode[1] <= self.MAX_SIZE, "invalid size"
            #file size tells me exactly how many content blocks should be allocated
            if inode[0] == 1:
                assert len(blocks) == (inode[1] + 255) // 256, "wrong file block count"
            assert bool(inode[12]) == (len(blocks) > 10), "wrong indirect pointer"
            #a block must be in the data area and belong to only one inode
            
            
            for block in blocks + ([inode[12]] if inode[12] else []):
                assert 19 <= block < 256 and block not in reachable, "invalid or shared block"
                reachable.add(block)
            if inode[0] == 2:
                entries = list(self.entries(number))
                #directory size counts live entries, not every slot in its blocks
                assert blocks and inode[1] == len(entries) * 32, "invalid directory size"
                assert len({name for name, _, _ in entries}) == len(entries), "duplicate name"
                for name, child, _ in entries:
                    assert self.parts('/' + name) == [name], "invalid entry name"
                    #each name must lead to a live inode that hasnt already got another name
                    assert child in used and child != 0 and child not in children, "invalid child inode"
                    children.add(child)
        assert children == used - {0}, "unreferenced inode"
        visited = set()









        def walk(number):
            #seeing an inode twice would mean the directory tree loops back on itself
            assert number not in visited, "directory cycle"
            visited.add(number)
            if self.inode(number)[0] == 2:
                for _, child, _ in self.entries(number):
                    walk(child)

        #start at root to make sure every used inode can really be reached by a path
        walk(0)
        assert visited == used, "unreachable inode"
        #any difference here means a leaked block or a block wrongly marked free
        assert reachable == {b for b in range(256) if self.bit(2, b)}, "data bitmap mismatch"


    def check_consistency(self):
        #take the lock here, helpers like check already run inside a locked operation
        with self.lock:
            self.check()



    def save(self, image_path):
        with self.lock:
            try:
                with open(image_path, "wb") as stream:
                    #one write saves everything since all the structures are already bytes
                    stream.write(self.disk)
            except OSError as exc:
                raise FSError(str(exc)) from exc



    def load(self, image_path):
        with self.lock:
            try:
                with open(image_path, "rb") as stream:
                    #this host file is the whole pretend disk, not just the file contents
                    data = stream.read()
            except OSError as exc:
                raise FSError(str(exc)) from exc
            #a truncated image cant match the layout, so reject it before swapping disks
            if len(data) != 65536:
                raise FSError("corrupt image: expected 65536 bytes; reformat with mkfs")
            #hold onto the current disk until the loaded image passes its checks
            previous = self.disk
            self.disk = bytearray(data)
            try:
                self.check()
            except (AssertionError, struct.error, UnicodeError, FSError, IndexError) as exc:
                #I put the old disk back if the image cannot be used
                self.disk = previous
                raise FSError("corrupt image; reformat with mkfs") from exc
