# process.py
import argparse
import ctypes
import glob
import hashlib
import os
import re
import subprocess
import threading
import time
from ctypes import wintypes

import psutil

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


def is_admin():
    try:
        # Only Windows users with admin privileges can read the C drive directly
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_in_new_thread(func):
    # Create a new thread and run the function in it
    thread = threading.Thread(target=func)

    # Start the new thread
    thread.start()

    # Return the thread
    return thread


def check_mutex():
    _LPSECURITY_ATTRIBUTES = wintypes.LPVOID
    _BOOL = ctypes.c_int
    _DWORD = ctypes.c_ulong
    _HANDLE = ctypes.c_void_p
    _CreateMutex = ctypes.windll.kernel32.CreateMutexW
    _CreateMutex.argtypes = [_LPSECURITY_ATTRIBUTES, _BOOL, wintypes.LPCWSTR]
    _CreateMutex.restype = _HANDLE
    _GetLastError = ctypes.windll.kernel32.GetLastError
    _GetLastError.argtypes = []
    _GetLastError.restype = _DWORD
    _ERROR_ALREADY_EXISTS = 183
    path = os.getcwd()
    # Try to create a named mutex
    mutex_name = hashlib.md5(path.encode()).hexdigest()
    mutex = _CreateMutex(0, False, mutex_name)
    logger.info(f'_CreateMutex {mutex_name}')
    # Check if the mutex already exists
    if _GetLastError() == _ERROR_ALREADY_EXISTS:
        logger.error(
            f'Another instance of this application is already running {mutex_name}. Waiting for it to disappear.')
        print(f"Another instance of this application is already running. {mutex_name}")
        wait_time = 10
        start_time = time.time()
        while time.time() - start_time < wait_time:
            # Try to create the mutex again to check if the other instance has released it
            temp_mutex = _CreateMutex(0, False, mutex_name)
            if _GetLastError() != _ERROR_ALREADY_EXISTS:
                # Mutex is gone, the other instance likely terminated
                logger.info(f"Mutex {mutex_name} disappeared. Proceeding.")
                ctypes.windll.kernel32.CloseHandle(temp_mutex)  # Close the temporary mutex
                return True  # Proceed with the current instance
            ctypes.windll.kernel32.CloseHandle(temp_mutex)  # Close the temporary mutex
            time.sleep(0.5)  # Wait a bit before retrying
        # If mutex still exists after waiting, kill the other instance
        logger.warning(
            f"Mutex {mutex_name} still exists after {wait_time} seconds. Attempting to kill existing process.")
        kill_exe(os.path.abspath(os.getcwd()))
        # After attempting to kill, the mutex should eventually be released.
        # You might want to add another short wait here or just let the mutex check
        # in the next iteration of the main script loop handle it if it restarts.
        return False  # Indicate that a mutex conflict was handled
    return True  # No mutex conflict, proceed


def restart_as_admin():
    import ctypes
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        import sys
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 0)
        sys.exit()


def all_pids() -> list[int]:
    pidbuffer = 512
    bytes_written = ctypes.c_uint32()
    while True:
        pids = (ctypes.c_uint32 * pidbuffer)()
        bufsize = ctypes.sizeof(pids)
        if ctypes.windll.kernel32.K32EnumProcesses(pids, bufsize, ctypes.byref(bytes_written)) == 0:
            return []
        if bytes_written.value < bufsize:
            break
        pidbuffer *= 2
    pidcount = bytes_written.value // 4
    return list(pids[:pidcount])


def get_path(input_string):
    """
    Extracts the path part from the input string.  It assumes the path ends
    before the first space followed by a hyphen.

    Args:
      input_string: The string containing the path and potentially other information.

    Returns:
      The path part of the string, or None if a valid path cannot be extracted.
    """
    try:
        # Split the string at the first occurrence of " -"
        parts = input_string.split(" -", 1)  # Split at " -" only once

        # The first part is the path (hopefully)
        path = parts[0].strip()  # Remove any leading or trailing spaces
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        # Check if it looks like a valid path (this can be improved, but it's a start)
        if os.path.exists(path):
            return path
        else:
            # If the path doesn't exist, try to see if it's relative to the current directory

            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                return abs_path

            return input_string  # Return None if it isn't a valid existing path
    except:
        return input_string


def execute(game_cmd: str, arguments=None):
    if game_cmd:
        if '://' in game_cmd:
            try:
                logger.info(f'try execute url {game_cmd}')
                os.startfile(game_cmd)
                return True
            except Exception as e:
                logger.error('execute error', e)
        else:
            game_path = get_path(game_cmd)
            if os.path.exists(game_path):
                try:
                    logger.info(f'try execute {game_cmd} {arguments}')
                    game_cmd_stripped = game_cmd.strip()
                    if game_cmd_stripped.startswith('"'):
                        cmd = f'start "" /b {game_cmd_stripped}'
                    elif game_cmd_stripped.startswith(game_path):
                        args_part = game_cmd_stripped[len(game_path):]
                        cmd = f'start "" /b "{game_path}"{args_part}'
                    else:
                        cmd = f'start "" /b "{game_cmd_stripped}"'
                    if arguments:
                        cmd += f" {arguments}"
                    subprocess.Popen(cmd, cwd=os.path.dirname(game_path), shell=True,
                                     creationflags=0x00000008)  # detached process
                    return True
                except Exception as e:
                    logger.error('execute error', e)
            else:
                logger.error(f'execute error path not exist {game_path}')


def kill_exe(relative_path=None, abs_path=None):
    """
    Kills processes matching either a relative or absolute path to an executable.

    Args:
        relative_path (str, optional):  A relative path to the executable (e.g., 'bin/my_app.exe'). Defaults to None.
        abs_path (str, optional):  An absolute path to the executable (e.g., 'C:/path/to/my_app.exe'). Defaults to None.

    Behavior:
        - If both relative_path and abs_path are provided, abs_path takes precedence.
        - Kills processes whose executable path (proc.info['exe']) either:
            - Starts with the resolved path of the relative_path, OR
            - Exactly matches the provided absolute path (case-insensitive).
        - Skips killing the current process and its parent process.
    """
    try:
        current_pid = os.getpid()
        parent_pid = os.getppid()

        if abs_path:
            # Absolute path takes precedence
            logger.info(f"Killing process(es) with absolute path: {abs_path}")
            abs_path = os.path.normcase(os.path.abspath(abs_path))  # Normalize and make case-insensitive
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    if proc.info['exe'] and os.path.normcase(proc.info['exe']) == abs_path:
                        if proc.pid != current_pid and proc.pid != parent_pid:
                            logger.info(f'Trying to kill the exe {proc.info}')
                            proc.kill()
                        else:
                            logger.info(
                                f'Skipped killing the current or parent process. Current PID: {current_pid}, Parent PID: {parent_pid}, Process Info: {proc.info}')
                except psutil.NoSuchProcess:
                    logger.warning(f"Process {proc.info['pid']} disappeared during iteration.")
                except Exception as e:
                    logger.error(f"Error processing process {proc.info.get('pid', 'N/A')}: {e}")

        elif relative_path:
            logger.info(f"Killing process(es) with relative path: {relative_path}")
            # Resolve relative path to an absolute path
            abs_relative_path = os.path.abspath(relative_path)

            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    if proc.info['exe'] and os.path.normpath(proc.info['exe']).startswith(abs_relative_path):
                        if proc.pid != current_pid and proc.pid != parent_pid:
                            logger.info(f'Trying to kill the exe {proc.info}')
                            proc.kill()
                        else:
                            logger.info(
                                f'Skipped killing the current or parent process. Current PID: {current_pid}, Parent PID: {parent_pid}, Process Info: {proc.info}')
                except psutil.NoSuchProcess:
                    logger.warning(f"Process {proc.info['pid']} disappeared during iteration.")

                except Exception as e:
                    logger.error(f"Error processing process {proc.info.get('pid', 'N/A')}: {e}")

        else:
            logger.warning("Both relative_path and abs_path are None.  No processes will be killed.")


    except Exception as e:
        logger.error('An error occurred while trying to kill the process.', e)  # Print traceback


def get_first_gpu_free_memory_mib():
    """
    Gets the free memory (in MiB) of the first available NVIDIA GPU using nvidia-smi.

    Returns:
        int: The free memory in MiB for the first GPU.
             Returns -1 if nvidia-smi is not found, fails, or output cannot be parsed.
    """
    try:
        # Command to execute
        command = [
            "nvidia-smi",
            "--query-gpu=memory.free",
            "--format=csv,noheader,nounits"
        ]

        # Execute the command
        result = subprocess.run(
            command,
            capture_output=True,  # Capture stdout and stderr
            text=True,  # Decode output as text (usually UTF-8)
            check=False  # Don't raise exception on non-zero exit code (we handle it)
        )

        # Check if the command executed successfully
        if result.returncode != 0:
            # print(f"nvidia-smi error (return code {result.returncode}): {result.stderr.strip()}", file=sys.stderr)
            return -1

        # Process the output
        output = result.stdout.strip()
        if not output:
            # print("nvidia-smi returned empty output.", file=sys.stderr)
            return -1

        # nvidia-smi might list multiple GPUs, each on a new line. Get the first one.
        first_gpu_memory_str = output.splitlines()[0]

        # Convert the memory value to an integer
        free_memory_mib = int(first_gpu_memory_str)
        return free_memory_mib

    except FileNotFoundError as e:
        logger.error(
            "Error: 'nvidia-smi' command not found. Make sure NVIDIA drivers are installed and nvidia-smi is in the PATH.",
            e)
        return -1
    except (ValueError, IndexError) as e:
        # ValueError if output is not an integer
        # IndexError if output.splitlines() is empty
        logger.error(f"Error parsing nvidia-smi output:", e)
        # print(f"Raw output was: '{result.stdout}'", file=sys.stderr)
        return -1
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred: ", e)
        return -1


def get_current_process_memory_usage():
    """
    Gets the memory usage of the current process.

    Returns:
        A tuple containing:
            - resident_memory (int): Resident Set Size (RSS) in MB.  This is the non-swapped physical memory a process has used.
            - virtual_memory (int): Virtual Memory Size (VMS) in MB. This includes all memory the process can access, including swapped out memory.
            - shared_memory (int/None): Shared memory (SHM) in MB, or None if not available.  This is the memory shared with other processes.  This might not be available on all systems (especially Windows, where psutil may return 0.0).
    """
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()

    resident_memory_mb = mem_info.rss / (1024 * 1024)  # Convert bytes to MB
    virtual_memory_mb = mem_info.vms / (1024 * 1024)

    try:
        shared_memory_mb = mem_info.shared / (1024 * 1024)
    except AttributeError:
        shared_memory_mb = None  # Shared memory might not be a valid metric on some systems

    return resident_memory_mb, virtual_memory_mb, shared_memory_mb








def parse_arguments_to_map(description="main script"):
    """
    Parses command-line arguments using argparse and returns them as a dictionary.

    Args:
        description (str, optional): A description for the argument parser. Defaults to "A script".

    Returns:
        dict: A dictionary where keys are argument names and values are their parsed values.
    """

    parser = argparse.ArgumentParser(description=description)

    # Add your arguments here.  This is just an example - adapt this to your needs!
    parser.add_argument("-t", "--task", help="which task to execute as index starting with 1", type=int, default=0)
    parser.add_argument("-e", "--exit", action="store_true", help="exit after task")

    args, _ = parser.parse_known_args()

    # Convert the args object to a dictionary
    arg_map = vars(args)  # vars() returns the __dict__ attribute of an object

    return arg_map




def is_cuda_12_or_above():
    """Checks nvidia-smi output for CUDA version >= 12.0."""
    try:
        # Run nvidia-smi and capture output
        output = subprocess.check_output(['nvidia-smi'], text=True)
        # Search for CUDA Version in the output
        match = re.search(r"CUDA Version:\s*(\d+\.\d+)", output)
        if match:
            version = float(match.group(1))
            logger.info(f"Detected CUDA Version: {version}")
            return version >= 12.0
        else:
            logger.error("CUDA Version string not found in nvidia-smi output.")
            return False
    except FileNotFoundError:
        logger.info("nvidia-smi command not found. Ensure NVIDIA drivers are installed.")
        return False
    except Exception as e:
        logger.error(f"nvidia-smi An error occurred:", e)
        return False


def create_shortcut(exe_path=None, shortcut_name_post=None, description=None, target_path=None, arguments=None):
    """
    Creates a shortcut in the Start Menu for the given executable.

    Args:
        exe_path: The full path to the executable file.
        shortcut_name: The name of the shortcut (without the .lnk extension).
        target_path:  Optional. The full path to the Start Menu location.
                          If None, uses the current user's Start Menu.
    """
    if not exe_path:
        cwd = os.getcwd()
        pattern = os.path.join(cwd, "ok*.exe")  # Construct the search pattern

        # Use glob to find files matching the pattern (case-insensitive)
        matching_files = glob.glob(pattern.lower()) + glob.glob(pattern.upper())  # search both cases

        for filename in glob.glob(pattern):
            exe_path = filename
            break

    if not os.path.exists(exe_path):
        logger.error(f'create_shortcut exe_path {exe_path} not exist')
        return False

    if not os.path.isabs(exe_path):
        exe_path = os.path.abspath(exe_path)

    if target_path is None:
        target_path = os.path.join(os.path.expandvars("%AppData%"), "Microsoft", "Windows", "Start Menu",
                                   "Programs")

    shortcut_name = os.path.splitext(os.path.basename(exe_path))[0]
    if shortcut_name_post:
        shortcut_name += shortcut_name_post

    if not os.path.exists(target_path):
        logger.error(f'create_shortcut target_path {target_path} not exist')
        return False

    shortcut_path = os.path.join(target_path, f"{shortcut_name}.lnk")

    try:
        from win32com.client import Dispatch
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortcut(shortcut_path)
        shortcut.TargetPath = exe_path
        if arguments is not None:
            shortcut.Arguments = arguments
        shortcut.WorkingDirectory = os.path.dirname(exe_path)
        shortcut.Description = description if description else shortcut_name
        shortcut.IconLocation = exe_path
        shortcut.save()

        logger.info(f"shortcut created at: {shortcut_path} {exe_path}")

    except Exception as e:
        logger.error(f"Error creating shortcut:", e)
        return False
    return shortcut_path


def prevent_sleeping(yes=True):
    # Prevent the system from sleeping
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000002 if yes else 0x80000000)


