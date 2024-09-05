import os
import signal
import sys
import threading
import traceback

from ok.util.path import get_relative_path


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

    # subprocess.Popen(r'explorer /select,"{}"'.format(output_file))


def kill_dump():
    print("Killing dump")
    dump_threads()
    sys.exit(0)


def console_handler(event):
    import win32con
    if event == win32con.CTRL_C_EVENT:
        print("CTRL+C event")
        dump_threads()
        sys.exit(0)
    elif event == win32con.CTRL_CLOSE_EVENT:
        print("Close event")
    elif event == win32con.CTRL_LOGOFF_EVENT:
        print("Logoff event")
    elif event == win32con.CTRL_SHUTDOWN_EVENT:
        print("Shutdown event")
    # Perform clean-up tasks here
    print("Performing clean-up...")
    # sys.exit(0)  # Exit the program
    return True


if __name__ == '__main__':

    import psutil
    import faulthandler

    # Enable the fault handler
    faulthandler.enable()

    # Iterate over all running processes
    for proc in psutil.process_iter(['pid', 'name', 'status', 'exe']):
        # Check if the process is unresponsive
        # print(proc.info['exe'])
        if proc.info['name'] == 'python.exe':
            # Dump the traceback
            print(f'dump {proc.pid} {proc.cmdline()} {proc.info["pid"] == os.getpid()}')
            # faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
            # Kill the process
            # os.kill(proc.info['pid'], signal.SIGTERM)

    # faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
    # Kill the process
    os.kill(16916, signal.SIGTERM)
