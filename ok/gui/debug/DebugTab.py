import subprocess
import time
from ctypes import windll, wintypes

from PySide6.QtCore import Qt, Signal, QCoreApplication
from PySide6.QtWidgets import QWidget, QFileDialog, QCompleter, QVBoxLayout, QHBoxLayout
from _ctypes import byref
from qfluentwidgets import PushButton, FlowLayout, ComboBox, SearchLineEdit, TextEdit

import ok.gui
from ok.capture.image.ImageCaptureMethod import ImageCaptureMethod
from ok.capture.windows.dump import dump_threads
from ok.config.Config import Config
from ok.gui.i18n.GettextTranslator import convert_to_mo_files
from ok.gui.util.Alert import alert_info, alert_error
from ok.gui.widget.Tab import Tab
from ok.interaction.DoNothingInteraction import DoNothingInteraction
from ok.logging.Logger import get_logger, exception_to_str
from ok.ocr.OCR import OCR
from ok.util.Handler import Handler

logger = get_logger(__name__)


class DebugTab(Tab):
    update_result_text: Signal = Signal(str)

    def __init__(self, app_config, exit_event):

        super().__init__()
        self.config = Config('debug', {'target_task': "", 'target_images': [], 'target_function': ""}
                             )
        self.log_window_config = Config('log_window', {'width': 800, 'height': 300, 'x': 0, 'y': 0, 'keyword': '',
                                                       'level': 'ALL', 'show': True})
        tool_widget = QWidget()
        layout = FlowLayout(tool_widget, False)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setVerticalSpacing(20)
        layout.setHorizontalSpacing(10)
        self.handler = Handler(exit_event, "DebugTab")

        self.addCard(self.tr("Debug Tool"), tool_widget)

        dump_button = PushButton(self.tr("Dump Threads(HotKey:Ctrl+Alt+D)"))
        dump_button.clicked.connect(lambda: self.handler.post(dump_threads))
        layout.addWidget(dump_button)
        # self.dump_shortcut = QShortcut(QKeySequence("Ctrl+Alt+D"), self)
        # self.dump_shortcut.activated.connect(dump_threads)

        capture_button = PushButton(self.tr("Capture Screenshot"))
        capture_button.clicked.connect(lambda: self.handler.post(capture))
        layout.addWidget(capture_button)

        ocr_button = PushButton("OCR")
        ocr_button.clicked.connect(lambda: self.handler.post(self.ocr))
        layout.addWidget(ocr_button)

        self.log_window = None

        log_window_button = PushButton(self.tr("Open Logs"))
        log_window_button.clicked.connect(self.toggle_log_window)
        layout.addWidget(log_window_button)

        if self.log_window_config.get('show'):
            self.toggle_log_window()

        gen_tr_button = PushButton(self.tr("Generate i18n files"))
        gen_tr_button.clicked.connect(self.gen_tr)
        layout.addWidget(gen_tr_button)

        convert_tr_button = PushButton(self.tr("Convert i18n files"))
        convert_tr_button.clicked.connect(convert_to_mo_files)
        layout.addWidget(convert_tr_button)

        call_task_widget = QWidget()
        call_task_container = QVBoxLayout(call_task_widget)
        call_task_layout = QHBoxLayout()
        call_task_container.addLayout(call_task_layout)
        self.addCard(self.tr("Debug Task Function"), call_task_widget)
        images = self.config.get("target_images")
        self.select_screenshot_button = PushButton(
            self.tr('{num} images selected').format(num=len(images)) if images else self.tr("Select Screenshots"))
        self.select_screenshot_button.clicked.connect(self.select_screenshot)
        call_task_layout.addWidget(self.select_screenshot_button)

        self.tasks_combo_box = ComboBox()
        call_task_layout.addWidget(self.tasks_combo_box)
        tasks = ok.gui.executor.get_all_tasks()
        class_names = [obj.__class__.__name__ for obj in tasks]
        self.tasks_combo_box.addItems(class_names)
        self.tasks_combo_box.currentTextChanged.connect(self.task_changed)

        self.target_function_edit = SearchLineEdit(self)
        self.target_function_edit.setPlaceholderText(self.tr('Type a function or property'))
        self.target_function_edit.setClearButtonEnabled(True)
        if self.config.get('target_function'):
            self.target_function_edit.setText(self.config.get('target_function'))
        call_task_layout.addWidget(self.target_function_edit, stretch=1)

        if self.config.get('target_task') in class_names:
            self.tasks_combo_box.setText(self.config.get('target_task'))
            self.task_changed(self.config.get('target_task'))
        else:
            self.tasks_combo_box.setCurrentIndex(0)
            self.config['target_task'] = class_names[0]

        self.call_button = PushButton(self.tr("Call"))
        self.call_button.clicked.connect(lambda: self.handler.post(self.call))

        call_task_layout.addWidget(self.call_button)

        self.result_edit = TextEdit()
        call_task_container.addWidget(self.result_edit, stretch=1)
        self.update_result_text.connect(self.result_edit.setText)
        self.handler.post(self.bind_hot_keys)
        self.handler.post(self.check_hotkey, 0.1)

        ok.gui.app.app.aboutToQuit.connect(self.unregister)

    def toggle_log_window(self):
        if self.log_window is None:
            from ok.gui.debug.LogWindow import LogWindow
            self.log_window = LogWindow(self.log_window_config)
            self.log_window.show()
            self.log_window_config['show'] = True
        elif self.log_window.isVisible():
            self.log_window.hide()
            self.log_window_config['show'] = False
        else:
            self.log_window_config['show'] = True
            self.log_window.show()
        logger.debug('showing log_window')

    def gen_tr(self):
        folder = ok.gui.app.gen_tr_po_files()
        subprocess.Popen(r'explorer /select,"{}"'.format(folder))

    def check_hotkey(self):
        # Example event type, you should use the appropriate QEvent.Type for your case
        msg = wintypes.MSG()

        # PeekMessageW is used to check for a hotkey press
        if windll.user32.PeekMessageW(byref(msg), None, 0, 0, 1):
            if msg.message == 0x0312:  # WM_HOTKEY
                logger.debug(f'hotkey pressed {msg}')
                if msg.wParam == 1:
                    logger.debug('dumping threads')
                    dump_threads()
                elif msg.wParam == 2:
                    self.handler.post(capture)

        # Repost the check_hotkey method to be called after 100 ms
        self.handler.post(self.check_hotkey, 0.1)

    def bind_hot_keys(self):
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        VK_D = 0x44  # Virtual-Key code for 'D'
        VK_S = 0x53

        if not windll.user32.RegisterHotKey(None, 1, MOD_ALT | MOD_CONTROL, VK_D):
            logger.debug("Failed to register hotkey for Alt+Ctrl+D")
        if not windll.user32.RegisterHotKey(None, 2, MOD_ALT | MOD_CONTROL, VK_S):
            logger.debug("Failed to register hotkey for Alt+Ctrl+S")
        logger.debug('bind_hot_keys')

    @staticmethod
    def unregister():
        # Unregister the hotkeys
        logger.debug('Unregister the hotkeys')
        windll.user32.UnregisterHotKey(None, 1)
        windll.user32.UnregisterHotKey(None, 2)

    def call(self):
        func_name = self.target_function_edit.text()
        task_name = self.config.get('target_task')
        task = ok.gui.executor.get_task_by_class_name(task_name)

        if not hasattr(task, func_name):
            alert_error(self.tr(f"No such attr: {func_name}"))
            return
        old_capture = ok.gui.device_manager.capture_method
        old_interaction = ok.gui.device_manager.interaction
        try:
            images = self.config.get("target_images")
            if images:
                ok.gui.device_manager.capture_method = ImageCaptureMethod(images)
                ok.gui.device_manager.interaction = DoNothingInteraction(ok.gui.device_manager.capture_method)
            else:
                task.next_frame()
            ok.gui.executor.debug_mode = True
            attr = getattr(task, func_name)
            if callable(attr):
                result = str(attr())
            else:
                result = str(attr)
        except Exception as e:
            logger.error('debug call exception', e)
            result = exception_to_str(e)
        ok.gui.executor.debug_mode = False
        ok.gui.device_manager.capture_method = old_capture
        ok.gui.device_manager.interaction = old_interaction
        self.update_result_text.emit(result)
        self.config['target_function'] = func_name
        alert_info(self.tr(f"call success: {result}"))

    def ocr(self):
        if not ok.gui.executor.ocr:
            alert_error(self.tr('No OCR configured'))
            return
        if ok.gui.device_manager.capture_method is not None:
            logger.info(f'ok.gui.device_manager.capture_method {ok.gui.device_manager.capture_method}')
            capture = str(ok.gui.device_manager.capture_method)
            frame = ok.gui.device_manager.capture_method.do_get_frame()
            if frame is not None:
                ocr = OCR()
                ocr.executor = ok.gui.executor
                result = ocr.ocr(frame=frame)
                self.update_result_text.emit(str(result))
                alert_info(self.tr(f"OCR success: {result}"))
            else:
                alert_error(self.tr('Capture returned None'))
        else:
            alert_error(self.tr('No Capture Available or Selected'))

    def task_changed(self, text):
        self.config['target_task'] = text
        task = ok.gui.executor.get_task_by_class_name(text)
        functions = [func for func in dir(task)]
        completer = QCompleter(functions, self.target_function_edit)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setMaxVisibleItems(10)
        self.target_function_edit.setCompleter(completer)

    def select_screenshot(self):
        file_names, _ = QFileDialog.getOpenFileNames(None, "Open Image", "", "Image Files (*.png *.jpg *.bmp)")

        if file_names:
            logger.info(f"Selected files: {file_names}")
            self.select_screenshot_button.setText(self.tr('{num} images selected').format(num=len(file_names)))
            self.config['target_images'] = file_names
        else:
            self.select_screenshot_button.setText(self.tr("Drop or Select Screenshot"))
            self.config['target_images'] = None


def capture():
    if ok.gui.device_manager.capture_method is not None:
        logger.info(f'ok.gui.device_manager.capture_method {ok.gui.device_manager.capture_method}')
        current_capture = str(ok.gui.device_manager.capture_method) + '_' + str(time.time() * 1000)
        try:
            frame = ok.gui.device_manager.capture_method.do_get_frame()
            if frame is not None:
                file_path = ok.gui.ok.screenshot.generate_screen_shot(frame, ok.gui.ok.screenshot.ui_dict,
                                                                      ok.gui.ok.screenshot.screenshot_folder,
                                                                      current_capture)

                # Use subprocess.Popen to open the file explorer and select the file
                subprocess.Popen(r'explorer /select,"{}"'.format(file_path))
                logger.info(f'captured screenshot: {current_capture}')
                alert_info(QCoreApplication.translate('DebugTab', 'Capture Success'), True)
            else:
                alert_error(QCoreApplication.translate('DebugTab', 'Capture returned None'))
        except Exception as e:
            alert_error(QCoreApplication.translate('DebugTab', str(e)))
    else:
        alert_error(QCoreApplication.translate('DebugTab', 'No Capture Available or Selected'))
