from PySide6.QtCore import Signal, QObject


class Communicate(QObject):
    log = Signal(int, str)
    fps = Signal(int)
    frame_time = Signal(int)
    scene = Signal(str)
    draw_box = Signal(str, object, str, object, bool)
    clear_box = Signal()
    task = Signal(object)
    task_done = Signal(object)
    window = Signal(bool, int, int, int, int, int, int, float)
    loading_progress = Signal(str)
    notification = Signal(str, str, bool, bool, str)
    executor_paused: Signal = Signal(bool)
    screenshot = Signal(object, str, bool, object)
    adb_devices: Signal = Signal(bool)
    config_validation: Signal = Signal(str)
    tab = Signal(str)
    capture_error = Signal()
    check_update = Signal(str)
    download_update = Signal(float, str, bool, str)
    starting_emulator = Signal(bool, str, int)
    quit = Signal()
    update_running = Signal(bool, bool)
    versions = Signal()
    must_update = Signal()
    launcher_profiles = Signal(list)
    update_logs = Signal()
    update_download_percent = Signal(bool, str, str, float)
    cuda_version = Signal(str)
    start_success = Signal()
    act = Signal()
    copyright = Signal()
    global_config = Signal(str)
    restart_admin = Signal()

    def emit_draw_box(self, key: str = None, boxes=None, color=None, frame=None, debug=True):
        self.draw_box.emit(key, boxes, color, frame, debug)


communicate = Communicate()
