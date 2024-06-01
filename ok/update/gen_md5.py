import os.path
import sys

from ok.util.path import dir_checksum


def write_checksum_to_file(folder_path):
    # Call the dir_checksum function
    checksum = dir_checksum(folder_path)

    # Write the checksum to a file named 'md5.txt' in the same folder
    file = os.path.join(folder_path, 'md5.txt')
    with open(file, 'w') as file:
        file.write(checksum)
    print(f'write checksum {checksum} to {file}')


if __name__ == "__main__":
    # Get the folder path from the command line arguments
    folder_path = sys.argv[1]

    # Call the function
    write_checksum_to_file(folder_path)
