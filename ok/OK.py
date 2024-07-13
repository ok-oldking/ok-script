import sys
import threading
import time
from typing import Dict, Any

from PySide6.QtWidgets import QApplication

import ok
from ok.logging.Logger import get_logger, config_logger
from ok.util.exit_event import ExitEvent
from ok.util.path import install_path_isascii
from ok.util.win32_process import check_mutex

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
    init_error = None

    def __init__(self, config: Dict[str, Any]):
        print(f"AutoHelper init, config: {config}")
        config["config_folder"] = config.get("config_folder") or 'configs'
        from ok.config.Config import Config
        Config.config_folder = config["config_folder"]
        config_logger(config)
        logger.info(f"AutoHelper init, config: {config}")
        ok.gui.ok = self
        config['debug'] = config.get("debug", False)
        self.debug = config['debug']
        try:
            import ctypes
            # Set DPI Awareness (Windows 10 and 8)
            errorCode = ctypes.windll.shcore.SetProcessDpiAwareness(1)
            logger.info(f'SetProcessDpiAwareness {errorCode}')
            if self.debug:
                import win32api
                win32api.SetConsoleCtrlHandler(self.console_handler, True)
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
            logger.error(f'__init__ error', e)
            self.quit()
            raise e

    def start(self):
        try:
            if self.config.get("use_gui"):
                if not self.init_error:
                    self.app.show_main_window()
                logger.debug('start app.exec()')
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

        template_matching = self.config.get('template_matching')
        if template_matching is not None:
            coco_feature_json = self.config.get('template_matching').get('coco_feature_json')
            from ok.feature.FeatureSet import FeatureSet
            self.feature_set = FeatureSet(self.debug, coco_feature_json,
                                          default_horizontal_variance=template_matching.get(
                                              'default_horizontal_variance', 0),
                                          default_vertical_variance=template_matching.get('default_vertical_variance',
                                                                                          0),
                                          default_threshold=template_matching.get('default_threshold', 0))

        from ok.task.TaskExecutor import TaskExecutor
        self.task_executor = TaskExecutor(self.device_manager, exit_event=self.exit_event,
                                          onetime_tasks=self.config.get('onetime_tasks', []),
                                          trigger_tasks=self.config.get('trigger_tasks', []),
                                          feature_set=self.feature_set,
                                          config_folder=self.config.get("config_folder"), debug=self.debug)

        ok.gui.executor = self.task_executor

        if self.config.get('ocr'):
            isascii, path = install_path_isascii()
            if not isascii:
                self.app.show_path_ascii_error(path)
                self.init_error = True
                return False
            from rapidocr_openvino import RapidOCR
            inference_num_threads = self.config.get('ocr').get('inference_num_threads', -1)
            self.ocr = RapidOCR(inference_num_threads=inference_num_threads)
            self.task_executor.ocr = self.ocr

        if not check_mutex():
            self.init_error = True
            self.app.show_already_running_error()

        return True

    def wait_task(self):
        while not self.exit_event.is_set():
            time.sleep(1)

    def console_handler(self, event):
        import win32con
        if event == win32con.CTRL_C_EVENT:
            logger.info("CTRL+C event dump threads")
            from ok.capture.windows.dump import dump_threads
            dump_threads()
            self.quit()
        elif event == win32con.CTRL_CLOSE_EVENT:
            logger.info("Close event quit")
            self.quit()
        elif event == win32con.CTRL_LOGOFF_EVENT:
            logger.info("Logoff event quit")
            self.quit()
        elif event == win32con.CTRL_SHUTDOWN_EVENT:
            logger.info("Shutdown event quit")
            self.quit()
        else:  # Perform clean-up tasks here
            print("Performing clean-up...")
        return True

    def quit(self):
        logger.debug('quit app')
        self.exit_event.set()
        if self.app:
            self.app.quit()

    def init_device_manager(self):
        if self.device_manager is None:
            from ok.capture.adb.DeviceManager import DeviceManager
            self.device_manager = DeviceManager(self.config,
                                                self.exit_event)
            ok.gui.device_manager = self.device_manager
