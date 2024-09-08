import os
import subprocess

# Directory to search
directory = "..\\.."

# Extension to match
extension = ".py"

# Command to run
command = "pyside6-lupdate {files} -target-language zh_CN -source-language en_US -ts zh_CN.ts"

# Find all files with the given extension in the directory and its subdirectories
files = []
for root, dirs, filenames in os.walk(directory):
    for filename in filenames:
        if filename.endswith(extension):
            # Join the root and filename to get the full file path
            full_path = os.path.join(root, filename)
            files.append(full_path)

# Join the file paths with a space
files_str = " ".join(files)

# Replace {files} in the command with the file paths
command = command.format(files=files_str)

# Run the command
subprocess.run(command, shell=True)
