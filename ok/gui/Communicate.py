import numpy as np
from PySide6.QtCore import Signal, QObject


class Communicate(QObject):
    log = Signal(int, str)
    fps = Signal(int)
    frame_time = Signal(int)
    scene = Signal(str)
    draw_box = Signal(str, object, str, np.ndarray)
    tasks = Signal()
    task_info = Signal()
    window = Signal(bool, int, int, int, int, int, int, float)
    loading_progress = Signal(str)
    init = Signal(bool, str)
    notification = Signal(str, str)
    executor_paused: Signal = Signal(bool)
    screenshot = Signal(np.ndarray, str)
    update_overlay = Signal()
    adb_devices: Signal = Signal()

    def emit_draw_box(self, key: str = None, boxes=None, color=None, frame=None):
        self.draw_box.emit(key, boxes, color, frame)


communicate = Communicate()
