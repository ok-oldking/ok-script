import os
import sys
import threading
import traceback

from ok import get_relative_path


def get_thread_name(thread_id):
    for thread in threading.enumerate():
        if thread.ident == thread_id:
            return thread.name
    return ""  # Return empty string if the thread name is not found


def dump_threads():
    # Get the stack trace for each thread
    thread_dumps = []
    for thread_id, frame in sys._current_frames().items():
        thread_name = get_thread_name(thread_id)
        thread_dump = f"Stack for thread {thread_id} (Name: {thread_name}):\n"
        thread_dump += "".join(traceback.format_stack(frame))
        thread_dumps.append(thread_dump)

    # Write the thread dumps to a file
    output_file = get_relative_path(os.path.join('logs', "thread_dumps.txt"))
    print(f'Dumping threads to {output_file}')

    with open(output_file, "w", encoding='utf-8') as f:
        f.write("\n\n".join(thread_dumps))

