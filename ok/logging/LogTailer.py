import logging
import os
import threading
import time

from ok.gui.Communicate import communicate


class LogTailer(threading.Thread):
    def __init__(self, file_path, exit_event):
        super().__init__()
        self.file_path = file_path
        self.stop_event = threading.Event()
        self.exit_event = exit_event

        # Create the file if it doesn't exist
        if not os.path.exists(self.file_path):
            open(self.file_path, 'w').close()

    def run(self):
        with open(self.file_path, mode='r', encoding='utf-8') as file:
            # Move the pointer to the end of the file
            file.seek(0, os.SEEK_END)

            while not self.stop_event.is_set() and not self.exit_event.is_set():
                line = file.readline()
                if not line:
                    time.sleep(0.1)  # Sleep briefly to avoid busy-waiting
                    continue
                communicate.log.emit(get_log_level_number(line), line)

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
