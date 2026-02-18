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
                    cmd = f'start "" /b "{game_cmd}"'
                    if arguments:
                        cmd += f" {arguments}"
                    subprocess.Popen(cmd, cwd=os.path.dirname(game_path), shell=True,
                                     creationflags=0x00000008)  # detached process
                    return True
                except Exception as e:
                    logger.error('execute error', e)
            else:
                logger.error(f'execute error path not exist {game_cmd}')


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


def read_global_gpu_pref():
    """
    Reads the 'SwapEffectUpgradeEnable' value from the DirectX User GPU Preferences
    in the Windows Registry and returns True if it is enabled (i.e., not set to "0;"),
    False if it is disabled ("0;"), and None if the value or key is not found.
    """
    if not can_enable_hdr():
        return None, None

    key_path = r"Software\Microsoft\DirectX\UserGpuPreferences"
    value_name = "DirectXUserGlobalSettings"

    try:
        # Open the registry key for reading
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

        # Read the value
        value, reg_type = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)  # Close the key *after* reading

        if reg_type != winreg.REG_SZ:
            logger.error(f"Warning: Expected REG_SZ, but got REG_TYPE {reg_type}. Returning None.")
            return None, None

        # Check if SwapEffectUpgradeEnable is disabled ("0;")
        hdr_enabled = parse_reg_value(value, 'AutoHDREnable')
        swipe_enabled = parse_reg_value(value, 'SwapEffectUpgradeEnable')

        logger.debug(f'check global gpu pref {value} {hdr_enabled} {swipe_enabled}')
        return hdr_enabled, swipe_enabled

    except FileNotFoundError:
        # Key or value not found
        logger.error(f"Key '{key_path}' or value '{value_name}' not found.")
        return None, None
    except Exception as e:
        logger.error(f"Error reading DirectX User GPU Preferences: {e}")
        return None, None


def can_enable_hdr():
    """
    check if can_enable_hdr
    """
    key_path = r"Software\Microsoft\DirectX\GraphicsSettings"
    value_name = "AutoHDROptOutApplicable"

    try:
        # Open the registry key for reading
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

        # Read the value
        value, reg_type = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)  # Close the key *after* reading

        # FIX: Allow REG_DWORD (4) as well as REG_SZ (1)
        if reg_type != winreg.REG_SZ and reg_type != winreg.REG_DWORD:
            logger.error(f"Warning: Expected REG_SZ or REG_DWORD, but got REG_TYPE {reg_type}. Returning None.")
            return False # FIX: Return boolean False, not tuple (None, None)

        logger.debug(f'check global AutoHDROptOutApplicable {value}')
        return value == 1 or value == "1"

    except FileNotFoundError:
        # Key or value not found
        # logger.error(f"Key '{key_path}' or value '{value_name}' not found.")
        return False # FIX: Return boolean
    except Exception as e:
        logger.error(f"Error reading DirectX User GPU Preferences: {e}")
        return False # FIX: Return boolean


def read_game_gpu_pref(game_executable_path):
    """
    Checks if Auto HDR is enabled for a specific game executable path in Windows.

    Args:
        game_executable_path (str): The full path to the game's executable file
                                     (e.g., "C:\\Games\\MyGame\\game.exe").

    Returns:
        bool: True if Auto HDR is enabled for the game, False otherwise.
              Returns None if the setting cannot be found.
    """
    if not can_enable_hdr():
        return None, None
    if not game_executable_path:
        return None, None
    try:
        # Open the registry key where per-app graphics settings are stored.
        key_path = r"Software\Microsoft\DirectX\UserGpuPreferences"
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

        try:
            # Open the registry key for reading
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

            # Read the value
            value, reg_type = winreg.QueryValueEx(key, game_executable_path)
            winreg.CloseKey(key)  # Close the key *after* reading

            if reg_type != winreg.REG_SZ:
                logger.error(f"Warning: Expected REG_SZ, but got REG_TYPE {reg_type}. Returning None.")
                return None, None # Consistent return

            hdr_enabled = parse_reg_value(value, 'AutoHDREnable')
            swipe_enabled = parse_reg_value(value, 'SwapEffectUpgradeEnable')

            logger.debug(f'check game gpu pref {value} {hdr_enabled} {swipe_enabled}')
            return hdr_enabled, swipe_enabled

        except FileNotFoundError:
            # Key or value not found
            logger.error(f"Key '{key_path}' or value '{game_executable_path}' not found.")
            return None, None
        except Exception as e:
            logger.error(f"Error reading DirectX User GPU Preferences: {e}")
            return None, None

    except FileNotFoundError:
        logger.error("Required registry key not found.")
        return None, None
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return None, None


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


def parse_reg_value(directx_string, the_key):
    """
    Parses the DirectX string to extract the AutoHDREnable value (if it exists)
    and determines if it represents an "enabled" state based on whether
    it's an odd number.

    Args:
        directx_string: The DirectX user preferences string.

    Returns:
        True if AutoHDREnable exists and is an odd number.
        False if AutoHDREnable does not exist, is not an integer, or is an even number.
    """
    if not directx_string:
        return None  # Return False if the input string is empty

    settings = {}

    pairs = directx_string.split(';')
    for pair in pairs:
        if not pair:
            continue

        parts = pair.split('=')
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()
            settings[key] = value

    auto_hdr_value = settings.get(the_key)
    logger.debug(f'parse_reg_value {directx_string} {the_key}={value} ')

    if auto_hdr_value is None:
        return None  # AutoHDREnable not found

    try:
        auto_hdr_int = int(auto_hdr_value)  # Convert to integer
        if the_key == 'AutoHDREnable' and auto_hdr_int == 2097:
            return False
    except ValueError:
        return None  # Not an integer value

    return auto_hdr_int % 2 != 0  # True if odd, False if even


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


import ctypes
from ctypes import wintypes


def is_hdr_enabled():
    # Constant definitions
    QDC_ONLY_ACTIVE_PATHS = 0x00000002
    DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9
    ERROR_SUCCESS = 0

    # Structure definitions
    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
        _fields_ = [
            ("adapterId", LUID),
            ("id", wintypes.UINT),
            ("modeInfoIdx", wintypes.UINT),
            ("statusFlags", wintypes.UINT),
        ]

    class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
        _fields_ = [
            ("adapterId", LUID),
            ("id", wintypes.UINT),
            ("modeInfoIdx", wintypes.UINT),
            ("outputTechnology", wintypes.UINT),
            ("rotation", wintypes.UINT),
            ("scaling", wintypes.UINT),
            ("refreshRateNumerator", wintypes.UINT),
            ("refreshRateDenominator", wintypes.UINT),
            ("scanLineOrdering", wintypes.UINT),
            ("targetAvailable", wintypes.BOOL),
            ("statusFlags", wintypes.UINT),
        ]

    class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
        _fields_ = [
            ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
            ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
            ("flags", wintypes.UINT),
        ]

    # --- FIX START: Define the missing structure ---
    # DISPLAYCONFIG_MODE_INFO contains a union of ~48 bytes.
    # The total struct size is 64 bytes. We use a byte array to reserve the union space safe/easy.
    class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
        _fields_ = [
            ("infoType", wintypes.UINT),
            ("id", wintypes.UINT),
            ("adapterId", LUID),
            ("modeInfo", ctypes.c_byte * 48)  # Reserve space for the union (Target/Source/Desktop modes)
        ]

    # --- FIX END ---

    class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.UINT),
            ("size", wintypes.UINT),
            ("adapterId", LUID),
            ("id", wintypes.UINT),
        ]

    class DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO(ctypes.Structure):
        _fields_ = [
            ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
            ("value", wintypes.UINT),
            ("colorEncoding", wintypes.UINT),
            ("bitsPerColorChannel", wintypes.UINT),
        ]

    # Load User32 DLL
    user32 = ctypes.windll.user32

    # Get buffer sizes
    num_path = wintypes.UINT()
    num_mode = wintypes.UINT()

    if user32.GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(num_path),
                                          ctypes.byref(num_mode)) != ERROR_SUCCESS:
        return False

    # Allocate buffers
    paths = (DISPLAYCONFIG_PATH_INFO * num_path.value)()

    # --- FIX: Allocate the correct structure type ---
    modes = (DISPLAYCONFIG_MODE_INFO * num_mode.value)()

    # Query active paths
    if user32.QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(num_path), paths, ctypes.byref(num_mode), modes,
                                 None) != ERROR_SUCCESS:
        return False

    # Check each active path
    for i in range(num_path.value):
        info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
        info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
        info.header.size = ctypes.sizeof(DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO)

        # Target ID must be used for Advanced Color Info
        info.header.adapterId = paths[i].targetInfo.adapterId
        info.header.id = paths[i].targetInfo.id

        if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info)) == ERROR_SUCCESS:
            # Mask 0x1 = Supported, Mask 0x2 = Enabled
            if (info.value & 0x2) == 0x2:
                return True

    return False
