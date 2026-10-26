from ctypes import windll, wintypes

from PySide6.QtCore import Qt, Signal, QCoreApplication
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QWidget, QFileDialog, QCompleter, QVBoxLayout, QHBoxLayout
from _ctypes import byref
from qfluentwidgets import PushButton, FlowLayout, ComboBox, SearchLineEdit, TextEdit

from ok import Config, og
from ok import Handler
from ok import Logger
from ok.capture.windows.dump import dump_threads
from ok.core.code_runner import submit_call, submit_task_call, wait_result
from ok.core.events import communicate
from ok.core.screenshot import screenshot_file_stem
from ok.device.capture import CAPTURE_BUSY_WAIT
from ok.task.exceptions import ExecutorBusyException
from ok.ui.qt.debug.JobControls import JobControls
from ok.ui.qt.i18n.GettextTranslator import convert_to_mo_files
from ok.ui.qt.util.Alert import alert_info, alert_error
from ok.ui.qt.widget.Tab import Tab
from ok.util.explorer import open_explorer_folder, reveal_in_explorer

logger = Logger.get_logger(__name__)

RESULT_ALERT_LENGTH = 200


class DebugTab(Tab):
    update_result_text: Signal = Signal(str)
    ocr_done: Signal = Signal(object)
    reload_done: Signal = Signal(object)

    def __init__(self, app_config, exit_event):

        super().__init__()
        self.config = Config('debug', {'target_task': "", 'target_images': [], 'target_function': ""}
                             )
        tool_widget = QWidget()
        layout = FlowLayout(tool_widget, False)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setVerticalSpacing(20)
        layout.setHorizontalSpacing(10)
        self.handler = Handler(exit_event, "DebugTab")
        # Hotkeys are registered to, and polled on, their own thread so that a
        # busy tool (capture waiting for WGC) cannot block Ctrl+Alt+D.
        self.hotkey_handler = Handler(exit_event, "DebugTabHotkeys")

        self.add_card(self.tr("Debug Tool"), tool_widget)

        dump_button = PushButton(self.tr("Dump Threads(HotKey:Ctrl+Alt+D)"))
        dump_button.clicked.connect(lambda: self.handler.post(dump_threads))
        layout.addWidget(dump_button)
        # self.dump_shortcut = QShortcut(QKeySequence("Ctrl+Alt+D"), self)
        # self.dump_shortcut.activated.connect(dump_threads)

        capture_button = PushButton(self.tr("Capture Screenshot"))
        capture_button.clicked.connect(lambda: self.handler.post(capture))
        layout.addWidget(capture_button)

        self.reload_button = PushButton(self.tr('Reload tasks'))
        self.reload_button.clicked.connect(self.reload_tasks)
        self.reload_done.connect(self.on_reload_done)
        layout.addWidget(self.reload_button)

        self.ocr_button = PushButton("OCR")
        self.ocr_button.clicked.connect(self.ocr_log)
        self.ocr_done.connect(self.on_ocr_done)
        layout.addWidget(self.ocr_button)

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
        self.add_card(self.tr("Debug Task Function"), call_task_widget)
        images = self.config.get("target_images")
        self.select_screenshot_button = PushButton(
            self.tr('{num} images selected').format(num=len(images)) if images else self.tr("Select Screenshots"))
        self.select_screenshot_button.clicked.connect(self.select_screenshot)
        call_task_layout.addWidget(self.select_screenshot_button)

        self.tasks_combo_box = ComboBox()
        call_task_layout.addWidget(self.tasks_combo_box)
        tasks = og.executor.get_all_tasks()
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
        elif class_names:
            self.tasks_combo_box.setCurrentIndex(0)
            self.config['target_task'] = class_names[0]

        communicate.task_list_updated.connect(self.refresh_tasks)
        callback = self.refresh_tasks
        self.destroyed.connect(lambda *_: communicate.task_list_updated.disconnect(callback))

        self.call_controls = JobControls(self.tr("Call"))
        self.call_controls.run_clicked.connect(self.call)
        self.call_controls.output.connect(self.append_result_text)
        self.call_controls.finished.connect(self.call_finished)
        call_task_container.addWidget(self.call_controls)

        self.result_edit = TextEdit()
        call_task_container.addWidget(self.result_edit, stretch=1)
        self.update_result_text.connect(self.result_edit.setText)
        self.hotkey_handler.post(self.bind_hot_keys)
        self.hotkey_handler.post(self.check_hotkey, 0.1)

        og.app.app.aboutToQuit.connect(self.unregister)

    def gen_tr(self):
        folder = og.app.gen_tr_po_files()
        reveal_in_explorer(folder)

    def reload_tasks(self):
        try:
            job = og.task_manager.reload_tasks()
        except Exception as error:
            alert_error(str(error))
            return
        self.reload_button.setEnabled(False)
        self.reload_button.setText(self.tr('Waiting to reload tasks...'))
        job.future.add_done_callback(lambda _: self.reload_done.emit(job))

    def on_reload_done(self, job):
        self.reload_button.setEnabled(True)
        self.reload_button.setText(self.tr('Reload tasks'))
        try:
            tasks = job.future.result()
        except Exception as error:
            logger.error('Task reload failed', error)
            alert_error(str(error))
            return
        alert_info(self.tr('Reloaded {count} tasks').format(count=len(tasks)))

    def refresh_tasks(self):
        selected = self.tasks_combo_box.currentText()
        names = [type(task).__name__ for task in og.executor.get_all_tasks()]
        self.tasks_combo_box.blockSignals(True)
        self.tasks_combo_box.clear()
        self.tasks_combo_box.addItems(names)
        if selected in names:
            self.tasks_combo_box.setText(selected)
        self.tasks_combo_box.blockSignals(False)
        self.task_changed(self.tasks_combo_box.currentText())

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
        self.hotkey_handler.post(self.check_hotkey, 0.1)

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
        func_name = self.target_function_edit.text().strip()
        task = og.executor.get_task_by_class_name(self.config.get('target_task'))
        images = self.config.get("target_images") or None
        self.config['target_function'] = func_name
        self.result_edit.clear()
        # Runs on the executor thread; with screenshots selected, only this
        # call sees them and its clicks and keys do nothing.
        self.call_controls.start(lambda on_output: submit_task_call(
            og.executor, task, func_name, images=images, on_output=on_output))

    def append_result_text(self, text):
        self.result_edit.moveCursor(QTextCursor.End)
        self.result_edit.insertPlainText(text)

    def call_finished(self, result):
        if result.error:
            logger.error(f'debug call exception {result.error}')
            self.append_result_text(result.error)
        elif result.cancelled:
            self.append_result_text(self.tr("Cancelled") + '\n')
        else:
            value = str(result.raw)
            self.append_result_text(value)
            alert_info(self.tr("Call success: {result}").format(result=value[:RESULT_ALERT_LENGTH]))

    def ocr_log(self):
        tasks = og.executor.get_all_tasks()
        if not tasks:
            return
        task = tasks[0]
        try:
            job = submit_call(og.executor, lambda: task.ocr(log=True), name='debug_ocr')
        except ExecutorBusyException as e:
            alert_error(self.tr('The app is controlled by {owner}').format(owner=e.owner))
            return
        self.ocr_button.setEnabled(False)
        job.future.add_done_callback(lambda _: self.ocr_done.emit(job))

    def on_ocr_done(self, job):
        self.ocr_button.setEnabled(True)
        result = wait_result(job)
        if result.error:
            logger.error(f'debug ocr_log exception {result.error}')
            alert_error(result.error.strip().splitlines()[-1])
            return
        if result.cancelled:
            return
        self.result_edit.setText(str(result.raw))
        alert_info(self.tr("OCR success (Logged): {result}").format(result=str(result.raw)[:RESULT_ALERT_LENGTH]))
        folder = og.ok.screenshot.screenshot_folder
        if folder:
            open_explorer_folder(folder)

    def task_changed(self, text):
        self.config['target_task'] = text
        task = og.executor.get_task_by_class_name(text)
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


def capture(processor=None):
    if og.device_manager.capture_method is not None:
        logger.info(f'og.device_manager.capture_method {og.device_manager.capture_method}')
        try:
            frame = og.device_manager.capture_method.get_frame(busy_wait=CAPTURE_BUSY_WAIT)
            if frame is not None:
                current_capture = screenshot_file_stem(og.device_manager.capture_method.__class__.__name__)
                file_path = og.ok.screenshot.generate_screen_shot(frame, og.ok.screenshot.ui_dict,
                                                                  og.ok.screenshot.screenshot_folder,
                                                                  current_capture, True, None, processor=processor)

                reveal_in_explorer(file_path)
                alert_info(QCoreApplication.translate('DebugTab', 'Capture Success'), True)
            else:
                alert_error(QCoreApplication.translate('DebugTab', 'Capture returned None'))
        except Exception as e:
            alert_error(QCoreApplication.translate('DebugTab', str(e)))
    else:
        alert_error(QCoreApplication.translate('DebugTab', 'No Capture Available or Selected'))
