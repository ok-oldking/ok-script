import subprocess

from PySide6.QtWidgets import QWidget
from qfluentwidgets import PushButton, FlowLayout

import ok.gui
from ok.capture.windows.dump import dump_threads
from ok.gui.widget.Tab import Tab
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler

logger = get_logger(__name__)


class DebugTab(Tab):
    def __init__(self, exit_event):
        super().__init__()
        widget = QWidget()
        layout = FlowLayout(widget, False)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setVerticalSpacing(20)
        layout.setHorizontalSpacing(10)
        self.addWidget(widget)
        self.handler = Handler(exit_event, "DebugTab")

        dump_button = PushButton(self.tr("Dump Threads(HotKey:Ctrl+Alt+D)"))
        dump_button.clicked.connect(lambda: self.handler.post(dump_threads))
        layout.addWidget(dump_button)

        capture_button = PushButton(self.tr("Capture Screenshot"))
        capture_button.clicked.connect(lambda: self.handler.post(self.capture))
        layout.addWidget(capture_button)

        open_log_folder = PushButton(self.tr("Open Logs"))

    def capture(self):
        if ok.gui.device_manager.capture_method is not None:
            logger.info(f'ok.gui.device_manager.capture_method {ok.gui.device_manager.capture_method}')
            capture = str(ok.gui.device_manager.capture_method)
            frame = ok.gui.device_manager.capture_method.do_get_frame()
            if frame is not None:
                file_path = ok.gui.ok.screenshot.generate_screen_shot(frame, ok.gui.ok.screenshot.ui_dict,
                                                                      ok.gui.ok.screenshot.screenshot_folder, capture)

                # Use subprocess.Popen to open the file explorer and select the file
                subprocess.Popen(r'explorer /select,"{}"'.format(file_path))
                logger.info(f'captured screenshot: {capture}')
                self.alert_info(self.tr('Capture Success'))
            else:
                self.alert_error(self.tr('Capture returned None'))
        else:
            self.alert_error(self.tr('No Capture Available or Selected'))
