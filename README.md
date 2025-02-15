# Minix Filesystem Tool

This Python tool provides basic operations on a Minix filesystem image, allowing you to explore and modify its contents. It supports reading directories, creating files, viewing file contents, and more.

---

## Features
- **List Directory (`ls`):** Shows the contents of the root directory.  
- **Read File (`cat`):** Prints the contents of a specified file.  
- **Create File (`touch`):** Adds a new file to the filesystem.  
- **Create Directory (`mkdir`):** Adds a new directory (with `.` and `..` entries).  
- **Append Data (`append`):** Appends text to an existing file.

---

## Usage

python mfstool.py <image> <command> [arguments...]

- `<image>`: Path to the Minix filesystem image (read/write mode).
- `<command>`: One of `ls`, `cat`, `touch`, `mkdir`, `append`.
- Additional parameters depend on the chosen command.

**Examples:**

python mfstool.py minix.img ls python mfstool.py minix.img cat dir/file python mfstool.py minix.img touch filename


---

## Notes
1. **Filename Lengths**: The script automatically detects whether the Minix image uses short (14‐byte) or long (30‐byte) filenames (based on the filesystem `magic` number).  
2. **Paths**: Currently supports a simplified path format like `directory/filename`.  
3. **Inodes & Data Blocks**: Reads/manipulates inode tables and data block addresses in a low-level manner, which shows important filesystem concepts like block allocation, indirect zones, and double indirect zones.  
