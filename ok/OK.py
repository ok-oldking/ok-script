import sys
import threading
import time
from typing import Dict, Any

from PySide6.QtWidgets import QApplication

import ok
from ok.logging.Logger import get_logger, config_logger
from ok.util.exit_event import ExitEvent
from ok.util.path import install_path_isascii

logger = get_logger(__name__)


class OK:
    executor = None
    adb = None
    adb_device = None
    feature_set = None
    hwnd = None
    device_manager = None
    ocr = None
    overlay_window = None
    app = None
    screenshot = None
    exit_event = ExitEvent()

    def __init__(self, config: Dict[str, Any]):
        print(f"AutoHelper init, config: {config}")
        ok.gui.ok = self
        self.debug = config.get("debug", False)
        try:
            self.config = config
            self.init_device_manager()
            from ok.gui.debug.Screenshot import Screenshot
            self.screenshot = Screenshot(self.exit_event)
            if config.get("use_gui"):
                from ok.gui.App import App
                self.app = App(config, self.exit_event)
                ok.gui.app = self.app
            else:
                self.device_manager.set_preferred_device()
                self.device_manager.start()
                self.do_init()
        except Exception as e:
            self.quit()
            raise e

    def start(self):
        try:
            if self.config.get("use_gui"):
                if self.do_init():
                    self.app.show_main_window()
                self.app.exec()
            else:
                self.task_executor.start()
                if self.config.get("debug"):
                    self.app = QApplication(sys.argv)
                    from ok.gui.overlay.OverlayWindow import OverlayWindow
                    self.overlay_window = OverlayWindow(ok.gui.device_manager.hwnd)
                    self.app.exec()
                else:
                    try:
                        # Starting the task in a separate thread (optional)
                        # This allows the main thread to remain responsive to keyboard interrupts
                        task_thread = threading.Thread(target=self.wait_task)
                        task_thread.start()

                        # Wait for the task thread to end (which it won't, in this case, without an interrupt)
                        task_thread.join()
                    except KeyboardInterrupt:
                        self.exit_event.set()
                        logger.info("Keyboard interrupt received, exiting script.")
                    finally:
                        # Clean-up code goes here (if any)
                        # This block ensures that the script terminates gracefully,
                        # releasing resources or performing necessary clean-up operations.
                        logger.info("Script has terminated.")
        except Exception as e:
            logger.error("start error", e)
            self.exit_event.set()
            if self.app:
                self.quit()

    def do_init(self):
        logger.info(f"initializing {self.__class__.__name__}, config: {self.config}")
        if self.config.get('ocr'):
            isascii, path = install_path_isascii()
            if not isascii:
                self.app.show_path_ascii_error(path)
                return False
            from rapidocr_openvino import RapidOCR
            self.ocr = RapidOCR()

        config_logger(self.config)

        if self.config.get('coco_feature_folder') is not None:
            coco_feature_folder = self.config.get('coco_feature_folder')
            from ok.feature.FeatureSet import FeatureSet
            self.feature_set = FeatureSet(coco_feature_folder,
                                          default_horizontal_variance=self.config.get('default_horizontal_variance', 0),
                                          default_vertical_variance=self.config.get('default_vertical_variance', 0),
                                          default_threshold=self.config.get('default_threshold', 0))

        from ok.task.TaskExecutor import TaskExecutor
        self.task_executor = TaskExecutor(self.device_manager, exit_event=self.exit_event,
                                          onetime_tasks=self.config.get('onetime_tasks', []),
                                          trigger_tasks=self.config.get('trigger_tasks', []),
                                          scenes=self.config['scenes'],
                                          feature_set=self.feature_set,
                                          ocr=self.ocr, config_folder=self.config.get("config_folder") or "config")

        if self.app:
            ok.gui.executor = self.task_executor

        return True

    def wait_task(self):
        while not self.exit_event.is_set():
            time.sleep(1)

    def quit(self):
        logger.debug('quit app')
        self.exit_event.set()
        if self.device_manager is not None:
            self.device_manager.stop()
        if self.app:
            self.app.quit()

    def init_device_manager(self):
        if self.device_manager is None:
            from ok.capture.adb.DeviceManager import DeviceManager
            self.device_manager = DeviceManager(self.config.get("config_folder") or "config",
                                                self.config.get('capture_window_title'),
                                                self.config.get('capture_window_exe_name'),
                                                self.config.get("debug"),
                                                self.exit_event)
            ok.gui.device_manager = self.device_manager
