import logging
import msvcrt
import os
import threading
import time

import win32file


class LogTailer(threading.Thread):
    def __init__(self, file_path, exit_event, listener):
        super().__init__()
        self.file_path = file_path
        self.stop_event = threading.Event()
        self.exit_event = exit_event
        self.listener = listener

        # Create the file if it doesn't exist
        if not os.path.exists(self.file_path):
            open(self.file_path, 'w').close()
            # Get a handle using Win32 API, specifying the shared access
        handle = win32file.CreateFile(
            self.file_path,
            win32file.GENERIC_READ,
            win32file.FILE_SHARE_DELETE | win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
            None,
            win32file.OPEN_EXISTING,
            0,
            None
        )

        # Detach the handle
        detached_handle = handle.Detach()

        # Get a file descriptor associated with the handle
        self.file_descriptor = msvcrt.open_osfhandle(detached_handle, os.O_RDONLY)

    def run(self):

        # Open the file descriptor
        with open(self.file_descriptor, mode='r', encoding='utf-8') as file:
            # Move the pointer to the end of the file
            file.seek(0, os.SEEK_END)

            while not self.stop_event.is_set() and not self.exit_event.is_set():
                line = file.readline()
                if not line:
                    time.sleep(0.1)  # Sleep briefly to avoid busy-waiting
                    continue
                self.listener(get_log_level_number(line), line)

    def stop(self):
        self.stop_event.set()


def get_log_level_number(log_message):
    log_levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    for level_name, level_number in log_levels.items():
        if level_name in log_message:
            return level_number
    return logging.INFO
