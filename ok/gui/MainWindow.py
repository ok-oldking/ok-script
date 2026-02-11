import threading

import pyappify
from PySide6.QtCore import QCoreApplication, QEvent, QSize, Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QApplication
from qfluentwidgets import MSFluentWindow, qconfig, FluentIcon, NavigationItemPosition, MessageBox, InfoBar, \
    InfoBarPosition

from ok.util.config import Config

from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_error
from ok.gui.widget.StartLoadingDialog import StartLoadingDialog
from ok.util.GlobalConfig import basic_options
from ok.util.clazz import init_class_by_name
from ok.util.process import restart_as_admin, parse_arguments_to_map

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class MainWindow(MSFluentWindow):

    def __init__(self, app, config, ok_config, icon, title, version, debug=False, about=None, exit_event=None,
                 global_config=None, executor=None, handler=None):
        super().__init__()
        logger.info('main window __init__')
        self.app = app
        self.executor = executor
        self.handler = handler
        self.ok_config = ok_config
        self.basic_global_config = global_config.get_config(basic_options)
        self.main_window_config = Config('main_window', {'last_version': 'v0.0.0'})
        self.exit_event = exit_event
        from ok.gui.start.StartTab import StartTab
        self.start_tab = StartTab(config, exit_event)
        self.onetime_tab = None
        self.trigger_tab = None
        self.version = version
        self.emulator_starting_dialog = None
        self.do_not_quit = False
        self.config = config
        self.shown = False

        communicate.restart_admin.connect(self.restart_admin)
        if config.get('show_update_copyright'):
            communicate.copyright.connect(self.show_update_copyright)


        self.addSubInterface(self.start_tab, FluentIcon.PLAY, self.tr('Capture'))

        self.first_task_tab = None
        self.grouped_task_tabs = []
        if self.executor.onetime_tasks:
            from ok.gui.tasks.OneTimeTaskTab import OneTimeTaskTab
            from collections import defaultdict

            groups = defaultdict(list)
            standalone_tasks = []
            for task in executor.onetime_tasks:
                if task.group_name:
                    groups[task.group_name].append(task)
                else:
                    standalone_tasks.append(task)

            if standalone_tasks:
                self.onetime_tab = OneTimeTaskTab(tasks=standalone_tasks)
                if self.first_task_tab is None:
                    self.first_task_tab = self.onetime_tab
                logger.debug(f"add default onetime_tab len {len(standalone_tasks)}")
                self.addSubInterface(self.onetime_tab, FluentIcon.BOOK_SHELF, self.tr('Tasks'))

            for group_name, tasks_in_group in groups.items():
                group_tab = OneTimeTaskTab(tasks=tasks_in_group)
                group_icon = tasks_in_group[0].group_icon
                if self.first_task_tab is None:
                    self.first_task_tab = group_tab
                logger.debug(f"add grouped_task_tabs {group_name} len {len(tasks_in_group)}")
                self.addSubInterface(group_tab, group_icon, self.app.tr(group_name))
                self.grouped_task_tabs.append(group_tab)

        if len(executor.trigger_tasks) > 0:
            from ok.gui.tasks.TriggerTaskTab import TriggerTaskTab
            self.trigger_tab = TriggerTaskTab()
            if self.first_task_tab is None:
                self.first_task_tab = self.trigger_tab
            self.addSubInterface(self.trigger_tab, FluentIcon.ROBOT, self.tr('Triggers'))

        if custom_tabs := config.get('custom_tabs'):
            for tab in custom_tabs:
                tab_obj = init_class_by_name(tab[0], tab[1])
                tab_obj.executor = executor
                self.addSubInterface(tab_obj, tab_obj.icon, tab_obj.name)

        if debug:
            from ok.gui.debug.DebugTab import DebugTab
            debug_tab = DebugTab(config, exit_event)
            self.addSubInterface(debug_tab, FluentIcon.DEVELOPER_TOOLS, self.tr('Debug'),
                                 position=NavigationItemPosition.BOTTOM)

        from ok.gui.about.AboutTab import AboutTab
        self.about_tab = AboutTab(config, self.app.updater)
        self.addSubInterface(self.about_tab, FluentIcon.QUESTION, self.tr('About'),
                             position=NavigationItemPosition.BOTTOM)

        from ok.gui.settings.SettingTab import SettingTab
        self.setting_tab = SettingTab()
        self.addSubInterface(self.setting_tab, FluentIcon.SETTING, self.tr('Settings'),
                             position=NavigationItemPosition.BOTTOM)

        dev = self.tr('Debug')
        profile = config.get('profile', "")
        self.setWindowTitle(f'{title} {version} {profile} {dev if debug else ""}')

        communicate.executor_paused.connect(self.executor_paused)
        communicate.tab.connect(self.navigate_tab)
        communicate.task_done.connect(self.activateWindow)
        communicate.must_update.connect(self.must_update)
        menu = QMenu()
        exit_action = menu.addAction(self.tr("Exit"))
        exit_action.triggered.connect(self.tray_quit)

        self.tray = QSystemTrayIcon(icon, parent=self)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_icon_activated)
        self.tray.show()
        self.tray.setToolTip(title)

        communicate.capture_error.connect(self.capture_error)
        communicate.notification.connect(self.show_notification)
        communicate.config_validation.connect(self.config_validation)
        communicate.starting_emulator.connect(self.starting_emulator)
        communicate.global_config.connect(self.goto_global_config)

        logger.info('main window __init__ done')

    def restart_admin(self):
        w = MessageBox(QCoreApplication.translate("app", "Alert"),
                       QCoreApplication.translate("StartController",
                                                  "PC version requires admin privileges, Please restart this app with admin privileges!"),
                       self.window())
        if w.exec():
            logger.info('restart_admin Yes button is pressed')
            thread = threading.Thread(target=restart_as_admin)
            thread.start()
            self.app.quit()

    def on_tray_icon_activated(self, reason):
        """Handles clicks on the system tray icon."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            logger.info('main window on_tray_icon_activated QSystemTrayIcon.ActivationReason.Trigger')
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            logger.info('main window on_tray_icon_activated QSystemTrayIcon.ActivationReason.MiddleClick')
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            logger.info(
                f'main window on_tray_icon_activated QSystemTrayIcon.ActivationReason.DoubleClick self.isVisible():{self.isVisible()}')
            self.showNormal()
            self.raise_()
            self.activateWindow()



    def goto_global_config(self, key):
        self.switchTo(self.setting_tab)
        self.setting_tab.goto_config(key)

    def tray_quit(self):
        logger.info('main window tray_quit')
        self.app.quit()

    def must_update(self):
        logger.info('must_update show_window')
        title = self.tr('Update')
        content = QCoreApplication.translate('app', 'The current version {} must be updated').format(
            self.app.updater.starting_version)
        w = MessageBox(title, content, self.window())
        self.executor.pause()
        if w.exec():
            logger.info('Yes button is pressed')
            self.app.updater.run()
        else:
            logger.info('No button is pressed')
            self.app.quit()

    def show_ok(self):
        title = self.tr('Update')
        content = QCoreApplication.translate('app', 'The current version {} must be updated').format(
            self.app.updater.starting_version)
        w = MessageBox(title, content, self.window())

    def show_update_copyright(self):
        title = self.tr('Info')
        content = self.tr(
            "This is a free software. If you purchased this anywhere, request a refund from the seller.")
        from qfluentwidgets import Dialog
        w = Dialog(title, content, self.window())
        w.cancelButton.setVisible(False)
        w.setContentCopyable(True)
        w.exec()
        self.switchTo(self.about_tab)

    def showEvent(self, event):
        if event.type() == QEvent.Show and not self.shown:
            self.shown = True
            args = parse_arguments_to_map()
            pyappify.hide_pyappify()
            if update_pyappify := self.config.get("update_pyappify"):
                pyappify.upgrade(update_pyappify.get('to_version'), update_pyappify.get('sha256'),
                                 [update_pyappify.get('zip_url')], self.exit_event)
            logger.info(f"Window has fully displayed {args}")
            communicate.start_success.emit()
            if self.basic_global_config.get('Kill Launcher after Start'):
                logger.info(f'MainWindow showEvent Kill Launcher after Start')
                pyappify.kill_pyappify()
            if self.version != self.main_window_config.get('last_version'):
                self.main_window_config['last_version'] = self.version
                if not self.config.get('auth'):
                    logger.info('update success, show copyright')
                    self.handler.post(lambda: communicate.copyright.emit(), delay=1)
            if args.get('task') > 0:
                task_index = args.get('task') - 1
                logger.info(f'start with params {task_index} {args.get("exit")}')
                self.app.start_controller.start(args.get('task') - 1, exit_after=args.get('exit'))
            elif self.basic_global_config.get('Auto Start Game When App Starts'):
                self.app.start_controller.start()
        super().showEvent(event)

    def set_window_size(self, width, height, min_width, min_height):
        screen = QScreen.availableGeometry(self.screen())
        if (self.ok_config['window_width'] > 0 and self.ok_config['window_height'] > 0 and
                self.ok_config['window_y'] > 0 and self.ok_config['window_x'] > 0):
            x, y, width, height = (self.ok_config['window_x'], self.ok_config['window_y'],
                                   self.ok_config['window_width'], self.ok_config['window_height'])
            if self.ok_config['window_maximized']:
                self.setWindowState(Qt.WindowMaximized)
            else:
                self.setGeometry(x, y, width, height)
        else:
            x = int((screen.width() - width) / 2)
            y = int((screen.height() - height) / 2)
            self.setGeometry(x, y, width, height)

        self.setMinimumSize(QSize(min_width, min_height))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize or event.type() == QEvent.Move:
            self.handler.post(self.update_ok_config, remove_existing=True, skip_if_running=True, delay=1)
        return super().eventFilter(obj, event)

    def update_ok_config(self):
        if self.isMaximized():
            self.ok_config['window_maximized'] = True
        else:
            self.ok_config['window_maximized'] = False
            geometry = self.geometry()
            self.ok_config['window_x'] = geometry.x()
            self.ok_config['window_y'] = geometry.y()
            self.ok_config['window_width'] = geometry.width()
            self.ok_config['window_height'] = geometry.height()
        logger.info(f'Window geometry updated in ok_config {self.ok_config}')

    def starting_emulator(self, done, error, seconds_left):
        if error:
            self.switchTo(self.start_tab)
            alert_error(error, True)
        if done:
            if self.emulator_starting_dialog:
                self.emulator_starting_dialog.close()
        else:
            if self.emulator_starting_dialog is None:
                self.emulator_starting_dialog = StartLoadingDialog(seconds_left,
                                                                   self)
            else:
                self.emulator_starting_dialog.set_seconds_left(seconds_left)
            self.emulator_starting_dialog.show()

    def config_validation(self, message):
        title = self.tr('Error')
        InfoBar.error(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self.window()
        )
        self.tray.showMessage(title, message)

    def show_notification(self, message, title=None, error=False, tray=False, show_tab=None):
        from ok.gui.util.app import show_info_bar
        show_info_bar(self.window(), self.app.tr(message), self.app.tr(title), error)
        if tray:
            self.tray.showMessage(self.app.tr(title), self.app.tr(message),
                                  QSystemTrayIcon.Critical if error else QSystemTrayIcon.Information,
                                  5000)
            self.navigate_tab(show_tab)

    def capture_error(self):
        self.show_notification(self.tr('Please check whether the game window is selected correctly!'),
                               self.tr('Capture Error'), error=True)

    def navigate_tab(self, index):
        logger.debug(f'navigate_tab {index}')
        if index == "start":
            self.switchTo(self.start_tab)
        elif index == "onetime" and self.onetime_tab is not None:
            self.switchTo(self.onetime_tab)
        elif index == "trigger" and self.trigger_tab is not None:
            self.switchTo(self.trigger_tab)
        elif index == "about" and self.about_tab is not None:
            self.switchTo(self.about_tab)

    def executor_paused(self, paused):
        if not paused and self.stackedWidget.currentIndex() == 0:
            self.switchTo(self.first_task_tab)
        self.show_notification(self.tr("Start Success.") if not paused else self.tr("Pause Success."), tray=not paused)

    def closeEvent(self, event):
        if self.app.exit_event.is_set():
            logger.info("Window closed exit_event.is_set")
            event.accept()
            return
        else:
            logger.info(f"Window closed exit_event.is not set {self.do_not_quit}")
            to_tray = self.basic_global_config.get('Minimize Window to System Tray when Closing')
            if to_tray:
                event.ignore()
                self.hide()
                return
            if not self.do_not_quit:
                pyappify.kill_pyappify()
                self.exit_event.set()
                self.executor.destory()
            event.accept()
            if not self.do_not_quit:
                QApplication.instance().exit()
