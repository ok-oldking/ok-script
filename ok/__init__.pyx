import argparse
import base64
import ctypes
import glob
import hashlib
import heapq
import importlib
import inspect
import json
import locale
import logging
import math
import os
import platform
import queue
import random
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import traceback
import uuid
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from functools import cmp_to_key
from logging.handlers import TimedRotatingFileHandler, QueueListener, QueueHandler
from typing import Dict
from typing import List
from typing import Optional
# cython: language_level=3
from typing import Union

import cv2
import numpy as np
import psutil
import pyappify
import pydirectinput
import requests
import win32api
import win32gui
import win32process
import win32ui
from PIL import Image
from PySide6.QtCore import QCoreApplication, Qt, QEvent, QSize, QLocale
from PySide6.QtGui import QIcon, QScreen
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QApplication
from qfluentwidgets import FluentIcon, NavigationItemPosition, MSFluentWindow, InfoBarPosition, InfoBar, MessageBox, \
    qconfig

from ok.capture.adb.minitouch import random_theta, random_rho, random_normal_distribution
from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_error, alert_info
from ok.gui.widget.StartLoadingDialog import StartLoadingDialog

os.environ["PYTHONIOENCODING"] = "utf-8"

cdef object _ok_log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(threadName)s %(message)s')

cdef object _ok_logger = logging.getLogger("ok")

cdef Logger logger = Logger._c_get_logger("ok")

cdef class Logger:
    cdef object logger
    cdef str name

    def __init__(self, str name):
        self.logger = _ok_logger  # Assuming a globally accessible logger object
        self.name = name.split('.')[-1]

    cpdef debug(self, object message):
        self.logger.debug("{}:{}".format(self.name, message))

    cpdef info(self, object message):
        self.logger.info("{}:{}".format(self.name, message))

    cpdef warning(self, object message):
        self.logger.warning("{}:{}".format(self.name, message))

    cpdef error(self, object message, Optional[Exception] exception=None):
        cdef str stack_trace_str = Logger.exception_to_str(exception)
        self.logger.error("{}:{} {}".format(self.name, message, stack_trace_str))

    cpdef critical(self, object message):
        self.logger.critical("{}:{}".format(self.name, message))

    @staticmethod
    def call_stack()-> str:
        stack = ""
        for frame_info in inspect.stack():
            frame = frame_info.frame  # get the frame object from the frame_info named tuple
            stack += (f"  File: {frame.f_code.co_filename}, "  # filename
                      f"Line: {frame.f_lineno}, "  # line number
                      f"Function: {frame.f_code.co_name}\n")  # function name
        return stack

    @staticmethod
    cdef Logger _c_get_logger(str name):
        return Logger(name)

    @staticmethod
    def get_logger(str name):
        return Logger._c_get_logger(name)

    @staticmethod
    cdef _log_exception_handler(exc_type, exc_value, exc_traceback):
        if _ok_logger is not None:
            # Format the traceback
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            tb_text = ''.join(tb_lines)
            # Log the exception
            _ok_logger.error(f"Uncaught exception: {tb_text}")

    @staticmethod
    cdef str _c_exception_to_str(Exception exception):
        cdef str stack_trace_str = ""
        if exception is not None:
            try:
                stack_trace_str = traceback.format_exc()  # Decode for Cython
            except Exception as e:
                stack_trace_str = "Error formatting exception: {}".format(str(e))
        return stack_trace_str

    @staticmethod
    def exception_to_str(Exception exception):
        return Logger._c_exception_to_str(exception)


class InfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.ERROR


def config_logger(config=None, name='ok-script'):
    parser = argparse.ArgumentParser(description='Process some parameters.')
    # Add the arguments
    parser.add_argument('--parent_pid', type=int, help='Parent process ID', default=0)
    # Parse the arguments
    args, _ = parser.parse_known_args()

    if not config:
        config = {'debug': True}
    if config.get('debug'):
        _ok_logger.setLevel(logging.DEBUG)
    else:
        _ok_logger.setLevel(logging.INFO)

    communicate_handler = CommunicateHandler()
    communicate_handler.setFormatter(_ok_log_formatter)
    _ok_logger.handlers = []

    if args.parent_pid == 0:
        # Handler for INFO, DEBUG, WARNING to stdout
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(_ok_log_formatter)
        stdout_handler.addFilter(InfoFilter())
        if config.get('debug'):  # Respect the global debug setting for stdout verbosity
            stdout_handler.setLevel(logging.DEBUG)
        else:
            stdout_handler.setLevel(logging.INFO)
        _ok_logger.addHandler(stdout_handler)

    # Handler for ERROR, CRITICAL to stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(_ok_log_formatter)
    stderr_handler.setLevel(logging.ERROR)
    _ok_logger.addHandler(stderr_handler)

    _ok_logger.addHandler(communicate_handler)
    logging.getLogger().handlers = []

    logger_file = get_relative_path(os.path.join('logs', name + '.log'))
    ensure_dir_for_file(logger_file)

    log_queue = queue.Queue()
    queue_handler = QueueHandler(log_queue)
    _ok_logger.addHandler(queue_handler)

    file_handler = SafeFileHandler(logger_file, when="midnight", interval=1,
                                   backupCount=7, encoding='utf-8')
    file_handler.setFormatter(_ok_log_formatter)
    file_handler.setLevel(logging.DEBUG)

    os.makedirs("logs", exist_ok=True)

    listener = QueueListener(log_queue, file_handler)
    listener.start()

    sys.excepthook = Logger._log_exception_handler


class SafeFileHandler(TimedRotatingFileHandler):
    def emit(self, record):
        try:
            if self.stream and not self.stream.closed:
                super().emit(record)
            else:
                raise ValueError("I/O operation on closed file.")
        except Exception:
            self.handleError(record)


def init_class_by_name(module_name, class_name, *args, **kwargs):
    module = importlib.import_module(module_name)
    class_ = getattr(module, class_name)
    return class_(*args, **kwargs)


class ExitEvent(threading.Event):
    queues = set()
    to_stops = set()

    def bind_queue(self, queue):
        self.queues.add(queue)

    def bind_stop(self, to_stop):
        self.to_stops.add(to_stop)

    def set(self):
        super(ExitEvent, self).set()
        logger.debug(f"ExitEvent set event empty queues {self.queues} to_stops: {self.to_stops}")
        for queue in self.queues:
            queue.put(None)

        for to_stop in self.to_stops:
            to_stop.stop()


@dataclass(order=True)
class ScheduledTask:
    execute_at: float
    task: callable = field(compare=False)


class Handler:
    def __init__(self, event: ExitEvent, name=None):
        self.task_queue = []
        self.executing = None
        self.condition = threading.Condition()
        self.exit_event = event
        self.name = name
        self.exit_event.bind_stop(self)
        self.thread = threading.Thread(target=self._process_tasks, name=name)
        self.thread.start()

    def _process_tasks(self):
        while not self.exit_event.is_set():
            scheduled_task_to_run = None
            with self.condition:
                while not self.task_queue and not self.exit_event.is_set():
                    self.condition.wait(timeout=1.0)  # Wait with a timeout to periodically check exit_event

                if self.exit_event.is_set():
                    break  # Exit outer loop

                if not self.task_queue:  # Still no tasks after wait (e.g. timeout)
                    continue

                now = time.time()
                next_task_info = self.task_queue[0]  # Peek

                if next_task_info.execute_at <= now:
                    scheduled_task_to_run = heapq.heappop(self.task_queue)
                else:
                    timeout = next_task_info.execute_at - now
                    self.condition.wait(timeout=max(0, timeout))  # max(0, timeout) in case now slightly passed
                    continue

            # Lock is released here
            if scheduled_task_to_run:
                if scheduled_task_to_run.task is None:  # Sentinel for stopping
                    logger.debug(f'stopping handler {self.thread.name}')
                    return  # Exit thread

                self.executing = scheduled_task_to_run.task
                try:
                    scheduled_task_to_run.task()
                except Exception as e:
                    logger.error(f'handler {self.thread.name} raised exception: {e}')  # exc_info=True is helpful
                finally:  # Ensure self.executing is cleared
                    self.executing = None
        logger.debug(f'handler {self.thread.name} processing loop finished due to exit event.')

    def post(self, task, delay=0, remove_existing=False, skip_if_running=False):
        with self.condition:
            if self.exit_event.is_set():
                logger.error(f'post handler {self.thread.name} already exits')
                self.condition.notify_all()
                return
            if remove_existing and len(self.task_queue) > 0:
                for obj in self.task_queue.copy():
                    if obj.task == task:
                        self.task_queue.remove(obj)
                        logger.debug(f'removing duplicate task {task}')
            if skip_if_running and self.executing == task:
                logger.debug(f'skipping duplicate task {task}')
                return
            if delay > 0:
                scheduled_task = ScheduledTask(time.time() + delay, task)
            else:
                scheduled_task = ScheduledTask(0, task)
            heapq.heappush(self.task_queue, scheduled_task)
            self.condition.notify_all()
            return True

    def stop(self):
        logger.info(f'handler stop raised exception {self.name}')
        with self.condition:
            self.task_queue.clear()
            heapq.heappush(self.task_queue, ScheduledTask(0, None))
            self.condition.notify_all()


def read_json_file(file_path) -> dict | None:
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError:
        return None

def write_json_file(file_path, data):
    ensure_dir_for_file(file_path)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return True

def is_admin():
    try:
        # Only Windows users with admin privileges can read the C drive directly
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def get_first_item(lst, default=None):
    return next(iter(lst), default) if lst is not None else default

def safe_get(lst, idx, default=None):
    try:
        return lst[idx]
    except IndexError:
        return default

def find_index_in_list(my_list, target_string, default_index=-1):
    try:
        index = my_list.index(target_string)
        return index
    except ValueError:
        return default_index

def get_path_relative_to_exe(*files):
    for file in files:
        if file is None:
            return
    frozen = getattr(sys, 'frozen', False)
    if frozen:
        # The application is running as a bundled executable
        application_path = os.path.abspath(sys.executable)
    else:
        # The application is running as a Python script
        application_path = os.path.abspath(sys.argv[0])
    logger.debug(f'get_path_relative_to_exe application_path {application_path} frozen {frozen}')
    the_dir = os.path.dirname(application_path)

    # Join the directory with the file paths
    path = os.path.join(the_dir, *files)

    # Normalize the path
    normalized_path = os.path.normpath(path)

    if not os.path.exists(normalized_path):
        path = path = os.path.join(os.getcwd(), *files)
        normalized_path = os.path.normpath(path)

    return normalized_path

def get_relative_path(*files):
    for file in files:
        if file is None:
            return

    # Join the directory with the file paths
    path = os.path.join(os.getcwd(), *files)

    # Normalize the path
    normalized_path = os.path.normpath(path)

    return normalized_path

def install_path_isascii():
    path = get_path_relative_to_exe('')

    isascii = path.isascii()

    return isascii, path

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    # Get the absolute path of the current script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if 'site-packages' in base_dir:  # if ok is installed by pip
        return relative_path
    # Move up one directory level
    base_dir = os.path.dirname(base_dir)
    # Move up another directory level
    base_dir = os.path.dirname(base_dir)
    # Check if the '_MEIPASS' attribute exists in the 'sys' module (used by PyInstaller)
    # If it exists, set 'base_path' to its value; otherwise, use 'base_dir'
    base_path = getattr(sys, '_MEIPASS', base_dir)
    # Combine 'base_path' with 'relative_path' to form the absolute path to the resource
    return os.path.join(base_path, relative_path)

def ensure_dir_for_file(file_path):
    # Extract the directory from the file path
    directory = os.path.dirname(file_path)

    return ensure_dir(directory)

def ensure_dir(directory, clear=False):
    # Check if the directory is a file
    if os.path.isfile(directory):
        # If it is a file, delete it
        os.remove(directory)

    # Check if the directory exists
    if directory and not os.path.exists(directory):
        # If the directory does not exist, create it (including any intermediate directories)
        os.makedirs(directory)
    elif clear:
        clear_folder(directory)

    return directory

def delete_if_exists(file_path):
    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            shutil.rmtree(file_path, onerror=handle_remove_error)
        else:
            os.remove(file_path)

def delete_folders_starts_with(path, starts_with):
    if os.path.isdir(path):
        for folder_name in os.listdir(path):
            folder_path = os.path.join(path, folder_name)
            if os.path.isdir(folder_path) and folder_name.startswith(starts_with):
                shutil.rmtree(folder_path, onerror=handle_remove_error)

def handle_remove_error(func, path, exc_info):
    print(f"Error removing {path}: {exc_info}")
    os.chmod(path, 0o777)
    time.sleep(0.01)
    func(path)

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

def clear_folder(folder_path):
    # Check if the folder exists
    if folder_path is None:
        return

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        return

    # Check if the path is a folder
    if not os.path.isdir(folder_path):
        print(f"The path {folder_path} is not a folder.")
        return

    # Delete all files in the folder
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)  # remove the file
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)  # remove dir and all contains
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

def find_first_existing_file(filenames, directory):
    for filename in filenames:
        full_path = os.path.join(directory, filename)
        if os.path.isfile(full_path):
            return full_path
    return None

def get_path_in_package(base, file):
    the_dir = os.path.dirname(os.path.realpath(base))

    # Get the path of the file relative to the script
    return os.path.join(the_dir, file)

def dir_checksum(directory, excludes=None):
    if excludes is None:
        excludes = []
    md5_hash = hashlib.md5()

    # Iterate over all files in the directory
    for path, dirs, files in os.walk(directory):
        for name in files:
            # Skip files in the excludes list
            if name in excludes:
                continue

            filepath = os.path.join(path, name)

            # Open the file in binary mode and calculate its MD5 checksum
            with open(filepath, 'rb') as f:
                while True:
                    data = f.read(8192)
                    if not data:
                        break
                    md5_hash.update(data)

    # Return the hexadecimal representation of the checksum
    return md5_hash.hexdigest()

def find_folder_with_file(root_folder, target_file):
    # Check the root folder itself
    if target_file in os.listdir(root_folder):
        return root_folder

    # Iterate over all subfolders in the root folder
    for folder, subfolders, files in os.walk(root_folder):
        if target_file in files:
            return folder

    return None

def get_folder_size(folder_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)
    return total_size  # Convert bytes to MB
import threading

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

NtQuerySystemInformation = ctypes.windll.ntdll.NtQuerySystemInformation
NtQuerySystemInformation.argtypes = (ctypes.c_int32, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
SystemProcessIdInformation = 0x58


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ('Length', ctypes.c_ushort),
        ('MaximumLength', ctypes.c_ushort),
        ('Buffer', ctypes.c_wchar_p),
    ]

    @classmethod
    def create(cls, init_with: Union[str, int]):
        buffer = ctypes.create_unicode_buffer(init_with)
        bufsize = len(buffer)
        if isinstance(init_with, str):
            wchlen = bufsize - 1  # exclude null
        else:
            wchlen = 0
        return cls(wchlen * 2, bufsize * 2, ctypes.cast(buffer, ctypes.c_wchar_p))

    def __str__(self):
        return ctypes.wstring_at(self.Buffer, self.Length // 2)


class SYSTEM_PROCESS_ID_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('ProcessId', ctypes.c_size_t),
        ('ImageName', UNICODE_STRING),
    ]


def ratio_text_to_number(supported_ratio):
    # Parse the supported ratio string
    supported_ratio_list = [int(i) for i in supported_ratio.split(':')]
    return supported_ratio_list[0] / supported_ratio_list[1]

def data_to_base64(data) -> str:
    """
    Serialize a dictionary or a list of dictionaries to a base64 encoded string.

    Args:
        data (Union[Dict, List[Dict]]): The data to serialize.

    Returns:
        str: The base64 encoded string.
    """
    # Serialize the data to a JSON string
    json_str = json.dumps(data)
    # Encode the JSON string to bytes
    json_bytes = json_str.encode('utf-8')
    # Base64 encode the bytes
    base64_bytes = base64.b64encode(json_bytes)
    # Convert the base64 bytes to a string
    base64_str = base64_bytes.decode('utf-8')
    return base64_str

def base64_to_data(base64_str: str) -> Union[Dict, List[Dict]]:
    """
    Deserialize a base64 encoded string back to a dictionary or a list of dictionaries.

    Args:
        base64_str (str): The base64 encoded string.

    Returns:
        Union[Dict, List[Dict]]: The deserialized data.
    """
    # Decode the base64 string to bytes
    json_bytes = base64.b64decode(base64_str)
    # Convert the bytes to a JSON string
    json_str = json_bytes.decode('utf-8')
    # Deserialize the JSON string back to a dictionary or list of dictionaries
    data = json.loads(json_str)
    return data

def get_readable_file_size(file_path):
    """Calculates the readable size of a file.

    Args:
        file_path (str): The path to the file.

    Returns:
        str: The readable file size (e.g., "1.23 MB").
    """

    if not os.path.exists(file_path):
        return "0B"

    size_bytes = os.path.getsize(file_path)
    return bytes_to_readable_size(size_bytes)

def bytes_to_readable_size(size_bytes):
    """Converts bytes to a human-readable size.

    Args:
        size_bytes (int): The size in bytes.

    Returns:
        str: The human-readable size.
    """

    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s}{size_name[i]}"

def execute(game_cmd: str):
    if game_cmd:
        game_path = get_path(game_cmd)
        if os.path.exists(game_path):
            try:
                logger.info(f'try execute {game_cmd}')
                subprocess.Popen(['start', '', '/b', game_cmd], cwd=os.path.dirname(game_path), shell=True,
                                 creationflags=0x00000008)  # detached process
                return True
            except Exception as e:
                logger.error('execute error', e)

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

cdef class Box:
    cdef public int x, y, width, height
    cdef public float confidence
    cdef public object name

    def __init__(self, x, y, width=0, height=0, confidence=1.0, name=None, to_x=-1, to_y=-1):
        self.x = int(round(x))
        self.y = int(round(y))
        if to_x != -1:
            self.width = int(round(to_x - x))
        else:
            self.width = int(round(width))
        if to_y != -1:
            self.height = int(round(to_y - y))
        else:
            self.height = int(round(height))

        if self.width == 0:
            self.width = 1
            logger.warning(f'box width is 0, fixed to 1 {x} {y} {width} {height} {to_x} {to_y}')
        if self.height == 0:
            self.height = 1
            logger.warning(f'box height is 0, fixed to 1 {x} {y} {width} {height} {to_x} {to_y}')

        if self.width <= 0 or self.height <= 0:
            raise ValueError(f'width and height must be greater than zero {x} {y} {width} {height} {to_x} {to_y}')

        self.confidence = confidence
        self.name = name

    def __eq__(self, other):
        if not isinstance(other, Box):
            return NotImplemented
        return (self.x == other.x and self.y == other.y and
                self.width == other.width and self.height == other.height and
                self.confidence == other.confidence and self.name == other.name)

    def area(self) -> int:
        """
        Calculates the area of the box.

        Returns:
            int: The area of the box (width * height).
        """
        # Use cdef types for performance if possible, though for simple multiplication
        # Python integers are often optimized well.
        return self.width * self.height

    def in_boundary(self, boxes):
        cdef list in_boundary_boxes = []
        cdef Box box
        for box in boxes:
            if (self.x <= box.x and self.x + self.width >= box.x + box.width and
                    self.y <= box.y and self.y + self.height >= box.y + box.height):
                in_boundary_boxes.append(box)
        return in_boundary_boxes

    def __repr__(self):
        return f'{self.name}_{self.confidence:.2f}'

    def __str__(self):
        if self.name is not None:
            return f"Box(name='{self.name}', x={self.x}, y={self.y}, width={self.width}, height={self.height}, confidence={round(self.confidence * 100)})"
        return f"Box(x={self.x}, y={self.y}, width={self.width}, height={self.height}, confidence={round(self.confidence * 100)})"

    def scale(self, width_ratio: float, height_ratio: float = None):
        """
        Scales the box by given width and height ratios, keeping the center point the same.
        If the scaling causes x or y to become negative, it will be set to 0,
        while maintaining the center point.

        Args:
            width_ratio: The ratio to scale the width by (e.g., 1.1 for 110%, 0.9 for 90%).
            height_ratio: The ratio to scale the height by (e.g., 1.1 for 110%, 0.9 for 90%).
                          If None, defaults to the width_ratio.

        Returns:
            A new Box object with the scaled dimensions and position.
        """

        if height_ratio is None:
            height_ratio = width_ratio

        center_x = self.x + self.width / 2.0
        center_y = self.y + self.height / 2.0

        new_width = round(self.width * width_ratio)
        new_height = round(self.height * height_ratio)

        new_x = round(center_x - new_width / 2.0)
        new_y = round(center_y - new_height / 2.0)

        if new_x < 0:
            new_x = 0

        if new_y < 0:
            new_y = 0

        return Box(new_x, new_y, new_width, new_height, confidence=self.confidence, name=self.name)

    def closest_distance(self, Box other):
        cdef int horizontal_distance, vertical_distance
        cdef int right1 = self.x + self.width
        cdef int bottom1 = self.y + self.height
        cdef int right2 = other.x + other.width
        cdef int bottom2 = other.y + other.height

        horizontal_distance = max(0, max(self.x, other.x) - min(right1, right2))
        vertical_distance = max(0, max(self.y, other.y) - min(bottom1, bottom2))
        return 0.0 if horizontal_distance == 0 and vertical_distance == 0 else math.sqrt(
            horizontal_distance ** 2 + vertical_distance ** 2)

    cpdef center_distance(self, other):
        x1, y1 = self.center()
        x2, y2 = other.center()

        dx = x2 - x1
        dy = y2 - y1
        # Calculate distance using the distance formula: sqrt((x2-x1)^2 + (y2-y1)^2)
        # Ensure intermediate calculations use float for precision before sqrt
        distance_float = math.sqrt(float(dx ** 2 + dy ** 2))
        # Return the integer part of the distance
        return distance_float

    def relative_with_variance(self, float relative_x=0.5, float relative_y=0.5):
        cdef float center_x = self.x + self.width * relative_x
        cdef float center_y = self.y + self.height * relative_y
        cdef float variance = random.uniform(0, 0.1)
        return int(round(center_x + variance)), int(round(center_y + variance))

    def copy(self, int x_offset=0, int y_offset=0, int width_offset=0, int height_offset=0, name=None):
        return Box(self.x + x_offset, self.y + y_offset, self.width + width_offset, self.height + height_offset,
                   self.confidence, name or self.name)

    def crop_frame(self, frame):  # type is unkown, can not be typed
        return frame[self.y:self.y + self.height, self.x:self.x + self.width]

    def center(self):
        return round(self.x + self.width / 2.0), round(self.y + self.height / 2.0)

    cdef float _distance_criteria(self, Box box, str direction, int orig_x, int orig_y, int orig_w, int orig_h,
                                  condition=None):
        cdef int box_x = box.x, box_y = box.y, box_w = box.width, box_h = box.height
        cdef int dx = max(orig_x - (box_x + box_w), box_x - (orig_x + orig_w), 0)
        cdef int dy = max(orig_y - (box_y + box_h), box_y - (orig_y + orig_h), 0)
        cdef float distance = math.sqrt(dx ** 2 + dy ** 2)
        if box is self:
            return float('inf')

        if direction == 'up' and self.y - (box.y + box.height / 2) >= 0:
            pass
        elif direction == 'down' and box.y - (self.y + self.height / 2) >= 0:
            pass
        elif direction == 'left' and self.x - (box.x + box.width / 2) >= 0:
            pass
        elif direction == 'right' and box.x - (self.x + self.width / 2) >= 0:
            pass
        elif direction == 'all':
            pass
        else:
            return float('inf')

        if condition is not None and not condition(box):
            return float('inf')

        return distance

    def find_closest_box(self, str direction, list boxes, condition=None):
        cdef int orig_x = self.x, orig_y = self.y, orig_w = self.width, orig_h = self.height

        boxes.sort(key=lambda box: self._distance_criteria(box, direction, orig_x, orig_y, orig_w, orig_h, condition))
        for box in boxes:
            if self._distance_criteria(box, direction, orig_x, orig_y, orig_w, orig_h, condition) != float('inf'):
                return box
        return None

cdef bint box_intersect(Box box1, Box box2):  # cdef function, no closure issues
    return not (box1.y > box2.y + box2.height or box1.y + box1.height < box2.y)

cdef int compare_boxes(Box box1, Box box2):  # cdef function, no closure issues
    cdef int cmp
    if box_intersect(box1, box2):
        cmp = box1.x - box2.x
        if cmp == 0:
            cmp = box1.y - box2.y
    else:
        cmp = box1.y - box2.y
        if cmp == 0:
            cmp = box1.x - box2.x
    if cmp == 0:
        cmp = int(box1.confidence * 1000 - box2.confidence * 1000)  #Use int to compare float
    if cmp == 0 and box1.name is not None and box2.name is not None:
        cmp = (box1.name > box2.name) - (box1.name < box2.name)
    return cmp

def find_highest_confidence_box(boxes):
    if not boxes:
        return None
    return max(boxes, key=lambda box: box.confidence)

cpdef sort_boxes(list[Box] boxes):
    boxes.sort(key=cmp_to_key(compare_boxes))  #Use external cdef function
    return boxes

cpdef Box find_box_by_name(list[Box] boxes, object names):
    if isinstance(names, (str, re.Pattern)):
        names = [names]

    cdef Box result = None
    cdef int priority = len(names)
    cdef int i
    cdef name
    for box in boxes:
        for i, name in enumerate(names):
            if (isinstance(name, str) and name == box.name) or (
                    isinstance(name, re.Pattern) and re.search(name, box.name)):
                if i < priority:
                    priority = i
                    result = box
                    if i == 0:
                        break

    return result

def get_bounding_box(list[Box] boxes):
    if not boxes:
        raise ValueError("The list of boxes is empty")

    cdef int min_x = min(box.x for box in boxes)
    cdef int min_y = min(box.y for box in boxes)
    cdef int max_x = max(box.x + box.width for box in boxes)
    cdef int max_y = max(box.y + box.height for box in boxes)

    return Box(min_x, min_y, max_x - min_x, max_y - min_y)

cpdef list[Box] find_boxes_within_boundary(list[Box] boxes, Box boundary_box, bint sort=True):
    cdef list[Box] within_boundary = []

    for box in boxes:
        if (box.x >= boundary_box.x and
                box.y >= boundary_box.y and
                box.x + box.width <= boundary_box.x + boundary_box.width and
                box.y + box.height <= boundary_box.y + boundary_box.height):
            within_boundary.append(box)
    if sort:
        within_boundary = sort_boxes(within_boundary)
    return within_boundary

def average_width(list[Box] boxes):
    cdef int total_width = sum(box.width for box in boxes)
    return int(total_width / len(boxes)) if boxes else 0

cpdef object crop_image(object image, Box box=None):
    if box is not None:
        if (0 <= box.x <= image.shape[1] - box.width and
                0 <= box.y <= image.shape[0] - box.height and
                box.width > 0 and box.height > 0):
            return image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        else:
            return image
    return image

def relative_box(frame_width, frame_height, x, y, to_x=1, to_y=1, width=0, height=0, name=None, confidence=1.0):
    if width == 0:
        width = to_x - x
    if height == 0:
        height = to_y - y
    return Box(round(x * frame_width), round(y * frame_height),
               round(width * frame_width), round(height * frame_height),
               name=name, confidence=confidence)

def find_boxes_by_name(boxes, names) -> list[Box]:
    # Ensure names is always a list
    if isinstance(names, (str, re.Pattern)):
        names = [names]

    result = []

    for box in boxes:
        # Flag to track if the box has been matched and should be added
        matched = False
        for name in names:
            if matched:
                break  # Stop checking names if we've already matched this box
            if (isinstance(name, str) and name == box.name) or (isinstance(box.name, str) and
                                                                isinstance(name, re.Pattern) and re.search(name,
                                                                                                           box.name)):
                matched = True
        if matched:
            result.append(box)

    return result

##Color.py


cdef dict black_color = {
    'r': (0, 0),  # Red range
    'g': (0, 0),  # Green range
    'b': (0, 0)  # Blue range
}

cdef dict white_color = {
    'r': (255, 255),  # Red range
    'g': (255, 255),  # Green range
    'b': (255, 255)  # Blue range
}

cdef is_close_to_pure_color(object image, int max_colors=5000, float percent=0.97):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    cdef dict color_counts = {}
    cdef tuple color
    cdef int total_pixels = image.shape[0] * image.shape[1]

    for row in image:
        for pixel in row:
            color = tuple(pixel)
            color_counts[color] = color_counts.get(color, 0) + 1
            if len(color_counts) > max_colors:
                return False

    dominant_color = max(color_counts, key=color_counts.get)
    dominant_count = color_counts[dominant_color]
    percentage = (dominant_count / total_pixels)
    return percentage > percent

def get_mask_in_color_range(object image, dict color_range):
    cdef object lower_bound, upper_bound, mask
    cdef int pixel_count

    lower_bound, upper_bound = color_range_to_bound(color_range)
    mask = cv2.inRange(image, lower_bound, upper_bound)
    pixel_count = np.count_nonzero(mask)

    return mask, pixel_count

cpdef tuple get_connected_area_by_color(object image, dict color_range, int connectivity=4, int gray_range=0):
    cdef object lower_bound, upper_bound, mask, diff_rg, diff_gb, diff_br, gray_mask
    cdef int num_labels
    cdef object labels, stats, centroids

    lower_bound, upper_bound = color_range_to_bound(color_range)
    mask = cv2.inRange(image, lower_bound, upper_bound)
    if gray_range > 0:
        diff_rg = np.abs(image[:, :, 0] - image[:, :, 1])
        diff_gb = np.abs(image[:, :, 1] - image[:, :, 2])
        diff_br = np.abs(image[:, :, 2] - image[:, :, 0])
        gray_mask = (diff_rg <= 10) & (diff_gb <= 10) & (diff_br <= 10)
        gray_mask = gray_mask.astype(np.uint8) * 255
        mask = mask & gray_mask

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=connectivity)
    return num_labels, stats, labels

cpdef tuple color_range_to_bound(dict color_range):
    cdef object lower_bound = np.array([color_range['b'][0], color_range['g'][0], color_range['r'][0]],
                                       dtype="uint8")
    cdef object upper_bound = np.array([color_range['b'][1], color_range['g'][1], color_range['r'][1]],
                                       dtype="uint8")
    return lower_bound, upper_bound

cpdef float calculate_colorfulness(object image, Box box=None):
    cdef object B, G, R, rg, yb
    cdef float rbMean, rbStd, ybMean, ybStd, stdRoot, meanRoot

    if box is not None:
        image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
    B, G, R = cv2.split(image.astype("float"))
    rg = np.absolute(R - G)
    yb = np.absolute(0.5 * (R + G) - B)
    rbMean, rbStd = np.mean(rg), np.std(rg)
    ybMean, ybStd = np.mean(yb), np.std(yb)
    stdRoot = np.sqrt((rbStd ** 2) + (ybStd ** 2))
    meanRoot = np.sqrt((rbMean ** 2) + (ybMean ** 2))
    colorfulness = stdRoot + (0.3 * meanRoot)

    return colorfulness / 100

cpdef float get_saturation(object image, Box box=None):
    cdef object hsv_image, saturation_channel
    cdef float mean_saturation

    if image is None:
        raise ValueError("Image not found or path is incorrect")

    if box is not None:
        if (box.x >= 0 and box.y >= 0 and
                box.x + box.width <= image.shape[1] and box.y + box.height <= image.shape[0] and
                box.width > 0 and box.height > 0):
            image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]

    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation_channel = hsv_image[:, :, 1]
    mean_saturation = saturation_channel.mean() / 255

    return mean_saturation

cpdef list find_color_rectangles(object image, dict color_range, int min_width, int min_height,
                                 int max_width=-1, int max_height=-1, float threshold=0.95, Box box=None):
    cdef object mask, roi_mask
    cdef int x_offset, y_offset, x, y, w, h, total_pixels, matching_pixels
    cdef float percent
    cdef object contours, results

    if image is None:
        raise ValueError("Image not found or path is incorrect")

    if box is not None:
        image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        x_offset = box.x
        y_offset = box.y
    else:
        x_offset = 0
        y_offset = 0

    lower_bound, upper_bound = color_range_to_bound(color_range)
    mask = cv2.inRange(image, lower_bound, upper_bound)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    results = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= min_width and h >= min_height and (max_height == -1 or h <= max_height) and (
                max_width == -1 or w <= max_width):
            roi_mask = mask[y:y + h, x:x + w]
            total_pixels = roi_mask.size
            matching_pixels = np.sum(roi_mask == 255)
            percent = (matching_pixels / total_pixels)
            if percent >= threshold:
                results.append(Box(x + x_offset, y + y_offset, w, h, confidence=percent))

    return results

cpdef bint is_pure_black(object frame):
    for channel in cv2.split(frame):
        if cv2.countNonZero(channel) > 0:
            return False
    return True

cpdef double calculate_color_percentage(object image, dict color_ranges, Box box=None):
    cdef object mask
    cdef double target_pixels, total_pixels
    cdef double percentage

    if box is not None:
        if (box.x >= 0 and box.y >= 0 and
                box.x + box.width <= image.shape[1] and box.y + box.height <= image.shape[0] and
                box.width > 0 and box.height > 0):
            image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        else:
            return 0
    else:
        image = image[:, :, :3]

    mask = cv2.inRange(image, (color_ranges['b'][0], color_ranges['g'][0], color_ranges['r'][0]),
                       (color_ranges['b'][1], color_ranges['g'][1], color_ranges['r'][1]))
    target_pixels = cv2.countNonZero(mask)
    total_pixels = image.size / 3
    percentage = target_pixels / total_pixels
    return percentage

cpdef double rgb_to_gray(object rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]

def create_non_black_mask(image):
    """
    Creates a binary mask identifying non-black pixels in an image.
    Args:
        image: Input image (NumPy array, BGR or Grayscale).
    Returns:
        A binary mask (uint8 NumPy array, 255 for non-black, 0 for black).
    """
    if image is None:
        raise ValueError("Input image cannot be None")
    if image.ndim == 2:  # Grayscale image
        # Non-black pixels are > 0
        _, mask = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY)
    elif image.ndim == 3 and image.shape[2] in [3, 4]:  # Color image (BGR or BGRA)
        # Convert to grayscale first, then threshold
        # Or, check if all channels are 0
        lower_black = np.array([0, 0, 0], dtype="uint8")
        upper_black = np.array([0, 0, 0], dtype="uint8")
        # Create a mask for black pixels (value 255 where pixel is black)
        # Use only first 3 channels in case of BGRA
        mask_black = cv2.inRange(image[:, :, :3], lower_black, upper_black)
        # Invert the mask (255 where pixel is non-black)
        mask = cv2.bitwise_not(mask_black)
    else:
        raise ValueError("Input image must be Grayscale (2D) or BGR/BGRA (3D)")
    return mask


class CommunicateHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        from ok.gui.Communicate import communicate
        self.communicate = communicate

    def emit(self, record):
        log_message = self.format(record)
        self.communicate.log.emit(record.levelno, log_message)


cdef class App:
    cdef public object global_config, app, ok_config, auth_config, locale, overlay, start_controller, loading_window, overlay_window, main_window, exit_event, icon, fire_base_analytics, to_translate, po_translation, updater
    cdef public dict config
    cdef public str about, title, version
    cdef bint debug

    def __init__(self, config, task_executor,
                 exit_event=None):
        super().__init__()
        og.exit_event = exit_event
        og.handler = Handler(exit_event, 'global')
        self.config = config
        self.auth_config = None
        self.global_config = task_executor.global_config if task_executor else None
        from ok.gui.util.app import init_app_config
        self.app, self.locale = init_app_config()
        self.ok_config = Config('_ok', {'window_x': -1, 'window_y': -1, 'window_width': -1, 'window_height': -1,
                                        'window_maximized': False})
        communicate.quit.connect(self.app.quit)

        self.about = self.config.get('about')
        self.title = self.config.get('gui_title')
        self.app.setApplicationName(self.title)
        self.app.setApplicationDisplayName(self.title)
        self.version = self.config.get('version')
        self.app.setApplicationVersion(self.version)
        self.debug = self.config.get('debug', False)
        if self.config.get(
                'git_update') and not pyappify.app_version and self.version != "dev" and not os.path.exists(
            '.venv'):
            from ok.update.GitUpdater import GitUpdater
            self.updater = GitUpdater(self.config, exit_event)
        else:
            self.updater = None

        logger.debug(f'locale name {self.locale.name()}')

        self.loading_window = None
        self.overlay_window = None
        self.main_window = None
        self.exit_event = exit_event
        self.icon = QIcon(get_path_relative_to_exe(config.get('gui_icon')) or ":/icon/icon.ico")
        if self.config.get('analytics'):
            self.fire_base_analytics = Analytics(self.config, self.exit_event)
        from ok.gui.StartController import StartController
        self.start_controller = StartController(self.config, exit_event)
        if self.config.get('debug') or self.config.get('use_overlay'):
            logger.debug('init overlay')
            from ok.gui.overlay.OverlayWindow import OverlayWindow
            self.overlay_window = OverlayWindow(og.device_manager.hwnd_window)
            self.to_translate = set()
        else:
            self.to_translate = None
        self.po_translation = None
        if not config.get('window_size'):
            logger.info(f'no config.window_size was set use default')
            config['window_size'] = {
                'width': 800,
                'height': 600,
                'min_width': 600,
                'min_height': 450,
            }
        og.app = self
        og.executor = task_executor
        if task_executor:
            og.device_manager = task_executor.device_manager
        if my_app := self.config.get('my_app'):
            og.my_app = init_class_by_name(my_app[0], my_app[1], exit_event)
        logger.debug('init app end')

    def quit(self):
        self.exit_event.set()
        self.app.quit()

    def tr(self, key):
        if not key:
            return key
        if ok_tr := QCoreApplication.translate("app", key):
            if ok_tr != key:
                return ok_tr
        if self.to_translate is not None:
            self.to_translate.add(key)
        if self.po_translation is None:
            locale_name = self.locale.name()
            try:
                from ok.gui.i18n.GettextTranslator import get_translations
                self.po_translation = get_translations(locale_name)
                self.po_translation.install()
                logger.info(f'translation installed for {locale_name}')
            except:
                logger.error(f'install translations error for {locale_name}')
                self.po_translation = "Failed"
        if self.po_translation != 'Failed':
            return self.po_translation.gettext(key)
        else:
            return key

    def gen_tr_po_files(self):
        folder = ""
        from ok.gui.common.config import Language
        for locale in Language:
            from ok.gui.i18n.GettextTranslator import update_po_file
            folder = update_po_file(self.to_translate, locale.value.name())
        return folder

    def show_message_window(self, title, message):
        from ok.gui.MessageWindow import MessageWindow
        message_window = MessageWindow(self.icon, title, message, exit_event=self.exit_event)
        message_window.show()

    def show_already_running_error(self):
        title = QCoreApplication.translate("app", 'Error')
        content = QCoreApplication.translate("app",
                                             "Another instance is already running")
        self.show_message_window(title, content)

    def show_path_ascii_error(self, path):
        title = QCoreApplication.translate("app", 'Error')
        content = QCoreApplication.translate("app",
                                             "Install dir {path} must be an English path, move to another path.").format(
            path=path)
        self.show_message_window(title, content)

    def update_overlay(self, visible, x, y, window_width, window_height, width, height, scaling):

        self.overlay_window.update_overlay(visible, x, y, window_width, window_height, width, height, scaling)

    def show_main_window(self):
        self.do_show_main()

    def do_show_main(self):
        if self.debug:
            communicate.window.connect(self.overlay_window.update_overlay)

        self.main_window = MainWindow(self, self.config, self.ok_config, self.icon, self.title, self.version,
                                      self.debug,
                                      self.about,
                                      self.exit_event, self.global_config)

        # Set the window title here
        self.main_window.setWindowIcon(self.icon)

        self.main_window.set_window_size(self.config['window_size']['width'], self.config['window_size']['height'],
                                         self.config['window_size']['min_width'],
                                         self.config['window_size']['min_height'])

        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

        logger.debug(f'show_main_window end')

    def exec(self):
        logger.info('app.exec()')
        sys.exit(self.app.exec())

def get_my_id():
    mac = uuid.getnode()
    value_with_salt = 'mac123:' + str(mac)
    hashed_value = hashlib.md5(value_with_salt.encode()).hexdigest()
    return hashed_value[:8]

def get_my_id_with_cwd():
    mac = uuid.getnode()
    value_with_salt = 'mac123:' + str(mac) + os.getcwd()
    hashed_value = hashlib.md5(value_with_salt.encode()).hexdigest()
    return hashed_value[:8]

k = None

cdef class Response:
    cdef public int code
    cdef public str message
    cdef public object data


## OK.pyx


class OK:
    executor = None
    adb = None
    adb_device = None
    feature_set = None
    hwnd = None
    device_manager = None
    ocr = None
    overlay_window = None
    app = None
    screenshot = None
    exit_event = ExitEvent()
    init_error = None

    def __init__(self, config):
        check_mutex()
        og.ok = self
        if pyappify.app_version:
            config['version'] = pyappify.app_version
        if pyappify.app_profile:
            config['profile'] = pyappify.app_profile
        og.config = config
        self.config = config
        config["config_folder"] = config.get("config_folder") or 'configs'
        Config.config_folder = config["config_folder"]
        config_logger(self.config)
        logger.info(f"ok-script init {config.get('version')}, {sys.argv}, pid={os.getpid()} config: {config}")
        pyappify.logger = logger
        logger.info(
            f"pyappify  app_version:{pyappify.app_version}, app_profile:{pyappify.app_profile}, pyappify_version:{pyappify.pyappify_version} pyappify_upgradeable:{pyappify.pyappify_upgradeable}, pyappify_executable:{pyappify.pyappify_executable}")
        config['debug'] = config.get("debug", False)
        self.task_executor = None
        self._app = None
        self.debug = config['debug']
        self.global_config = GlobalConfig(config.get('global_configs'))
        self.global_config.get_config(basic_options)
        og.global_config = self.global_config
        og.set_use_dml()
        try:
            import ctypes
            # Set DPI Awareness (Windows 10 and 8)
            errorCode = ctypes.windll.shcore.SetProcessDpiAwareness(1)
            logger.info(f'SetProcessDpiAwareness {errorCode}')
            if self.debug:
                import win32api
                win32api.SetConsoleCtrlHandler(self.console_handler, True)
            self.config = config
            self.init_device_manager()
            from ok.gui.debug.Screenshot import Screenshot
            self.screenshot = Screenshot(self.exit_event)
            self.do_init()
        except Exception as e:
            logger.error(f'__init__ error', e)
            self.quit()
            raise e

    @property
    def app(self):
        if self._app is None:
            self._app = App(self.config, self.task_executor, self.exit_event)
        return self._app

    def start(self):
        logger.info(f'OK start id:{id(self)} pid:{os.getpid()}')
        try:
            if self.config.get("use_gui"):
                if not self.init_error:
                    self.app.show_main_window()
                logger.debug('start app.exec()')
                self.app.exec()
            else:
                self.task_executor.start()
                if self.config.get("debug") or self.config.get('use_overlay'):
                    from PySide6.QtWidgets import QApplication
                    app = QApplication(sys.argv)
                    from ok.gui.overlay.OverlayWindow import OverlayWindow
                    self.overlay_window = OverlayWindow(og.device_manager.hwnd_window)
                    app.exec()
                else:
                    try:
                        # Starting the task in a separate thread (optional)
                        # This allows the main thread to remain responsive to keyboard interrupts
                        task_thread = threading.Thread(target=self.wait_task)
                        task_thread.start()

                        # Wait for the task thread to end (which it won't, in this case, without an interrupt)
                        task_thread.join()
                    except KeyboardInterrupt:
                        self.exit_event.set()
                        logger.info("Keyboard interrupt received, exiting script.")
                    finally:
                        # Clean-up code goes here (if any)
                        # This block ensures that the script terminates gracefully,
                        # releasing resources or performing necessary clean-up operations.
                        logger.info("Script has terminated.")
        except Exception as e:
            logger.error("start error", e)
            self.exit_event.set()
            if self.app:
                self.quit()

    def do_init(self):
        logger.info(f"do_init, config: {self.config}")

        template_matching = self.config.get('template_matching')
        if template_matching is not None:
            coco_feature_json = self.config.get('template_matching').get('coco_feature_json')
            self.feature_set = FeatureSet(self.debug, coco_feature_json,
                                          default_horizontal_variance=template_matching.get(
                                              'default_horizontal_variance', 0),
                                          default_vertical_variance=template_matching.get('default_vertical_variance',
                                                                                          0),
                                          default_threshold=template_matching.get('default_threshold', 0),
                                          feature_processor=template_matching.get('feature_processor'))
        ocr_target_height = 0
        if ocr := self.config.get('ocr'):
            isascii, path = install_path_isascii()
            ocr_target_height = ocr.get('target_height', 0)
            if not isascii:
                logger.info(f'show_path_ascii_error')
                self.app.show_path_ascii_error(path)
                self.init_error = True
                self.app.exec()
                return False

        self.task_executor = TaskExecutor(self.device_manager, exit_event=self.exit_event,
                                          wait_until_settle_time=self.config.get('wait_until_settle_time', 1),
                                          feature_set=self.feature_set,
                                          config_folder=self.config.get("config_folder"), debug=self.debug,
                                          global_config=self.global_config, ocr_target_height=ocr_target_height,
                                          config=self.config)
        from ok.gui.tasks.TaskManger import TaskManager
        og.task_manager = TaskManager(task_executor=self.task_executor,
                                      onetime_tasks=self.config.get('onetime_tasks', []),
                                      trigger_tasks=self.config.get('trigger_tasks', []),
                                      scene=self.config.get('scene'))
        og.executor = self.task_executor
        logger.info(f"do_init, end")
        return True

    def wait_task(self):
        while not self.exit_event.is_set():
            time.sleep(1)

    def console_handler(self, event):
        import win32con
        if event == win32con.CTRL_C_EVENT:
            logger.info("CTRL+C event dump threads")
            from ok.capture.windows.dump import dump_threads
            dump_threads()
            self.quit()
        elif event == win32con.CTRL_CLOSE_EVENT:
            logger.info("Close event quit")
            self.quit()
        elif event == win32con.CTRL_LOGOFF_EVENT:
            logger.info("Logoff event quit")
            self.quit()
        elif event == win32con.CTRL_SHUTDOWN_EVENT:
            logger.info("Shutdown event quit")
            self.quit()
        else:  # Perform clean-up tasks here
            logger.info("Performing clean-up...")
        return True

    def quit(self):
        logger.info('quit app')
        self.exit_event.set()

    def init_device_manager(self):
        if self.device_manager is None:
            self.device_manager = DeviceManager(self.config,
                                                self.exit_event, self.global_config)
            og.device_manager = self.device_manager


cdef class BaseScene:
    def reset(self):
        pass

## Task.pyx

cdef class BaseTask(OCR):
    cdef public str name
    cdef public str description
    cdef public bint _enabled
    cdef public object config
    cdef public object info
    cdef public dict default_config
    cdef public dict config_description
    cdef public dict config_type
    cdef public bint _paused
    cdef public object lock
    cdef public object _handler
    cdef public bint running
    cdef public bint exit_after_task
    cdef public bint trigger_interval
    cdef public double last_trigger_time
    cdef public double start_time
    cdef public object icon
    cdef public list supported_languages

    def __init__(self, executor=None):
        super().__init__(executor)
        self.name = self.__class__.__name__
        self.description = ""
        self._enabled = False
        self.config = None
        self.exit_after_task = False
        self.info = {}
        self.default_config = {}
        self.global_config_names = []
        self.config_description = {}
        self.config_type = {}
        self.supported_languages = []
        self._paused = False
        self.lock = threading.Lock()
        self._handler = None
        self.running = False
        self.trigger_interval = 0
        self.last_trigger_time = 0
        self.start_time = 0
        self.icon = None
        self.first_run_alert = None
        self.show_create_shortcut = False

    def run_task_by_class(self, cls):
        task = self.get_task_by_class(cls)
        old_ifo = task.info
        task.info = self.info
        try:
            task.run()
        except Exception as e:
            self.log_error(f'run_task_by_class {cls}', e)
            task.info = old_ifo
            raise e
        task.info = old_ifo

    def post_init(self):
        pass

    def create_shortcut(self):
        index = self.executor.onetime_tasks.index(self) + 1
        path = create_shortcut(None, f' {self.name}', arguments=f"-t {index}")
        if path:
            path2 = create_shortcut(None, f' {self.name} exit_after', arguments=f"-t {index} -e")
            subprocess.Popen(r'explorer /select,"{}"'.format(path))

    def tr(self, message):
        return og.app.tr(message)

    def should_trigger(self):
        if self.trigger_interval == 0:
            return True
        now = time.time()
        time_diff = now - self.last_trigger_time
        if time_diff > self.trigger_interval:
            self.last_trigger_time = now
            return True
        return False

    def is_custom(self):
        return og.task_manager.is_custom(self)

    def add_first_run_alert(self, first_run_alert):
        self.default_config.update({'_first_run_alert': ""})
        self.first_run_alert = first_run_alert

    def add_exit_after_config(self):
        self.default_config.update({'Exit After Task': False})
        self.config_description.update(
            {'Exit After Task': 'Exit the Game and the App after Successfully Executing the Task'})

    def get_status(self):
        if self.running:
            return "Running"
        elif self.enabled:
            if self.paused:
                return "Paused"
            else:
                return "In Queue"
        else:
            return "Not Started"

    def enable(self):
        if not self._enabled:
            self._enabled = True
            self.info_clear()
            self.executor.interaction.on_run()
            logger.info(f'enabled task {self}')
        communicate.task.emit(self)

    @property
    def handler(self) -> Handler:
        with self.lock:
            if self._handler is None:
                self._handler = Handler(self.executor.exit_event, __name__)
            return self._handler

    def pause(self):
        if isinstance(self, TriggerTask):
            self.executor.pause()
        else:
            self.executor.pause(self)
            self._paused = True
            communicate.task.emit(self)
        if self.executor.is_executor_thread():
            self.sleep(1)

    def unpause(self):
        self._paused = False
        self.executor.start()
        communicate.task.emit(self)

    @property
    def paused(self):
        return self._paused

    def log_info(self, message, notify=False):
        self.logger.info(message)
        self.info_set("Log", message)
        if notify:
            self.notification(message, tray=True)

    def log_debug(self, message, notify=False):
        self.logger.debug(message)
        if notify:
            self.notification(message, tray=True)

    def log_error(self, message, exception=None, notify=False):
        self.logger.error(message, exception)
        if exception is not None:
            if len(exception.args) > 0:
                message += exception.args[0]
            else:
                message += str(exception)
        self.info_set("Error", message)
        if notify:
            self.notification(message, error=True, tray=True)

    def go_to_tab(self, tab):
        self.log_info(f"go to tab {tab}")
        communicate.tab.emit(tab)

    def notification(self, message, title=None, error=False, tray=False, show_tab=None):
        if og.app:
            communicate.notification.emit(message, title, error, tray, show_tab)

    @property
    def enabled(self):
        return self._enabled

    def info_clear(self):
        self.info.clear()

    def info_incr(self, key, inc=1):
        # If the key is in the dictionary, get its value. If not, return 0.
        value = self.info.get(key, 0)
        # Increment the value
        value += inc
        # Store the incremented value back in the dictionary
        self.info[key] = value

    def info_add_to_list(self, key, item):
        value = self.info.get(key, [])
        if isinstance(item, list):
            value += item
        else:
            value.append(item)
        self.info[key] = value

    def info_set(self, key, value):
        if key != 'Log' and key != 'Error':
            self.logger.info(f'info_set {key} {value}')
        self.info[key] = value

    def info_get(self, *args, **kwargs):
        return self.info.get(*args, **kwargs)

    def info_add(self, key, count=1):
        self.info[key] = self.info.get(key, 0) + count

    def load_config(self):
        self.config = Config(self.__class__.__name__, self.default_config, validator=self.validate)

    def validate(self, key, value):
        message = self.validate_config(key, value)
        if message:
            return False, message
        else:
            return True, None

    def validate_config(self, key, value):
        pass

    def disable(self):
        self._enabled = False
        communicate.task.emit(self)

    @property
    def hwnd_title(self):
        if self.executor.device_manager.hwnd_window:
            return self.executor.device_manager.hwnd_window.hwnd_title
        else:
            return ""

    def run(self):
        pass

    def trigger(self):
        return True

    def on_destroy(self):
        pass

    def on_create(self):
        pass

    def set_executor(self, executor):
        self.load_config()
        self.on_create()

    def find_boxes(self, boxes, match=None, boundary=None):
        if match:
            boxes = find_boxes_by_name(boxes, match)
        if boundary:
            box = self.get_box_by_name(boundary) if isinstance(boundary, str) else boundary
            boxes = find_boxes_within_boundary(boxes, box)
        return boxes


class TaskDisabledException(Exception):
    pass


class CannotFindException(Exception):
    pass


class FinishedException(Exception):
    pass


class WaitFailedException(Exception):
    pass


cdef class TaskExecutor:
    cdef public object _frame
    cdef public bint paused
    cdef double pause_start
    cdef double pause_end_time
    cdef double _last_frame_time
    cdef double wait_until_timeout
    cdef public object device_manager
    cdef public object feature_set
    cdef double wait_until_settle_time
    cdef double wait_scene_timeout
    cdef public object exit_event
    cdef public bint debug_mode
    cdef public bint debug
    cdef public object global_config
    cdef public dict _ocr_lib
    cdef public int ocr_target_height
    cdef public object current_task
    cdef str config_folder
    cdef int trigger_task_index
    cdef public list trigger_tasks
    cdef public list onetime_tasks
    cdef object thread, locale
    cdef public object scene
    cdef public dict text_fix
    cdef public object ocr_po_translation
    cdef public object config
    cdef object basic_options, lock

    def __init__(self, device_manager,
                 wait_until_timeout=10, wait_until_settle_time=-1,
                 exit_event=None, feature_set=None,
                 ocr_lib=None,
                 config_folder=None, debug=False, global_config=None, ocr_target_height=0, config=None):
        self._frame = None
        device_manager.executor = self
        self.pause_start = time.time()
        self.pause_end_time = time.time()
        self._last_frame_time = 0
        self.paused = True
        self.config = config
        self.scene = None
        from ok.gui.common.config import cfg
        self.locale = cfg.get(cfg.language).value
        self.text_fix = {}
        self.ocr_po_translation = None
        self.load_tr()
        self.ocr_target_height = ocr_target_height
        self.device_manager = device_manager
        self.feature_set = feature_set
        self.wait_until_settle_time = wait_until_settle_time
        self.wait_scene_timeout = wait_until_timeout
        self.exit_event = exit_event
        self.debug_mode = False
        self.debug = debug
        self.global_config = global_config
        self._ocr_lib = {}
        if self.config.get('ocr') and not self.config.get('ocr').get('default', False):
            self.config['ocr']['default'] = self.config.get('ocr')
        self.current_task = None
        self.config_folder = config_folder or "config"
        self.trigger_task_index = -1
        self.basic_options = global_config.get_config(basic_options)

        self.trigger_tasks = []
        self.onetime_tasks = []
        self.thread = None
        self.lock = threading.Lock()

    cdef load_tr(self):
        locale_name = self.locale.name()
        try:
            from ok.gui.i18n.GettextTranslator import get_ocr_translations
            self.ocr_po_translation = get_ocr_translations(locale_name)
            self.ocr_po_translation.install()
            logger.info(f'translation ocr installed for {locale_name}')
        except:
            logger.error(f'install ocr translations error for {locale_name}')
            self.ocr_po_translation = None

    @property
    def interaction(self):
        return self.device_manager.interaction

    @property
    def method(self):
        return self.device_manager.capture_method

    def ocr_lib(self, name="default"):
        if name not in self._ocr_lib:
            lib = self.config.get('ocr').get(name).get('lib')
            to_download = self.config.get('ocr').get(name).get('download_models')
            if to_download:
                models = self.config.get('download_models').get(to_download)
                from ok.gui.util.download import download_models
                download_models(models)

            config_params = self.config.get('ocr').get(name).get('params')
            if config_params is None:
                config_params = {}
            if lib == 'paddleocr':
                logger.info('use paddleocr as ocr lib')
                from paddleocr import PaddleOCR
                import os
                lang = 'ch'
                config_params['use_textline_orientation'] = False
                config_params['use_doc_unwarping'] = False
                config_params['use_doc_orientation_classify'] = False
                config_params['device'] = "gpu" if is_cuda_12_or_above() else "cpu"
                logger.info(f'init PaddleOCR with {config_params}')
                self._ocr_lib[name] = PaddleOCR(**config_params)
                import logging
                logging.getLogger('ppocr').setLevel(logging.ERROR)
                config_logger(self.config)
            elif lib == 'dgocr':
                if config_params.get('use_dml', True):
                    config_params['use_dml'] = og.use_dml
                from dgocr import DGOCR
                self._ocr_lib[name] = DGOCR(**config_params)
            elif lib == 'onnxocr':
                from onnxocr.onnx_paddleocr import ONNXPaddleOcr
                logger.info(f'init onnxocr {config_params}')
                self._ocr_lib[name] = ONNXPaddleOcr(use_angle_cls=False, use_gpu=False, use_dml=og.use_dml,
                                                    use_openvino=config_params.get('use_openvino', False))
            elif lib == 'rapidocr':
                from rapidocr import RapidOCR
                params = {"Global.use_cls": False, "Global.max_side_len": 100000, "Global.min_side_len": 0,
                          "EngineConfig.onnxruntime.use_dml": og.use_dml}
                params.update(config_params)
                logger.info(f'init rapidocr {params}')
                self._ocr_lib[name] = RapidOCR(params=params)
            else:
                raise Exception(f'ocr lib not supported: {lib}')
            logger.info(f'ocr_lib init {self._ocr_lib[name]} {lib}')
        return self._ocr_lib[name]

    def nullable_frame(self):
        return self._frame

    def check_frame_and_resolution(self, supported_ratio, min_size, time_out=8.0):
        if supported_ratio is None or min_size is None:
            return True, '0x0'
        logger.info(f'start check_frame_and_resolution')
        self.device_manager.update_resolution_for_hwnd()
        cdef double start = time.time()
        cdef object frame = None
        while frame is None and (time.time() - start) < time_out:
            frame = self.method.get_frame()
            time.sleep(0.1)
        if frame is None:
            logger.error(f'check_frame_and_resolution failed can not get frame after {time_out} {time.time() - start}')
            return False, '0x0'
        cdef int width = self.method.width
        cdef int height = self.method.height
        cdef actual_ratio = 0
        if height == 0:
            actual_ratio = 0
        else:
            actual_ratio = width / height
        supported_ratio = ratio_text_to_number(supported_ratio)
        # Calculate the difference between the actual and supported ratios
        difference = abs(actual_ratio - supported_ratio)
        support = difference <= 0.01 * supported_ratio
        if not support:
            logger.error(f'resolution error {width}x{height} {frame is None}')
        if not support and frame is not None:
            communicate.screenshot.emit(frame, "resolution_error", False, None)
        # Check if the difference is within 1%
        if support and min_size is not None:
            if width < min_size[0] or height < min_size[1]:
                support = False
        return support, f"{width}x{height}"

    def can_capture(self):
        return self.method is not None and self.interaction is not None and self.interaction.should_capture()

    def next_frame(self):
        self.reset_scene()
        while not self.exit_event.is_set():
            if self.can_capture():
                frame = self.method.get_frame()
                if frame is not None:
                    height, width = frame.shape[:2]
                    if height <= 0 or width <= 0:
                        logger.warning(f"captured wrong size frame: {width}x{height}")
                    self._frame = frame.copy()
                    self._last_frame_time = time.time()
                    return self._frame
            self.sleep(1)
            logger.error("got no frame!")
        raise FinishedException()

    def is_executor_thread(self):
        return self.thread == threading.current_thread()

    def connected(self):
        return self.method is not None and self.method.connected()

    @property
    def frame(self):
        while self.paused and not self.debug_mode:
            self.sleep(1)
        if self.exit_event.is_set():
            logger.info("frame Exit event set. Exiting early.")
            sys.exit(0)
        if self._frame is None:
            self.next_frame()
        return self._frame

    cpdef check_enabled(self, check_pause=True):
        if check_pause and self.paused:
            self.sleep(1)
        if self.current_task and not self.current_task.enabled:
            logger.info(f'{self.current_task} is disabled, raise Exception')
            self.current_task = None
            raise TaskDisabledException()

    cpdef sleep(self, double timeout):
        """
        Sleeps for the specified timeout, checking for an exit event every 100ms, with adjustments to prevent oversleeping.

        :param timeout: The total time to sleep in seconds.
        """
        if timeout <= 0:
            return
        self.reset_scene(check_enabled=False)
        if self.debug_mode:
            time.sleep(timeout)
            return
        self.pause_end_time = time.time() + timeout
        cdef double to_sleep = 0
        while True:
            self.check_enabled(check_pause=False)
            if self.exit_event.is_set():
                logger.info("sleep Exit event set. Exiting early.")
                sys.exit(0)
            if not (self.paused or (
                    self.current_task is not None and self.current_task.paused) or self.interaction is None or not self.interaction.should_capture()):
                to_sleep = self.pause_end_time - time.time()
                if to_sleep <= 0:
                    return
                if to_sleep > 1:
                    to_sleep = 1
                time.sleep(to_sleep)
            else:
                time.sleep(0.1)

    def pause(self, task=None):
        if task is not None:
            if self.current_task != task:
                raise Exception(f"Can only pause current task {self.current_task}")
        elif not self.paused:
            self.paused = True
            communicate.executor_paused.emit(self.paused)
            self.reset_scene(check_enabled=False)
            self.pause_start = time.time()
            return True

    def stop_current_task(self):
        if task := self.current_task:
            task.disable()
            task.unpause()

    def start(self):
        with self.lock:
            if self.thread is None:
                self.thread = threading.Thread(target=self.execute, name="TaskExecutor")
                self.thread.start()
            if self.paused:
                self.paused = False
                communicate.executor_paused.emit(self.paused)
                self.pause_end_time += self.pause_start - time.time()

    def wait_condition(self, condition, time_out=0, pre_action=None, post_action=None, settle_time=-1,
                       raise_if_not_found=False):
        self.reset_scene()
        start = time.time()
        if time_out == 0:
            time_out = self.wait_scene_timeout
        settled = 0
        result = None
        while not self.exit_event.is_set():
            if pre_action is not None:
                pre_action()
            self.next_frame()
            result = condition()
            result_str = list_or_obj_to_str(result)
            if result:
                logger.debug(
                    f"found result {result_str} {(time.time() - start):.3f}")
                if settle_time == -1:
                    settle_time = self.wait_until_settle_time
                if settle_time > 0:
                    if settled > 0 and time.time() - settled > settle_time:
                        return result
                    if settled == 0:
                        settled = time.time()
                    continue
                else:
                    return result
            else:
                settled = 0
            if post_action is not None:
                post_action()
            if time.time() - start > time_out:
                logger.info(f"wait_until timeout {condition} {time_out} seconds")
                break
        if raise_if_not_found:
            raise WaitFailedException()
        return None

    def reset_scene(self, check_enabled=True):
        if check_enabled:
            self.check_enabled()
        self._frame = None
        if self.scene:
            self.scene.reset()

    cdef tuple next_task(self):
        if self.exit_event.is_set():
            logger.error(f"next_task exit_event.is_set exit")
            return None, False, False
        for onetime_task in self.onetime_tasks:
            if onetime_task.enabled:
                logger.info(f'get one enabled onetime_task {onetime_task.name}')
                return onetime_task, True, False
        cycled = False
        for _ in range(len(self.trigger_tasks)):
            if self.trigger_task_index == len(self.trigger_tasks) - 1:
                self.trigger_task_index = -1
                self.trigger_sleep()
                cycled = True
            self.trigger_task_index += 1
            task = self.trigger_tasks[self.trigger_task_index]
            if task.enabled and task.should_trigger():
                return task, cycled, True
        return None, cycled, False

    def active_trigger_task_count(self):
        return len([x for x in self.trigger_tasks if x.enabled])

    cdef trigger_sleep(self):
        if interval := self.basic_options.get('Trigger Interval', 1):
            self.sleep(interval / 1000)

    cdef execute(self):
        logger.info(f"start execute")
        cdef object task
        cdef bint cycled
        while not self.exit_event.is_set():
            if self.paused:
                logger.info(f'executor is paused sleep')
                self.sleep(1)
            task, cycled, is_trigger_task = self.next_task()
            if not task:
                time.sleep(1)
                continue
            if cycled:
                self.reset_scene()
            elif time.time() - self._last_frame_time > 0.2:
                self.reset_scene()
            try:
                task.start_time = time.time()
                if not is_trigger_task:
                    task.running = True
                    self.current_task = task
                    communicate.task.emit(task)
                if cycled or self._frame is None:
                    self.next_frame()
                if is_trigger_task:
                    if task.run():
                        self.trigger_task_index = -1
                        self.reset_scene()
                        continue
                else:
                    prevent_sleeping(True)
                    logger.debug(f'start running onetime_task {task.name}')
                    task.run()
                    logger.debug(f'end running onetime_task {task.name}')
                    prevent_sleeping(False)
                    task.disable()
                    communicate.task_done.emit(task)
                    if task.exit_after_task or task.config.get('Exit After Task'):
                        logger.info('Successfully Executed Task, Exiting Game and App!')
                        alert_info('Successfully Executed Task, Exiting Game and App!')
                        time.sleep(5)
                        self.device_manager.stop_hwnd()
                        time.sleep(5)
                        communicate.quit.emit()
                self.current_task = None
                if not is_trigger_task:
                    communicate.task.emit(task)
                if self.current_task is not None:
                    self.current_task.running = False
                    if not is_trigger_task:
                        communicate.task.emit(self.current_task)
                    self.current_task = None
            except TaskDisabledException:
                logger.info(f"TaskDisabledException, continue {task}")
                from ok import og
                communicate.notification.emit('Stopped', task.name, False,
                                              True, "start")
                continue
            except FinishedException:
                logger.info(f"FinishedException, breaking")
                break
            except Exception as e:
                if isinstance(e, CaptureException):
                    communicate.capture_error.emit()
                name = task.name
                task.disable()
                from ok import og
                error = str(e)
                communicate.notification.emit(error, name, True, True, None)
                tab = "trigger" if is_trigger_task else "onetime"
                task.info_set(QCoreApplication.tr('app', 'Error'), error)
                logger.error(f"{name} exception", e)
                if self._frame is not None:
                    communicate.screenshot.emit(self.frame, name, True, None)
                self.current_task = None
                communicate.task.emit(None)

        logger.debug(f'exit_event is set, destroy all tasks')
        for task in self.onetime_tasks:
            task.on_destroy()
        for task in self.trigger_tasks:
            task.on_destroy()
        if self.interaction:
            self.interaction.on_destroy()

    def stop(self):
        logger.info('stop')
        self.exit_event.set()

    def wait_until_done(self):
        self.thread.join()

    def get_all_tasks(self):
        return self.onetime_tasks + self.trigger_tasks

    def get_task_by_class_name(self, class_name):
        for onetime_task in self.onetime_tasks:
            if onetime_task.__class__.__name__ == class_name:
                return onetime_task
        for trigger_task in self.trigger_tasks:
            if trigger_task.__class__.__name__ == class_name:
                return trigger_task

    def get_task_by_class(self, cls):
        logger.debug(f'get_task_by_class {cls} {self.onetime_tasks} {self.trigger_tasks}')
        for onetime_task in self.onetime_tasks:
            if isinstance(onetime_task, cls):
                return onetime_task
        for trigger_task in self.trigger_tasks:
            if isinstance(trigger_task, cls):
                return trigger_task

def list_or_obj_to_str(val):
    if val is not None:
        if isinstance(val, list):
            return ', '.join(str(obj) for obj in val)
        else:
            return str(val)
    else:
        return None

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
        matching_files = glob.glob(pattern.lower()) + glob.glob(pattern.upper())  #search both cases

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

cdef prevent_sleeping(yes=True):
    # Prevent the system from sleeping
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000002 if yes else 0x80000000)

cdef class ExecutorOperation:
    cdef double last_click_time
    cdef public TaskExecutor _executor
    cdef public object logger

    def __init__(self, TaskExecutor executor):
        self._executor = executor
        self.logger = Logger.get_logger(self.__class__.__name__)
        self.last_click_time = 0

    def exit_is_set(self):
        return self.executor.exit_event.is_set()

    def get_task_by_class(self, cls):
        return self.executor.get_task_by_class(cls)

    def box_in_horizontal_center(self, box, off_percent=0.02):
        if box is None:
            return False

        center = self.executor.method.width / 2
        box_center = box.x + box.width / 2

        offset = abs(box_center - center)

        if offset / self.executor.method.width < off_percent:
            return True
        else:
            return False

    @property
    def executor(self):
        return self._executor

    @property
    def debug(self):
        return self.executor.debug

    def clipboard(self):
        from ok.third_party.paperclip import paste
        return paste()

    def is_scene(self, the_scene):
        return isinstance(self.executor.current_scene, the_scene)

    def reset_scene(self):
        self.executor.reset_scene()

    def click(self, x: int | Box | List[Box] = -1, y=-1, move_back=False, name=None, interval=-1, move=True,
              down_time=0.01, after_sleep=0, key='left'):
        if isinstance(x, Box) or isinstance(x, list):
            return self.click_box(x, move_back=move_back, down_time=down_time, after_sleep=after_sleep)
        elif 0 < x < 1 or 0 < y < 1:
            return self.click_relative(x, y, move_back=move_back, move=move, interval=interval, after_sleep=after_sleep,
                                       name=name, down_time=down_time, key=key)
        if not self.check_interval(interval):
            self.executor.reset_scene()
            return False
        communicate.emit_draw_box(f"{key}_click",
                                  [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="click", confidence=-1)],
                                  "green")
        self.executor.interaction.click(x, y, move_back=move_back, name=name, move=move, down_time=down_time, key=key)
        if name:
            self.logger.info(f'{key}_click {name} {x, y} after_sleep {after_sleep}')
        if after_sleep > 0:
            self.sleep(after_sleep)
        self.executor.reset_scene()
        return True

    def back(self, *args, **kwargs):
        self.executor.interaction.back(*args, **kwargs)

    def middle_click(self, *args, **kwargs):
        return self.click(*args, **kwargs, key="middle")

    def right_click(self, *args, **kwargs):
        return self.click(*args, **kwargs, key="right")

    def check_interval(self, interval):
        if interval <= 0:
            return True
        now = time.time()
        if now - self.last_click_time < interval:
            return False
        else:
            self.last_click_time = now
            return True

    def is_adb(self):
        if device := self._executor.device_manager.get_preferred_device():
            return device.get('device') != 'windows'

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("mouse_down",
                                  [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="click", confidence=-1)], "green",
                                  frame)
        self.executor.reset_scene()
        self.executor.interaction.mouse_down(x, y, name=name, key=key)

    def mouse_up(self, name=None, key="left"):
        communicate.emit_draw_box("mouse_up",
                                  self.box_of_screen(0.5, 0.5, width=0.01, height=0.01, name="mouse_up", confidence=-1),
                                  "green")
        self.executor.interaction.mouse_up(key=key)
        self.executor.reset_scene()

    def swipe_relative(self, from_x, from_y, to_x, to_y, duration=0.5, settle_time=0):
        self.swipe(int(self.width * from_x), int(self.height * from_y), int(self.width * to_x),
                   int(self.height * to_y), duration, settle_time=settle_time)

    def input_text(self, text):
        name = f"input_text_{text}"
        communicate.emit_draw_box(name, self.box_of_screen(0.5, 0.5, width=0.01, height=0.01, name=name, confidence=-1),
                                  "blue")
        self.executor.interaction.input_text(text)

    @property
    def hwnd(self):
        return self.executor.device_manager.hwnd_window

    def scroll_relative(self, x, y, count):
        self.scroll(int(self.width * x), int(self.height * y), count)

    def scroll(self, x, y, count):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("scroll", [
            Box(x, y, 10, 10,
                name="scroll")], "green", frame)
        # ms = int(duration * 1000)
        self.executor.interaction.scroll(x, y, count)
        self.executor.reset_scene()
        # self.sleep(duration)

    def swipe(self, from_x, from_y, to_x, to_y, duration=0.5, after_sleep=0.1, settle_time=0):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("swipe", [
            Box(min(from_x, to_x), min(from_y, to_y), max(abs(from_x - from_x), 10), max(abs(from_y - to_y), 10),
                name="swipe")], "green", frame)
        ms = int(duration * 1000)
        self.executor.reset_scene()
        self.executor.interaction.swipe(from_x, from_y, to_x, to_y, ms, settle_time=settle_time)
        self.sleep(after_sleep)

    def screenshot(self, name=None, frame=None, show_box=False, frame_box=None):
        if name is None:
            raise ValueError('screenshot name cannot be None')
        communicate.screenshot.emit(self.frame if frame is None else frame, name, show_box, frame_box)

    def click_box_if_name_match(self, boxes, names, relative_x=0.5, relative_y=0.5):
        """
        Clicks on a box from a list of boxes if the box's name matches one of the specified names.
        The box to click is selected based on the order of names provided, with priority given
        to the earliest match in the names list.

        Parameters:
        - boxes (list): A list of box objects. Each box object must have a 'name' attribute.
        - names (str or list): A string or a list of strings representing the name(s) to match against the boxes' names.
        - relative_x (float, optional): The relative X coordinate within the box to click,
                                        as a fraction of the box's width. Defaults to 0.5 (center).
        - relative_y (float, optional): The relative Y coordinate within the box to click,
                                        as a fraction of the box's height. Defaults to 0.5 (center).

        Returns:
        - box: the matched box

        The method attempts to find and click on the highest-priority matching box. If no matches are found,
        or if there are no boxes, the method returns False. This operation is case-sensitive.
        """
        to_click = find_box_by_name(boxes, names)
        if to_click is not None:
            self.logger.info(f"click_box_if_name_match found {to_click}")
            self.click_box(to_click, relative_x, relative_y)
            return to_click

    def box_of_screen(self, x, y, to_x= 1.0, to_y=1.0, width = 0.0, height = 0.0, name=None,
                      hcenter=False, confidence=1.0):
        if name is None:
            name = f"{x} {y} {width} {height}"
        if self.out_of_ratio():
            should_width = self.executor.device_manager.supported_ratio * self.height
            return self.box_of_screen_scaled(should_width, self.height,
                                             x_original=x * should_width,
                                             y_original=self.height * y,
                                             to_x=to_x * should_width,
                                             to_y=to_y * self.height, width_original=width * should_width,
                                             height_original=self.height * height,
                                             name=name, hcenter=hcenter, confidence=confidence)
        else:
            return relative_box(self.executor.method.width, self.executor.method.height, x, y,
                                to_x=to_x, to_y=to_y, width=width, height=height, name=name, confidence=confidence)

    def out_of_ratio(self):
        return self.executor.device_manager.supported_ratio and abs(
            self.width / self.height - self.executor.device_manager.supported_ratio) > 0.01

    def ensure_in_front(self):
        self.executor.device_manager.adb_ensure_in_front()

    def box_of_screen_scaled(self, original_screen_width, original_screen_height, x_original, y_original,
                             to_x = 0, to_y = 0, width_original=0, height_original=0,
                             name=None, hcenter=False, confidence=1.0):
        if width_original == 0:
            width_original = to_x - x_original
        if height_original == 0:
            height_original = to_y - y_original
        x, y, w, h, scale = adjust_coordinates(x_original, y_original, width_original, height_original,
                                               self.screen_width, self.screen_height, original_screen_width,
                                               original_screen_height, hcenter=hcenter)
        return Box(x, y, w, h, name=name, confidence=confidence)

    def height_of_screen(self, percent):
        return int(percent * self.executor.method.height)

    @property
    def screen_width(self):
        return self.executor.method.width

    @property
    def screen_height(self):
        return self.executor.method.height

    def width_of_screen(self, percent):
        return int(percent * self.executor.method.width)

    def click_relative(self, x, y, move_back=False, hcenter=False, move=True, after_sleep=0, name=None, interval=-1,
                       down_time=0.02,
                       key="left"):
        if self.out_of_ratio():
            should_width = self.executor.device_manager.supported_ratio * self.height
            x, y, w, h, scale = adjust_coordinates(x * should_width, y * self.height, 0, 0,
                                                   self.screen_width, self.screen_height, should_width,
                                                   self.height, hcenter=hcenter)
        else:
            x, y = int(self.width * x), int(self.height * y)
        self.click(x, y, move_back, name=name, move=move, down_time=down_time, after_sleep=after_sleep,
                   interval=interval, key=key)

    def middle_click_relative(self, x, y, move_back=False, down_time=0.01):
        self.middle_click(int(self.width * x), int(self.height * y), move_back,
                          name=f'relative({x:.2f}, {y:.2f})', down_time=down_time)

    @property
    def height(self):
        return self.executor.method.height

    @property
    def width(self):
        return self.executor.method.width

    def move_relative(self, x, y):
        self.move(int(self.width * x), int(self.height * y))

    def move(self, x, y):
        self.executor.interaction.move(x, y)
        self.executor.reset_scene()

    def click_box(self, box: Box | List[Box] = None, relative_x=0.5, relative_y=0.5, raise_if_not_found=False,
                  move_back=False, down_time=0.01, after_sleep=1):
        if isinstance(box, list):
            if len(box) > 0:
                box = box[0]

        if isinstance(box, str):
            box = self.get_box_by_name(box)

        if not box:
            self.logger.error(f"click_box box is None")
            if raise_if_not_found:
                raise Exception(f"click_box box is None")
            return
        x, y = box.relative_with_variance(relative_x, relative_y)
        return self.click(x, y, name=box.name, move_back=move_back, down_time=down_time, after_sleep=after_sleep)

    def wait_scene(self, scene_type=None, time_out=0, pre_action=None, post_action=None):
        return self.executor.wait_scene(scene_type, time_out, pre_action, post_action)

    def sleep(self, timeout):
        self.executor.sleep(timeout)
        return True

    def send_key(self, key, down_time=0.02, interval=-1, after_sleep=0):
        if not self.check_interval(interval):
            self.executor.reset_scene()
            return False
        communicate.emit_draw_box("send_key",
                                  [Box(max(0, 0), max(0, 0), 20, 20, name="send_key_" + str(key), confidence=-1)],
                                  "green")
        self.executor.reset_scene()
        self.executor.interaction.send_key(key, down_time)
        if after_sleep > 0:
            self.sleep(after_sleep)
        return True

    def get_global_config(self, option):
        return self.executor.global_config.get_config(option)

    def get_global_config_desc(self, option):
        return self.executor.global_config.get_config_desc(option)

    def send_key_down(self, key):
        self.executor.reset_scene()
        self.executor.interaction.send_key_down(key)

    def send_key_up(self, key):
        self.executor.reset_scene()
        self.executor.interaction.send_key_up(key)

    def wait_until(self, condition, time_out=0, pre_action=None, post_action=None, settle_time=-1,
                   raise_if_not_found=False):
        return self.executor.wait_condition(condition, time_out, pre_action, post_action, settle_time=settle_time,
                                            raise_if_not_found=raise_if_not_found)

    def wait_click_box(self, condition, time_out=0, pre_action=None, post_action=None, raise_if_not_found=False):
        target = self.wait_until(condition, time_out, pre_action, post_action)
        self.click_box(box=target, raise_if_not_found=raise_if_not_found)
        return target

    def next_frame(self):
        return self.executor.next_frame()

    def adb_ui_dump(self):
        return self.executor.device_manager.adb_ui_dump()

    @property
    def frame(self):
        return self.executor.frame

    @staticmethod
    def draw_boxes(feature_name=None, boxes=None, color="red", debug=True):
        communicate.emit_draw_box(feature_name, boxes, color, debug=debug)

    def clear_box(self):
        communicate.clear_box.emit()

    def calculate_color_percentage(self, color, box: Box | str):
        box = self.get_box_by_name(box)
        percentage = calculate_color_percentage(self.frame, color, box)
        box.confidence = percentage
        self.draw_boxes(box.name, box)
        return percentage

    def adb_shell(self, *args, **kwargs):
        return self.executor.device_manager.shell(*args, **kwargs)

cdef class TriggerTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config['_enabled'] = False
        self.trigger_interval = 0

    def on_create(self):
        self._enabled = self.config.get('_enabled', False)

    def get_status(self):
        if self.enabled:
            return "Enabled"
        else:
            return "Disabled"

    def enable(self):
        super().enable()
        self.config['_enabled'] = True

    def disable(self):
        super().disable()
        self.config['_enabled'] = False

cdef class FindFeature(ExecutorOperation):
    def __init__(self, TaskExecutor executor):
        super().__init__(executor)

    def find_feature(self, feature_name=None, horizontal_variance=0, vertical_variance=0, threshold=0,
                     use_gray_scale=False, x=-1, y=-1, to_x=-1, to_y=-1, width=-1, height=-1, box=None, canny_lower=0,
                     canny_higher=0, frame_processor=None, template=None, match_method=cv2.TM_CCOEFF_NORMED,
                     screenshot=False,
                     mask_function=None, frame=None) -> List[Box]:
        if box and isinstance(box, str):
            box = self.get_box_by_name(box)
        return self.executor.feature_set.find_feature(frame if frame is not None else self.executor.frame, feature_name,
                                                      horizontal_variance,
                                                      vertical_variance,
                                                      threshold, use_gray_scale, x, y, to_x, to_y, width, height,
                                                      box=box, match_method=match_method, screenshot=screenshot,
                                                      canny_lower=canny_lower, canny_higher=canny_higher,
                                                      frame_processor=frame_processor,
                                                      template=template, mask_function=mask_function)

    def get_feature_by_name(self, name):
        if self.executor.feature_set:
            return self.executor.feature_set.get_feature_by_name(self.frame, name)
        raise ValueError(f"No feature found for name {name}")

    def get_box_by_name(self, name):
        if isinstance(name, Box):
            return name
        if self.executor.feature_set:
            box = self.executor.feature_set.get_box_by_name(self.frame, name)
            if box:
                return box
        if name == 'right':
            return self.box_of_screen(0.5, 0, 1, 1)
        elif name == 'bottom_right':
            return self.box_of_screen(0.5, 0.5, 1, 1)
        elif name == 'top_right':
            return self.box_of_screen(0.5, 0, 1, 0.5)
        elif name == 'left':
            return self.box_of_screen(0, 0, 0.5, 1)
        elif name == 'bottom_left':
            return self.box_of_screen(0, 0.5, 0.5, 1)
        elif name == 'top_left':
            return self.box_of_screen(0, 0, 0.5, 0.5)
        elif name == 'bottom':
            return self.box_of_screen(0, 0.5, 1, 1)
        elif name == 'top':
            return self.box_of_screen(0, 0, 1, 0.5)
        else:
            raise ValueError(f"No box found for category {name}")

    def find_feature_and_set(self, features, horizontal_variance=0, vertical_variance=0, threshold=0):
        ret = True
        if features is None:
            raise Exception("features cannot be None")
        if isinstance(features, str):
            features = [features]
        for feature in features:
            result = self.find_one(feature, horizontal_variance, vertical_variance, threshold)
            if result is None:
                ret = False
            setattr(self, feature, result)
        return ret

    def wait_feature(self, feature, horizontal_variance=0, vertical_variance=0, threshold=0,
                     time_out=0, pre_action=None, post_action=None, use_gray_scale=False, box=None,
                     raise_if_not_found=False, canny_lower=0, canny_higher=0, settle_time=-1,
                     frame_processor=None):
        return self.wait_until(
            lambda: self.find_one(feature, horizontal_variance, vertical_variance, threshold,
                                  use_gray_scale=use_gray_scale, box=box,
                                  canny_lower=canny_lower, canny_higher=canny_higher,
                                  frame_processor=frame_processor),
            time_out=time_out,
            pre_action=pre_action,
            post_action=post_action,
            raise_if_not_found=raise_if_not_found, settle_time=settle_time)

    def wait_click_feature(self, feature, horizontal_variance=0, vertical_variance=0, threshold=0, relative_x=0.5,
                           relative_y=0.5,
                           time_out=0, pre_action=None, post_action=None, box=None, raise_if_not_found=True,
                           use_gray_scale=False, canny_lower=0, canny_higher=0, click_after_delay=0, settle_time=-1,
                           after_sleep=0):
        box = self.wait_until(
            lambda: self.find_one(feature, horizontal_variance, vertical_variance, threshold, box=box,
                                  use_gray_scale=use_gray_scale, canny_lower=canny_lower, canny_higher=canny_higher),
            time_out=time_out,
            pre_action=pre_action,
            post_action=post_action, raise_if_not_found=raise_if_not_found,
            settle_time=settle_time)
        if box is not None:
            if click_after_delay > 0:
                self.sleep(click_after_delay)
            self.click_box(box, relative_x, relative_y, after_sleep=after_sleep)
            return True
        return False

    def find_one(self, feature_name=None, horizontal_variance=0, vertical_variance=0, threshold=0,
                 use_gray_scale=False, box=None, canny_lower=0, canny_higher=0,
                 frame_processor=None, template=None, mask_function=None, frame=None, match_method=cv2.TM_CCOEFF_NORMED,
                 screenshot=False) -> Box:
        boxes = self.find_feature(feature_name=feature_name, horizontal_variance=horizontal_variance,
                                  vertical_variance=vertical_variance, threshold=threshold,
                                  use_gray_scale=use_gray_scale, box=box, canny_lower=canny_lower,
                                  canny_higher=canny_higher, match_method=match_method, screenshot=screenshot,
                                  frame_processor=frame_processor, template=template, mask_function=mask_function,
                                  frame=frame)
        if len(boxes) > 0:
            if len(boxes) > 1:
                logger.warning(f"find_one:found {feature_name} too many {len(boxes)}")
            highest_box = find_highest_confidence_box(boxes)
            return highest_box

    def on_feature(self, boxes):
        pass

    def feature_exists(self, feature_name: str) -> bool:
        return self.executor.feature_set.feature_exists(feature_name)

    def find_best_match_in_box(self, box, to_find, threshold, use_gray_scale=False,
                               canny_lower=0, canny_higher=0,
                               frame_processor=None, mask_function=None):
        max_conf = 0
        max_box = None
        for feature_name in to_find:
            feature = self.find_one(feature_name, box=box,
                                    threshold=threshold, use_gray_scale=use_gray_scale,
                                    canny_lower=canny_lower, canny_higher=canny_higher,
                                    frame_processor=frame_processor, mask_function=mask_function)
            if feature and feature.confidence > max_conf:
                max_conf = feature.confidence
                max_box = feature
        # logger.debug(f'find_best_match_in_box: {max_box} {max_conf}')
        return max_box

    def find_first_match_in_box(self, box, to_find, threshold, use_gray_scale=False,
                                canny_lower=0, canny_higher=0,
                                frame_processor=None, mask_function=None):
        for feature_name in to_find:
            feature = self.find_one(feature_name, box=box,
                                    threshold=threshold, use_gray_scale=use_gray_scale,
                                    canny_lower=canny_lower, canny_higher=canny_higher,
                                    frame_processor=frame_processor, mask_function=mask_function)
            if feature:
                logger.debug(f'find_first_match_in_box: {feature}')
                return feature

cdef class OCR(FindFeature):
    """
    Optical Character Recognition (OCR) class for detecting and recognizing text within images.

    Attributes:
        ocr_default_threshold (float): The default confidence threshold for OCR results.
        ocr_target_height (int): The target height for resizing images before OCR.
    """

    cdef public float ocr_default_threshold
    cdef bint log_debug

    def __init__(self, TaskExecutor executor):
        super().__init__(executor)

    def get_threshold(self, lib, threshold):
        if threshold > 0:
            return threshold
        else:
            return self.executor.config.get('ocr').get(lib).get('default_threshold', 0.8)

    cpdef list ocr(self, double x=0, double y=0, double to_x=1, double to_y=1, match=None,
                   int width=0, int height=0, object box=None, name=None,
                   double threshold=0,
                   object frame=None, int target_height=0, bint use_grayscale=False, bint log=False,
                   frame_processor=None, lib='default'):
        """
        Performs OCR on a region of an image.

        Args:
            x (double): Relative x-coordinate of the top-left corner of the region.
            y (double): Relative y-coordinate of the top-left corner of the region.
            to_x (double): Relative x-coordinate of the bottom-right corner of the region.
            to_y (double): Relative y-coordinate of the bottom-right corner of the region.
            match (str | List[str] | Pattern[str] | List[Pattern[str]] | None): A string, list of strings, regex pattern, or list of regex patterns to match against the recognized text.
            width (int): Width of the region in pixels.
            height (int): Height of the region in pixels.
            box (Box): A Box object defining the region.
            name (str): A name for the region.
            threshold (double): The confidence threshold for OCR results.
            frame (np.ndarray): The image frame to perform OCR on.
            target_height (int): The target height for resizing the image before OCR.
            use_grayscale (bool): Whether to convert the image to grayscale before OCR.
            log (bool): Whether to log the OCR results.

        Returns:
            list: A list of Box objects representing the detected text regions, sorted by y-coordinate.
                 Returns an empty list if no text is detected or no matches are found.

        Raises:
            Exception: If no image frame is provided.
        """
        if box and isinstance(box, str):
            box = self.get_box_by_name(box)
        if self.executor.paused:
            self.executor.sleep(1)
        frame_height, frame_width = self.executor.frame.shape[0], self.executor.frame.shape[1]
        if threshold == 0:
            threshold = self.ocr_default_threshold
        start = time.time()
        match = self.fix_match_regex(match)
        if frame is not None:
            image = frame
        else:
            image = self.executor.frame
        if image is None:
            raise Exception("ocr no frame")
        else:
            if box is None:
                box = relative_box(frame_width, frame_height, x, y, to_x, to_y, width, height, name)
            if box is not None:
                image = image[box.y:box.y + box.height, box.x:box.x + box.width]
                if not box.name and match:
                    box.name = str(match)
            if use_grayscale:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            image, scale_factor = resize_image(image, frame_height, target_height)
            if frame_processor is not None:
                image = frame_processor(image)
            detected_boxes, ocr_boxes = self.ocr_fun(lib)(box, image, match, scale_factor, threshold, lib)

            communicate.emit_draw_box("ocr" + join_list_elements(name), detected_boxes, "red")
            communicate.emit_draw_box("ocr_zone" + join_list_elements(name), [box] if box else [],
                                      "blue")  # ensure list for drawing

            if log and self.debug:
                self.screenshot('ocr', frame=image, show_box=True, frame_box=box)
            if log:
                level = logger.info
            elif self.log_debug and self.debug:
                level = logger.debug
            else:
                level = None
            if level:
                level(
                    f"ocr_zone {box} found result: {detected_boxes}) time: {(time.time() - start):.2f} scale_factor: {scale_factor:.2f} target_height:{target_height} resized_shape:{image.shape} all_boxes: {ocr_boxes}")
            if level and not detected_boxes and ocr_boxes:
                level(f'ocr detected but no match: {match} {ocr_boxes}')
            return sort_boxes(detected_boxes)

    def ocr_fun(self, lib):
        lib_name = self.executor.config.get('ocr').get(lib).get('lib')
        if lib_name == 'paddleocr':
            return self.paddle_ocr
        elif lib_name == 'dgocr':
            return self.duguang_ocr
        elif lib_name == 'onnxocr':
            return self.onnx_ocr
        else:
            return self.rapid_ocr

    cdef object fix_match_regex(self, match):
        if match and self.executor.ocr_po_translation:
            if not isinstance(match, list):
                match = [match]
            for i in range(len(match)):
                if isinstance(match[i], re.Pattern):
                    original_pattern_object = match[i]
                    original_pattern_string = original_pattern_object.pattern
                    original_flags = original_pattern_object.flags

                    # 2. Translate the ORIGINAL PATTERN STRING
                    translated_pattern_string = self.executor.ocr_po_translation.gettext(original_pattern_string)
                    # logger.debug(f'translate regex {original_pattern_string} {translated_pattern_string}')
                    if isinstance(translated_pattern_string, str):
                        match[i] = re.compile(translated_pattern_string, original_flags)
                    else:
                        logger.warning(
                            f"Warning: Translation failed for pattern: {original_pattern_string} {translated_pattern_string}. Keeping original.")
        return match

    cdef str fix_texts(self, detected_boxes):
        for detected_box in detected_boxes:
            detected_box.name = detected_box.name.strip()
            if self.executor.ocr_po_translation is not None:
                fix = self.executor.ocr_po_translation.gettext(detected_box.name)
                if fix != detected_box.name:
                    detected_box.name = fix
                else:
                    no_space = detected_box.name.replace(" ", "")
                    fix = self.executor.ocr_po_translation.gettext(no_space)
                    if fix != no_space:
                        detected_box.name = fix
            if fix := self.executor.text_fix.get(detected_box.name):
                logger.debug(f'text_fixed {detected_box.name} -> {fix}')
                detected_box.name = fix

    cpdef add_text_fix(self, fix):
        """Adds text fixes to the text_fix dictionary."""
        self.executor.text_fix.update(fix)

    def onnx_ocr(self, object box, object image, match, double scale_factor, double threshold, lib):
        try:
            result = self.executor.ocr_lib(lib).ocr(image)
        except Exception as e:
            logger.error('onnx_ocr', e)
            self.screenshot('onnx_ocr_exception', frame=image)
            raise e
        cdef list detected_boxes = []
        # logger.debug(f'rapid_ocr result {result}')
        # Process the results and create Box objects
        if result[0] is not None:
            for i in range(len(result[0])):
                pos = result[0][i][0]
                text = result[0][i][1][0]
                confidence = result[0][i][1][1]
                width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
                if width <= 0 or height <= 0:
                    logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                    if self.debug:
                        self.screenshot('negative_text', frame=image)
                    continue
                detected_box = self.get_box(box, confidence, height, pos, scale_factor, text, threshold, width)
                # logger.debug(f'rapid_ocr {text} {box} {confidence} {threshold} detected_box {detected_box}')
                if detected_box:
                    detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        self.fix_texts(detected_boxes)
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    def rapid_ocr(self, object box, object image, match, double scale_factor, double threshold, lib):
        try:
            result = self.executor.ocr_lib(lib)(image, use_det=True, use_cls=False, use_rec=True)
        except Exception as e:
            logger.error('rapid_ocr_exception', e)
            self.screenshot('rapid_ocr_exception', frame=image)
            raise e
        cdef list detected_boxes = []
        # logger.debug(f'rapid_ocr result {result}')
        # Process the results and create Box objects
        if result.boxes is not None:
            for i in range(len(result.boxes)):
                pos = result.boxes[i]
                text = result.txts[i]
                confidence = result.scores[i]
                width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
                if width <= 0 or height <= 0:
                    logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                    if self.debug:
                        self.screenshot('negative_text', frame=image)
                    continue
                detected_box = self.get_box(box, confidence, height, pos, scale_factor, text, threshold, width)
                # logger.debug(f'rapid_ocr {text} {box} {confidence} {threshold} detected_box {detected_box}')
                if detected_box:
                    detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        self.fix_texts(detected_boxes)
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    def duguang_ocr(self, object box, object image, match, double scale_factor, double threshold, lib):
        try:
            results = self.executor.ocr_lib(lib).run(image)
        except Exception as e:
            logger.error('duguang_ocr_exception', e)
            self.screenshot('duguang_ocr_exception', frame=image)
            raise e
        cdef list detected_boxes = []
        # logger.debug(f'rapid_ocr result {result}')
        # Process the results and create Box objects
        for result in results:
            pos = result[0]
            text, confidence = result[1]
            width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
            if width <= 0 or height <= 0:
                logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                if self.debug:
                    self.screenshot('negative_text', frame=image)
                continue
            detected_box = self.get_box(box, confidence, height, pos, scale_factor, text, threshold, width)
            # logger.debug(f'rapid_ocr {text} {box} {confidence} {threshold} detected_box {detected_box}')
            if detected_box:
                detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        self.fix_texts(detected_boxes)
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    def paddle_ocr(self, object box, object image, match, double scale_factor, double threshold, lib):
        start = time.time()
        cdef results = self.executor.ocr_lib(lib).predict(image)
        cdef list detected_boxes = []
        # Process the results and create Box objects
        if results:
            result = results[0]

            for idx in range(len(result['rec_texts'])):
                pos = result['rec_boxes'][idx]
                text = result['rec_texts'][idx]
                confidence = result['rec_scores'][idx]

                width, height = round(pos[2] - pos[0]), round(pos[3] - pos[1])
                if width <= 0 or height <= 0:
                    logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                    continue
                if confidence >= threshold:
                    detected_box = Box(pos[0], pos[1], width, height, confidence, text)
                    scale_box(detected_box, scale_factor)
                    if box is not None:
                        detected_box.x += box.x
                        detected_box.y += box.y
                    detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        self.fix_texts(detected_boxes)
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    cdef get_box(self, object box, double confidence, int height, pos, double scale_factor, text, double threshold,
                 int width):
        detected_box = None
        if confidence >= threshold:
            detected_box = Box(pos[0][0], pos[0][1], width, height, confidence, text)
            scale_box(detected_box, scale_factor)
            if box is not None:
                detected_box.x += box.x
                detected_box.y += box.y
        return detected_box

    cpdef wait_click_ocr(self, double x=0, double y=0, double to_x=1, double to_y=1, int width=0, int height=0,
                         box=None, name=None,
                         match=None, double threshold=0, frame=None, int target_height=0, int time_out=0,
                         bint raise_if_not_found=False, recheck_time=0, after_sleep=0, post_action=None, log=False,
                         settle_time=-1, lib="default"):

        result = self.wait_ocr(x, y, width=width, height=height, to_x=to_x, to_y=to_y, box=box, name=name, match=match,
                               threshold=threshold, frame=frame, target_height=target_height, time_out=time_out,
                               raise_if_not_found=raise_if_not_found, post_action=post_action, log=log,
                               settle_time=settle_time, lib=lib)
        if recheck_time > 0:
            self.sleep(1)
            result = self.ocr(x, y, width=width, height=height, to_x=to_x, to_y=to_y, box=box, name=name, match=match,
                              threshold=threshold, frame=frame, target_height=target_height, log=log, lib=lib)
        if result is not None:
            self.click_box(result, after_sleep=after_sleep)
            return result
        else:
            logger.warning(f'wait ocr no box {x} {y} {width} {height} {to_x} {to_y} {match}')

    def wait_ocr(self, double x=0, double y=0, double to_x=1, double to_y=1, int width=0, int height=0, name=None,
                 box=None,
                 match=None, double threshold=0, frame=None, int target_height=0, int time_out=0, post_action=None,
                 bint raise_if_not_found=False, log=False, settle_time=-1, lib="default"):
        boxes = self.wait_until(
            lambda: self.ocr(x, y, to_x=to_x, to_y=to_y, width=width, height=height, box=box, name=name,
                             match=match, threshold=threshold, frame=frame, target_height=target_height, log=log,
                             lib=lib),
            time_out=time_out, post_action=post_action,
            raise_if_not_found=raise_if_not_found, settle_time=settle_time)
        if not boxes and raise_if_not_found:
            logger.error(f'wait_ocr failed, ocr again and log')
            boxes = self.ocr(x, y, to_x=to_x, to_y=to_y, width=width, height=height, box=box, name=name,
                             threshold=threshold, frame=frame, target_height=target_height, log=True, lib=lib)
        return boxes

cdef tuple resize_image(object image, int frame_height, int target_height):
    """Resizes the image if the original height is significantly larger than the target height."""
    cdef double scale_factor = 1.0
    cdef int original_height = image.shape[0]
    cdef int image_height, image_width, new_width, new_height

    if target_height > 0 and frame_height >= 1.5 * target_height:
        image_height, image_width = image.shape[:2]
        scale_factor = target_height / frame_height
        new_width = <int> round(image_width * scale_factor)
        new_height = <int> round(image_height * scale_factor)
        image = cv2.resize(image, (new_width, new_height))
    return image, scale_factor

cdef void scale_box(object box, double scale_factor):
    """Scales the box coordinates by the given scale factor."""
    if scale_factor != 1:
        box.x = <int> round(box.x / scale_factor)
        box.y = <int> round(box.y / scale_factor)
        box.width = <int> round(box.width / scale_factor)
        box.height = <int> round(box.height / scale_factor)

cdef str join_list_elements(input_object):
    """Joins the elements of a list into a single string."""
    if input_object is None:
        return ''
    elif isinstance(input_object, list):
        return ''.join(map(str, input_object))
    else:
        return str(input_object)

## Capture.pyx

# This is an undocumented nFlag value for PrintWindow
PW_CLIENT_ONLY = 1 << 0
cdef int PW_RENDERFULLCONTENT = 0x00000002
PBYTE = ctypes.POINTER(ctypes.c_ubyte)
WGC_NO_BORDER_MIN_BUILD = 20348
WGC_MIN_BUILD = 19041


class CaptureException(Exception):
    pass


cdef class BaseCaptureMethod:
    name = "None"
    description = ""
    cdef public tuple _size
    cdef public object exit_event

    def __init__(self):
        self._size = (0, 0)
        self.exit_event = None

    def close(self):
        # Some capture methods don't need an initialization process
        pass

    @property
    def width(self):
        self.measure_if_0()
        return self._size[0]

    @property
    def height(self):
        return self._size[1]

    def get_name(self):
        return self.name

    def measure_if_0(self):
        if self._size[0] == 0:
            self.get_frame()

    cpdef object get_frame(self):
        cdef object frame
        if self.exit_event.is_set():
            return
        try:
            frame = self.do_get_frame()
            if frame is not None:
                self._size = (frame.shape[1], frame.shape[0])
                if frame.shape[2] == 4:
                    frame = frame[:, :, :3]
            return frame
        except Exception as e:
            raise CaptureException(str(e)) from e

    def __str__(self):
        return f'{self.get_name()}_{self.width}x{self.height}'

    def do_get_frame(self):
        pass

    def draw_rectangle(self):
        pass

    def clickable(self):
        pass

    def connected(self):
        pass

cdef class BaseWindowsCaptureMethod(BaseCaptureMethod):
    cdef public object _hwnd_window

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__()
        self._hwnd_window = hwnd_window

    @property
    def hwnd_window(self):
        return self._hwnd_window

    @hwnd_window.setter
    def hwnd_window(self, hwnd_window):
        self._hwnd_window = hwnd_window

    def connected(self):
        return self._hwnd_window is not None and self._hwnd_window.exists and self._hwnd_window.hwnd > 0

    def get_abs_cords(self, x, y):
        return self._hwnd_window.get_abs_cords(x, y)

    def clickable(self):
        return self._hwnd_window is not None and self._hwnd_window.visible

cdef get_crop_point(int frame_width, int frame_height, int target_width, int target_height):
    cdef int x = round((frame_width - target_width) / 2)
    cdef int y = (frame_height - target_height) - x
    return x, y

cdef class WindowsGraphicsCaptureMethod(BaseWindowsCaptureMethod):
    name = "Windows Graphics Capture"
    description = "fast, most compatible, capped at 60fps"

    cdef object last_frame
    cdef double last_frame_time
    cdef object frame_pool
    cdef object item
    cdef object session
    cdef object cputex
    cdef object rtdevice
    cdef object dxdevice
    cdef object immediatedc
    cdef object evtoken
    cdef object last_size

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__(hwnd_window)
        self.last_frame = None
        self.last_frame_time = time.time()
        self.frame_pool = None
        self.item = None
        self.session = None
        self.cputex = None
        self.rtdevice = None
        self.dxdevice = None
        self.immediatedc = None
        self.start_or_stop()

    cdef frame_arrived_callback(self, x, y):
        cdef object next_frame
        try:
            self.last_frame_time = time.time()
            next_frame = self.frame_pool.TryGetNextFrame()
            if next_frame is not None:
                self.last_frame = self.convert_dx_frame(next_frame)
            else:
                logger.warning('frame_arrived_callback TryGetNextFrame returned None')
        except Exception as e:
            logger.error(f"TryGetNextFrame error {e}")
            self.close()
            return

    cdef object convert_dx_frame(self, frame):
        if not frame:
            # logger.warning('convert_dx_frame self.last_dx_frame is none')
            return None
        cdef bint need_reset_framepool = False
        if frame.ContentSize.Width != self.last_size.Width or frame.ContentSize.Height != self.last_size.Height:
            need_reset_framepool = True
            self.last_size = frame.ContentSize

        if need_reset_framepool:
            logger.info('need_reset_framepool')
            self.reset_framepool(frame.ContentSize)
            return
        cdef bint need_reset_device = False

        cdef object tex = None

        cdef object cputex = None
        cdef object desc = None
        cdef object mapinfo = None
        cdef object img = None
        try:
            from ok.capture.windows import d3d11
            from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import IDirect3DDxgiInterfaceAccess
            from ok.rotypes.roapi import GetActivationFactory
            tex = frame.Surface.astype(IDirect3DDxgiInterfaceAccess).GetInterface(
                d3d11.ID3D11Texture2D.GUID).astype(d3d11.ID3D11Texture2D)
            desc = tex.GetDesc()
            desc2 = d3d11.D3D11_TEXTURE2D_DESC()
            desc2.Width = desc.Width
            desc2.Height = desc.Height
            desc2.MipLevels = desc.MipLevels
            desc2.ArraySize = desc.ArraySize
            desc2.Format = desc.Format
            desc2.SampleDesc = desc.SampleDesc
            desc2.Usage = d3d11.D3D11_USAGE_STAGING
            desc2.CPUAccessFlags = d3d11.D3D11_CPU_ACCESS_READ
            desc2.BindFlags = 0
            desc2.MiscFlags = 0
            cputex = self.dxdevice.CreateTexture2D(ctypes.byref(desc2), None)
            self.immediatedc.CopyResource(cputex, tex)
            mapinfo = self.immediatedc.Map(cputex, 0, d3d11.D3D11_MAP_READ, 0)
            img = np.ctypeslib.as_array(ctypes.cast(mapinfo.pData, PBYTE),
                                        (desc.Height, mapinfo.RowPitch // 4, 4))[
                  :, :desc.Width].copy()
            self.immediatedc.Unmap(cputex, 0)
            # logger.debug(f'frame latency {(time.time() - start):.3f} {(time.time() - dx_time):.3f}')
            return img
        except OSError as e:
            if e.winerror == d3d11.DXGI_ERROR_DEVICE_REMOVED or e.winerror == d3d11.DXGI_ERROR_DEVICE_RESET:
                need_reset_framepool = True
                need_reset_device = True
                logger.error('convert_dx_frame win error', e)
            else:
                raise e
        finally:
            if tex is not None:
                tex.Release()
            if cputex is not None:
                cputex.Release()
        if need_reset_framepool:
            self.reset_framepool(frame.ContentSize, need_reset_device)
            return self.get_frame()

    @property
    def hwnd_window(self):
        return self._hwnd_window

    @hwnd_window.setter
    def hwnd_window(self, hwnd_window):
        self._hwnd_window = hwnd_window
        self.start_or_stop()

    def connected(self):
        return self.hwnd_window is not None and self.hwnd_window.exists and self.frame_pool is not None

    def start_or_stop(self, capture_cursor=False):
        if self.hwnd_window.hwnd and self.hwnd_window.exists and self.frame_pool is None:
            try:
                from ok.capture.windows import d3d11
                from ok.rotypes import IInspectable
                from ok.rotypes.Windows.Foundation import TypedEventHandler
                from ok.rotypes.Windows.Graphics.Capture import Direct3D11CaptureFramePool, IGraphicsCaptureItemInterop, \
                    IGraphicsCaptureItem, GraphicsCaptureItem
                from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
                from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import IDirect3DDevice, \
                    CreateDirect3D11DeviceFromDXGIDevice, \
                    IDirect3DDxgiInterfaceAccess
                from ok.rotypes.roapi import GetActivationFactory
                logger.info('init windows capture')
                interop = GetActivationFactory('Windows.Graphics.Capture.GraphicsCaptureItem').astype(
                    IGraphicsCaptureItemInterop)
                self.rtdevice = IDirect3DDevice()
                self.dxdevice = d3d11.ID3D11Device()
                self.immediatedc = d3d11.ID3D11DeviceContext()
                self.create_device()
                item = interop.CreateForWindow(self.hwnd_window.hwnd, IGraphicsCaptureItem.GUID)
                self.item = item
                self.last_size = item.Size
                delegate = TypedEventHandler(GraphicsCaptureItem, IInspectable).delegate(
                    self.close)
                self.evtoken = item.add_Closed(delegate)
                self.frame_pool = Direct3D11CaptureFramePool.CreateFreeThreaded(self.rtdevice,
                                                                                DirectXPixelFormat.B8G8R8A8UIntNormalized,
                                                                                1, item.Size)
                self.session = self.frame_pool.CreateCaptureSession(item)
                pool = self.frame_pool
                pool.add_FrameArrived(
                    TypedEventHandler(Direct3D11CaptureFramePool, IInspectable).delegate(
                        self.frame_arrived_callback))
                self.session.IsCursorCaptureEnabled = capture_cursor
                if WINDOWS_BUILD_NUMBER >= WGC_NO_BORDER_MIN_BUILD:
                    self.session.IsBorderRequired = False
                self.session.StartCapture()
                return True
            except Exception as e:
                logger.error(f'start_or_stop failed: {self.hwnd_window}', exception=e)
                return False
        elif not self.hwnd_window.exists and self.frame_pool is not None:
            self.close()
            return False
        return self.hwnd_window.exists

    def create_device(self):
        from ok.capture.windows import d3d11
        from ok.rotypes.Windows.Graphics.DirectX.Direct3D11 import CreateDirect3D11DeviceFromDXGIDevice
        d3d11.D3D11CreateDevice(
            None,
            d3d11.D3D_DRIVER_TYPE_HARDWARE,
            None,
            d3d11.D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            None,
            0,
            d3d11.D3D11_SDK_VERSION,
            ctypes.byref(self.dxdevice),
            None,
            ctypes.byref(self.immediatedc)
        )
        self.rtdevice = CreateDirect3D11DeviceFromDXGIDevice(self.dxdevice)
        self.evtoken = None

    def close(self):
        logger.info('destroy windows capture')
        if self.frame_pool is not None:
            self.frame_pool.Close()
            self.frame_pool = None
        if self.session is not None:
            self.session.Close()  # E_UNEXPECTED ???
            self.session = None
        self.item = None
        if self.rtdevice:
            self.rtdevice.Release()
        if self.dxdevice:
            self.dxdevice.Release()
        if self.cputex:
            self.cputex.Release()

    cpdef object do_get_frame(self):
        cdef object frame
        cdef double latency, now, start_wait
        if self.start_or_stop():
            frame = self.last_frame
            if frame is None:
                now = time.time()
                if now - self.last_frame_time > 10:
                    logger.warning('no frame for 10 sec, try to restart')
                    self.close()
                    self.last_frame_time = time.time()
                    return self.do_get_frame()
                start_wait = now
                while self.last_frame is None and (time.time() - start_wait) < 1.0:
                    if self.frame_pool is None:
                        return None
                    time.sleep(0.003)
                frame = self.last_frame
            if frame is None:
                return None
            self.last_frame = None
            latency = time.time() - self.last_frame_time
            if latency > 2:
                logger.warning(f"latency too large return None frame: {latency}")
                return None
            frame = self.crop_image(frame)
            if frame is not None:
                new_height, new_width = frame.shape[:2]
                if new_width <= 0 or new_height <= 0:
                    logger.warning(f"get_frame size <=0 {new_width}x{new_height}")
                    return None

            return frame

    def reset_framepool(self, size, reset_device=False):
        logger.info(f'reset_framepool')
        from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat
        if reset_device:
            self.create_device()
        self.frame_pool.Recreate(self.rtdevice,
                                 DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, size)

    def crop_image(self, frame):
        if frame is not None:
            x, y = get_crop_point(frame.shape[1], frame.shape[0], self.hwnd_window.width, self.hwnd_window.height)
            if x > 0 or y > 0:
                frame = self.crop_image_border_title(frame, x, y)
        return frame

    def crop_image_border_title(self, image, border, title_height):
        # Load the image
        # Image dimensions
        height, width = image.shape[:2]

        # Calculate the coordinates for the bottom-right corner
        x2 = width - border
        y2 = height - border

        # Crop the image
        cropped_image = image[title_height:y2, border:x2]

        # print(f"cropped image: {title_height}-{y2}, {border}-{x2} {cropped_image.shape}")
        #
        # cv2.imshow('Image Window', cropped_image)
        #
        # # Wait for any key to be pressed before closing the window
        # cv2.waitKey(0)

        return cropped_image

WINDOWS_BUILD_NUMBER = int(platform.version().split(".")[-1]) if sys.platform == "win32" else -1

def windows_graphics_available():
    logger.info(
        f"check available WINDOWS_BUILD_NUMBER:{WINDOWS_BUILD_NUMBER} >= {WGC_MIN_BUILD} {WINDOWS_BUILD_NUMBER >= WGC_MIN_BUILD}")
    if WINDOWS_BUILD_NUMBER >= WGC_MIN_BUILD:
        try:
            from ok.rotypes import idldsl
            from ok.rotypes.roapi import GetActivationFactory
            from ok.rotypes.Windows.Graphics.Capture import IGraphicsCaptureItemInterop
            GetActivationFactory('Windows.Graphics.Capture.GraphicsCaptureItem').astype(
                IGraphicsCaptureItemInterop)
            return True
        except Exception as e:
            logger.error(f'check available failed: {e}', exception=e)
            return False

cdef is_blank(image):
    """
    BitBlt can return a balnk buffer. Either because the target is unsupported,
    or because there's two windows of the same name for the same executable.
    """
    return not image.any()

cdef bint render_full
render_full = False

cdef class BitBltCaptureMethod(BaseWindowsCaptureMethod):
    name = "BitBlt"
    short_description = "fastest, least compatible"
    description = (
            "\nThe best option when compatible. But it cannot properly record "
            + "\nOpenGL, Hardware Accelerated or Exclusive Fullscreen windows. "
            + "\nThe smaller the selected region, the more efficient it is. "
    )

    cdef object dc_object, bitmap, window_dc, compatible_dc
    cdef int last_hwnd, last_width, last_height

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__(hwnd_window)
        self.dc_object = None
        self.bitmap = None
        self.window_dc = None
        self.compatible_dc = None
        self.last_hwnd = 0
        self.last_width = 0
        self.last_height = 0

    cpdef object do_get_frame(self):
        cdef int x, y
        if self.hwnd_window.real_x_offset != 0 or self.hwnd_window.real_y_offset != 0:
            x = self.hwnd_window.real_x_offset
            y = self.hwnd_window.real_y_offset
        else:
            x, y = get_crop_point(self.hwnd_window.window_width, self.hwnd_window.window_height,
                                  self.hwnd_window.width, self.hwnd_window.height)
        return self.bit_blt_capture_frame(x,
                                          y,
                                          render_full)

    def get_name(self):
        return f'BitBlt_{render_full}'

    def test_exclusive_full_screen(self):
        frame = self.do_get_frame()
        if frame is None:
            logger.error(f'Failed to test_exclusive_full_screen {self.hwnd_window}')
            return False
        return True

    def test_is_not_pure_color(self):
        frame = self.do_get_frame()
        if frame is None:
            logger.error(f'Failed to test_is_not_pure_color frame is None {self.hwnd_window}')
            return False
        else:
            if is_close_to_pure_color(frame):
                logger.error(f'Failed to test_is_not_pure_color failed {self.hwnd_window}')
                return False
            else:
                return True

    cdef object bit_blt_capture_frame(self, int border, int title_height,
                                      bint _render_full_content=False):
        cdef int hwnd = self.hwnd_window.hwnd
        if hwnd <= 0:
            return None

        cdef int width = self.hwnd_window.real_width or self.hwnd_window.width
        cdef int height = self.hwnd_window.real_height or self.hwnd_window.height

        if width <= 0 or height <= 0:
            return None
        cdef object image
        image = None

        cdef int x, y
        x = border
        y = title_height

        try:
            if self.last_hwnd != hwnd or self.last_height != height or self.last_width != width:
                if self.last_hwnd > 0:
                    try_delete_dc(self.dc_object)
                    try_delete_dc(self.compatible_dc)
                    win32gui.ReleaseDC(hwnd, self.window_dc)
                    win32gui.DeleteObject(self.bitmap.GetHandle())
                self.window_dc = win32gui.GetWindowDC(hwnd)
                self.dc_object = win32ui.CreateDCFromHandle(self.window_dc)
                self.compatible_dc = self.dc_object.CreateCompatibleDC()
                self.bitmap = win32ui.CreateBitmap()
                self.bitmap.CreateCompatibleBitmap(self.dc_object, width, height)
                self.last_hwnd = hwnd
                self.last_width = width
                self.last_height = height

            # Causes a 10-15x performance drop. But allows recording hardware accelerated windows
            if _render_full_content:
                ctypes.windll.user32.PrintWindow(hwnd, self.dc_object.GetSafeHdc(), PW_RENDERFULLCONTENT)

            # On Windows there is a shadow around the windows that we need to account for.
            # left_bounds, top_bounds = 3, 0

            self.compatible_dc.SelectObject(self.bitmap)
            self.compatible_dc.BitBlt(
                (0, 0),
                (width, height),
                self.dc_object,
                (x, y),
                win32con.SRCCOPY,
            )
            image = np.frombuffer(self.bitmap.GetBitmapBits(True), dtype=np.uint8)
        except:
            # Invalid handle or the window was closed while it was being manipulated
            return None

        if is_blank(image):
            image = None
        else:
            image.shape = (height, width, BGRA_CHANNEL_COUNT)

        # Cleanup DC and handle
        return image

cdef class HwndWindow:
    cdef public object app_exit_event, stop_event, mute_option, thread, device_manager, global_config
    cdef public str title, exe_full_path, hwnd_class, _hwnd_title
    cdef public int hwnd, player_id, window_width, window_height, x, y, width, height, frame_width, frame_height, real_width, real_height, real_x_offset, real_y_offset
    cdef public bint visible, exists, pos_valid, to_handle_mute
    cdef public double scaling, frame_aspect_ratio
    cdef public list monitors_bounds, exe_names
    cdef public list visible_monitors

    def __init__(self, exit_event, title, exe_name=None, frame_width=0, frame_height=0, player_id=-1, hwnd_class=None,
                 global_config=None, device_manager=None):
        super().__init__()
        logger.info(f'HwndWindow init title:{title} player_id:{player_id} exe_name:{exe_name} hwnd_class:{hwnd_class}')
        self.app_exit_event = exit_event
        self.exe_names = None
        self.visible_monitors = []
        self.device_manager = device_manager
        self.to_handle_mute = True
        self.title = title
        self.stop_event = threading.Event()
        self.visible = False
        self.player_id = player_id
        self.window_width = 0
        self.window_height = 0
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.hwnd = 0
        self.frame_width = 0
        self.frame_height = 0
        self.exists = False
        self.title = None
        self.exe_full_path = None
        self.real_width = 0
        self.real_height = 0
        self.real_x_offset = 0
        self.real_y_offset = 0
        self.scaling = 1.0
        self.frame_aspect_ratio = 0
        self.hwnd_class = hwnd_class
        self.pos_valid = False
        self._hwnd_title = ""
        self.monitors_bounds = get_monitors_bounds()
        self.mute_option = global_config.get_config(basic_options)
        self.global_config = global_config
        self.mute_option.validator = self.validate_mute_config
        self.update_window(title, exe_name, frame_width, frame_height, player_id, hwnd_class)
        self.thread = threading.Thread(target=self.update_window_size, name="update_window_size")
        self.thread.start()

    def validate_mute_config(self, key, value):
        if key == 'Mute Game while in Background' and self.hwnd:
            logger.info(f'validate_mute_config {value}')
            if value:
                self.handle_mute(value)
            else:
                logger.info(f'config changed unmute set_mute_state {value}')
                set_mute_state(self.hwnd, 0)
        return True, None

    def stop(self):
        self.stop_event.set()

    def bring_to_front(self):
        if self.hwnd:
            win32gui.SetForegroundWindow(self.hwnd)

    def try_resize_to(self, resize_to):
        if not self.global_config.get_config('Basic Options').get('Auto Resize Game Window'):
            return False
        if self.hwnd and self.window_width > 0:
            show_title_bar(self.hwnd)
            screen_width = win32api.GetSystemMetrics(0)
            screen_height = win32api.GetSystemMetrics(1)
            x, y, window_width, window_height, width, height, scaling = get_window_bounds(self.hwnd)
            title_height = window_height - height
            logger.info(f'try_resize_to {x, y, window_width, window_height, width, height, scaling} ')
            border = window_width - width
            resize_width = 0
            resize_height = 0
            for resolution in resize_to:
                if screen_width >= border + resolution[0] and screen_height >= title_height + resolution[
                    1]:
                    resize_width = resolution[0] + border
                    resize_height = resolution[1] + title_height
                    break
            if resize_width > 0:
                resize_window(self.hwnd, resize_width, resize_height)
                self.do_update_window_size()
                if self.window_height == resize_height and self.window_width == resize_width:
                    logger.info(f'resize hwnd success to {self.width}x{self.height}')
                    return True
                else:
                    logger.error(f'resize hwnd failed: {self.width}x{self.height}')

    def update_window(self, title, exe_name, frame_width, frame_height, player_id=-1, hwnd_class=None):
        self.player_id = player_id
        self.title = title
        if isinstance(exe_name, str):
            self.exe_names = [exe_name]
        else:
            self.exe_names = exe_name
        self.update_frame_size(frame_width, frame_height)
        self.hwnd_class = hwnd_class

    def update_frame_size(self, width, height):
        logger.debug(f"update_frame_size:{self.frame_width}x{self.frame_height} to {width}x{height}")
        if width != self.frame_width or height != self.frame_height:
            self.frame_width = width
            self.frame_height = height
            if width > 0 and height > 0:
                self.frame_aspect_ratio = width / height
                logger.debug(f"HwndWindow: frame ratio: width: {width}, height: {height}")
        self.hwnd = 0
        self.do_update_window_size()

    def update_window_size(self):
        while not self.app_exit_event.is_set() and not self.stop_event.is_set():
            self.do_update_window_size()
            time.sleep(0.2)
        if self.hwnd and self.mute_option.get('Mute Game while in Background'):
            logger.info(f'exit reset mute state to 0')
            set_mute_state(self.hwnd, 0)

    def get_abs_cords(self, x, y):
        return self.x + x, self.y + y

    def do_update_window_size(self):
        try:
            changed = False
            visible, x, y, window_width, window_height, width, height, scaling = self.visible, self.x, self.y, self.window_width, self.window_height, self.width, self.height, self.scaling
            if self.hwnd == 0:
                name, self.hwnd, self.exe_full_path, self.real_x_offset, self.real_y_offset, self.real_width, self.real_height = find_hwnd(
                    self.title,
                    self.exe_names or self.device_manager.config.get('selected_exe'),
                    self.frame_width, self.frame_height, player_id=self.player_id, class_name=self.hwnd_class,
                    selected_hwnd=self.device_manager.config.get('selected_hwnd'))
                if self.hwnd > 0:
                    logger.info(
                        f'do_update_window_size find_hwnd {self.hwnd} {self.exe_full_path} {win32gui.GetClassName(self.hwnd)} real:{self.real_x_offset},{self.real_y_offset},{self.real_width},{self.real_height}')
                    changed = True
                self.exists = self.hwnd > 0
            if self.hwnd > 0:
                self.exists = win32gui.IsWindow(self.hwnd)
                if self.exists:
                    visible = self.is_foreground()
                    x, y, window_width, window_height, width, height, scaling = get_window_bounds(
                        self.hwnd)
                    if self.frame_aspect_ratio != 0 and height != 0:
                        window_ratio = width / height
                        if window_ratio < self.frame_aspect_ratio:
                            cropped_window_height = int(width / self.frame_aspect_ratio)
                            height = cropped_window_height
                    pos_valid = check_pos(x, y, width, height, self.monitors_bounds)
                    if isinstance(self.device_manager.capture_method,
                                  BaseWindowsCaptureMethod) and not pos_valid and pos_valid != self.pos_valid and self.device_manager.executor is not None:
                        if self.device_manager.executor.pause():
                            logger.error(f'og.executor.pause pos_invalid: {x, y, width, height}')
                            communicate.notification.emit('Paused because game window is minimized or out of screen!',
                                                          None,
                                                          True, True, "start")
                    if pos_valid != self.pos_valid:
                        self.pos_valid = pos_valid
                else:
                    if self.device_manager.executor is not None and self.device_manager.executor.pause():
                        if self.global_config.get_config('Basic Options').get('Exit App when Game Exits'):
                            alert_info('Auto exit because game exited', True)
                            communicate.quit.emit()
                        else:
                            communicate.notification.emit('Paused because game exited', None, True, True, "start")
                    self.hwnd = 0
                if visible != self.visible:
                    self.visible = visible
                    for visible_monitor in self.visible_monitors:
                        visible_monitor.on_visible(visible)
                    changed = True
                if changed:
                    self.handle_mute()
                if (window_width != self.window_width or window_height != self.window_height or
                    x != self.x or y != self.y or width != self.width or height != self.height or scaling != self.scaling) and (
                        (x >= -1 and y >= -1) or self.visible):
                    self.x, self.y, self.window_width, self.window_height, self.width, self.height, self.scaling = x, y, window_width, window_height, width, height, scaling
                    changed = True
                if changed:
                    logger.info(
                        f"do_update_window_size changed,visible:{self.visible} x:{self.x} y:{self.y} window:{self.width}x{self.height} self.window:{self.window_width}x{self.window_height} real:{self.real_width}x{self.real_height}")
                    communicate.window.emit(self.visible, self.x + self.real_x_offset, self.y + self.real_y_offset,
                                            self.window_width, self.window_height,
                                            self.width,
                                            self.height, self.scaling)
        except Exception as e:
            logger.error(f"do_update_window_size exception", e)

    def is_foreground(self):
        return is_foreground_window(self.hwnd)

    def handle_mute(self, mute=None):
        if mute is None:
            mute = self.mute_option.get('Mute Game while in Background')
        logger.info(
            f'handle_mute hwnd:{self.hwnd} mute:{mute} self.to_handle_mute:{self.to_handle_mute} visible:{self.visible}')
        if self.hwnd and self.to_handle_mute and mute:
            set_mute_state(self.hwnd, 0 if self.visible else 1)

    def frame_ratio(self, size):
        if self.frame_width > 0 and self.width > 0:
            return int(size / self.frame_width * self.width)
        else:
            return size

    @property
    def hwnd_title(self):
        if not self._hwnd_title:
            if self.hwnd:
                self._hwnd_title = win32gui.GetWindowText(self.hwnd)
        return self._hwnd_title

    def __str__(self) -> str:
        return str(
            f"title_{self.title}_{self.exe_names}_{self.width}x{self.height}_{self.hwnd}_{self.exists}_{self.visible}")

def check_pos(x, y, width, height, monitors_bounds):
    return width >= 0 and height >= 0 and is_window_in_screen_bounds(x, y, width, height, monitors_bounds)

def get_monitors_bounds():
    monitors_bounds = []
    monitors = win32api.EnumDisplayMonitors()
    for monitor in monitors:
        monitor_info = win32api.GetMonitorInfo(monitor[0])
        monitor_rect = monitor_info['Monitor']
        monitors_bounds.append(monitor_rect)
    return monitors_bounds

def is_window_in_screen_bounds(window_left, window_top, window_width, window_height, monitors_bounds):
    window_right, window_bottom = window_left + window_width, window_top + window_height

    for monitor_rect in monitors_bounds:
        monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_rect

        # Check if the window is within the monitor bounds
        if (window_left >= monitor_left and window_top >= monitor_top and
                window_right <= monitor_right and window_bottom <= monitor_bottom):
            return True

    return False

def find_hwnd(title, exe_names, frame_width, frame_height, player_id=-1, class_name=None,
              selected_hwnd=0):
    if exe_names is None and title is None:
        return None, 0, None, 0, 0, 0, 0
    frame_aspect_ratio = frame_width / frame_height if frame_height != 0 else 0

    def callback(hwnd, results):
        if selected_hwnd > 0:
            if selected_hwnd != selected_hwnd:
                return True
        if win32gui.IsWindow(hwnd) and win32gui.IsWindowEnabled(hwnd) and win32gui.IsWindowVisible(hwnd):
            text = None
            if title:
                text = win32gui.GetWindowText(hwnd)
                if isinstance(title, str):
                    if title != text:
                        return True
                elif not re.search(title, text):
                    return True
            name, full_path, cmdline = get_exe_by_hwnd(hwnd)
            # logger.debug(f'find_hwnd {name, full_path, cmdline} exe_names:{exe_names}')
            if not name:
                return True
            if exe_names:
                match = False
                for exe_name in exe_names:
                    if compare_path_safe(name, exe_name) or compare_path_safe(exe_name, full_path):
                        match = True
                if not match:
                    return True
            if player_id != -1:
                if player_id != get_player_id_from_cmdline(cmdline):
                    logger.warning(
                        f'player id check failed,cmdline {cmdline} {get_player_id_from_cmdline(cmdline)} != {player_id}')
                    return True
                else:
                    logger.info(f'player id check success')
            if class_name is not None:
                if win32gui.GetClassName(hwnd) != class_name:
                    return True
            if text is None:
                text = win32gui.GetWindowText(hwnd)
            x, y, _, _, width, height, scaling = get_window_bounds(
                hwnd)
            ret = (hwnd, full_path, width, height, x, y, text)
            results.append(ret)
        return True

    results = []
    win32gui.EnumWindows(callback, results)

    if len(results) > 0:
        logger.info(f'find_hwnd results {len(results)} {results}')
        biggest = None
        for result in results:
            if biggest is None or (result[2] * result[3]) > biggest[2] * biggest[3]:
                biggest = result
        x_offset = 0
        y_offset = 0
        real_width = 0
        real_height = 0
        if frame_aspect_ratio != 0:
            real_width, real_height = biggest[2], biggest[3]
            matching_child = enum_child_windows(biggest, frame_aspect_ratio)
            if matching_child is not None:
                x_offset, y_offset, real_width, real_height = matching_child
            logger.info(
                f'find_hwnd {frame_width, frame_height} {biggest} {x_offset, y_offset, real_width, real_height}')
        return biggest[6], biggest[0], biggest[1], x_offset, y_offset, real_width, real_height

    return None, 0, None, 0, 0, 0, 0

def get_mute_state(hwnd):
    from pycaw.api.audioclient import ISimpleAudioVolume
    from pycaw.utils import AudioUtilities
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        if session.Process and session.Process.pid == pid:
            volume = session._ctl.QueryInterface(ISimpleAudioVolume)
            return volume.GetMute()
    return 0

# Function to get the mute state
def set_mute_state(hwnd, mute):
    from pycaw.api.audioclient import ISimpleAudioVolume
    from pycaw.utils import AudioUtilities
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        if session.Process and session.Process.pid == pid:
            volume = session._ctl.QueryInterface(ISimpleAudioVolume)
            volume.SetMute(mute, None)  # 0 to unmute, 1 to mute
            break

def get_player_id_from_cmdline(cmdline):
    for i in range(len(cmdline)):
        if i != 0:
            if cmdline[i].isdigit():
                return int(cmdline[i])
    for i in range(len(cmdline)):
        if i != 0:
            value = re.search(r'index=(\d+)', cmdline[i])
            # Return the value if it exists, otherwise return None
            if value is not None:
                return int(value.group(1))
    return 0

def enum_child_windows(biggest, frame_aspect_ratio):
    ratio_match = []

    def child_callback(hwnd, _):
        visible = win32gui.IsWindowVisible(hwnd)
        parent = win32gui.GetParent(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        parent_rect = win32gui.GetWindowRect(parent)
        real_width = rect[2] - rect[0]
        real_height = rect[3] - rect[1]
        logger.info(f'find_hwnd child_callback {visible} {biggest[0]} {parent_rect} {rect} {real_width} {real_height}')
        if visible:
            ratio = real_width / real_height
            difference = abs(ratio - frame_aspect_ratio)
            support = difference <= 0.01 * frame_aspect_ratio
            percent = (real_width * real_height) / (biggest[2] * biggest[3])
            if support and percent >= 0.7:
                x_offset = rect[0] - biggest[4]
                y_offset = rect[1] - biggest[5]
                ratio_match.append((difference, (x_offset, y_offset, real_width, real_height)))
        return True

    win32gui.EnumChildWindows(biggest[0], child_callback, None)

    if len(ratio_match) > 0:
        ratio_match.sort(key=lambda x: x[0])  # Sort by the difference in aspect ratio
        logger.debug(f'ratio_match sorted {ratio_match}')
        return ratio_match[0][1]  # Return the window with the closest ratio

    return None

def get_exe_by_hwnd(hwnd):
    # Get the process ID associated with the window
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        # Get the process name and executable path
        if pid > 0:
            process = psutil.Process(pid)
            return process.name(), process.exe(), process.cmdline()
        else:
            return None, None, None
    except Exception as e:
        logger.error('get_exe_by_hwnd error', e)
        return None, None, None

# orignal https://github.com/Toufool/AutoSplit/blob/master/src/capture_method/DesktopDuplicationCaptureMethod.py
cdef class DesktopDuplicationCaptureMethod(BaseWindowsCaptureMethod):
    name = "Direct3D Desktop Duplication"
    short_description = "slower, bound to display"
    description = (
            "\nDuplicates the desktop using Direct3D. "
            + "\nIt can record OpenGL and Hardware Accelerated windows. "
            + "\nAbout 10-15x slower than BitBlt. Not affected by window size. "
            + "\nOverlapping windows will show up and can't record across displays. "
            + "\nThis option may not be available for hybrid GPU laptops, "
            + "\nsee D3DDD-Note-Laptops.md for a solution. "
    )
    cdef object desktop_duplication

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__(hwnd_window)
        import d3dshot
        self.desktop_duplication = d3dshot.create(capture_output="numpy")

    cpdef object do_get_frame(self):

        hwnd = self.hwnd_window.hwnd
        if hwnd == 0:
            return None

        hmonitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        if not hmonitor:
            return None

        self.desktop_duplication.display = find_display(hmonitor, self.desktop_duplication.displays)

        cdef int left, top, right, bottom
        cdef object screenshot
        left = self.hwnd_window.x
        top = self.hwnd_window.y
        right = left + self.hwnd_window.width
        bottom = top + self.hwnd_window.height
        screenshot = self.desktop_duplication.screenshot((left, top, right, bottom))
        if screenshot is None:
            return None
        return cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)

    def close(self):
        if self.desktop_duplication is not None:
            self.desktop_duplication.stop()

cdef find_display(hmonitor, displays):
    for display in displays:
        if display.hmonitor == hmonitor:
            return display
    raise ValueError("Display not found")

DWMWA_EXTENDED_FRAME_BOUNDS = 9
MAXBYTE = 255
"""How many channels in a BGR image"""
cdef int BGRA_CHANNEL_COUNT
BGRA_CHANNEL_COUNT = 4
"""How many channels in a BGRA image"""


class ImageShape(IntEnum):
    Y = 0
    X = 1
    Channels = 2


class ColorChannel(IntEnum):
    Blue = 0
    Green = 1
    Red = 2
    Alpha = 3


def decimal(value: float):
    # Using ljust instead of :2f because of python float rounding errors
    return f"{int(value * 100) / 100}".ljust(4, "0")

def is_digit(value: str | int | None):
    """Checks if `value` is a single-digit string from 0-9."""
    if value is None:
        return False
    try:
        return 0 <= int(value) <= 9  # noqa: PLR2004
    except (ValueError, TypeError):
        return False

def is_valid_hwnd(hwnd: int):
    """Validate the hwnd points to a valid window and not the desktop or whatever window obtained with `""`."""
    if not hwnd:
        return False
    if sys.platform == "win32":
        return bool(win32gui.IsWindow(hwnd) and win32gui.GetWindowText(hwnd))
    return True

cdef try_delete_dc(dc):
    if dc is not None:
        try:
            dc.DeleteDC()
            return True
        except win32ui.error:
            pass

cdef class ADBCaptureMethod(BaseCaptureMethod):
    name = "ADB command line Capture"
    description = "use the adb screencap command, slow but works when in background/minimized, takes 300ms per frame"
    cdef bint _connected
    cdef object device_manager

    def __init__(self, device_manager, exit_event, width=0, height=0):
        super().__init__()
        self.exit_event = exit_event
        self._connected = (width != 0 and height != 0)
        self.device_manager = device_manager

    cpdef object do_get_frame(self):
        return self.screencap()

    cdef object screencap(self):
        if self.exit_event.is_set():
            return None
        cdef object frame
        frame = self.device_manager.do_screencap(self.device_manager.device)
        if frame is not None:
            self._connected = True
        else:
            self._connected = False
        return frame

    def connected(self):
        if not self._connected and self.device_manager.device is not None:
            self.screencap()
        return self._connected and self.device_manager.device is not None

cdef class ImageCaptureMethod(BaseCaptureMethod):
    name = "Image capture method "
    description = "for debugging"
    cdef list images
    cdef int index

    def __init__(self, exit_event, images):
        super().__init__()
        self.exit_event = exit_event
        self.set_images(images)
        self.index = 0

    def set_images(self, images):
        self.images = list(reversed(images))
        self.index = 0
        self.get_frame()  # fill size

    def get_abs_cords(self, x, y):
        return x, y

    cpdef object do_get_frame(self):
        cdef str image_path
        if len(self.images) > 0:
            image_path = self.images[self.index]
            if image_path:
                frame = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                # Update index for next call
                if self.index < len(self.images) - 1:
                    self.index += 1
                return frame

    def connected(self):
        return True


class DeviceManager:

    def __init__(self, app_config, exit_event=None, global_config=None):
        logger.info('__init__ start')
        self._device = None
        self._adb = None
        self.executor = None
        self.capture_method = None
        self.global_config = global_config
        self._adb_lock = threading.Lock()
        if app_config.get('adb'):
            self.packages = app_config.get('adb').get('packages')
        else:
            self.packages = None
        supported_resolution = app_config.get(
            'supported_resolution', {})
        self.supported_ratio = parse_ratio(supported_resolution.get('ratio'))
        self.windows_capture_config = app_config.get('windows')
        self.adb_capture_config = app_config.get('adb')
        self.debug = app_config.get('debug')
        self.interaction = None
        self.device_dict = {}
        self.exit_event = exit_event
        self.resolution_dict = {}
        default_capture = 'windows' if app_config.get('windows') else 'adb'
        self.config = Config("devices",
                             {"preferred": "", "pc_full_path": "", 'capture': default_capture, 'selected_exe': '',
                              'selected_hwnd': 0})
        self.handler = Handler(exit_event, 'RefreshAdb')
        if self.windows_capture_config is not None:
            if isinstance(self.windows_capture_config.get('exe'), str):
                self.windows_capture_config['exe'] = [self.windows_capture_config.get('exe')]

            self.hwnd_window = HwndWindow(exit_event, self.windows_capture_config.get('title'),
                                          self.windows_capture_config.get('exe'),
                                          hwnd_class=self.windows_capture_config.get('hwnd_class'),
                                          global_config=self.global_config, device_manager=self)
            if self.windows_capture_config.get(
                    'interaction') == 'PostMessage':
                self.win_interaction_class = PostMessageInteraction
            elif self.windows_capture_config.get(
                    'interaction') == 'Genshin':
                self.win_interaction_class = GenshinInteraction
            elif self.windows_capture_config.get(
                    'interaction') == 'ForegroundPostMessage':
                self.win_interaction_class = ForegroundPostMessageInteraction
            elif self.windows_capture_config.get(
                    'interaction') == 'Pynput':
                self.win_interaction_class = PynputInteraction
            elif self.windows_capture_config.get(
                    'interaction') and self.windows_capture_config.get(
                'interaction') != 'PyDirect':
                self.win_interaction_class = self.windows_capture_config.get(
                    'interaction')
            else:
                self.win_interaction_class = PyDirectInteraction
        else:
            self.hwnd_window = None

        logger.info('__init__ end')

    def stop_hwnd(self):
        if self.hwnd_window:
            logger.info(f'stop_hwnd {self.hwnd_window.exe_full_path}')
            if self.hwnd_window.exe_full_path:
                kill_exe(abs_path=self.hwnd_window.exe_full_path)

    def select_hwnd(self, exe, hwnd):
        self.config['selected_exe'] = exe
        self.config['selected_hwnd'] = hwnd

    def refresh(self):
        logger.debug('calling refresh')
        self.handler.post(self.do_refresh, remove_existing=True, skip_if_running=True)

    @property
    def adb(self):
        with self._adb_lock:
            if self._adb is None:
                import adbutils
                logger.debug(f'init adb')
                from adbutils._utils import _get_bin_dir
                bin_dir = _get_bin_dir()
                exe = os.path.join(bin_dir, "adb.exe" if os.name == 'nt' else 'adb')
                from adbutils._utils import _is_valid_exe
                if os.path.isfile(exe) and _is_valid_exe(exe):
                    os.environ['ADBUTILS_ADB_PATH'] = exe
                    logger.info(f'set ADBUTILS_ADB_PATH {os.getenv("ADBUTILS_ADB_PATH")}')
                else:
                    logger.error(f'set ADBUTILS_ADB_PATH failed {exe}')
                self._adb = adbutils.AdbClient(host="127.0.0.1", socket_timeout=4)
                from adbutils import AdbError
                try:
                    self._adb.device_list()
                except AdbError as e:
                    self.try_kill_adb(e)
            return self._adb

    def try_kill_adb(self, e=None):
        logger.error('try kill adb server', e)
        import psutil
        for proc in psutil.process_iter():
            # Check whether the process name matches
            if proc.name() == 'adb.exe' or proc.name() == 'adb':
                logger.info(f'kill adb by process name {proc.cmdline()}')
                try:
                    proc.kill()
                except Exception as e:
                    logger.error(f'kill adb server failed', e)
        logger.info('try kill adb end')

    def adb_connect(self, addr, try_connect=True):
        from adbutils import AdbError
        try:
            for device in self.adb.list():
                if self.exit_event.is_set():
                    logger.error(f"adb_connect exit_event is set")
                    return None
                if device.serial == addr:
                    if device.state == 'offline':
                        logger.info(f'adb_connect offline disconnect first {addr}')
                        self.adb.disconnect(addr)
                    else:
                        logger.info(f'adb_connect already connected {addr}')
                        return self.adb.device(serial=addr)
            if try_connect:
                ret = self.adb.connect(addr, timeout=5)
                logger.info(f'adb_connect try_connect {addr} {ret}')
                return self.adb_connect(addr, try_connect=False)
            else:
                logger.info(f'adb_connect {addr} not in device list {self.adb.list()}')
        except AdbError as e:
            logger.error(f"adb connect error {addr}", e)
            self.try_kill_adb(e)
        except Exception as e:
            logger.error(f"adb connect error return none {addr}", e)

    def get_devices(self):
        return list(self.device_dict.values())

    def update_pc_device(self):
        if self.windows_capture_config is not None:
            name, hwnd, full_path, x, y, width, height = find_hwnd(self.windows_capture_config.get('title'),
                                                                   self.windows_capture_config.get(
                                                                       'exe') or self.config.get('selected_exe'), 0, 0,
                                                                   player_id=-1,
                                                                   class_name=self.windows_capture_config.get(
                                                                       'hwnd_class'),
                                                                   selected_hwnd=self.config.get('selected_hwnd'))
            nick = name or self.windows_capture_config.get('exe')
            pc_device = {"address": "", "imei": 'pc', "device": "windows",
                         "model": "", "nick": nick, "width": width,
                         "height": height,
                         "hwnd": nick, "capture": "windows",
                         "connected": hwnd > 0,
                         "full_path": full_path or self.config.get('pc_full_path')
                         }
            logger.info(f'start update_pc_device {self.windows_capture_config}, pc_device: {pc_device}')
            if full_path and full_path != self.config.get('pc_full_path'):
                logger.info(f'start update_pc_device pc_full_path {full_path}')
                self.config['pc_full_path'] = full_path

            if width != 0:
                pc_device["resolution"] = f"{width}x{height}"
            self.device_dict['pc'] = pc_device

    def do_refresh(self, current=False):
        try:
            self.update_pc_device()
            self.refresh_emulators(current)
            self.refresh_phones(current)
        except Exception as e:
            logger.error('refresh error', e)

        if self.exit_event.is_set():
            return
        self.do_start()

        logger.debug(f'refresh {self.device_dict}')

    def refresh_phones(self, current=False):
        if self.adb_capture_config is None:
            return
        for adb_device in self.adb.iter_device():
            imei = self.adb_get_imei(adb_device)
            if imei is not None:
                preferred = self.get_preferred_device()
                if current and preferred is not None and preferred['imei'] != imei:
                    logger.debug(f"refresh current only skip others {preferred['imei']} != {imei}")
                    continue
                found = False
                for device in self.device_dict.values():
                    if device.get('adb_imei') == imei:
                        found = True
                        break
                if not found:
                    width, height = self.get_resolution(adb_device)
                    logger.debug(f'refresh_phones found an phone {adb_device}')
                    phone_device = {"address": adb_device.serial, "device": "adb", "connected": True, "imei": imei,
                                    "nick": adb_device.prop.model or imei, "player_id": -1,
                                    "resolution": f'{width}x{height}'}
                    self.device_dict[imei] = phone_device
        logger.debug(f'refresh_phones done')

    def refresh_emulators(self, current=False):
        if self.adb_capture_config is None:
            return
        from ok.alas.emulator_windows import EmulatorManager
        manager = EmulatorManager()
        installed_emulators = manager.all_emulator_instances
        logger.info(f'installed emulators {installed_emulators}')
        for emulator in installed_emulators:
            preferred = self.get_preferred_device()
            if current and preferred is not None and preferred['imei'] != emulator.name:
                logger.debug(f"refresh current only skip others {preferred['imei']} != {emulator.name}")
                continue
            adb_device = self.adb_connect(emulator.serial)
            if adb_device is not None:
                adb_width, adb_height = self.get_resolution(adb_device)
            else:
                adb_width, adb_height = 0, 0
            name, hwnd, full_path, x, y, width, height = find_hwnd(None,
                                                                   emulator.path, adb_width, adb_height,
                                                                   emulator.player_id)
            logger.info(
                f'adb_connect emulator result {emulator.path} {emulator.player_id} {emulator.type} {adb_device} hwnd_size {width, height} adb_size {adb_width, adb_height} {name, hwnd}')
            connected = adb_device is not None
            emulator_device = {"address": emulator.serial, "device": "adb", "full_path": emulator.path,
                               "connected": connected, "imei": emulator.name, "player_id": emulator.player_id,
                               "nick": name or emulator.name, "emulator": emulator}
            if adb_device is not None:
                emulator_device["resolution"] = f"{adb_width}x{adb_height}"
                emulator_device["adb_imei"] = self.adb_get_imei(adb_device)
            self.device_dict[emulator.name] = emulator_device
        logger.info(f'refresh emulators {self.device_dict}')

    def get_resolution(self, device=None):
        if device is None:
            device = self.device
        width, height = 0, 0
        if device is not None:
            if resolution := self.resolution_dict.get(device.serial):
                return resolution
            frame = self.do_screencap(device)
            if frame is not None:
                height, width, _ = frame.shape
                logger.info(f'get_resolution capture frame frame.shape {width, height}')
                if self.supported_ratio is None or abs(width / height - self.supported_ratio) < 0.01:
                    self.resolution_dict[device.serial] = (width, height)
                else:
                    logger.warning(f'resolution error {device.serial} {self.supported_ratio} {width, height}')
            else:
                logger.info(f'get_resolution capture frame is None')
        return width, height

    def set_preferred_device(self, imei=None, index=-1):
        logger.debug(f"set_preferred_device {imei} {index}")
        if self.executor:
            self.executor.stop_current_task()
        if index != -1:
            imei = self.get_devices()[index]['imei']
        elif imei is None:
            imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        if preferred is None:
            if len(self.device_dict) > 0:
                connected_device = None
                for device in self.device_dict.values():
                    if device.get('connected') or connected_device is None:
                        connected_device = device
                logger.info(f'first start use first or connected device {connected_device}')
                preferred = connected_device
                imei = preferred['imei']
            else:
                logger.warning(f'no devices')
                return
        if self.config.get("preferred") != imei:
            logger.info(f'preferred device did change {imei}')
            self.config["preferred"] = imei
            self.start()
        logger.debug(f'preferred device: {preferred}')

    def shell_device(self, device, *args, **kwargs):
        kwargs.setdefault('timeout', 5)
        try:
            return device.shell(*args, **kwargs)
        except Exception as e:
            logger.error(f"adb shell error maybe offline {device}", e)
            return None

    def adb_get_imei(self, device):
        return (self.shell_device(device, "settings get secure android_id") or
                self.shell_device(device, "service call iphonesubinfo 4") or device.prop.model)

    def do_screencap(self, device) -> np.ndarray | None:
        if device is None:
            return None
        try:
            png_bytes = self.shell_device(device, "screencap -p", encoding=None)
            if png_bytes is not None and len(png_bytes) > 0:
                image_data = np.frombuffer(png_bytes, dtype=np.uint8)
                image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
                if image is not None:
                    return image
                else:
                    logger.error(f"Screencap image decode error, probably disconnected")
        except Exception as e:
            logger.error('screencap', e)

    def adb_ui_dump(self):
        device = self.device
        if device:
            try:
                dump_output = self.shell_device(device, ["uiautomator", "dump"], encoding='utf-8')
                match = re.search(r"/sdcard/.*\.xml", dump_output)
                if match:
                    dump_file_path = match.group(0)  # Get the file path from the regex
                    logger.debug(f"Dumped UI file at: {dump_file_path}")
                    xml_content = None
                    local_file_path = os.path.join('temp', 'window_dump.xml')

                    if not os.path.exists('temp'):
                        os.makedirs('temp')

                    delete_if_exists(local_file_path)

                    device.sync.pull(dump_file_path, local_file_path)
                    if os.path.isfile(local_file_path):
                        with open(local_file_path, 'r', encoding='utf-8') as f:
                            xml_content = f.read()
                    return xml_content
                else:
                    logger.error(f"Error: Could not extract the file path from the output:  {dump_output}")
                    return None
            except Exception as e:
                logger.error('adb_ui_dump exception', e)

    def get_preferred_device(self):
        imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        return preferred

    def get_preferred_capture(self):
        return self.config.get("capture")

    def set_hwnd_name(self, hwnd_name):
        preferred = self.get_preferred_device()
        if preferred.get("hwnd") != hwnd_name:
            preferred['hwnd'] = hwnd_name
            if self.hwnd_window:
                self.hwnd_window.title = hwnd_name
            self.config.save_file()

    def set_capture(self, capture):
        if self.config.get("capture") != capture:
            if self.executor:
                self.executor.stop_current_task()
            self.config['capture'] = capture
            self.start()

    def get_hwnd_name(self):
        preferred = self.get_preferred_device()
        return preferred.get('hwnd')

    def ensure_hwnd(self, title, exe, frame_width=0, frame_height=0, player_id=-1, hwnd_class=None):
        if self.hwnd_window is None:
            self.hwnd_window = HwndWindow(self.exit_event, title, exe, frame_width, frame_height, player_id,
                                          hwnd_class, global_config=self.global_config, device_manager=self)
        else:
            self.hwnd_window.update_window(title, exe, frame_width, frame_height, player_id, hwnd_class)

    def use_windows_capture(self):
        self.capture_method = update_capture_method(self.windows_capture_config, self.capture_method, self.hwnd_window,
                                                    exit_event=self.exit_event)
        if self.capture_method is None:
            logger.error(f'cant find a usable windows capture')
        else:
            logger.info(f'capture method {type(self.capture_method)}')

    def start(self):
        self.handler.post(self.do_start, remove_existing=True, skip_if_running=True)

    def do_start(self):
        logger.debug(f'do_start')
        preferred = self.get_preferred_device()
        if preferred is None:
            if self.device_dict:
                self.set_preferred_device()
            return

        if preferred['device'] == 'windows':
            self.ensure_hwnd(self.windows_capture_config.get('title'), self.windows_capture_config.get('exe'),
                             hwnd_class=self.windows_capture_config.get('hwnd_class'))
            self.use_windows_capture()
            if not isinstance(self.interaction, self.win_interaction_class):
                self.interaction = self.win_interaction_class(self.capture_method, self.hwnd_window)
            preferred['connected'] = self.capture_method is not None and self.capture_method.connected()
        else:
            width, height = self.get_resolution()
            if self.config.get('capture') == "windows":
                self.ensure_hwnd(None, preferred.get('full_path'), width, height, preferred['player_id'])
                logger.info(f'do_start use windows capture {self.hwnd_window.title}')
                self.use_windows_capture()
            else:
                if self.config.get('capture') == 'ipc':
                    if not isinstance(self.capture_method, NemuIpcCaptureMethod):
                        if self.capture_method is not None:
                            self.capture_method.close()
                        self.capture_method = NemuIpcCaptureMethod(self, self.exit_event)
                    self.capture_method.update_emulator(self.get_preferred_device().get('emulator'))
                    logger.info(f'use ipc capture {preferred}')
                else:
                    if not isinstance(self.capture_method, ADBCaptureMethod):
                        logger.debug(f'use adb capture')
                        if self.capture_method is not None:
                            self.capture_method.close()
                        self.capture_method = ADBCaptureMethod(self, self.exit_event, width=width,
                                                               height=height)
                        logger.info(f'use adb capture {preferred}')
                if preferred.get('full_path'):
                    logger.info(f'ensure_hwnd for debugging {preferred} {width, height}')
                    self.ensure_hwnd(None, preferred.get('full_path').replace("nx_main/MuMuNxMain.exe",
                                                                              "nx_device/12.0/shell/MuMuNxDevice.exe"),
                                     width, height,
                                     preferred['player_id'])
                elif self.hwnd_window is not None:
                    self.hwnd_window.stop()
                    self.hwnd_window = None
                if not isinstance(self.interaction, ADBInteraction):
                    self.interaction = ADBInteraction(self, self.capture_method, width, height)
                else:
                    self.interaction.capture = self.capture_method
                    self.interaction.width = width
                    self.interaction.height = height

        communicate.adb_devices.emit(True)

    def update_resolution_for_hwnd(self):
        if self.hwnd_window is not None and self.hwnd_window.frame_aspect_ratio == 0 and self.adb_capture_config:
            width, height = self.get_resolution()
            logger.debug(f'update resolution for {self.hwnd_window} {width}x{height}')
            self.hwnd_window.update_frame_size(width, height)

    @property
    def device(self):
        if preferred := self.get_preferred_device():
            if self._device is None:
                logger.debug(f'get device connect {preferred}')
                self._device = self.adb_connect(preferred.get('address'))
            if self._device is not None and self._device.serial != preferred.get('address'):
                logger.info(f'get device adb device addr changed {preferred}')
                self._device = self.adb_connect(preferred.get('address'))
        else:
            logger.error(f'self.get_preferred_device returned None')
        return self._device

    def adb_kill_server(self):
        if self.adb is not None:
            self.adb.server_kill()
            logger.debug('adb kill_server')

    @property
    def width(self):
        if self.capture_method is not None:
            return self.capture_method.width
        return 0

    @property
    def height(self):
        if self.capture_method is not None:
            return self.capture_method.height
        return 0

    def update_device_list(self):
        pass

    def shell(self, *args, **kwargs):
        # Set default timeout to 5 if not provided

        device = self.device
        logger.debug(f'adb shell {device} {args} {kwargs}')
        if device is not None:
            return self.shell_device(device, *args, **kwargs)
        else:
            raise Exception('Device is none')

    def device_connected(self):
        if self.get_preferred_device()['device'] == 'windows':
            return True
        elif self.device is not None:
            try:
                state = self.shell('echo 1')
                logger.debug(f'device_connected check device state is {state}')
                return state is not None
            except Exception as e:
                logger.error(f'device_connected error occurred, {e}')

    def get_exe_path(self, device):
        path = device.get('full_path')
        if device.get(
                'device') == 'windows' and self.windows_capture_config:
            if path == "none":
                path = None
            if self.windows_capture_config.get(
                    'calculate_pc_exe_path'):
                path = self.windows_capture_config.get('calculate_pc_exe_path')(path)
                logger.info(f'calculate_pc_exe_path {path}')
            if os.path.exists(path):
                return path
        elif emulator := device.get('emulator'):
            from ok.alas.platform_windows import get_emulator_exe
            return get_emulator_exe(emulator)
        else:
            return None

    def adb_check_installed(self, packages):
        installed = self.shell('pm list packages')
        if isinstance(packages, str):
            packages = [packages]
        for package in packages:
            if package in installed:
                return package

    def adb_check_in_front(self, packages):
        front = self.device is not None and self.device.app_current()
        logger.debug(f'adb_check_in_front {front}')
        if front:
            if isinstance(packages, str):
                packages = [packages]
            for package in packages:
                if package == front.package:
                    return True

    def adb_start_package(self, package):
        self.shell(f'monkey -p {package} -c android.intent.category.LAUNCHER 1')

    def adb_ensure_in_front(self):
        front = self.adb_check_in_front(self.packages)
        logger.debug(f'adb_ensure_in_front {front}')
        if front:
            return front
        elif installed := self.adb_check_installed(self.packages):
            self.adb_start_package(installed)
            return True


def parse_ratio(ratio_str):
    if ratio_str:
        # Split the string into two parts: '16' and '9'
        numerator, denominator = ratio_str.split(':')
        # Convert the strings to integers and perform the division
        ratio_float = int(numerator) / int(denominator)
        return ratio_float

cdef class NemuIpcCaptureMethod(BaseCaptureMethod):
    name = "Nemu Ipc Capture"
    description = "mumu player 12 only"
    cdef bint _connected
    cdef public object device_manager, nemu_impl, emulator

    def __init__(self, device_manager, exit_event, width=0, height=0):
        super().__init__()
        self.device_manager = device_manager
        self.exit_event = exit_event
        self._connected = (width != 0 and height != 0)
        self.nemu_impl = None
        self.emulator = None

    def update_emulator(self, emulator):
        self.emulator = emulator
        logger.info(f'update_path_and_id {emulator}')
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    def init_nemu(self):
        self.check_mumu_app_keep_alive_400()
        if not self.nemu_impl:
            from ok.capture.adb.nemu_ipc import NemuIpc
            self.nemu_impl = NemuIpc(
                nemu_folder=self.base_folder(),
                instance_id=self.emulator.player_id,
                display_id=0
            )

    def base_folder(self):
        return os.path.dirname(os.path.dirname(self.emulator.path))

    def check_mumu_app_keep_alive_400(self):
        """
        Check app_keep_alive from emulator config if version >= 4.0

        Args:
            file: E:/ProgramFiles/MuMuPlayer-12.0/vms/MuMuPlayer-12.0-1/config/customer_config.json

        Returns:
            bool: If success to read file
        """
        file = os.path.abspath(os.path.join(
            self.base_folder(),
            f'vms/MuMuPlayer-12.0-{self.emulator.player_id}/configs/customer_config.json'))

        # with E:\ProgramFiles\MuMuPlayer-12.0\shell\MuMuPlayer.exe
        # config is E:\ProgramFiles\MuMuPlayer-12.0\vms\MuMuPlayer-12.0-1\config\customer_config.json
        try:
            with open(file, mode='r', encoding='utf-8') as f:
                s = f.read()
                data = json.loads(s)
        except FileNotFoundError:
            logger.warning(f'Failed to check check_mumu_app_keep_alive, file {file} not exists')
            return False
        value = deep_get(data, keys='customer.app_keptlive', default=None)
        # logger.info(f'customer.app_keptlive {value}')
        if str(value).lower() == 'true':
            # https://mumu.163.com/help/20230802/35047_1102450.html
            logger.error('Please turn off enable background keep alive in MuMuPlayer settings')
            raise Exception('Please turn off enable background keep alive in MuMuPlayer settings')
        return True

    def close(self):
        super().close()
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    cpdef object do_get_frame(self):
        self.init_nemu()
        return self.screencap()

    cdef object screencap(self):
        if self.exit_event.is_set():
            return None
        if self.nemu_impl:
            return self.nemu_impl.screenshot(timeout=0.5)

    def connected(self):
        return True

def deep_get(d, keys, default=None):
    """
    Get values in dictionary safely.
    https://stackoverflow.com/questions/25833613/safe-method-to-get-value-of-nested-dictionary

    Args:
        d (dict):
        keys (str, list): Such as `Scheduler.NextRun.value`
        default: Default return if key not found.

    Returns:

    """
    if isinstance(keys, str):
        keys = keys.split('.')
    assert type(keys) is list
    if d is None:
        return default
    if not keys:
        return d
    return deep_get(d.get(keys[0]), keys[1:], default)

def update_capture_method(config, capture_method, hwnd, exit_event=None):
    """
    Updates the capture method based on a prioritized list from the config.

    It iterates through the capture methods specified in config['capture_method']
    and attempts to initialize each one. The first successful method is returned.
    """
    try:
        method_preferences = config.get('capture_method', [])

        for method_name in method_preferences:
            if method_name == 'WGC':
                if win_graphic := get_win_graphics_capture(capture_method, hwnd, exit_event):
                    logger.info(f'use WGC capture')
                    return win_graphic
            elif method_name == 'BitBlt_RenderFull':
                global render_full
                render_full = True
                if bitblt_capture := get_capture(capture_method, BitBltCaptureMethod, hwnd, exit_event):
                    logger.info(f'use BitBlt_RenderFull capture')
                    return bitblt_capture
            elif method_name == 'BitBlt':
                global render_full
                hdr_enabled, swap_enabled = read_game_gpu_pref(hwnd.exe_full_path)
                render_full = swap_enabled is True or \
                              (swap_enabled is None and read_global_gpu_pref()[1] is True)
                logger.info(f'use BitBlt capture swap_enabled: {swap_enabled}, render_full: {render_full}')

                if bitblt_capture := get_capture(capture_method, BitBltCaptureMethod, hwnd, exit_event):
                    return bitblt_capture
            elif method_name == 'DXGI':
                if dxgi_capture := get_capture(capture_method, DesktopDuplicationCaptureMethod, hwnd, exit_event):
                    return dxgi_capture

        return None  # Return None if no capture method was successful
    except Exception as e:
        logger.error(f'update_capture_method exception, return None: {e}')
        return None

def get_win_graphics_capture(capture_method, hwnd, exit_event):
    if windows_graphics_available():
        target_method = WindowsGraphicsCaptureMethod
        capture_method = get_capture(capture_method, target_method, hwnd, exit_event)
        if capture_method.start_or_stop():
            return capture_method

def get_capture(capture_method, target_method, hwnd, exit_event):
    if not isinstance(capture_method, target_method):
        if capture_method is not None:
            capture_method.close()
        capture_method = target_method(hwnd)
    capture_method.hwnd_window = hwnd
    capture_method.exit_event = exit_event
    return capture_method

MDT_EFFECTIVE_DPI = 0
user32 = ctypes.WinDLL('user32', use_last_error=True)

def is_window_minimized(hWnd):
    return user32.IsIconic(hWnd) != 0

def get_window_bounds(hwnd):
    try:
        extended_frame_bounds = ctypes.wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(extended_frame_bounds),
            ctypes.sizeof(extended_frame_bounds),
        )
        client_x, client_y, client_width, client_height = win32gui.GetClientRect(hwnd)
        window_left, window_top, window_right, window_bottom = win32gui.GetWindowRect(hwnd)
        window_width = window_right - window_left
        window_height = window_bottom - window_top
        client_x, client_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
        monitor = user32.MonitorFromWindow(hwnd, 2)  # 2 = MONITOR_DEFAULTTONEAREST

        # Get the DPI
        dpiX = ctypes.c_uint()
        dpiY = ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpiX), ctypes.byref(dpiY))
        return client_x, client_y, window_width, window_height, client_width, client_height, dpiX.value / 96
    except Exception as e:
        logger.error(f'get_window_bounds exception', e)
        return 0, 0, 0, 0, 0, 0, 1

def is_foreground_window(hwnd):
    return win32gui.IsWindowVisible(hwnd) and win32gui.GetForegroundWindow() == hwnd

def show_title_bar(hwnd):
    try:
        # Get the current window styles
        current_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        # Check if the title bar style is already present
        if current_style & win32con.WS_CAPTION:
            logger.info(f"Window '{hwnd}' already has a title bar.")
            return True
        # Calculate the new style with WS_CAPTION added
        new_style = current_style | win32con.WS_CAPTION
        # Optional: Remove styles that might conflict (e.g., WS_POPUP)
        new_style &= ~win32con.WS_POPUP
        # new_style &= ~win32con.WS_BORDER
        # Set the new window styles
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
        # Tell the window to redraw its non-client area
        win32gui.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                              win32con.SWP_FRAMECHANGED | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        # Re-check the style to confirm the change
        updated_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        time.sleep(0.01)
        if updated_style & win32con.WS_CAPTION:
            logger.info(f"Title bar shown for window '{hwnd}'.")
            return True
        else:
            logger.info(f"Failed to show title bar for window '{hwnd}'.")
            return False
    except Exception as e:
        print(f"Error showing title bar for window '{hwnd}': {e}")
        return False

def resize_window(hwnd, width, height):
    """
    Resizes the window with the given handle (hwnd) to the specified width and height,
    and then centers it on the screen.
    Returns True if successful, False otherwise.
    """
    if not hwnd:
        logger.info("Invalid window handle provided.")
        return False
    try:
        # --- Resize the window ---
        # We'll resize first, as the GetWindowRect after this will give us the
        # dimensions including the border after resizing.
        # SetWindowPos Flags for resizing
        SWP_SHOWWINDOW = 0x0040
        SWP_NOZORDER = 0x0004
        SWP_NOREPOSITION = 0x0002  # We are resizing, not repositioning yet
        # Using the ctypes SetWindowPos as in your original function
        user32.SetWindowPos(hwnd, None, 0, 0, width, height, SWP_SHOWWINDOW | SWP_NOZORDER | SWP_NOREPOSITION)
        # Give the system a brief moment to apply the resize (optional, but can help)
        time.sleep(0.01)
        # --- Center the window ---
        # Get the *new* window dimensions after resizing
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        window_width = right - left
        window_height = bottom - top
        # Get the screen resolution
        screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
        # Calculate the center position
        center_x = (screen_width - window_width) // 2
        center_y = (screen_height - window_height) // 2
        # Set the window position (using SWP_NOSIZE as we're only moving)
        # SetWindowPos Flags for centering
        SWP_NOSIZE = 0x0001  # Don't change size (already resized)
        # SWP_NOZORDER = 0x0004 # Already specified
        # SWP_SHOWWINDOW = 0x0040 # Already specified
        user32.SetWindowPos(hwnd, None, center_x, center_y, 0, 0,
                            SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
        time.sleep(0.01)
        logger.info(f"Window with handle {hwnd} resized to {width}x{height} and centered at ({center_x}, {center_y}).")
        return True
    except Exception as e:
        logger.error(f"Error resizing and centering window with handle {hwnd}: {e}")
        return False

# string_compare.pyx

cdef bint compare_path_safe(str str1, str str2):
    if str1 is None and str2 is None:
        return True
    if str1 is None or str2 is None:
        return False
    return str1.replace('\\', '/').lower() == str2.replace('\\', '/').lower()


## globals.py
class OkGlobals:

    def __init__(self):
        super().__init__()
        self.app = None
        self.executor = None
        self.device_manager = None
        self.handler = None
        self.auth_uid = None
        self.auth_rd = None
        self.auth_expire = 0
        self.trial_expire = 0
        self.my_app = None
        self.dpi_scaling = 1.0
        self.ok = None
        self.config = None
        self.task_manager = None
        self.app_path = get_path_relative_to_exe()
        self.use_dml = False
        self.global_config = None
        logger.info(f'app path {self.app_path}')

    def set_use_dml(self):
        use_dml_txt_option = self.global_config.get_config('Basic Options').get('Use DirectML')
        use_dml = False
        if use_dml_txt_option == 'Auto':
            nv_free_gpu_memory = get_first_gpu_free_memory_mib()
            if nv_free_gpu_memory > 3000:
                use_dml = True
            logger.info(f'Use DirectML is auto nv_free_gpu_memory: {nv_free_gpu_memory}, use_dml: {use_dml}')
        elif use_dml_txt_option == 'Yes':
            use_dml = True
        if use_dml:
            window_build_number_str = platform.version().split(".")[-1]
            window_build_number = int(window_build_number_str) if window_build_number_str.isdigit() else 0
            use_dml = window_build_number >= 18362
        logger.info(f'use_dml result is {use_dml}')
        self.use_dml = use_dml

    def get_trial_expire_util_str(self):
        # Convert the timestamp to a datetime object
        expire_date = datetime.fromtimestamp(self.trial_expire)

        # Format the datetime object to a string
        expire_date_str = expire_date.strftime('%Y-%m-%d %H:%M:%S')

        return expire_date_str

    def get_expire_util_str(self):
        # Convert the timestamp to a datetime object
        expire_date = datetime.fromtimestamp(self.auth_expire)

        # Format the datetime object to a string
        expire_date_str = expire_date.strftime('%Y-%m-%d %H:%M:%S')

        return expire_date_str

    def set_dpi_scaling(self, window):
        window_handle = window.windowHandle()
        screen = window_handle.screen()
        self.dpi_scaling = screen.devicePixelRatio()
        logger.debug('dpi_scaling: {}'.format(self.dpi_scaling))


og = OkGlobals()


## Config.py


class Config(dict):
    config_folder = 'configs'

    def __init__(self, name, default, folder=None, validator=None):
        """
        Initialize the Config object.

        :param default: Default configuration values.
        :param folder: Folder where the config file is stored.
        :param name: Name of the config file.
        :param validator: Optional function to validate key-value pairs.
        """
        self.default = default
        self.validator = validator
        if folder is None:
            folder = self.config_folder
        self.config_file = get_relative_path(folder, f"{name}.json")

        # Read the config file, if it exists, otherwise use default
        config = read_json_file(self.config_file)
        if config is None:
            self.reset_to_default()
        else:
            super().__init__()
            modified = self.verify_config(config, default)
            if modified:
                self.save_file()
        logger.debug(f'init self.config = {self}')

    def save_file(self):
        """
        Save the current configuration to the file.
        """
        try:
            write_json_file(self.config_file, self)
        except Exception as e:
            logger.error(f'save_file error: {e}')

    def get_default(self, key):
        return self.default.get(key)

    def reset_to_default(self):
        """
        Reset the configuration to the default values.
        """
        super().clear()
        self.update(self.default)
        self.save_file()
        logger.debug(f'reset_to_default self.config = {self}')

    def pop(self, key, default=None):
        """
        Remove and return a value from the configuration.

        :param key: The key to remove.
        :param default: The default value if the key does not exist.
        :return: The removed value.
        """
        result = super().pop(key, default)
        self.save_file()
        return result

    def popitem(self):
        """
        Remove and return the last key-value pair from the configuration.
        """
        result = super().popitem()
        self.save_file()
        return result

    def clear(self):
        """
        Clear all configuration values.
        """
        super().clear()
        self.save_file()

    def __setitem__(self, key, value):
        if value != self.get(key) and self.validate(key, value):
            old_value = self.get(key)
            super().__setitem__(key, value)
            if old_value != value:
                self.save_file()

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError as e:
            logger.error(f'KeyError: {key} not found in config: {self}')
            raise e

    def has_user_config(self):
        return not all(key.startswith('_') for key in self)

    def validate(self, key, value):
        """
        Validate a configuration key-value pair.

        :param key: The key to validate.
        :param value: The value to validate.
        :return: True if valid, False otherwise.
        """
        if self.validator is not None:
            valid, message = self.validator(key, value)
            if not valid:
                communicate.config_validation.emit(message)
                return False
        return True

    def verify_config(self, current, default_config):
        """
        Verify the configuration against the default configuration.

        :param default_config: The default configuration.
        :return: True if the config was modified, False otherwise.
        """
        modified = False

        # Remove entries that do not exist in default_config
        for key in list(current.keys()):
            if key not in default_config:
                del current[key]
                modified = True

        for key in list(default_config.keys()):
            if key not in current or not isinstance(current[key], type(default_config[key])):
                value = default_config[key]
                modified = True
            elif self.validator is not None:
                valid = self.validate(key, current[key])
                if not valid:
                    value = default_config[key]
                    modified = True
                else:
                    value = current[key]
            else:
                value = current[key]
            self[key] = value

        return modified


## analytics

class Analytics:
    def __init__(self, app_config, exit_event):
        self.report_url = app_config.get('analytics').get('report_url')
        self.app_config = app_config
        self._config = None
        og.handler.post(self.send_alive, 20)
        self._user_properties = None
        self._fv = 1

    @property
    def user_properties(self):
        if self._user_properties is None:
            os_name_val = 'windows'
            os_version_val = "Unknown"
            os_build_val = 0
            cpu_name_val = "Unknown"
            total_memory_gb_val = 0
            # gpu_name_val is removed as per instruction

            try:
                # Get OS information
                kernel_ver_str = platform.win32_ver()[1]
                os_ver_intermediate = kernel_ver_str.split('.')[0]
                os_build_val = int(kernel_ver_str.split('.')[-1])

                reported_os_version = os_ver_intermediate
                if os_ver_intermediate == "10" and os_build_val >= 22000:
                    reported_os_version = "11"
                os_version_val = reported_os_version
            except Exception as e:
                logger.error(f"Error getting OS info: {e}")

            try:
                # Get CPU information using platform.processor()
                cpu_name_val = platform.processor().strip()
                if not cpu_name_val:  # Fallback if platform.processor() returns empty
                    cpu_name_val = "Unknown"
            except Exception as e:
                logger.error(f"Error getting CPU info: {e}")
                cpu_name_val = "Unknown"  # Ensure fallback on error

            try:
                # Get total memory (in GB) using psutil
                total_memory_bytes = psutil.virtual_memory().total
                total_memory_gb_val = float(total_memory_bytes) / (1024 ** 3)  # Bytes to GB
            except Exception as e:
                logger.error(f"Error getting memory info: {e}")

            # GPU information collection is removed.

            self._user_properties = {
                "os": os_name_val,
                "os_version": str(os_version_val),
                "os_build": str(os_build_val),
                "cpu": cpu_name_val,
                "memory": str(int(total_memory_gb_val)),
            }

            if hasattr(og, 'device_manager'):
                config = og.device_manager.config
                if config:
                    self._user_properties["device"] = config.get('preferred')
                    self._user_properties["device_capture"] = config.get('capture')

                capture = og.device_manager.capture_method
                if capture:
                    if hasattr(capture, '_size'):
                        width, height = capture._size
                        if width and height:
                            self._user_properties["device_sr"] = f'{width}x{height}'
                    else:
                        logger.warning("og.device_manager.capture_method exists but has no _size attribute.")
            else:
                logger.warning("'og.device_manager' not found. Skipping device specific properties.")

        return self._user_properties

    @property
    def client_id(self):
        if self._config is None:
            self._config = Config('statistics', {'client_id': ''})
        if not self._config.get('client_id'):
            self._config['client_id'] = self.get_unique_client_id()
        else:
            self._fv = 0
        return self._config.get('client_id')

    def send_alive(self):
        from ok.gui.common.config import cfg
        params = {
            "device_id": self.client_id,
            "app_version": self.app_config.get('version'),
            "app_name": self.app_config.get('app_id') or self.app_config.get('gui_title'),
            'locale': cfg.get(cfg.language).value.name(),
            'sr': get_screen_resolution(),
            "os": 'windows',
        }

        params.update(self.user_properties)

        logger.info(f'send report {params}')
        try:
            response = requests.post(self.report_url, json=params, timeout=10)
            if response.status_code == 200:
                logger.debug(f'Successfully send report')
            else:
                logger.error(f'Failed to send event: {response.status_code} - {response.text}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Failed to send report due to network error: {e}')
        og.handler.post(self.send_alive, 3600 * 6)

    def get_unique_client_id(self):
        user_dict = self.user_properties.copy()
        user_dict['mac'] = uuid.getnode()
        if 'os_build' in user_dict:
            del user_dict['os_build']
        # "gpu" key will not be in user_dict if it's not in user_properties
        global hash_dict_keys_values
        if 'hash_dict_keys_values' not in globals():
            import hashlib, json
            def hash_dict_keys_values(d):
                s = json.dumps(d, sort_keys=True)
                return hashlib.sha256(s.encode('utf-8')).hexdigest()
        return hash_dict_keys_values(user_dict)


def get_screen_resolution():
    user32 = ctypes.windll.user32
    screensize = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return f"{screensize[0]}x{screensize[1]}"

def hash_dict_keys_values(my_dict):
    # Sort the dictionary by keys
    sorted_items = sorted(my_dict.items())

    # Initialize an empty string to store concatenated key-value pairs
    concatenated_kv = ''

    # Concatenate sorted key-value pairs
    for key, value in sorted_items:
        concatenated_kv += f'{key}{value}'

    # Encode the concatenated string
    encoded_kv = concatenated_kv.encode()

    # Create a new md5 hash object
    hash_object = hashlib.md5(encoded_kv)

    # Get the hexadecimal representation of the hash
    hash_hex = hash_object.hexdigest()

    return hash_hex


## ConfigOptions
class ConfigOption:

    def __init__(self, name, default=None, description="", config_description=None, config_type=None,
                 validator=None, icon=FluentIcon.INFO):
        self.name = name
        self.description = description
        self.default_config = default or {}
        self.config_description = config_description or {}
        self.config_type = config_type
        self.validator = validator
        self.icon = icon


basic_options = ConfigOption('Basic Options', {
    'Auto Start Game When App Starts': False,
    'Minimize Window to System Tray when Closing': False,
    'Mute Game while in Background': False,
    'Auto Resize Game Window': True,
    'Exit App when Game Exits': False,
    'Use DirectML': 'Yes',
    'Trigger Interval': 1,
}, config_type={'Use DirectML': {'type': "drop_down", 'options': ['Auto', 'Yes', 'No']}}
                             , config_description={'Use DirectML': 'Use GPU to Improve Performance',
                                                   'Trigger Interval': 'Increase Delay between Trigger Tasks to Reduce CPU/GPU Usage(Milliseconds)'},
                             icon=FluentIcon.GAME)


class GlobalConfig:
    def __init__(self, config_options):
        self.configs = {}
        self.config_options = {}
        self.lock = threading.Lock()
        if config_options:
            for config_option in config_options:
                self.get_config(config_option)

    def get_config(self, option):
        with self.lock:
            if isinstance(option, str):
                if config := self.configs.get(option):
                    return config
                for config in self.configs.values():
                    if option in config:
                        return config
                raise RuntimeError(f'Can not find global config {option}')
            config = self.configs.get(option.name)
            if config is None:
                config = Config(option.name, option.default_config, validator=option.validator)
                self.configs[option.name] = config
                self.config_options[option.name] = option
            return config

    def get_config_desc(self, key):
        for config_option in self.config_options.values():
            desc_s = config_option.config_description
            if key in desc_s:
                return desc_s

    def get_all_visible_configs(self):
        with self.lock:
            configs = []
            # Filter out keys that start with '_'
            for k, v in self.configs.items():
                if not k.startswith('_'):
                    configs.append((k, v, self.config_options.get(k)))
            return sorted(configs, key=lambda x: x[0])


class InfoDict(dict):

    def __delitem__(self, key):
        super().__delitem__(key)

    def clear(self):
        super().clear()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)


## FeatureSet

cdef class FeatureSet:
    cdef int width, height
    cdef double default_threshold, default_horizontal_variance, default_vertical_variance
    cdef str coco_json
    cdef bint debug, load_success
    cdef dict feature_dict, box_dict
    cdef object lock, feature_processor

    def __init__(self, debug, coco_json: str, default_horizontal_variance,
                 default_vertical_variance, default_threshold=0.95, feature_processor=None) -> None:
        """
        Initialize the FeatureSet by loading images and annotations from a COCO dataset.

        Args:
            coco_json (str): Directory containing the JSON file and images.
            width (int): Scale images to this width.
            height (int): Scale images to this height.
        """
        self.coco_json = get_path_relative_to_exe(coco_json)
        self.debug = debug
        self.feature_dict = {}
        self.box_dict = {}
        self.load_success = False
        self.feature_processor = feature_processor

        logger.debug(f'Loading features from {self.coco_json}')

        # Process images and annotations
        self.width = 0
        self.height = 0
        if default_threshold == 0:
            default_threshold = 0.95
        self.default_threshold = default_threshold
        self.default_horizontal_variance = default_horizontal_variance
        self.default_vertical_variance = default_vertical_variance
        self.lock = threading.Lock()

    def feature_exists(self, feature_name: str) -> bool:
        return feature_name in self.feature_dict

    cdef bint empty(self):
        return len(self.feature_dict) == 0 and len(self.box_dict) == 0

    cpdef bint check_size(self, object frame):
        with self.lock:
            height, width = frame.shape[:2]
            if self.width != width or self.height != height and height > 0 and width > 0:
                logger.info(f"FeatureSet: Width and height changed from {self.width}x{self.height} to {width}x{height}")
                self.width = width
                self.height = height
                self.process_data()
            elif not self.feature_dict:
                self.process_data()
        return self.load_success

    cdef bint process_data(self):
        """
        Process the images and annotations from the COCO dataset.

        Args:
            width (int): Target width for scaling images.
            height (int): Target height for scaling images.
        """
        self.feature_dict, self.box_dict, compressed, self.load_success = read_from_json(self.coco_json, self.width,
                                                                                         self.height)
        if self.debug and not compressed:
            from ok.feature.CompressCoco import compress_coco
            logger.info(f'coco not compressed try to compress the COCO dataset')
            compress_coco(self.coco_json)
            self.feature_dict, self.box_dict, compressed, self.load_success = read_from_json(self.coco_json, self.width,
                                                                                             self.height)
        if self.feature_processor:
            logger.info('process features with feature_processor')
            for feature in self.feature_dict:
                self.feature_processor(feature, self.feature_dict[feature])
        return self.load_success

    cpdef object get_box_by_name(self, mat, category_name):
        self.check_size(mat)
        return self.box_dict.get(category_name)

    cdef save_images(self, str target_folder):
        """
        Save all images in the featureDict to the specified folder.

        Args:
            target_folder (str): The folder where images will be saved.
        """
        # Ensure the target folder exists
        os.makedirs(target_folder, exist_ok=True)

        # Iterate through the featureDict and save each image
        for category_name, image in self.feature_dict.items():
            # Construct the filename
            file_name = f"{category_name}.jpg"
            file_path = os.path.join(target_folder, file_name)

            # Save the image
            cv2.imwrite(file_path, image.mat)

    cpdef object get_feature_by_name(self, mat, name):
        self.check_size(mat)
        return self.feature_dict.get(name)

    def find_one_feature(self, mat: np.ndarray, category_name, horizontal_variance: float = 0,
                         vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x=-1, y=-1,
                         to_x=-1, to_y=-1, width=-1, height=-1, box=None, canny_lower=0, canny_higher=0,
                         frame_processor=None, template=None, mask_function=None, match_method=cv2.TM_CCOEFF_NORMED,
                         screenshot=False):
        """
        Find a feature within a given variance.

        Args:
            mat (np.ndarray): The image in which to find the feature.
            category_name (str): The category name of the feature to find.
            horizontal_variance (float): Allowed horizontal variance as a percentage of width.
            vertical_variance (float): Allowed vertical variance as a percentage of height.
            threshold (float): Allowed confidence threshold for the feature.
            use_gray_scale (bool): If True, convert image to grayscale before finding the feature.

        Returns:
            List[Box]: A list of boxes where the feature is found.
        """
        self.check_size(mat)

        if threshold == 0:
            threshold = self.default_threshold
        if horizontal_variance == 0:
            horizontal_variance = self.default_horizontal_variance
        if vertical_variance == 0:
            vertical_variance = self.default_vertical_variance
        if template is None and category_name not in self.feature_dict:
            raise ValueError(f"FeatureSet: {category_name} not found in featureDict")
        if template is None:
            feature = self.feature_dict[category_name]
            template = feature.mat
        else:
            feature = None
        if box is not None:
            search_x1 = max(box.x, 0)
            search_y1 = max(box.y, 0)
            search_x2 = min(box.x + box.width, mat.shape[1])
            search_y2 = min(box.y + box.height, mat.shape[0])
        elif x != -1 and y != -1:
            frame_height, frame_width, *_ = mat.shape
            if width == -1:
                width = to_x - x
            if height == -1:
                height = to_y - y
            search_x1 = round(x * frame_width)
            search_y1 = round(y * frame_height)
            search_x2 = round((x + width) * frame_width)
            search_y2 = round((y + height) * frame_height)
        elif feature is None:
            search_x1 = 0
            search_y1 = 0
            search_y2, search_x2 = mat.shape[:2]
        else:
            # Define search area using variance
            x_offset = self.width * horizontal_variance
            y_offset = self.height * vertical_variance
            # if the feature was scaled increase the search area by 1px each direction
            if feature.scaling != 1:
                if horizontal_variance == 0:
                    x_offset = 1
                if vertical_variance == 0:
                    y_offset = 1

            search_x1 = max(0, round(feature.x - x_offset))
            search_y1 = max(0, round(feature.y - y_offset))
            feature_width, feature_height = feature.width, feature.height
            search_x2 = min(self.width, round(feature.x + feature_width + x_offset))
            search_y2 = min(self.height, round(feature.y + feature_height + y_offset))

        search_area = mat[search_y1:search_y2, search_x1:search_x2, :3]

        # Crop the search area from the image
        feature_height, feature_width = template.shape[:2]
        if use_gray_scale:
            search_area = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
            if len(feature.mat.shape) != 2:
                template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        if canny_lower != 0 and canny_higher != 0:
            if len(search_area.shape) != 2:
                search_area = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
            search_area = cv2.Canny(search_area, canny_lower, canny_higher)
            if len(template.shape) != 2:
                template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
                template = cv2.Canny(template, canny_lower, canny_higher)
        if feature is not None and feature.mask is None:
            if mask_function is not None:
                feature.mask = mask_function(feature.mat)
        mask = None
        if feature is not None:
            mask = feature.mask
            feature.mat = template
        elif mask_function is not None:
            mask = mask_function(template)

        if frame_processor is not None:
            search_area = frame_processor(search_area)

        if feature is not None and (
                feature.mat.shape[1] > search_area.shape[1] or feature.mat.shape[0] > search_area.shape[0]):
            logger.error(
                f'feature template {category_name} {box.name if box else ""} size greater than search area {feature.mat.shape} > {search_area.shape}')

        result = cv2.matchTemplate(search_area, template, match_method,
                                   mask=mask)

        if screenshot:
            logger.info(f'template matching screenshot match_method:{match_method} canny:{canny_lower, canny_higher}')
            communicate.screenshot.emit(mat, "mat", True, None)
            communicate.screenshot.emit(search_area, "search_area", False, box)
            communicate.screenshot.emit(template, "template", False, None)

        # Define a threshold for acceptable matches
        locations = filter_and_sort_matches(result, threshold, feature_width, feature_height)
        boxes = []

        for loc in locations:  # Iterate through found locations
            x, y = loc[0][0] + search_x1, loc[0][1] + search_y1
            confidence = 1.0 if math.isinf(loc[1]) and loc[1] > 0 else loc[1]
            boxes.append(Box(x, y, feature_width, feature_height, confidence, category_name))

        boxes = sort_boxes(boxes)
        if category_name:
            communicate.emit_draw_box(category_name, boxes, "red")
            search_name = "search_" + category_name
            communicate.emit_draw_box(search_name,
                                      Box(search_x1, search_y1, search_x2 - search_x1, search_y2 - search_y1,
                                          name=search_name), "blue")
        return boxes

    def find_feature(self, mat: np.ndarray, category_name, horizontal_variance: float = 0,
                     vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x=-1, y=-1,
                     to_x=-1, to_y=-1, width=-1, height=-1, box=None, canny_lower=0, canny_higher=0,
                     frame_processor=None, template=None, mask_function=None, match_method=cv2.TM_CCOEFF_NORMED,
                     screenshot=False):
        """
        Find a feature within a given variance.

        Args:
            mat (np.ndarray): The image in which to find the feature.
            category_name (str): The category name of the feature to find.
            horizontal_variance (float): Allowed horizontal variance as a percentage of width.
            vertical_variance (float): Allowed vertical variance as a percentage of height.
            threshold (float): Allowed confidence threshold for the feature.
            use_gray_scale (bool): If True, convert image to grayscale before finding the feature.

        Returns:
            List[Box]: A list of boxes where the feature is found.
        """
        if type(category_name) is list:
            results = []
            for cn in category_name:
                results += self.find_one_feature(mat=mat, category_name=cn,
                                                 horizontal_variance=horizontal_variance,
                                                 vertical_variance=vertical_variance, threshold=threshold,
                                                 use_gray_scale=use_gray_scale, x=x, y=y,
                                                 to_x=to_x, to_y=to_y, width=width, height=height, box=box,
                                                 canny_lower=canny_lower, canny_higher=canny_higher,
                                                 frame_processor=frame_processor,
                                                 template=template, mask_function=mask_function,
                                                 match_method=match_method, screenshot=screenshot)
            return sort_boxes(results)
        else:
            return self.find_one_feature(mat=mat, category_name=category_name,
                                         horizontal_variance=horizontal_variance,
                                         vertical_variance=vertical_variance, threshold=threshold,
                                         use_gray_scale=use_gray_scale, x=x, y=y,
                                         to_x=to_x, to_y=to_y, width=width, height=height, box=box,
                                         canny_lower=canny_lower, canny_higher=canny_higher,
                                         frame_processor=frame_processor,
                                         template=template, mask_function=mask_function, match_method=match_method,
                                         screenshot=screenshot)


class BaseInteraction:

    def __init__(self, capture):
        self.capture = capture

    def should_capture(self):
        return True

    def send_key(self, key, down_time=0.02):
        logger.debug(f'Sending key {key}')

    def send_key_down(self, key):
        pass

    def send_key_up(self, key):
        pass

    def move(self, x, y):
        pass

    def swipe(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
        pass

    def click(self, x=-1, y=-1, move_back=False, name=None, move=move, down_time=0.05, key="left"):
        pass

    def on_run(self):
        pass

    def input_text(self, text):
        pass

    def back(self, after_sleep=0):
        self.send_key('esc')
        if after_sleep > 0:
            time.sleep(after_sleep)

    def scroll(self, x, y, scroll_amount):
        pass

    def on_destroy(self):
        pass


class PyDirectInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        pydirectinput.FAILSAFE = False
        self.hwnd_window = hwnd_window
        self.check_clickable = True
        if not is_admin():
            logger.error(f"You must be an admin to use Win32Interaction")

    def clickable(self):
        if self.check_clickable:
            return self.hwnd_window.is_foreground()
        else:
            return True

    def send_key(self, key, down_time=0.01):
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyDown(str(key))
        time.sleep(down_time)
        pydirectinput.keyUp(str(key))

    def send_key_down(self, key):
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyDown(str(key))

    def scroll(self, x, y, scroll_amount):
        import mouse
        if scroll_amount < 0:
            sign = -1
        elif scroll_amount > 0:
            sign = 1
        else:
            sign = 0
        # abs_x, abs_y = self.capture.get_abs_cords(x, y)
        # click_pos = win32api.MAKELONG(x, y)
        logger.debug(f'pydirect do_scroll {x}, {y}, {scroll_amount}')
        self.move(x, y)
        time.sleep(0.001)
        for i in range(abs(scroll_amount)):
            mouse.wheel(sign)
            time.sleep(0.001)
        # mouse.wheel(scroll_amount)
        time.sleep(0.02)

    def send_key_up(self, key):
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyUp(str(key))

    def move(self, x, y):
        import mouse
        if not self.clickable():
            return
        x, y = self.capture.get_abs_cords(x, y)
        mouse.move(x, y)

    def swipe(self, x1, y1, x2, y2, duration, after_sleep=0.1, settle_time=0):
        # Convert coordinates to integers
        x1, y1 = self.capture.get_abs_cords(x1, y1)
        x2, y2 = self.capture.get_abs_cords(x2, y2)

        # Move the mouse to the start point (x1, y1)
        pydirectinput.moveTo(x1, y1)
        time.sleep(0.1)  # Pause for a moment

        # Press the left mouse button down
        pydirectinput.mouseDown()

        # Calculate the relative movement (dx, dy)
        dx = x2 - x1
        dy = y2 - y1

        # Calculate the number of steps
        steps = int(duration / 100)  # 100 steps per second

        # Calculate the step size
        step_dx = dx / steps
        step_dy = dy / steps

        # Move the mouse to the end point (x2, y2) in small steps
        for i in range(steps):
            pydirectinput.moveTo(x1 + int(i * step_dx), y1 + int(i * step_dy))
            time.sleep(0.01)  # Sleep for 10ms
        if after_sleep > 0:
            time.sleep(after_sleep)
        # Release the left mouse button
        pydirectinput.mouseUp()

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=False, key="left"):
        super().click(x, y, name=name)
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return
        # Convert the x, y position to lParam
        # lParam = win32api.MAKELONG(x, y)
        current_x, current_y = -1, -1
        if move_back:
            current_x, current_y = pydirectinput.position()
        import mouse
        if x != -1 and y != -1:
            x, y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {x, y}")
            mouse.move(x, y)
        mouse.click(key)
        if current_x != -1 and current_y != -1:
            mouse.move(current_x, current_y)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return
        if x != -1 and y != -1:
            x, y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {x, y}")
            pydirectinput.moveTo(x, y)
        button = self.get_mouse_button(key)
        pydirectinput.mouseDown(button=button)

    def get_mouse_button(self, key):
        button = pydirectinput.LEFT if key == "left" else pydirectinput.RIGHT
        return button

    def mouse_up(self, key="left"):
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return
        button = self.get_mouse_button(key)
        pydirectinput.mouseUp(button=button)

    def should_capture(self):
        return self.clickable()

    def on_run(self):
        self.hwnd_window.bring_to_front()


class PynputInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self.check_clickable = True
        if not is_admin():
            logger.error(f"You must be an admin to use PynputInteraction")

    def clickable(self):
        if self.check_clickable:
            return self.hwnd_window.is_foreground()
        else:
            return True

    def _parse_key(self, key):
        from pynput import keyboard
        try:
            return keyboard.Key[key.lower()]
        except KeyError:
            return key

    def send_key(self, key, down_time=0.01):
        from pynput import keyboard
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return

        controller = keyboard.Controller()
        parsed_key = self._parse_key(str(key))
        controller.press(parsed_key)
        time.sleep(down_time)
        controller.release(parsed_key)

    def send_key_down(self, key):
        from pynput import keyboard
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return

        controller = keyboard.Controller()
        parsed_key = self._parse_key(str(key))
        controller.press(parsed_key)

    def send_key_up(self, key):
        from pynput import keyboard
        if not self.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return

        controller = keyboard.Controller()
        parsed_key = self._parse_key(str(key))
        controller.release(parsed_key)

    def scroll(self, x, y, scroll_amount):
        from pynput import mouse
        if scroll_amount < 0:
            sign = -1
        elif scroll_amount > 0:
            sign = 1
        else:
            sign = 0
        logger.debug(f'pynput do_scroll {x}, {y}, {scroll_amount}')
        self.move(x, y)
        time.sleep(0.001)

        controller = mouse.Controller()
        for i in range(abs(scroll_amount)):
            controller.scroll(0, sign)
            time.sleep(0.001)
        time.sleep(0.02)

    def move(self, x, y):
        from pynput import mouse
        if not self.clickable():
            return

        abs_x, abs_y = self.capture.get_abs_cords(x, y)
        controller = mouse.Controller()
        controller.position = (abs_x, abs_y)

    def swipe(self, x1, y1, x2, y2, duration, after_sleep=0.1, settle_time=0):
        from pynput import mouse
        x1, y1 = self.capture.get_abs_cords(x1, y1)
        x2, y2 = self.capture.get_abs_cords(x2, y2)

        controller = mouse.Controller()
        controller.position = (x1, y1)
        time.sleep(0.1)

        controller.press(mouse.Button.left)

        dx = x2 - x1
        dy = y2 - y1

        steps = int(duration / 100)
        if steps <= 0:
            steps = 1

        step_dx = dx / steps
        step_dy = dy / steps

        for i in range(steps):
            controller.position = (x1 + int(i * step_dx), y1 + int(i * step_dy))
            time.sleep(0.01)
        controller.position = (x2, y2)

        if after_sleep > 0:
            time.sleep(after_sleep)

        controller.release(mouse.Button.left)

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=False, key="left"):
        from pynput import mouse
        super().click(x, y, name=name)
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return

        controller = mouse.Controller()
        current_pos = None
        if move_back:
            current_pos = controller.position

        if x != -1 and y != -1:
            abs_x, abs_y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {abs_x, abs_y}")
            controller.position = (abs_x, abs_y)
            time.sleep(0.02)

        button = self.get_mouse_button(key)
        controller.press(button)
        time.sleep(down_time)
        controller.release(button)

        if current_pos:
            controller.position = current_pos

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        from pynput import mouse
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return

        controller = mouse.Controller()
        if x != -1 and y != -1:
            abs_x, abs_y = self.capture.get_abs_cords(x, y)
            logger.info(f"mouse_down {abs_x, abs_y}")
            controller.position = (abs_x, abs_y)
            time.sleep(0.02)

        button = self.get_mouse_button(key)
        controller.press(button)

    def get_mouse_button(self, key):
        from pynput import mouse
        if key == "right":
            return mouse.Button.right
        if key == "middle":
            return mouse.Button.middle
        return mouse.Button.left

    def mouse_up(self, key="left"):
        from pynput import mouse
        if not self.clickable():
            logger.info(f"window in background, not clickable")
            return

        controller = mouse.Controller()
        button = self.get_mouse_button(key)
        controller.release(button)

    def should_capture(self):
        return self.clickable()

    def on_run(self):
        self.hwnd_window.bring_to_front()


# can interact with background windows, some games support it, like wuthering waves
class PostMessageInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        self.mouse_pos = (0, 0)
        self.last_activate = 0
        self.activate_interval = 1
        self.lparam = 0x1e0001
        self.activated = False
        self.hwnd_window.visible_monitors.append(self)

    @property
    def hwnd(self):
        return self.hwnd_window.hwnd

    def on_visible(self, visible):
        if visible:
            self.activated = False

    def send_key(self, key, down_time=0.01):
        super().send_key(key, down_time)
        self.send_key_down(key)
        time.sleep(down_time)
        self.send_key_up(key)

    def send_key_down(self, key, activate=True):
        if activate:
            self.try_activate()
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYDOWN, vk_code, self.lparam)

    def send_key_up(self, key):
        # logger.debug(f'send_key_up {key}')
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYUP, vk_code, self.lparam)

    def get_key_by_str(self, key):
        key = str(key)
        if key_code := vk_key_dict.get(key.upper()):
            vk_code = key_code
        else:
            vk_code = win32api.VkKeyScan(key)
        return vk_code

    def input_text(self, text, activate=True):
        if activate:
            self.try_activate()
        for c in text:
            self.post(win32con.WM_CHAR,
                      ord(c), 0)
            time.sleep(0.01)

    def move(self, x, y, down_btn=0):
        long_pos = self.update_mouse_pos(x, y, True)
        self.post(win32con.WM_MOUSEMOVE, down_btn, long_pos)

    def scroll(self, x, y, scroll_amount):
        self.try_activate()
        # Calculate the wParam
        # Positive scroll_amount indicates scroll up, negative is scroll down
        logger.debug(f'scroll {x}, {y}, {scroll_amount}')
        if x > 0 and y > 0:
            long_position = self.update_mouse_pos(x, y)
        else:
            long_position = 0
        wParam = win32api.MAKELONG(0, win32con.WHEEL_DELTA * scroll_amount)
        # Send the WM_MOUSEWHEEL message
        self.post(win32con.WM_MOUSEWHEEL, wParam, long_position)

    def post(self, message, wParam=0, lParam=0):
        win32gui.PostMessage(self.hwnd, message, wParam, lParam)

    def swipe(self, x1, y1, x2, y2, duration=3, after_sleep=0.1, settle_time=0):
        # Move the mouse to the start point (x1, y1)
        self.move(x1, y1)
        time.sleep(0.1)  # Pause for a moment

        # Press the left mouse button down
        self.mouse_down(x1, y1)

        # Calculate the relative movement (dx, dy)
        dx = x2 - x1
        dy = y2 - y1

        # Calculate the number of steps
        steps = int(duration / 100)  # 100 steps per second

        # Calculate the step size
        step_dx = dx / steps
        step_dy = dy / steps

        # Move the mouse to the end point (x2, y2) in small steps
        for i in range(steps):
            self.move(x1 + int(i * step_dx), y1 + int(i * step_dy), down_btn=win32con.MK_LBUTTON)
            time.sleep(0.01)  # Sleep for 10ms
        if after_sleep > 0:
            time.sleep(after_sleep)
        # Release the left mouse button
        self.mouse_up()

    def activate(self):
        self.post(win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)

    def deactivate(self):
        self.post(win32con.WM_ACTIVATE, win32con.WA_INACTIVE, 0)

    def try_activate(self):
        if not self.activated:
            if not self.hwnd_window.is_foreground():
                self.activated = True
                self.activate()

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=True, key="left"):
        super().click(x, y, name=name)
        if move:
            self.move(x, y)
            time.sleep(down_time)
        long_position = self.update_mouse_pos(x, y, activate=not move)

        if key == "left":
            btn_down = win32con.WM_LBUTTONDOWN
            btn_mk = win32con.MK_LBUTTON
            btn_up = win32con.WM_LBUTTONUP
        elif key == "middle":
            btn_down = win32con.WM_MBUTTONDOWN
            btn_mk = win32con.MK_MBUTTON
            btn_up = win32con.WM_MBUTTONUP
        else:
            btn_down = win32con.WM_RBUTTONDOWN
            btn_mk = win32con.MK_RBUTTON
            btn_up = win32con.WM_RBUTTONUP

        self.post(btn_down, btn_mk, long_position
                  )
        time.sleep(down_time)
        self.post(btn_up, 0, long_position
                  )

    def right_click(self, x=-1, y=-1, move_back=False, name=None):
        super().right_click(x, y, name=name)
        long_position = self.update_mouse_pos(x, y)
        self.post(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, long_position)
        self.post(win32con.WM_RBUTTONUP, 0, long_position)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        long_position = self.update_mouse_pos(x, y)
        action = win32con.WM_LBUTTONDOWN if key == "left" else win32con.WM_RBUTTONDOWN
        btn = win32con.MK_LBUTTON if key == "left" else win32con.MK_RBUTTON
        self.post(action, btn, long_position)

    def update_mouse_pos(self, x, y, activate=True):
        self.try_activate()
        if x == -1 or y == -1:
            x, y = self.mouse_pos
        else:
            self.mouse_pos = (x, y)
        # logger.debug(f'mouse_pos: {x, y}')
        return win32api.MAKELONG(x, y)

    def mouse_up(self, key="left"):
        action = win32con.WM_LBUTTONUP if key == "left" else win32con.WM_RBUTTONUP
        self.post(action, 0,
                  win32api.MAKELONG(self.mouse_pos[0], self.mouse_pos[1]))

    def should_capture(self):
        return True


import win32con

vk_key_dict = {
    'F1': win32con.VK_F1,
    'F2': win32con.VK_F2,
    'F3': win32con.VK_F3,
    'F4': win32con.VK_F4,
    'F5': win32con.VK_F5,
    'F6': win32con.VK_F6,
    'F7': win32con.VK_F7,
    'F8': win32con.VK_F8,
    'F9': win32con.VK_F9,
    'F10': win32con.VK_F10,
    'F11': win32con.VK_F11,
    'F12': win32con.VK_F12,
    'ESC': win32con.VK_ESCAPE,
    'ALT': win32con.VK_MENU,
    'CONTROL': win32con.VK_CONTROL,
    'SHIFT': win32con.VK_SHIFT,
    'TAB': win32con.VK_TAB,
    'ENTER': win32con.VK_RETURN,
    'SPACE': win32con.VK_SPACE,
    'LEFT': win32con.VK_LEFT,
    'UP': win32con.VK_UP,
    'RIGHT': win32con.VK_RIGHT,
    'DOWN': win32con.VK_DOWN,
    # Add more keys as needed
}


class DoNothingInteraction(BaseInteraction):
    pass


class ADBInteraction(BaseInteraction):

    def __init__(self, device_manager, capture, device_width, device_height):
        super().__init__(capture)
        self.device_manager = device_manager
        self._u2 = None
        self._u2_device = None
        self.use_u2 = importlib.util.find_spec("uiautomator2")

    def send_key(self, key, down_time=0.02, after_sleep=0):
        self.device_manager.device.shell(f"input keyevent {key}")
        if after_sleep > 0:
            time.sleep(after_sleep)

    def input_text(self, text):
        # Convert each character to its Unicode code point
        # unicode_code_points = [ord(char) for char in text]
        #
        # # Iterate over the Unicode code points and send input key events
        # for code_point in unicode_code_points:
        self.device_manager.shell(f"input text {text}")

    @property
    def u2(self):
        if self._u2 is None or self._u2_device != self.device_manager.device:
            logger.info(f'init u2 device')
            import uiautomator2
            self._u2_device = self.device_manager.device
            self._u2 = uiautomator2.connect(self._u2_device)
        return self._u2

    def swipe_nemu(self, from_x, from_y, to_x, to_y, duration, after_sleep=0.1, settle_time=0):
        p2 = (to_x, to_y)
        points = insert_swipe(p0=(from_x, from_y), p3=p2)

        for point in points:
            self.capture.nemu_impl.down(*point)
            time.sleep(0.010)

        start = time.time()
        while time.time() - start < settle_time:
            self.capture.nemu_impl.down(*p2)
            time.sleep(0.140)

        self.capture.nemu_impl.up()

        time.sleep(0.1)

    def swipe_u2(self, from_x, from_y, to_x, to_y, duration, after_sleep=0.1, settle_time=0):
        """
        Performs a swipe gesture using low-level touch events, allowing
        a pause ('settle_time') at the end point before lifting the touch.
        Note: The 'duration' parameter has limited effect on the actual
        movement speed when using basic touch.down/move/up events.
        The move itself is typically fast.
        Args:
            from_x (int): Starting X coordinate.
            from_y (int): Starting Y coordinate.
            to_x (int): Ending X coordinate.
            to_y (int): Ending Y coordinate.
            duration (float): Intended duration of the swipe (limited effect).
            settle_time (float): Seconds to pause at (to_x, to_y) before touch up.
        """
        # Touch down at the starting point
        self.u2.touch.down(from_x, from_y)
        # Optional small delay after touching down before starting move
        time.sleep(0.02)
        dx = to_x - from_x
        dy = to_y - from_y
        steps = int(max(abs(dx), abs(dy)) / 16)
        logger.debug(f'swipe steps: {steps}')
        for i in range(1, steps + 1):
            progress = i / steps
            current_x = int(from_x + dx * progress)
            current_y = int(from_y + dy * progress)
            self.u2.touch.move(current_x, current_y)
            # Sleep between steps (except potentially the last one before settle)
            if i < steps - 5:
                time.sleep(0.001)
            else:
                time.sleep(0.005)
        # Move to the ending point (move itself is usually quick)
        self.u2.touch.move(to_x, to_y)
        # Pause for settle_time seconds *before* lifting the finger
        if settle_time > 0:
            time.sleep(settle_time)
        # Lift the touch up at the ending point
        self.u2.touch.up(to_x, to_y)

    def swipe(self, from_x, from_y, to_x, to_y, duration, after_sleep=0.1, settle_time=0):
        if isinstance(self.capture, NemuIpcCaptureMethod):
            self.swipe_nemu(from_x, from_y, to_x, to_y, duration, after_sleep, settle_time)
        elif self.use_u2:
            self.swipe_u2(from_x, from_y, to_x, to_y, duration, after_sleep, settle_time)
        else:
            self.device_manager.device.shell(
                f"input swipe {round(from_x)} {round(from_y)} {round(to_x)} {round(to_y)} {duration}")
        if after_sleep > 0:
            time.sleep(after_sleep)

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=True, key=None):
        super().click(x, y, name=name)
        x = round(x)
        y = round(y)
        if isinstance(self.capture, NemuIpcCaptureMethod):
            self.capture.nemu_impl.click_nemu_ipc(x, y)
        else:
            self.device_manager.shell(f"input tap {x} {y}")

    def back(self, after_sleep=0):
        self.send_key('KEYCODE_BACK', after_sleep=after_sleep)


# Define the MOUSEINPUT structure
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


# Define the INPUT structure
class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("mi", MOUSEINPUT)]


# Define the SendInput function
SendInput = ctypes.windll.user32.SendInput
SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
SendInput.restype = ctypes.c_uint


class GenshinInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        self.post_interaction = PostMessageInteraction(capture, hwnd_window)
        self.hwnd_window = hwnd_window
        self.hwnd_window.visible_monitors.append(self)
        self.user32 = ctypes.windll.user32
        self.cursor_position = None

    @property
    def hwnd(self):
        return self.hwnd_window.hwnd

    def do_post_scroll(self, x, y, scroll_amount):
        # Calculate the wParam
        # Positive scroll_amount indicates scroll up, negative is scroll down
        logger.debug(f'scroll {x}, {y}, {scroll_amount}')
        if x > 0 and y > 0:
            long_position = self.make_mouse_position(x, y)
        else:
            long_position = 0
        wParam = win32api.MAKELONG(0, win32con.WHEEL_DELTA * scroll_amount)
        # Send the WM_MOUSEWHEEL message
        self.post(win32con.WM_MOUSEWHEEL, wParam, long_position)

    def do_send_key(self, key, down_time=0.02):
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYDOWN, vk_code, 0x1e0001)
        if down_time > 0.1:
            time.sleep(down_time)
        else:
            self.post(win32con.WM_CHAR, vk_code, 0x1e0001)
        self.post(win32con.WM_KEYUP, vk_code, 0xc01e0001)
        if down_time <= 0.1:
            time.sleep(down_time)
        else:
            time.sleep(0.02)

    def operate(self, fun, block=False):
        bg = not self.hwnd_window.is_foreground()
        result = None
        if bg:
            if block:
                self.block_input()
            self.cursor_position = win32api.GetCursorPos()
            self.activate()
        try:
            result = fun()
        except Exception as e:
            logger.error(f'operate exception', e)
        if bg:
            self.deactivate()
            time.sleep(0.02)
            win32api.SetCursorPos(self.cursor_position)
            if block:
                self.unblock_input()
        return result

    def send_key(self, key, down_time=0.02):
        logger.debug(f'GenshinInteraction send key {key} {down_time}')
        # self.do_send_key(key)
        self.operate(lambda: self.do_send_key(key, down_time))

    def block_input(self):
        self.user32.BlockInput(True)

    def unblock_input(self):
        self.user32.BlockInput(False)

    def send_key_down(self, key):
        current_position = win32api.GetCursorPos()
        self.post_interaction.activate()
        self.post_interaction.send_key_down(key)
        win32api.SetCursorPos(current_position)

    def do_send_key_down(self, key):
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYDOWN, vk_code, 0x1e0001)
        self.post(win32con.WM_CHAR, vk_code, 0x1e0001)

    def do_send_key_up(self, key):
        vk_code = self.get_key_by_str(key)
        self.post(win32con.WM_KEYUP, vk_code, 0xc01e0001)

    def send_key_up(self, key):
        logger.debug(f'send_key_up {key}')
        vk_code = self.get_key_by_str(key)
        self.deactivate()

    def get_key_by_str(self, key):
        key = str(key)
        if key_code := vk_key_dict.get(key.upper()):
            vk_code = key_code
        else:
            vk_code = win32api.VkKeyScan(key)
        return vk_code

    def move(self, x, y, down_btn=0):
        long_pos = self.update_mouse_pos(x, y, True)
        self.post(win32con.WM_MOUSEMOVE, down_btn, long_pos)

    def middle_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01):
        self.operate(lambda: self.do_middle_click(x, y, move_back, name, down_time))

    def do_scroll(self, x, y, scroll_amount):
        import mouse
        if scroll_amount < 0:
            sign = -1
        elif scroll_amount > 0:
            sign = 1
        else:
            sign = 0
        abs_x, abs_y = self.capture.get_abs_cords(x, y)
        click_pos = win32api.MAKELONG(x, y)
        logger.debug(f'do_scroll {x}, {y}, {click_pos} {scroll_amount}')
        win32api.SetCursorPos((abs_x, abs_y))
        time.sleep(0.1)
        for i in range(abs(scroll_amount)):
            mouse.wheel(sign)
            time.sleep(0.001)
        # mouse.wheel(scroll_amount)
        time.sleep(0.1)

    def scroll(self, x, y, scroll_amount):
        return self.operate(lambda: self.do_scroll(x, y, scroll_amount), block=True)

    def post(self, message, wParam=0, lParam=0):
        win32gui.PostMessage(self.hwnd, message, wParam, lParam)

    def swipe(self, x1, y1, x2, y2, duration=3, after_sleep=0, settle_time=0.1):
        # Move the mouse to the start point (x1, y1)
        logger.debug(f'genshin swipe start {x1, y1, x2, y2}')
        self.move(x1, y1)
        time.sleep(0.1)  # Pause for a moment

        # Press the left mouse button down
        self.mouse_down(x1, y1)

        # Calculate the relative movement (dx, dy)
        dx = x2 - x1
        dy = y2 - y1

        # Calculate the number of steps
        steps = int(duration / 100)  # 100 steps per second

        # Calculate the step size
        step_dx = dx / steps
        step_dy = dy / steps

        # Move the mouse to the end point (x2, y2) in small steps
        for i in range(steps):
            self.move(x1 + int(i * step_dx), y1 + int(i * step_dy), down_btn=win32con.MK_LBUTTON)
            time.sleep(0.01)  # Sleep for 10ms
        if settle_time > 0:
            time.sleep(settle_time)
        # Release the left mouse button
        self.mouse_up()
        logger.debug(f'genshin swipe end {x1, y1, x2, y2}')

    def activate(self):
        logger.debug(f'GenshinInteraction activate {self.hwnd}')
        self.hwnd_window.to_handle_mute = False
        self.post_interaction.activate()

    def deactivate(self):
        logger.debug('GenshinInteraction deactivate')
        self.post_interaction.deactivate()
        self.hwnd_window.to_handle_mute = True

    def try_activate(self):
        if not self.hwnd_window.is_foreground():
            self.activate()

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02, move=True, key="left"):
        self.operate(lambda: self.do_click(x, y, down_time=down_time, key=key), block=True)

    def do_middle_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02):
        self.do_click(x, y, move_back, name, down_time, key="middle")

    def do_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02, move=True, key="left"):
        click_pos = self.make_mouse_position(x, y)
        logger.debug(f'click {x}, {y}, {click_pos} {down_time}')
        if key == "left":
            btn_down = win32con.WM_LBUTTONDOWN
            btn_mk = win32con.MK_LBUTTON
            btn_up = win32con.WM_LBUTTONUP
        elif key == "middle":
            btn_down = win32con.WM_MBUTTONDOWN
            btn_mk = win32con.MK_MBUTTON
            btn_up = win32con.WM_MBUTTONUP
        else:
            btn_down = win32con.WM_RBUTTONDOWN
            btn_mk = win32con.MK_RBUTTON
            btn_up = win32con.WM_RBUTTONUP
        self.post(btn_down, btn_mk, click_pos
                  )
        self.post(btn_up, 0, click_pos
                  )
        time.sleep(down_time)

    def do_mouse_up(self, x=-1, y=-1, move_back=False, move=True, btn=None):
        if btn is None:
            btn = win32con.WM_LBUTTONUP
        elif btn == 'right':
            btn = win32con.WM_RBUTTONUP
        click_pos = win32api.MAKELONG(x, y)
        logger.debug(f'do_mouse_up {x}, {y}, {click_pos}')
        self.post(btn, 0, click_pos
                  )

    def right_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02):
        self.do_click(x, y, move_back, name, down_time, key="right")

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        self.operate(lambda: self.do_mouse_down(x, y, name, key))

    def do_mouse_down(self, x=-1, y=-1, name=None, key="left"):
        click_pos = self.make_mouse_position(x, y)
        action = win32con.WM_LBUTTONDOWN if key == "left" else win32con.WM_RBUTTONDOWN
        btn = win32con.MK_LBUTTON if key == "left" else win32con.MK_RBUTTON
        self.post(action, btn, click_pos
                  )

    def make_mouse_position(self, x, y):
        if x < 0:
            click_pos = win32api.MAKELONG(round(self.capture.width * 0.5), round(self.capture.height * 0.5))
        else:
            abs_x, abs_y = self.capture.get_abs_cords(x, y)
            click_pos = win32api.MAKELONG(x, y)
        if x >= 0:
            win32api.SetCursorPos((abs_x, abs_y))
            time.sleep(0.001)
        return click_pos

    def do_mouse_up(self, x=-1, y=-1, key="left"):
        click_pos = self.make_mouse_position(x, y)
        logger.debug(f'click {x}, {y}, {click_pos}')
        action = win32con.WM_LBUTTONUP if key == "left" else win32con.WM_RBUTTONUP
        self.post(action, 0, click_pos
                  )

    def update_mouse_pos(self, x, y, activate=True):
        self.try_activate()
        if x == -1 or y == -1:
            x, y = self.mouse_pos
        else:
            self.mouse_pos = (x, y)
        # logger.debug(f'mouse_pos: {x, y}')
        return win32api.MAKELONG(x, y)

    def mouse_up(self, x=-1, y=-1, key="left"):
        self.operate(lambda: self.do_mouse_up(x, y, key))

    def should_capture(self):
        return True

    def on_visible(self, visible):
        """
        Your custom function to be executed when the window becomes active.

        Args:
            hwnd: The handle of the window that became active.
        """
        logger.debug(f"on_visible {visible}")
        if visible:
            self.post_interaction.activate()

    def on_destroy(self):
        logger.info('GenshinInteraction on_destroy')
        self.hwnd_window.bring_to_front()
        self.activate()

    def move_mouse_relative(self, dx, dy):
        self.operate(lambda: self.do_move_mouse_relative(dx, dy), block=True)

    def do_move_mouse_relative(self, dx, dy):
        """
        Moves the mouse cursor relative to its current position using user32.SendInput.

        Args:
            dx: The number of pixels to move the mouse horizontally (positive for right, negative for left).
            dy: The number of pixels to move the mouse vertically (positive for down, negative for up).
        """

        mi = MOUSEINPUT(dx, dy, 0, 1, 0, None)
        i = INPUT(0, mi)  # type=0 indicates a mouse event
        SendInput(1, ctypes.pointer(i), ctypes.sizeof(INPUT))


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


class ForegroundPostMessageInteraction(GenshinInteraction):
    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture, hwnd_window)
        pydirectinput.FAILSAFE = False
        self.check_clickable = True
        if not is_admin():
            logger.error(f"You must be an admin to use Win32Interaction")

    def clickable(self):
        if self.check_clickable:
            return self.hwnd_window.is_foreground()
        else:
            return True

    def should_capture(self):
        return self.clickable()

    def on_run(self):
        self.hwnd_window.bring_to_front()


def read_from_json(coco_json, width=-1, height=-1):
    feature_dict = {}
    box_dict = {}
    ok_compressed = None
    load_success = True
    data = load_json(coco_json)
    coco_folder = os.path.dirname(coco_json)
    logger.info(f"read_from_json {coco_folder} {coco_json}")

    # Create a map from image ID to file name
    image_map = {image['id']: image['file_name'] for image in data['images']}

    # Create a map from category ID to category name
    category_map = {category['id']: category['name'] for category in data['categories']}

    for image_id, file_name in image_map.items():
        # Load and scale the image
        image_path = str(os.path.join(coco_folder, file_name))
        if ok_compressed is None:
            with Image.open(image_path) as img:
                ok_compressed = 'ok_compressed' in img.info.keys()
        whole_image = cv2.imread(image_path)
        if whole_image is None:
            logger.error(f'Could not read image {image_path}')
            raise ValueError(f'Could not read image {image_path}')
        _, original_width = whole_image.shape[:2]
        image_height, image_width = whole_image.shape[:2]

        for annotation in data['annotations']:
            if image_id != annotation['image_id']:
                continue

            category_id = annotation['category_id']
            bbox = annotation['bbox']
            x, y, w, h = bbox

            # Crop the image to the bounding box
            image = whole_image[round(y):round(y + h), round(x):round(x + w), :3]

            x, y = round(x), round(y)
            h, w, _ = image.shape
            # Calculate the scaled bounding box

            # Store in featureDict using the category name
            category_name = category_map[category_id]

            x, y, w, h, scale = adjust_coordinates(x, y, w, h, width, height, image_width, image_height,
                                                   hcenter='hcenter' in category_name)

            image = cv2.resize(image, (w, h))

            logger.debug(
                f"loaded {category_name} resized width {width} / original_width:{original_width},scale_x:{width / original_width}")
            if category_name in feature_dict:
                raise ValueError(f"Multiple boxes found for category {category_name}")
            # if not category_name.startswith('box_'):
            feature_dict[category_name] = Feature(image, x, y, scale)
            box_dict[category_name] = Box(x, y, image.shape[1], image.shape[0], name=category_name)

    return feature_dict, box_dict, ok_compressed, load_success

def load_json(coco_json):
    with open(coco_json, 'r') as file:
        data = json.load(file)
        for images in data['images']:
            images['file_name'] = un_fk_label_studio_path(images['file_name'])
        return data

def un_fk_label_studio_path(path):
    # Check if the path is an absolute path
    if os.path.isabs(path):
        # Check if the path contains the "images" folder
        match = re.search(r'\\(images\\.*\.(jpg|png)$)', path)
        if match:
            # Extract the "images\\*.jpg" part
            return match.group(1).replace("images\\", "images/")
    return path

def adjust_coordinates(x, y, w, h, screen_width, screen_height, image_width, image_height, hcenter=False):
    # logger.debug(f'scaling images {screen_width}x{screen_height} {image_width}x{image_height} {x}, {y}, {w}, {h}')
    if screen_width != -1 and screen_height != -1 and (screen_width != image_width or screen_height != image_height):
        scale_x, scale_y = screen_width / image_width, screen_height / image_height
    else:
        scale_x, scale_y = 1, 1

    scale = min(scale_x, scale_y)
    w, h = round(w * scale), round(h * scale)

    if scale_x > scale_y:
        y = round(y * scale)
        x = scale_by_anchor(x, image_width, screen_width, scale, hcenter=hcenter)
    elif scale_x < scale_y:
        x = round(x * scale)
        y = scale_by_anchor(y, image_height, screen_height, scale, hcenter=hcenter)
    else:
        x, y = round(x * scale), round(y * scale)

    # logger.debug(f'scaled images {scale_x}, {scale_y} to {screen_width}x{screen_height} {x}, {y}, {w}, {h}')

    return x, y, w, h, scale

def scale_by_anchor(x, image_width, screen_width, scale, hcenter=False):
    if (x + image_width) / 2 > screen_width * 0.5:
        if hcenter:
            x = round(screen_width * 0.5 + (x - image_width * 0.5) * scale)
        else:
            x = screen_width - round((image_width - x) * scale)
    else:
        if hcenter:
            x = round(screen_width * 0.5 - (image_width * 0.5 - x) * scale)
        else:
            x = round(x * scale)
    return x

def replace_extension(filename):
    if filename.endswith('.jpg'):
        return filename[:-4] + '.png', True

def filter_and_sort_matches(result, threshold, w, h):
    # Find all matches above the confidence threshold
    loc = np.where(result >= threshold)
    matches = list(zip(*loc[::-1]))  # Convert to (x, y) coordinates

    # Get the match confidence scores
    confidences = result[result >= threshold]

    # Combine the coordinates and confidences, and sort by confidence in descending order
    matches_with_confidence = sorted(zip(matches, confidences), key=lambda x: x[1], reverse=True)

    # List to store selected matches
    selected_matches = []

    def is_overlapping(match, selected):
        x1, y1 = match
        for (x2, y2), _ in selected:
            if (x1 < x2 + w and x1 + w > x2 and y1 < y2 + h and y1 + h > y2):
                return True
        return False

    # Select non-overlapping matches
    for match, confidence in matches_with_confidence:
        if not is_overlapping(match, selected_matches):
            selected_matches.append((match, confidence))

    return selected_matches

def mask_white(image, lower_white=255):
    # Check if the image is grayscale
    if len(image.shape) == 2 or image.shape[2] == 1:
        # Image is grayscale
        lower_white = np.array([lower_white])
        upper_white = np.array([255])
    else:
        # Image is in color
        lower_white = np.array([lower_white, lower_white, lower_white])
        upper_white = np.array([255, 255, 255])

    # Create a mask for the white color
    return cv2.inRange(image, lower_white, upper_white)


class Feature:
    def __init__(self, mat: np.ndarray, x: int = 0, y: int = 0, scaling=1) -> None:
        """
        Initialize a Feature with an image (Mat) and its bounding box coordinates.

        Args:
            mat (np.ndarray): The OpenCV Mat object representing the image.
            x (int): The x-coordinate of the top-left corner of the bounding box.
            y (int): The y-coordinate of the top-left corner of the bounding box.
            width (int): The width of the bounding box.
            height (int): The height of the bounding box.
        """
        self.mat = mat
        self.scaling = scaling
        self.x = round(x)
        self.y = round(y)
        self.mask = None

    @property
    def width(self):
        return self.mat.shape[1]

    @property
    def height(self):
        return self.mat.shape[0]

    def scaling(self):
        return self.scaling

    def __str__(self) -> str:
        return str(f'self.x: {self.x}, self.y: {self.y}, width: {self.width}, height: {self.height}')


class MainWindow(MSFluentWindow):

    def __init__(self, app, config, ok_config, icon, title, version, debug=False, about=None, exit_event=None,
                 global_config=None):
        super().__init__()
        logger.info('main window __init__')
        self.app = app
        self.ok_config = ok_config
        self.basic_global_config = og.executor.global_config.get_config(basic_options)
        self.main_window_config = Config('main_window', {'last_version': 'v0.0.0'})
        self.original_layout = None
        self.exit_event = exit_event
        from ok.gui.start.StartTab import StartTab
        self.start_tab = StartTab(config, exit_event)
        self.onetime_tab = None
        self.trigger_tab = None
        self.version = version
        self.emulator_starting_dialog = None
        og.set_dpi_scaling(self)
        self.do_not_quit = False
        self.config = config
        self.shown = False

        communicate.restart_admin.connect(self.restart_admin)
        if config.get('show_update_copyright'):
            communicate.copyright.connect(self.show_update_copyright)
        qconfig.themeChanged.disconnect(self._updateBackgroundColor)

        self.addSubInterface(self.start_tab, FluentIcon.PLAY, self.tr('Capture'))

        if len(og.executor.onetime_tasks) > 0:
            from ok.gui.tasks.OneTimeTaskTab import OneTimeTaskTab
            self.onetime_tab = OneTimeTaskTab()
            self.first_task_tab = self.onetime_tab
            self.addSubInterface(self.onetime_tab, FluentIcon.BOOK_SHELF, self.tr('Tasks'))
        if len(og.executor.trigger_tasks) > 0:
            from ok.gui.tasks.TriggerTaskTab import TriggerTaskTab
            self.trigger_tab = TriggerTaskTab()
            if self.first_task_tab is None:
                self.first_task_tab = self.trigger_tab
            self.addSubInterface(self.trigger_tab, FluentIcon.ROBOT, self.tr('Triggers'))

        if custom_tabs := config.get('custom_tabs'):
            for tab in custom_tabs:
                tab_obj = init_class_by_name(tab[0], tab[1])
                tab_obj.executor = og.executor
                self.addSubInterface(tab_obj, tab_obj.icon, tab_obj.name)

        if debug:
            from ok.gui.debug.DebugTab import DebugTab
            debug_tab = DebugTab(config, exit_event)
            self.addSubInterface(debug_tab, FluentIcon.DEVELOPER_TOOLS, self.tr('Debug'),
                                 position=NavigationItemPosition.BOTTOM)

        from ok.gui.about.AboutTab import AboutTab
        self.about_tab = AboutTab(config, self.app.updater)
        self.addSubInterface(self.about_tab, FluentIcon.QUESTION, self.tr('About'),
                             position=NavigationItemPosition.BOTTOM)

        from ok.gui.settings.SettingTab import SettingTab
        self.setting_tab = SettingTab()
        self.addSubInterface(self.setting_tab, FluentIcon.SETTING, self.tr('Settings'),
                             position=NavigationItemPosition.BOTTOM)

        # Styling the tabs and content if needed, for example:
        dev = self.tr('Debug')
        profile = config.get('profile', "")
        self.setWindowTitle(f'{title} {version} {profile} {dev if debug else ""}')

        communicate.executor_paused.connect(self.executor_paused)
        communicate.tab.connect(self.navigate_tab)
        communicate.task_done.connect(self.activateWindow)
        communicate.must_update.connect(self.must_update)
        # Create a context menu for the tray
        menu = QMenu()
        exit_action = menu.addAction(self.tr("Exit"))
        exit_action.triggered.connect(self.tray_quit)

        self.tray = QSystemTrayIcon(icon, parent=self)

        # Set the context menu and show the tray icon
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_icon_activated)
        self.tray.show()
        self.tray.setToolTip(title)

        communicate.capture_error.connect(self.capture_error)
        communicate.notification.connect(self.show_notification)
        communicate.config_validation.connect(self.config_validation)
        communicate.starting_emulator.connect(self.starting_emulator)
        communicate.global_config.connect(self.goto_global_config)

        logger.info('main window __init__ done')

    def setMicaEffectEnabled(self, isEnabled: bool):
        pass

    def restart_admin(self):
        w = MessageBox(QCoreApplication.translate("app", "Alert"),
                       QCoreApplication.translate("StartController",
                                                  "PC version requires admin privileges, Please restart this app with admin privileges!"),
                       self.window())
        if w.exec():
            logger.info('restart_admin Yes button is pressed')
            thread = threading.Thread(target=restart_as_admin)
            thread.start()
            self.app.quit()

    def on_tray_icon_activated(self, reason):
        """Handles clicks on the system tray icon."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            logger.info('main window on_tray_icon_activated QSystemTrayIcon.ActivationReason.Trigger')
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            logger.info('main window on_tray_icon_activated QSystemTrayIcon.ActivationReason.MiddleClick')
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            logger.info(
                f'main window on_tray_icon_activated QSystemTrayIcon.ActivationReason.DoubleClick self.isVisible():{self.isVisible()}')
            self.showNormal()
            self.raise_()  # Raise the window to the top of the stacking order
            self.activateWindow()  # Give the window focus

    def _onThemeChangedFinished(self):
        pass

    def goto_global_config(self, key):
        self.switchTo(self.setting_tab)
        self.setting_tab.goto_config(key)

    def tray_quit(self):
        logger.info('main window tray_quit')
        self.app.quit()

    def must_update(self):
        logger.info('must_update show_window')
        title = self.tr('Update')
        content = QCoreApplication.translate('app', 'The current version {} must be updated').format(
            og.app.updater.starting_version)
        w = MessageBox(title, content, self.window())
        og.executor.pause()
        if w.exec():
            logger.info('Yes button is pressed')
            og.app.updater.run()
        else:
            logger.info('No button is pressed')
            self.app.quit()

    def show_ok(self):
        title = self.tr('Update')
        content = QCoreApplication.translate('app', 'The current version {} must be updated').format(
            og.app.updater.starting_version)
        w = MessageBox(title, content, self.window())

    def show_update_copyright(self):
        title = self.tr('Info')
        content = self.tr(
            "This is a free software. If you purchased this anywhere, request a refund from the seller.")
        from qfluentwidgets import Dialog
        w = Dialog(title, content, self.window())
        w.cancelButton.setVisible(False)
        w.setContentCopyable(True)
        w.exec()
        self.switchTo(self.about_tab)

    def showEvent(self, event):
        if event.type() == QEvent.Show and not self.shown:
            self.shown = True
            args = parse_arguments_to_map()
            pyappify.hide_pyappify()
            if update_pyappify := og.config.get("update_pyappify"):
                pyappify.upgrade(update_pyappify.get('to_version'), update_pyappify.get('sha256'),
                                 [update_pyappify.get('zip_url')], self.exit_event)
            logger.info(f"Window has fully displayed {args}")
            communicate.start_success.emit()
            if self.version != self.main_window_config.get('last_version'):
                self.main_window_config['last_version'] = self.version
                if not self.config.get('auth'):
                    logger.info('update success, show copyright')
                    og.handler.post(lambda: communicate.copyright.emit(), delay=1)
            if args.get('task') > 0:
                task_index = args.get('task') - 1
                logger.info(f'start with params {task_index} {args.get("exit")}')
                og.app.start_controller.start(args.get('task') - 1, exit_after=args.get('exit'))
            elif self.basic_global_config.get('Auto Start Game When App Starts'):
                og.app.start_controller.start()
        super().showEvent(event)

    def set_window_size(self, width, height, min_width, min_height):
        screen = QScreen.availableGeometry(self.screen())
        if (self.ok_config['window_width'] > 0 and self.ok_config['window_height'] > 0 and
                self.ok_config['window_y'] > 0 and self.ok_config['window_x'] > 0):
            x, y, width, height = (self.ok_config['window_x'], self.ok_config['window_y'],
                                   self.ok_config['window_width'], self.ok_config['window_height'])
            if self.ok_config['window_maximized']:
                self.setWindowState(Qt.WindowMaximized)
            else:
                self.setGeometry(x, y, width, height)
        else:
            x = int((screen.width() - width) / 2)
            y = int((screen.height() - height) / 2)
            self.setGeometry(x, y, width, height)

        self.setMinimumSize(QSize(min_width, min_height))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize or event.type() == QEvent.Move:
            og.handler.post(self.update_ok_config, remove_existing=True, skip_if_running=True, delay=1)
        return super().eventFilter(obj, event)

    def update_ok_config(self):
        if self.isMaximized():
            self.ok_config['window_maximized'] = True
        else:
            self.ok_config['window_maximized'] = False
            geometry = self.geometry()
            self.ok_config['window_x'] = geometry.x()
            self.ok_config['window_y'] = geometry.y()
            self.ok_config['window_width'] = geometry.width()
            self.ok_config['window_height'] = geometry.height()
        logger.info(f'Window geometry updated in ok_config {self.ok_config}')

    def starting_emulator(self, done, error, seconds_left):
        if error:
            self.switchTo(self.start_tab)
            alert_error(error, True)
        if done:
            if self.emulator_starting_dialog:
                self.emulator_starting_dialog.close()
        else:
            if self.emulator_starting_dialog is None:
                self.emulator_starting_dialog = StartLoadingDialog(seconds_left,
                                                                   self)
            else:
                self.emulator_starting_dialog.set_seconds_left(seconds_left)
            self.emulator_starting_dialog.show()

    def config_validation(self, message):
        title = self.tr('Error')
        InfoBar.error(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,  # won't disappear automatically
            parent=self.window()
        )
        self.tray.showMessage(title, message)

    def show_notification(self, message, title=None, error=False, tray=False, show_tab=None):
        from ok.gui.util.app import show_info_bar
        show_info_bar(self.window(), og.app.tr(message), og.app.tr(title), error)
        if tray:
            self.tray.showMessage(og.app.tr(title), og.app.tr(message),
                                  QSystemTrayIcon.Critical if error else QSystemTrayIcon.Information,
                                  5000)
            self.navigate_tab(show_tab)

    def capture_error(self):
        self.show_notification(self.tr('Please check whether the game window is selected correctly!'),
                               self.tr('Capture Error'), error=True)

    def navigate_tab(self, index):
        logger.debug(f'navigate_tab {index}')
        if index == "start":
            self.switchTo(self.start_tab)
        elif index == "onetime" and self.onetime_tab is not None:
            self.switchTo(self.onetime_tab)
        elif index == "trigger" and self.trigger_tab is not None:
            self.switchTo(self.trigger_tab)
        elif index == "about" and self.about_tab is not None:
            self.switchTo(self.about_tab)

    def executor_paused(self, paused):
        if not paused and self.stackedWidget.currentIndex() == 0:
            self.switchTo(self.first_task_tab)
        self.show_notification(self.tr("Start Success.") if not paused else self.tr("Pause Success."), tray=not paused)

    def closeEvent(self, event):
        if og.app.exit_event.is_set():
            logger.info("Window closed exit_event.is_set")
            event.accept()
            return
        else:
            logger.info(f"Window closed exit_event.is not set {self.do_not_quit}")
            to_tray = self.basic_global_config.get('Minimize Window to System Tray when Closing')
            if to_tray:
                event.ignore()  # Prevent the window from closing
                self.hide()
                return
            if not self.do_not_quit:
                pyappify.kill_pyappify()
                self.exit_event.set()
            event.accept()
            if not self.do_not_quit:
                QApplication.instance().exit()


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
                return None

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

        if reg_type != winreg.REG_SZ:
            logger.error(f"Warning: Expected REG_SZ, but got REG_TYPE {reg_type}. Returning None.")
            return None, None

        logger.debug(f'check global AutoHDROptOutApplicable {value}')
        return value == 1 or value == "1"

    except FileNotFoundError:
        # Key or value not found
        logger.error(f"Key '{key_path}' or value '{value_name}' not found.")
        return None, None
    except Exception as e:
        logger.error(f"Error reading DirectX User GPU Preferences: {e}")
        return None, None

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


class DiagnosisTask(BaseTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Diagnosis"
        self.description = "Performance Test"

    def run(self):
        start = time.time()
        capture_total = 0
        ocr_total = 0
        cpu_readings = []
        pid = os.getpid()
        process = psutil.Process(pid)
        cores = psutil.cpu_count(logical=True)
        while True:
            self.info['Frame Count'] = self.info.get('Frame Count', 0) + 1
            self.info['Process Frame Rate'] = round(
                self.info['Frame Count'] / ((time.time() - start) or 1),
                2)
            self.info['Capture Frame Rate'] = round(
                self.info['Frame Count'] / (capture_total or 1),
                2)
            self.info['Game Resolution'] = f'{self.frame.shape[1]}x{self.frame.shape[0]}'
            if self.info['Frame Count'] == 1:
                self.ocr()  # warm up
            operation_start = time.time()
            boxes = self.ocr(threshold=0.1)
            ocr_total += time.time() - operation_start
            self.info['Texts'] = ",".join(box.name for box in boxes)
            self.info['Capture Latency'] = f"{round(1000 * capture_total / self.info['Frame Count'], 2)} ms"
            self.info['OCR Latency'] = f"{round(1000 * ocr_total / self.info['Frame Count'], 2)} ms"
            if self.info['Frame Count'] % 20 == 1:
                rss, vms, _ = get_current_process_memory_usage()  # We don't care about shm here
                self.info['Memory'] = f'{round(rss)} MB'

            cpu_usage = process.cpu_percent(interval=0)
            cpu_readings.append(cpu_usage)
            cpu_readings = cpu_readings[-20:]

            self.info['CPU'] = f"{round(get_median(cpu_readings) / cores, 2)}%"

            operation_start = time.time()
            self.next_frame()
            capture_total += time.time() - operation_start


def get_median(my_list):
    if not my_list:  # Check if the list is empty
        return 0
    return statistics.median(my_list)

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

def get_language_fallbacks(locale_name: str) -> list[str]:
    """
    Generates a fallback list for a given locale name like 'en_US'.
    """
    # Use QLocale to parse the input and get language enum
    input_locale = QLocale(locale_name)
    target_language_enum = input_locale.language()

    # Get canonical names using QLocale for consistency
    target_name = input_locale.name()  # e.g., "en_US"
    base_lang_locale = QLocale(target_language_enum)  # Locale for just the language
    base_lang_code = base_lang_locale.name()  # e.g., "en"
    fallbacks = []
    processed = set()  # Keep track of added names to avoid duplicates
    # 1. Add the original locale name
    fallbacks.append(target_name)
    processed.add(target_name)
    # 2. Add the base language code if it's different
    if base_lang_code != target_name and base_lang_code not in processed:
        fallbacks.append(base_lang_code)
        processed.add(base_lang_code)
    try:
        all_countries = list(QLocale.Country)

        for country_enum in all_countries:
            # Skip AnyCountry as it would just recreate the base_lang_code
            if country_enum == QLocale.Country.AnyCountry:
                continue
            # Create locale for the target language + current country
            variant_locale = QLocale(target_language_enum, country_enum)
            variant_name = variant_locale.name()  # e.g., "en_GB"
            # Add if it's valid (not C locale) and not already added
            if variant_locale.language() != QLocale.Language.C and variant_name not in processed:
                fallbacks.append(variant_name)
                processed.add(variant_name)
    except Exception as e:
        logger.error(f"Warning: Could not iterate through QLocale.Country enums", e)
        # Continue without the extra variants if enum iteration fails
    return fallbacks

def insert_swipe(p0, p3, speed=15, min_distance=10):
    """
    Insert way point from start to end.
    First generate a cubic bézier curve

    Args:
        p0: Start point.
        p3: End point.
        speed: Average move speed, pixels per 10ms.
        min_distance:

    Returns:
        list[list[int]]: List of points.

    Examples:
        > insert_swipe((400, 400), (600, 600), speed=20)
        [[400, 400], [406, 406], [416, 415], [429, 428], [444, 442], [462, 459], [481, 478], [504, 500], [527, 522],
        [545, 540], [560, 557], [573, 570], [584, 582], [592, 590], [597, 596], [600, 600]]
    """
    p0 = np.array(p0)
    p3 = np.array(p3)

    # Random control points in Bézier curve
    distance = np.linalg.norm(p3 - p0)
    p1 = 2 / 3 * p0 + 1 / 3 * p3 + random_theta() * random_rho(distance * 0.1)
    p2 = 1 / 3 * p0 + 2 / 3 * p3 + random_theta() * random_rho(distance * 0.1)

    # Random `t` on Bézier curve, sparse in the middle, dense at start and end
    segments = max(int(distance / speed) + 1, 5)
    lower = random_normal_distribution(-85, -60)
    upper = random_normal_distribution(80, 90)
    theta = np.arange(lower + 0., upper + 0.0001, (upper - lower) / segments)
    ts = np.sin(theta / 180 * np.pi)
    ts = np.sign(ts) * abs(ts) ** 0.9
    ts = (ts - min(ts)) / (max(ts) - min(ts))

    # Generate cubic Bézier curve
    points = []
    prev = (-100, -100)
    for t in ts:
        point = p0 * (1 - t) ** 3 + 3 * p1 * t * (1 - t) ** 2 + 3 * p2 * t ** 2 * (1 - t) + p3 * t ** 3
        point = point.astype(int).tolist()
        if np.linalg.norm(np.subtract(point, prev)) < min_distance:
            continue

        points.append(point)
        prev = point

    # Delete nearing points
    if len(points[1:]):
        distance = np.linalg.norm(np.subtract(points[1:], points[0]), axis=1)
        mask = np.append(True, distance > min_distance)
        points = np.array(points)[mask].tolist()
        if len(points) <= 1:
            points = [p0, p3]
    else:
        points = [p0, p3]

    return points
