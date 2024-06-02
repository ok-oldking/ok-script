import numpy as np
from PySide6.QtCore import Signal, QObject


class Communicate(QObject):
    log = Signal(int, str)
    fps = Signal(int)
    frame_time = Signal(int)
    scene = Signal(str)
    draw_box = Signal(str, object, str, np.ndarray)
    task = Signal(object)
    task_info = Signal()
    window = Signal(bool, int, int, int, int, int, int, float)
    loading_progress = Signal(str)
    notification = Signal(str, str, bool)
    executor_paused: Signal = Signal(bool)
    screenshot = Signal(np.ndarray, str)
    update_overlay = Signal()
    adb_devices: Signal = Signal(bool)
    config_validation: Signal = Signal(str)
    tab = Signal(str)
    capture_error = Signal()
    check_update = Signal()
    download_update = Signal(float, str, bool, str)
    quit = Signal()

    def emit_draw_box(self, key: str = None, boxes=None, color=None, frame=None):
        self.draw_box.emit(key, boxes, color, frame)


communicate = Communicate()
