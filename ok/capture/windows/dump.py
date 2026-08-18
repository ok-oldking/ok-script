import os
import sys
import threading
import traceback

# dump.py lives at <app>/ok/capture/windows/, so the app working directory is
# three levels up.  Resolve it from __file__ rather than os.getcwd() because a
# hung process may have an invalid/deleted working directory (which made the
# old dump path fail with OSError 22 "Invalid argument").
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       os.pardir, os.pardir, os.pardir))
LOG_DIR = os.path.join(APP_DIR, 'logs')
FALLBACK_DIR = os.path.join(os.path.expanduser('~'), 'Documents')


def get_thread_name(thread_id):
    for thread in threading.enumerate():
        if thread.ident == thread_id:
            return thread.name
    return ""  # Return empty string if the thread name is not found


def dump_threads(output_file=None):
    """Dump every thread's Python stack to a text file.

    Returns the path written, or None if it could not be written anywhere.
    """
    thread_dumps = []
    for thread_id, frame in sys._current_frames().items():
        thread_name = get_thread_name(thread_id)
        thread_dump = f"Stack for thread {thread_id} (Name: {thread_name}):\n"
        try:
            thread_dump += "".join(traceback.format_stack(frame))
        except Exception:
            pass
        thread_dumps.append(thread_dump)

    body = "\n\n".join(thread_dumps)

    candidates = []
    if output_file:
        candidates.append(output_file)
    candidates.append(os.path.join(LOG_DIR, "thread_dumps.txt"))
    candidates.append(os.path.join(FALLBACK_DIR, "ok-ww_thread_dumps.txt"))

    last_error = None
    for candidate in candidates:
        try:
            directory = os.path.dirname(candidate)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(candidate, "w", encoding='utf-8') as f:
                f.write(body)
            return candidate
        except Exception as e:  # noqa: BLE001 - fall through to next candidate
            last_error = e

    # pythonw has no stdout; print() can raise if sys.stdout is None.
    try:
        print(f'Dumping threads failed ({last_error}); writing to stderr')
        sys.stderr.write(body)
    except Exception:
        pass
    return None
