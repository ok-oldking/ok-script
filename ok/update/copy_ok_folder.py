import sys

import os
import shutil


def find_and_copy_site_package():
    # Define the folder name you want to find and copy
    folder_to_copy = "ok"

    # Get the current working directory
    current_dir = os.getcwd()

    # Define the target directory pattern
    target_pattern = os.path.join('Lib', 'site-packages')
    destination = os.path.join(current_dir, folder_to_copy)

    if os.path.exists(destination):
        print(f'destination exists: {destination}, skip copying')
        return

    # Loop through all potential site-packages directories
    for path in sys.path:
        normalized_path = os.path.normpath(path)
        if normalized_path.endswith(target_pattern):
            full_path = os.path.join(normalized_path, folder_to_copy)
            if os.path.exists(full_path) and os.path.isdir(full_path):
                # Define the destination path

                # Copy the folder
                shutil.copytree(full_path, destination)
                print(f"Copied '{full_path}' to '{destination}'")
                return 0  # Exit with status code 0 (success)

    print(f"Folder '{folder_to_copy}' not found in site-packages", file=sys.stderr)
    return 1  # Exit with status code 1 (error)


if __name__ == "__main__":
    exit_code = find_and_copy_site_package()
    sys.exit(exit_code)
