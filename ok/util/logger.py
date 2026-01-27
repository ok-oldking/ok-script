import argparse
import inspect
import logging
import os
import queue
import sys
import traceback
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
from typing import Optional

from ok.util.file import ensure_dir_for_file, get_relative_path

_ok_log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(threadName)s %(message)s')
_ok_logger = logging.getLogger("ok")


class Logger:
    def __init__(self, name: str):
        self.logger = _ok_logger
        self.name = name.split('.')[-1]

    def debug(self, message):
        self.logger.debug(f"{self.name}:{message}")

    def info(self, message):
        self.logger.info(f"{self.name}:{message}")

    def warning(self, message):
        self.logger.warning(f"{self.name}:{message}")

    def error(self, message, exception: Optional[Exception] = None):
        stack_trace_str = self.exception_to_str(exception)
        self.logger.error(f"{self.name}:{message} {stack_trace_str}")

    def critical(self, message):
        self.logger.critical(f"{self.name}:{message}")

    @staticmethod
    def call_stack() -> str:
        stack = ""
        for frame_info in inspect.stack():
            frame = frame_info.frame
            stack += (f"  File: {frame.f_code.co_filename}, "
                      f"Line: {frame.f_lineno}, "
                      f"Function: {frame.f_code.co_name}\n")
        return stack

    @staticmethod
    def get_logger(name: str):
        return Logger(name)

    @staticmethod
    def exception_to_str(exception: Exception) -> str:
        stack_trace_str = ""
        if exception is not None:
            try:
                stack_trace_str = traceback.format_exc()
            except Exception as e:
                stack_trace_str = f"Error formatting exception: {str(e)}"
        return stack_trace_str


def _log_exception_handler(exc_type, exc_value, exc_traceback):
    if _ok_logger is not None:
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        tb_text = ''.join(tb_lines)
        _ok_logger.error(f"Uncaught exception: {tb_text}")


sys.excepthook = _log_exception_handler


class InfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.ERROR


class SafeFileHandler(TimedRotatingFileHandler):
    def emit(self, record):
        try:
            if self.stream and not self.stream.closed:
                super().emit(record)
            else:
                raise ValueError("I/O operation on closed file.")
        except Exception:
            self.handleError(record)


class CommunicateHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        from ok.gui.Communicate import communicate
        self.communicate = communicate

    def emit(self, record):
        log_message = self.format(record)
        self.communicate.log.emit(record.levelno, log_message)


def config_logger(config=None, name='ok-script'):
    parser = argparse.ArgumentParser(description='Process some parameters.')
    parser.add_argument('--parent_pid', type=int, help='Parent process ID', default=0)
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
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(_ok_log_formatter)
        stdout_handler.addFilter(InfoFilter())
        if config.get('debug'):
            stdout_handler.setLevel(logging.DEBUG)
        else:
            stdout_handler.setLevel(logging.INFO)
        _ok_logger.addHandler(stdout_handler)

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
