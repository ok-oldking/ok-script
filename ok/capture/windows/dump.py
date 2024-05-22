import sys
import traceback
import threading

from ok.util.path import get_path_relative_to_exe

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
    output_file = get_path_relative_to_exe("thread_dumps.txt")
    print(f'Dumping threads to {output_file}')

    with open(output_file, "w") as file:
        file.write("\n\n".join(thread_dumps))
