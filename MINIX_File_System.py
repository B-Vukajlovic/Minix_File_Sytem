import sys
import struct
import time

# Name: Boris Vukajlovic

# This Minix Filesystem Tool allows users to perform basic operations on a
# Minix filesystem image, including listing the root directory, reading file contents,
# creating new files, and creating new directories.

BLOCK_SIZE = 1024
INODE_SIZE = 32
BOOT_BLOCK = 1
SUPER_BLOCK = 1
EMPTY = 0
MAX_FILENAME_SHORT = 14
MAX_FILENAME_LONG = 30
NUM_DIRECT_ZONES = 7
INDIRECT_ZONE_INDEX = 7
DOUBLE_INDIRECT_ZONE_INDEX = 8

S_IFREG = 0x8000
S_IFDIR = 0x4000
S_IRUSR = 0x100
S_IWUSR = 0x80
S_IXUSR = 0x40


# Parses the superblock data from the filesystem image.
# Input: superblock data (bytes)
# Return: dictionary with superblock fields
def parse_superblock(sb_data):
    sb_dict = {}

    fields = [
        ("num_inodes", "H"),
        ("num_zones", "H"),
        ("imap_blocks", "H"),
        ("zmap_blocks", "H"),
        ("first_data_zone", "H"),
        ("log_zone_size", "H"),
        ("max_file_size", "I"),
        ("magic", "H"),
        ("state", "H")
    ]

    idx = 0
    for field_name, fmt in fields:
        size = struct.calcsize(fmt)
        (sb_dict[field_name],) = struct.unpack_from("<" + fmt, sb_data, idx)
        idx += size

    return sb_dict


# Parses an inode from the filesystem image.
# Input: file object, superblock dictionary, inode number
# Return: dictionary with inode fields
def parse_inode(file, sb_dict, inode_number):
    inode_table_start_block = BOOT_BLOCK + SUPER_BLOCK + sb_dict["imap_blocks"] + sb_dict["zmap_blocks"]
    inode_table_start_byte = inode_table_start_block * BLOCK_SIZE
    inode_offset = inode_table_start_byte + (inode_number - 1) * INODE_SIZE

    file.seek(inode_offset)
    inode_data = file.read(INODE_SIZE)

    inode_format = "<HHIIBB9H"
    inode_values = struct.unpack(inode_format, inode_data)

    inode_dict = {
        "i_mode": inode_values[0],
        "i_uid": inode_values[1],
        "i_size": inode_values[2],
        "i_time": inode_values[3],
        "i_gid": inode_values[4],
        "i_nlinks": inode_values[5],
        "i_zone": inode_values[6:15]
    }

    return inode_dict


# Reads the root directory entries.
# Input: file object, superblock dictionary, maximum filename length
# Return: list of cleaned filenames in the root directory
def read_root_directory_entries(file, sb_dict, max_filename_length):
    root_inode = parse_inode(file, sb_dict, 1)
    entry_format = f"<H{max_filename_length}s"
    entry_size = struct.calcsize(entry_format)
    entries = []

    for zone_number in root_inode["i_zone"]:
        if zone_number != EMPTY:
            file.seek(zone_number * BLOCK_SIZE)
            block_data = file.read(BLOCK_SIZE)
            for offset in range(0, BLOCK_SIZE, entry_size):
                entry_data = block_data[offset:offset + entry_size]
                inode_number, filename = struct.unpack(entry_format, entry_data)
                if inode_number != 0:
                    cleaned_filename = filename.rstrip(b'\0')
                    entries.append(cleaned_filename)
    return entries


# Prints directory entries.
# Input: list of directory entries (filenames)
def print_directory_entries(entries):
    for entry in entries:
        sys.stdout.buffer.write(entry)
        sys.stdout.buffer.write(b'\n')


# Prints the root directory.
# Input: file object, superblock dictionary, maximum filename length
def print_root_directory(file, sb_dict, max_filename_length):
    entries = read_root_directory_entries(file, sb_dict, max_filename_length)
    print_directory_entries(entries)


# Fetches addresses from an indirect block.
# Input: file object, block number
# Return: list of valid addresses
def fetch_indirect_block_addresses(file, block_num):
    file.seek(block_num * BLOCK_SIZE)
    block_data = file.read(BLOCK_SIZE)

    block_format = "<" + "H" * (BLOCK_SIZE // 2)
    addresses = struct.unpack_from(block_format, block_data)
    valid_addresses = []
    for address in addresses:
        if address != EMPTY:
            valid_addresses.append(address)

    return valid_addresses


# Fetches addresses from a double indirect block.
# Input: file object, block number
# Return: list of data block addresses
def fetch_double_indirect_block_addresses(file, block_num):
    indirect_addresses = fetch_indirect_block_addresses(file, block_num)
    data_block_addresses = []

    for indirect_address in indirect_addresses:
        data_block_addresses.extend(fetch_indirect_block_addresses(file, indirect_address))
    return data_block_addresses


# Reads file data from the filesystem.
# Input: file object, superblock dictionary, inode dictionary
# Return: bytearray of file content
def read_file_data(file, inode):
    file_content = bytearray()
    remaining_size = inode["i_size"]

    for zone in inode["i_zone"][:NUM_DIRECT_ZONES]:
        if zone != EMPTY and remaining_size > 0:
            file.seek(zone * BLOCK_SIZE)
            bytes_to_read = min(BLOCK_SIZE, remaining_size)
            file_content.extend(file.read(bytes_to_read))
            remaining_size -= bytes_to_read

    if remaining_size > 0 and inode["i_zone"][INDIRECT_ZONE_INDEX] != EMPTY:
        indirect_index = inode["i_zone"][INDIRECT_ZONE_INDEX]
        indirect_blocks = fetch_indirect_block_addresses(file, indirect_index)
        for block in indirect_blocks:
            if remaining_size <= 0:
                break
            file.seek(block * BLOCK_SIZE)
            bytes_to_read = min(BLOCK_SIZE, remaining_size)
            file_content.extend(file.read(bytes_to_read))
            remaining_size -= bytes_to_read

    if remaining_size > 0 and inode["i_zone"][DOUBLE_INDIRECT_ZONE_INDEX] != EMPTY:
        double_indirect_index = inode["i_zone"][DOUBLE_INDIRECT_ZONE_INDEX]
        double_indirect_blocks = fetch_double_indirect_block_addresses(file, double_indirect_index)
        for block in double_indirect_blocks:
            if remaining_size <= 0:
                break
            file.seek(block * BLOCK_SIZE)
            bytes_to_read = min(BLOCK_SIZE, remaining_size)
            file_content.extend(file.read(bytes_to_read))
            remaining_size -= bytes_to_read

    return file_content


# Displays the contents of a file.
# Input: file object, superblock dictionary, directory inode number, filename, maximum filename length
def cat_file(file, sb_dict, dir_inode_number, filename, max_filename_length):
    dir_inode = parse_inode(file, sb_dict, dir_inode_number)
    entry_format = f"<H{max_filename_length}s"
    entry_size = struct.calcsize(entry_format)

    for zone in dir_inode["i_zone"]:
        if zone != EMPTY:
            file.seek(zone * BLOCK_SIZE)
            block_data = file.read(BLOCK_SIZE)
            for offset in range(0, BLOCK_SIZE, entry_size):
                entry_data = block_data[offset:offset + entry_size]
                inode_number, entry_name = struct.unpack(entry_format, entry_data)
                if entry_name.rstrip(b'\0').decode() == filename:
                    file_inode = parse_inode(file, sb_dict, inode_number)
                    file_content = read_file_data(file, file_inode)
                    sys.stdout.buffer.write(file_content)
                    return
    print(f"File {filename} not found in dir", file=sys.stderr)


# Finds the inode number of a directory.
# Input: file object, superblock dictionary, directory name, maximum filename length, root
# inode number (default: 1)
# Return: inode number of the directory or None if not found
def find_inode_of_directory(file, sb_dict, dir_name, max_filename_length, root_inode_number=1):
    root_inode = parse_inode(file, sb_dict, root_inode_number)
    entry_format = f"<H{max_filename_length}s"
    entry_size = struct.calcsize(entry_format)

    for zone in root_inode["i_zone"]:
        if zone != EMPTY:
            file.seek(zone * BLOCK_SIZE)
            block_data = file.read(BLOCK_SIZE)
            for offset in range(0, BLOCK_SIZE, entry_size):
                entry_data = block_data[offset:offset + entry_size]
                inode_number, entry_name = struct.unpack(entry_format, entry_data)
                if entry_name.rstrip(b'\0').decode() == dir_name:
                    return inode_number
    return None


# Creates a new file in the root directory.
# Input: file object, superblock dictionary, filename, maximum filename length
def create_new_file(file, sb_dict, filename, max_filename_length):
    root_inode = parse_inode(file, sb_dict, 1)

    for inode_number in range(1, sb_dict["num_inodes"] + 1):
        inode = parse_inode(file, sb_dict, inode_number)
        if inode["i_nlinks"] == 0:
            break
    else:
        print("Error: No free inodes available.", file=sys.stderr)
        return

    new_inode_offset = inode_number - 1
    inode_table_start_block = BOOT_BLOCK + SUPER_BLOCK + sb_dict["imap_blocks"] + sb_dict["zmap_blocks"]
    inode_table_start_byte = inode_table_start_block * BLOCK_SIZE
    inode_offset = inode_table_start_byte + (new_inode_offset * INODE_SIZE)

    new_inode = struct.pack("<HHIIBB9H",
                            S_IFREG | S_IRUSR | S_IWUSR | S_IXUSR,
                            0,
                            0,
                            int(time.time()),
                            0,
                            1,
                            *(EMPTY,) * 9)

    file.seek(inode_offset)
    file.write(new_inode)

    root_dir_block = root_inode["i_zone"][0]
    file.seek(root_dir_block * BLOCK_SIZE)
    block_data = file.read(BLOCK_SIZE)

    entry_format = f"<H{max_filename_length}s"
    entry_size = struct.calcsize(entry_format)

    for offset in range(0, BLOCK_SIZE, entry_size):
        entry_data = block_data[offset:offset + entry_size]
        inode_num, name = struct.unpack(entry_format, entry_data)
        if inode_num == 0:
            break
    else:
        print("Error: No free directory entry available.", file=sys.stderr)
        return

    new_dir_entry = struct.pack(entry_format, inode_number, filename.ljust(max_filename_length, '\0').encode())

    file.seek((root_dir_block * BLOCK_SIZE) + offset)
    file.write(new_dir_entry)


# Creates a new directory in the root directory with '.' and '..' entries.
# Input: file object, superblock dictionary, directory name, maximum filename length
def create_new_directory(file, sb_dict, dirname, max_filename_length):
    root_inode = parse_inode(file, sb_dict, 1)
    free_inode_number = None

    for inode_number in range(1, sb_dict["num_inodes"] + 1):
        inode = parse_inode(file, sb_dict, inode_number)
        if inode["i_nlinks"] == 0:
            free_inode_number = inode_number
            break

    if free_inode_number is None:
        print("Error: No free inodes available.", file=sys.stderr)
        return

    new_inode_offset = free_inode_number - 1
    inode_table_start_block = BOOT_BLOCK + SUPER_BLOCK + sb_dict["imap_blocks"] + sb_dict["zmap_blocks"]
    inode_table_start_byte = inode_table_start_block * BLOCK_SIZE
    inode_offset = inode_table_start_byte + (new_inode_offset * INODE_SIZE)

    new_inode = struct.pack("<HHIIBB9H",
                            S_IFDIR | S_IRUSR | S_IWUSR | S_IXUSR,
                            0,
                            BLOCK_SIZE,
                            int(time.time()),
                            0,
                            2,
                            *(EMPTY,) * 9)

    file.seek(inode_offset)
    file.write(new_inode)

    root_dir_block = root_inode["i_zone"][0]
    file.seek(root_dir_block * BLOCK_SIZE)
    block_data = file.read(BLOCK_SIZE)

    entry_format = f"<H{max_filename_length}s"
    entry_size = struct.calcsize(entry_format)

    for offset in range(0, BLOCK_SIZE, entry_size):
        entry_data = block_data[offset:offset + entry_size]
        inode_num, name = struct.unpack(entry_format, entry_data)
        if inode_num == 0:
            break
    else:
        print("Error: No free directory entry available.", file=sys.stderr)
        return

    new_dir_entry = struct.pack(entry_format, free_inode_number, dirname.ljust(max_filename_length, '\0').encode())
    file.seek((root_dir_block * BLOCK_SIZE) + offset)
    file.write(new_dir_entry)

    new_dir_block = None
    for zone_number in range(sb_dict["first_data_zone"], sb_dict["nzones"]):
        file.seek(zone_number * BLOCK_SIZE)
        block_data = file.read(BLOCK_SIZE)
        if block_data == bytes([EMPTY] * BLOCK_SIZE):
            new_dir_block = zone_number
            break

    if new_dir_block is None:
        print("Error: No free data blocks available.", file=sys.stderr)
        return

    file.seek(inode_offset + 16)
    file.write(struct.pack("<H", new_dir_block))

    file.seek(new_dir_block * BLOCK_SIZE)
    new_dir_data = struct.pack(entry_format, free_inode_number, b'.'.ljust(max_filename_length, b'\0'))
    new_dir_data += struct.pack(entry_format, 1, b'..'.ljust(max_filename_length, b'\0'))
    file.write(new_dir_data)


# Appends data to an existing file.
# Input: file object, superblock dictionary, directory inode number, filename, data to append,
# maximum filename length
def append_to_file(file, sb_dict, dir_inode_number, filename, data, max_filename_length):
    dir_inode = parse_inode(file, sb_dict, dir_inode_number)
    entry_format = f"<H{max_filename_length}s"
    entry_size = struct.calcsize(entry_format)

    for zone in dir_inode["i_zone"]:
        if zone != EMPTY:
            file.seek(zone * BLOCK_SIZE)
            block_data = file.read(BLOCK_SIZE)
            for offset in range(0, BLOCK_SIZE, entry_size):
                entry_data = block_data[offset:offset + entry_size]
                inode_number, entry_name = struct.unpack(entry_format, entry_data)
                if entry_name.rstrip(b'\0').decode() == filename:
                    file_inode = parse_inode(file, sb_dict, inode_number)
                    current_size = file_inode["i_size"]
                    new_size = current_size + len(data)
                    file_content = read_file_data(file, sb_dict, file_inode)
                    file_content.extend(data.encode())

                    for i, zone in enumerate(file_inode["i_zone"][:NUM_DIRECT_ZONES]):
                        if zone != EMPTY:
                            file.seek(zone * BLOCK_SIZE)
                            file.write(file_content[:BLOCK_SIZE])
                            file_content = file_content[BLOCK_SIZE:]

                    if len(file_content) > 0 and file_inode["i_zone"][INDIRECT_ZONE_INDEX] != EMPTY:
                        indirect_blocks = fetch_indirect_block_addresses(file,
                                                                         file_inode["i_zone"][INDIRECT_ZONE_INDEX])
                        for block in indirect_blocks:
                            if len(file_content) <= 0:
                                break
                            file.seek(block * BLOCK_SIZE)
                            file.write(file_content[:BLOCK_SIZE])
                            file_content = file_content[BLOCK_SIZE:]

                    if len(file_content) > 0 and file_inode["i_zone"][DOUBLE_INDIRECT_ZONE_INDEX] != EMPTY:
                        double_indirect_index = file_inode["i_zone"][DOUBLE_INDIRECT_ZONE_INDEX]
                        double_indirect_blocks = fetch_double_indirect_block_addresses(file, double_indirect_index)

                        for block in double_indirect_blocks:
                            if len(file_content) <= 0:
                                break
                            file.seek(block * BLOCK_SIZE)
                            file.write(file_content[:BLOCK_SIZE])
                            file_content = file_content[BLOCK_SIZE:]

                    imap_zmap_blocks = sb_dict["imap_blocks"] + sb_dict["zmap_blocks"]
                    inode_table_start_block = BOOT_BLOCK + SUPER_BLOCK + imap_zmap_blocks
                    inode_table_start_byte = inode_table_start_block * BLOCK_SIZE
                    inode_offset = inode_table_start_byte + (inode_number - 1) * INODE_SIZE

                    new_inode = struct.pack("<HHIIBB9H",
                                            file_inode["i_mode"],
                                            file_inode["i_uid"],
                                            new_size,
                                            int(time.time()),
                                            file_inode["i_gid"],
                                            file_inode["i_nlinks"],
                                            *file_inode["i_zone"])

                    file.seek(inode_offset)
                    file.write(new_inode)
                    return
    print(f"File {filename} not found in dir", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: mfstool.py image command params", file=sys.stderr)
        sys.exit(1)

    disk_image = sys.argv[1]
    command = sys.argv[2]

    with open(disk_image, "r+b") as file:
        file.seek(BLOCK_SIZE, 0)
        sb_data = file.read(BLOCK_SIZE)

        sb_dict = parse_superblock(sb_data)

        match command:
            case "ls":
                max_filename_length = MAX_FILENAME_LONG if sb_dict["magic"] == 0x138F else MAX_FILENAME_SHORT
                print_root_directory(file, sb_dict, max_filename_length)
            case "cat":
                if len(sys.argv) != 4:
                    print("Error: Incorrect usage. Please use: mfstool.py image cat path/to/file", file=sys.stderr)
                    sys.exit(1)

                file_path = sys.argv[3].split('/')
                if len(file_path) != 2:
                    print("Error: Only paths in the format 'directory/filename' are supported.", file=sys.stderr)
                    sys.exit(1)

                dir_name, file_name = file_path
                max_filename_length = MAX_FILENAME_LONG if sb_dict["magic"] == 0x138F else MAX_FILENAME_SHORT
                dir_inode_number = find_inode_of_directory(file, sb_dict, dir_name, max_filename_length)

                if dir_inode_number is None:
                    print(f"Error: The directory '{dir_name}' was not found.", file=sys.stderr)
                    sys.exit(1)

                cat_file(file, sb_dict, dir_inode_number, file_name, max_filename_length)
            case "touch":
                if len(sys.argv) != 4:
                    print("Error: Incorrect usage. Please use: mfstool.py image touch filename", file=sys.stderr)
                    sys.exit(1)

                filename = sys.argv[3]
                max_filename_length = MAX_FILENAME_LONG if sb_dict["magic"] == 0x138F else MAX_FILENAME_SHORT

                if len(filename) > max_filename_length:
                    print(f"Error: Filename '{filename}' is too long.", file=sys.stderr)
                    sys.exit(1)

                create_new_file(file, sb_dict, filename, max_filename_length)
            case "mkdir":
                if len(sys.argv) != 4:
                    print("Error: Incorrect usage. Please use: mfstool.py image mkdir dirname", file=sys.stderr)
                    sys.exit(1)

                dirname = sys.argv[3]
                max_filename_length = MAX_FILENAME_LONG if sb_dict["magic"] == 0x138F else MAX_FILENAME_SHORT

                if len(dirname) > max_filename_length:
                    print(f"Error: Directory name '{dirname}' is too long.", file=sys.stderr)
                    sys.exit(1)

                create_new_directory(file, sb_dict, dirname, max_filename_length)
            case "append":
                if len(sys.argv) != 5:
                    print("Error: Incorrect usage. Please use: mfstool.py image append path/to/file data_to_append",
                          file=sys.stderr)
                    sys.exit(1)

                file_path = sys.argv[3].split('/')
                if len(file_path) != 2:
                    print("Error: Only paths in the format 'directory/filename' are supported.", file=sys.stderr)
                    sys.exit(1)

                dir_name, file_name = file_path
                data_to_append = sys.argv[4]
                max_filename_length = MAX_FILENAME_LONG if sb_dict["magic"] == 0x138F else MAX_FILENAME_SHORT
                dir_inode_number = find_inode_of_directory(file, sb_dict, dir_name, max_filename_length)

                if dir_inode_number is None:
                    print(f"Error: The directory '{dir_name}' was not found.", file=sys.stderr)
                    sys.exit(1)

                append_to_file(file, sb_dict, dir_inode_number, file_name, data_to_append, max_filename_length)
            case _:
                print(f"Unknown command: {command}", file=sys.stderr)
