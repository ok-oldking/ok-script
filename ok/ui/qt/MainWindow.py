import os
import threading

import pyappify
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMenu, QSystemTrayIcon, QVBoxLayout

_pyappify_stop_lock = threading.Lock()


def request_pyappify_shutdown():
    """Terminate the launcher without ever blocking Qt's GUI thread."""
    def stop_launcher():
        if not _pyappify_stop_lock.acquire(blocking=False):
            return
        try:
            pyappify.kill_pyappify()
        except Exception as error:
            logger.warning(f'kill_pyappify failed: {error}')
        finally:
            _pyappify_stop_lock.release()

    thread = threading.Thread(
        target=stop_launcher, name='PyAppifyShutdown', daemon=True)
    thread.start()
    return thread


from ok.util.config import Config

from ok.ui.qt.Communicate import communicate
from ok.ui.qt.common.config import cfg as ui_config
from ok.ui.qt.kit import AnimatedStackedWidget, ContentLayer, Dialog,KitWindow, NavigationView, Theme as KitTheme, set_toast_anchor, show_toast, \
    theme as kit_theme
from ok.ui.qt.kit.navigation import NAV_INDICATOR_DURATION
from ok.ui.qt.kit.theme import set_style_property
from ok.ui.qt.shell.lazy_page import LazyPage
from ok.ui.qt.shell.nav_icons import nav_icon
from ok.ui.qt.shell.run_bar import RunBar
from ok.ui.qt.util.Alert import alert_error
from ok.ui.qt.util.pyappify_startup import get_startup_version_change
from ok.util.GlobalConfig import basic_options, KILL_LAUNCHER_AFTER_START, NOTIFICATION_OPTION_NAME
from ok.util.clazz import init_class_by_name
from ok.util.process import restart_as_admin
from ok.util.shortcut import create_app_shortcut

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

SECTION_RUN = "run"
SECTION_GAME = "game"
SECTION_DEVELOP = "develop"


def game_starting_or_started(auto_start_enabled=False, start_task_requested=False, start_controller=None,
                             executor=None):
    """Whether startup launched, is launching, or will launch the game and its tasks."""
    if auto_start_enabled or start_task_requested:
        return True
    if start_controller is not None and getattr(start_controller, 'starting', False):
        return True
    return executor is not None and not getattr(executor, 'paused', True)


UPDATE_CHECK_GAME_PROCESS_CONFIG = 'update_only_game_exit'
GAME_PROCESS_UPDATE_DELAY_MS = 10_000
GAME_PROCESS_POLL_INTERVAL_MS = 2_000
# Background startup work waits this long after the window is first shown.
POST_SHOW_STARTUP_DELAY_MS = 500


def game_process_exists(device_manager):
    """Whether the selected game's window/process (or emulator device) is present."""
    if device_manager is None:
        return False
    hwnd_window = getattr(device_manager, 'hwnd_window', None)
    if hwnd_window is not None and getattr(hwnd_window, 'exists', False):
        return True
    try:
        device = device_manager.get_preferred_device()
    except Exception as error:
        logger.debug(f'game_process_exists failed to read preferred device: {error}')
        return False
    return bool(device and device.get('connected'))


def fit_window_size(width, height, min_width, min_height, available_width, available_height):
    """Clamp a requested window size and minimum into the available screen area."""
    min_width = min(min_width, available_width)
    min_height = min(min_height, available_height)
    width = max(min_width, min(width, available_width))
    height = max(min_height, min(height, available_height))
    return width, height, min_width, min_height


class MainWindow(KitWindow):
    mcp_sdk_loaded = Signal()

    def __init__(self, app, config, ok_config, icon, title, version, debug=False, about=None, exit_event=None,
                 global_config=None, executor=None, handler=None):
        super().__init__()
        self.mcp_sdk_loaded.connect(self._on_mcp_sdk_loaded)
        self._theme_cooldowns = set()
        logger.info('main window __init__')
        self._sync_kit_theme()
        ui_config.theme_changed.connect(self._sync_kit_theme)
        self.app = app
        self.executor = executor
        self.handler = handler
        self.ok_config = ok_config
        self.basic_global_config = global_config.get_config(basic_options)
        self.main_window_config = Config('main_window', {'last_version': 'v0.0.0'})
        self.exit_event = exit_event
        self.tasks_page = None
        self.version = version
        self.do_not_quit = False
        self.config = config
        self.shown = False
        self._pages = {}
        communicate.restart_admin.connect(self.restart_admin)
        if config.get('show_update_copyright'):
            communicate.copyright.connect(self.show_update_copyright)

        self.navigation = NavigationView()
        kit_theme.install(self.navigation)
        self.navigation.add_section(SECTION_RUN, QCoreApplication.translate("MainWindow", "Run"))
        self.navigation.add_section(SECTION_GAME, QCoreApplication.translate("MainWindow", "Game"))
        self.navigation.add_section(SECTION_DEVELOP, QCoreApplication.translate("MainWindow", "Develop"))
        self.navigation.current_changed.connect(lambda key: self.switch_to(self._pages[key]))
        self.navigation.compact_changed.connect(self._save_navigation_state)
        self.stack = AnimatedStackedWidget(Qt.Orientation.Vertical)
        # The run bar is a toolbar fused to the title bar, so the executor state is always in view.
        self.run_bar = RunBar(exit_event)
        set_style_property(self.title_bar, "fused", True)

        # Pages sit on a content layer; with Mica or Acrylic the material shows only
        # in the frame around it (title bar, run bar, sidebar).
        self.content_layer = ContentLayer()
        layer_layout = QVBoxLayout(self.content_layer)
        layer_layout.setContentsMargins(0, 0, 0, 0)
        layer_layout.addWidget(self.stack)
        pages = QHBoxLayout()
        pages.setContentsMargins(0, 0, 0, 0)
        pages.setSpacing(0)
        pages.addWidget(self.navigation)
        pages.addWidget(self.content_layer, 1)
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.run_bar)
        body.addLayout(pages, 1)
        # Keep tips flush with the bottom edge of the title bar.
        set_toast_anchor(self, self.title_bar, gap=0)

        self.schedule_tab = None
        self.global_config_tabs = []  # [(config, LazyPage)]

        # Prepare custom tabs and separate them by add_after_default_tabs
        before_custom_tabs = []
        after_custom_tabs = []
        if custom_tabs := config.get('custom_tabs'):
            for tab in custom_tabs:
                tab_obj = init_class_by_name(tab[0], tab[1])
                tab_obj.executor = executor
                if tab_obj.add_after_default_tabs:
                    after_custom_tabs.append(tab_obj)
                else:
                    before_custom_tabs.append(tab_obj)

        for tab_obj in before_custom_tabs:
            self.add_page(tab_obj, tab_obj.icon, self.app.tr(tab_obj.name), SECTION_GAME)

        from ok import og
        self.imported_tabs = {}  # {file_name: tab_object}

        # One page for one-time and trigger tasks; task groups are its filter tabs.
        from ok.ui.qt.tasks.tasks_page import TasksPage
        self.tasks_page = TasksPage()
        if self.tasks_page.has_tasks():
            self.add_page(self.tasks_page, "tasks", self.tr('Tasks'), SECTION_RUN)
        else:
            self.tasks_page.dispose()
            self.tasks_page.deleteLater()
            self.tasks_page = None

        for tab_obj in after_custom_tabs:
            self.add_page(tab_obj, tab_obj.icon, self.app.tr(tab_obj.name), SECTION_GAME)

        if og.task_manager.has_custom:
            from ok.ui.qt.tasks.EditTaskTab import EditTaskTab
            self.edit_task_tab = EditTaskTab()
            self.add_page(self.edit_task_tab, "pen", self.tr('Script'), SECTION_DEVELOP)

        # Settings, Templates and global config pages are rarely opened, so they are
        # built on first use (LazyPage) to keep window construction fast.
        if og.task_manager.has_custom or debug:
            def template_tab():
                from ok.ui.qt.tasks.TemplateTab import TemplateTab
                return TemplateTab(config=config)
            self.template_tab = LazyPage(template_tab)
            self.add_page(self.template_tab, "image", self.tr('Templates'), SECTION_DEVELOP)

        from ok.ui.qt.debug.diagnosis_page import DiagnosisPage
        self.diagnosis_page = DiagnosisPage(exit_event, debug=debug)
        self.add_page(self.diagnosis_page, "pulse", self.tr('Diagnosis'), SECTION_DEVELOP)

        self._add_plugin_tab()

        # Initial load of imported tabs
        self.update_imported_tabs()
        communicate.task_list_updated.connect(self.update_imported_tabs)

        # Resolve this launch from local metadata; Windows migration runs in
        # ScheduleTaskTab's worker so COM cannot block window construction.
        try:
            from ok.ui.qt.tasks.schedule_index_sync import resolve_current_schedule_task
            resolve_current_schedule_task()
        except Exception:
            logger.exception("schedule task index sync failed in __init__")

        # 添加计划任务Tab（不要求任务 visible，未显示在 GUI 的任务也可计划调度）
        any_support_schedule = any(task.support_schedule_task for task in self.executor.onetime_tasks)
        if any_support_schedule:
            from ok.ui.qt.tasks.ScheduleTaskTab import ScheduleTaskTab
            self.schedule_tab = ScheduleTaskTab(config=self.config)
            self.add_page(self.schedule_tab, "calendar", self.tr('Schedule'), SECTION_RUN)

        from ok.ui.qt.shell.log_page import LogPage
        self.log_page = LogPage()
        self.add_page(self.log_page, "file", self.tr('Log'), SECTION_RUN)

        notification_tab = None
        for name, config_obj, option in global_config.get_all_visible_configs():
            if getattr(option, 'show_at_tab', False):
                def global_config_tab(config_obj=config_obj, option=option):
                    from ok.ui.qt.settings.GlobalConfigTab import GlobalConfigTab
                    return GlobalConfigTab(config_obj, option)
                config_tab = LazyPage(global_config_tab)
                self.global_config_tabs.append((config_obj, config_tab))
                if name == NOTIFICATION_OPTION_NAME:
                    notification_tab = config_tab
                else:
                    self.add_page(config_tab, option.icon, self.app.tr(option.name), SECTION_GAME)

        if notification_tab is not None:
            self.notification_tab = notification_tab
            self.add_page(notification_tab, "bell", self.app.tr(NOTIFICATION_OPTION_NAME), SECTION_GAME)

        def settings_page():
            from ok.ui.qt.settings.settings_page import SettingsPage
            return SettingsPage()
        self.setting_tab = LazyPage(settings_page)
        self.add_page(self.setting_tab, "gear", self.tr('Settings'), bottom=True)

        from ok.ui.qt.about.AboutTab import AboutTab
        self.about_tab = AboutTab(config, exit_event=exit_event)
        self.add_page(self.about_tab, "info", self.tr('About'), bottom=True)
        self.game_process_poll_timer = None
        self.update_check_timer = None
        self.update_toast = None
        if self.about_tab.update_card is not None:
            self.about_tab.update_card.update_available_changed.connect(self._set_about_update_available)
            self.about_tab.update_card.new_version_available.connect(self._show_new_version_toast)

        dev = self.tr('Debug')
        profile = config.get('profile', "")
        self.setWindowTitle(f'{title} {version} {profile} {dev if debug else ""}')
        self.title_bar.set_title(title)
        self.title_bar.set_badge(" ".join(part for part in (version, profile, dev if debug else "") if part))

        start_page = self.startup_task_tab() or self.stack.widget(0)
        if start_page is not None:
            self.switch_to(start_page)

        self.exclusive_toast = None
        communicate.executor_exclusive.connect(self.executor_exclusive_changed)
        communicate.tab.connect(self.navigate_tab)
        menu = QMenu()
        exit_action = menu.addAction(self.tr("Exit"))
        exit_action.triggered.connect(self.tray_quit)

        self.tray = QSystemTrayIcon(icon, parent=self)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_icon_activated)
        self.tray.show()
        self.tray.setToolTip(title)
        from ok.notification import NotificationManager, TraySystemNotifier
        self.notification_manager = NotificationManager(
            global_config, executor, exit_event, app_name=title, app_icon=config.get('gui_icon'),
            system_notifier=TraySystemNotifier(
                self.tray, QSystemTrayIcon.Information, QSystemTrayIcon.Critical))

        communicate.capture_error.connect(self.capture_error)
        communicate.notification.connect(self.show_notification)
        communicate.config_validation.connect(self.config_validation)
        communicate.starting_emulator.connect(self.starting_emulator)
        communicate.global_config.connect(self.goto_global_config)

        logger.info('main window __init__ done')

    # --- pages ----------------------------------------------------------------

    def add_page(self, widget, icon, text, section=None, bottom=False):
        """Host ``widget`` as a page with a sidebar entry; returns its navigation key."""
        if not widget.objectName():
            widget.setObjectName(f'page_{id(widget)}')
        key = widget.objectName()
        self._pages[key] = widget
        self.stack.addWidget(widget)
        self.navigation.add_item(key, text, nav_icon(icon), section, bottom=bottom)
        return key

    def remove_page(self, widget):
        key = widget.objectName()
        if self._pages.get(key) is widget:
            del self._pages[key]
            self.navigation.remove_item(key)
        self.stack.removeWidget(widget)

    def switch_to(self, widget):
        if self.stack.indexOf(widget) < 0:
            return
        defer_build = isinstance(widget, LazyPage) and not widget.is_built() and self.isVisible()
        if isinstance(widget, LazyPage) and not defer_build:
            widget.page()
        self.stack.setCurrentWidget(widget)
        self.navigation.set_current(widget.objectName())
        if defer_build:
            # Building blocks the event loop, so let the selection highlight land first.
            QTimer.singleShot(NAV_INDICATOR_DURATION + 20, lambda: self._build_lazy_page(widget))

    def _build_lazy_page(self, widget):
        if widget.is_built() or self.stack.currentWidget() is not widget:
            return  # already built, or the user moved on; it builds on the next visit
        widget.page()
        self.stack.animate_current()

    def current_page(self):
        return self.stack.currentWidget()

    def _set_about_update_available(self, available):
        self.navigation.set_badge(self.about_tab.objectName(), bool(available))

    def _game_starting_or_started(self):
        from ok import og
        ok_instance = getattr(og, 'ok', None)
        args = getattr(ok_instance, 'args', None) or {}
        return game_starting_or_started(
            auto_start_enabled=bool(self.basic_global_config.get('Auto Start Game When App Starts')),
            start_task_requested=bool(args.get('task')),
            start_controller=getattr(getattr(og, 'app', None), 'start_controller', None),
            executor=self.executor or getattr(og, 'executor', None),
        )

    def _startup_update_check(self):
        if self.about_tab.update_card is None:
            return
        if not self._game_starting_or_started():
            logger.info('startup pyappify update check')
            self.about_tab.check_for_updates(automatic=True)
            return
        if not self.config.get(UPDATE_CHECK_GAME_PROCESS_CONFIG, False):
            logger.info('skip startup pyappify update check because the game is starting or started')
            return
        logger.info('defer startup pyappify update check until the game exits')
        self.game_process_poll_timer = QTimer(self)
        self.game_process_poll_timer.timeout.connect(self._poll_game_process_for_update_check)
        self.game_process_poll_timer.start(GAME_PROCESS_POLL_INTERVAL_MS)

    @staticmethod
    def _game_running_or_launching():
        from ok import og
        start_controller = getattr(getattr(og, 'app', None), 'start_controller', None)
        if start_controller is not None and getattr(start_controller, 'starting', False):
            return True
        return game_process_exists(getattr(og, 'device_manager', None))

    def _poll_game_process_for_update_check(self):
        if self._game_running_or_launching():
            return
        self.game_process_poll_timer.stop()
        logger.info(f'game exited, check pyappify update in {GAME_PROCESS_UPDATE_DELAY_MS}ms')
        if self.update_check_timer is None:
            self.update_check_timer = QTimer(self)
            self.update_check_timer.setSingleShot(True)
            self.update_check_timer.timeout.connect(self._deferred_update_check)
        self.update_check_timer.start(GAME_PROCESS_UPDATE_DELAY_MS)

    def _deferred_update_check(self):
        if self._game_running_or_launching():
            logger.info('game started again before the deferred pyappify update check, keep waiting for exit')
            self.game_process_poll_timer.start(GAME_PROCESS_POLL_INTERVAL_MS)
            return
        self.about_tab.check_for_updates(automatic=True)

    def _show_new_version_toast(self, version):
        if self.update_toast is not None:
            self.update_toast.close()
        self.update_toast = show_toast(
            self,
            self.tr('Version {version} is available.').format(version=version),
            title=self.tr('New version available'),
            tone='accent',
            duration=0,
            actions=[
                (self.tr('Update'), lambda: self._update_to_version(version), 'primary'),
                (self.tr('Cancel'), None),
            ],
        )
        self.update_toast.destroyed.connect(self._forget_update_toast)

    def _forget_update_toast(self, *_):
        self.update_toast = None

    def _update_to_version(self, version):
        logger.info(f'update to {version} from new version toast')
        self.switch_to(self.about_tab)
        self.about_tab.update_card.update_to_version(version)

    # --- theme ----------------------------------------------------------------

    @staticmethod
    def _get_dwm_accent_color():
        """Return the DWM accent color as a compatibility fallback."""
        try:
            import ctypes
            from ctypes import wintypes

            colorization_color = wintypes.DWORD()
            opaque_blend = wintypes.BOOL()
            result = ctypes.windll.dwmapi.DwmGetColorizationColor(
                ctypes.byref(colorization_color), ctypes.byref(opaque_blend)
            )
            if result != 0:
                return None

            argb = colorization_color.value
            return QColor((argb >> 16) & 0xff, (argb >> 8) & 0xff, argb & 0xff)
        except (AttributeError, OSError):
            logger.exception('Failed to read the Windows system accent color')
            return None

    def get_system_accent_color(self):
        """Return the base Windows accent color (legacy helper)."""
        return self._get_dwm_accent_color()

    def _system_accent(self, color_type_name='Accent'):
        try:
            from ok.rotypes.Windows.UI.ViewManagement import UIColorType, get_color_value
            value = get_color_value(getattr(UIColorType, color_type_name))
            return QColor(value.red, value.green, value.blue)
        except (ImportError, OSError, TypeError, AttributeError):
            logger.exception('Failed to read the Windows accent color palette')
            return self.get_system_accent_color()

    def _sync_kit_theme(self):
        """Apply the saved theme mode, window backdrop and the Windows accent color."""
        kit_theme.set_theme(KitTheme(ui_config.theme_mode))
        kit_theme.set_backdrop(ui_config.backdrop)
        if accent := self._system_accent():
            kit_theme.set_accent(accent)

    def _apply_system_theme_change(self):
        """Pick up a new Windows accent; the kit follows light/dark itself in system mode."""
        try:
            self._sync_kit_theme()
            logger.info(f'System theme synchronized: mode={ui_config.theme_mode}, dark={kit_theme.is_dark()}')
        finally:
            self._theme_cooldowns.discard('system-theme')

    def _schedule_system_theme_change(self):
        if not hasattr(self, '_theme_cooldowns'):
            self._theme_cooldowns = set()
        if 'system-theme' in self._theme_cooldowns:
            return
        self._theme_cooldowns.add('system-theme')
        QTimer.singleShot(250, self._apply_system_theme_change)

    def nativeEvent(self, event_type, message):
        try:
            import ctypes
            from ctypes import wintypes

            native_message = wintypes.MSG.from_address(int(message))
            if native_message.message == 0x0320:  # WM_DWMCOLORIZATIONCOLORCHANGED
                logger.info('System colorization colors changed')
                self._schedule_system_theme_change()
            elif (
                native_message.message == 0x001A  # WM_SETTINGCHANGE
                and native_message.lParam
                and ctypes.wstring_at(native_message.lParam) == "ImmersiveColorSet"
            ):
                logger.info('System theme changed')
                self._schedule_system_theme_change()
        except (OSError, TypeError, ValueError) as e:
            logger.error('Failed to process Windows theme change', e)

        return super().nativeEvent(event_type, message)

    # --- plugins and imported scripts -----------------------------------------

    def update_imported_tabs(self):
        """Update navigation pages for imported scripts."""
        from ok.ui.qt.plugins.imported_tabs import ImportedTabs
        if not hasattr(self, '_imported_tab_controller'):
            self._imported_tab_controller = ImportedTabs(self)
        self._imported_tab_controller.refresh()

    def _add_plugin_tab(self):
        if self.config.get('plugin', False):
            from ok.ui.qt.plugins.PluginTab import PluginTab
            self.plugin_tab = PluginTab()
            self.add_page(self.plugin_tab, "grid", self.plugin_tab.tr('Plugins'), SECTION_DEVELOP)

    # --- dialogs and notifications --------------------------------------------

    def restart_admin(self):
        dialog = Dialog(self, QCoreApplication.translate("app", "Alert"),
                        QCoreApplication.translate("StartController",
                                                   "PC version requires admin privileges, Please restart this app with admin privileges!"))
        accepted = dialog.exec()
        dialog.deleteLater()
        if accepted:
            logger.info('restart_admin Yes button is pressed')
            thread = threading.Thread(target=restart_as_admin, daemon=True)
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

    def bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if self.windowHandle():
            self.windowHandle().requestActivate()
        if os.name == 'nt':
            try:
                import win32con
                import win32gui
                hwnd = int(self.winId())
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
            except Exception as e:
                logger.debug(f'bring_to_front native activation failed: {e}')

    def goto_global_config(self, key):
        for config_obj, config_tab in self.global_config_tabs:
            if key in config_obj:
                self.switch_to(config_tab)
                return
        self.switch_to(self.setting_tab)
        self.setting_tab.page().goto_config(key)

    def tray_quit(self):
        logger.info('main window tray_quit')
        self.app.quit()

    def show_update_copyright(self):
        dialog = Dialog(self, self.tr('Info'), self.tr(
            "This is a free software. If you purchased this anywhere, request a refund from the seller."))
        dialog.set_cancel_visible(False)
        dialog.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dialog.exec()
        dialog.deleteLater()
        self.switch_to(self.about_tab)

    def show_startup_version_change_notice(self):
        version_change = get_startup_version_change()
        if not version_change:
            return

        logger.info(f'show startup version change on about tab {version_change.title}')
        self.switch_to(self.about_tab)

    def showEvent(self, event):
        first_show = event.type() == QEvent.Show and not self.shown
        if first_show:
            self.shown = True
            pyappify.hide_pyappify()
            if update_pyappify := self.config.get("update_pyappify"):
                pyappify.upgrade(
                    update_pyappify.get('to_version'),
                    update_pyappify.get('sha256'),
                    [update_pyappify.get('zip_url')],
                    exit_event=self.exit_event,
                )
            logger.info("Window has fully displayed")
            from ok import og
            og.ok.start_runtime()
            if self.basic_global_config.get(KILL_LAUNCHER_AFTER_START):
                logger.info(f'MainWindow showEvent Kill Launcher After Start')
                request_pyappify_shutdown()
            startup_version_change = get_startup_version_change()
            if self.version != self.main_window_config.get('last_version'):
                self.main_window_config['last_version'] = self.version
                if not self.config.get('auth') and not startup_version_change:
                    logger.info('update success, show copyright')
                    self.handler.post(lambda: communicate.copyright.emit(), delay=1)
                elif startup_version_change:
                    logger.info('skip copyright dialog because startup version change is shown on about tab')
            # Check for .okscript file in command line arguments
            self._check_okscript_args()
        super().showEvent(event)
        if first_show:
            QTimer.singleShot(0, self.bring_to_front)
            QTimer.singleShot(250, self.show_startup_version_change_notice)
            # These start worker threads that hold the GIL; started here they delay the
            # first paint by several hundred milliseconds, so they wait until it is done.
            QTimer.singleShot(POST_SHOW_STARTUP_DELAY_MS, self._post_show_startup)

    def _post_show_startup(self):
        if self.exit_event is not None and self.exit_event.is_set():
            return
        # The MCP server goes first: an agent may be waiting to connect, and the
        # update check would compete with it for the GIL.
        if not self._start_deferred_mcp_server():
            self._start_background_checks()

    def _start_background_checks(self):
        self._startup_update_check()
        create_app_shortcut(self.basic_global_config)

    def _start_deferred_mcp_server(self):
        """Begin the MCP start ``OK.start`` postponed; False when there is none to do."""
        from ok import og
        runtime = getattr(og, 'ok', None)
        if runtime is None or not runtime.take_deferred_mcp_start():
            return False

        def preload():
            # Importing the SDK is the slow part; do it off the GUI thread.
            try:
                import mcp.server  # noqa: F401
                import uvicorn  # noqa: F401
            except Exception:
                pass  # start_mcp_server reports the import error
            self.mcp_sdk_loaded.emit()

        threading.Thread(target=preload, name='McpPreload', daemon=True).start()
        return True

    def _on_mcp_sdk_loaded(self):
        from ok import og
        if self.exit_event is not None and self.exit_event.is_set():
            return
        try:
            og.ok.start_mcp_server()
        except Exception as error:
            # As when the server was started before the window: without it this
            # launch is not what was asked for.
            logger.error('start mcp server error', error)
            og.ok.quit()
            return
        self._start_background_checks()

    # --- geometry -------------------------------------------------------------

    def set_window_size(self, width, height, min_width, min_height):
        screen = self.screen().availableGeometry()
        width, height, min_width, min_height = fit_window_size(
            width, height, min_width, min_height, screen.width(), screen.height())
        self.setMinimumSize(QSize(min_width, min_height))
        if (self.ok_config['window_width'] > 0 and self.ok_config['window_height'] > 0 and
                self.ok_config['window_y'] > 0 and self.ok_config['window_x'] > 0):
            x, y = self.ok_config['window_x'], self.ok_config['window_y']
            saved_width, saved_height, _, _ = fit_window_size(
                self.ok_config['window_width'], self.ok_config['window_height'], min_width, min_height,
                screen.width(), screen.height())
            if self.ok_config['window_maximized']:
                self.setWindowState(Qt.WindowMaximized)
            else:
                x = max(screen.left(), min(x, screen.right() - saved_width))
                y = max(screen.top(), min(y, screen.bottom() - saved_height))
                self.setGeometry(x, y, saved_width, saved_height)
        else:
            x = screen.left() + (screen.width() - width) // 2
            y = screen.top() + (screen.height() - height) // 2
            self.setGeometry(x, y, width, height)
        self.apply_navigation_state()

    def apply_navigation_state(self):
        self.navigation.set_compact(not self.ok_config.get('navigation_expanded', True), animate=False)

    def _save_navigation_state(self, compact):
        self.ok_config['navigation_expanded'] = not compact

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._post_geometry_update()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._post_geometry_update()

    def _post_geometry_update(self):
        # Geometry events also arrive while the native window is created in __init__.
        handler = getattr(self, 'handler', None)
        if handler is not None and getattr(self, 'shown', False):
            handler.post(self.update_ok_config, remove_existing=True, skip_if_running=True, delay=1)

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

    # --- executor events ------------------------------------------------------

    def starting_emulator(self, done, error, seconds_left):
        # The run bar shows launch progress; failures open the connection settings.
        if error:
            alert_error(error, True)
            self.run_bar.open_popover()

    def config_validation(self, message):
        title = self.tr('Error')
        show_toast(self, message, title, "danger", duration=5000)
        self.tray.showMessage(title, message)

    def show_notification(self, message, title=None, error=False, tray=False, show_tab=None, params=None, images=None):
        from ok import og
        translated_message = QCoreApplication.translate("app", message)
        if params:
            translated_message = translated_message.format(**params)
        translated_title = og.app.tr(title) if title else ""
        show_toast(self.window(), translated_message, translated_title or None, "danger" if error else "neutral",
                   duration=8000)
        notification_manager = getattr(self, 'notification_manager', None)
        if notification_manager is not None:
            notification_manager.notify_system(
                translated_title, translated_message, error, tray)
            notification_manager.submit(translated_title, translated_message, images)
        self.navigate_tab(show_tab)

    def capture_error(self):
        self.show_notification(self.tr('Please check whether the game window is selected correctly!'),
                               self.tr('Capture Error'), error=True)

    def navigate_tab(self, index):
        logger.debug(f'navigate_tab {index}')
        if index == "start":
            self.run_bar.open_popover()
        elif index in ("onetime", "trigger") and self.tasks_page is not None:
            self.switch_to(self.tasks_page)
            self.tasks_page.set_filter(index)
        elif index == "schedule" and self.schedule_tab is not None:
            self.switch_to(self.schedule_tab)
        elif index == "log":
            self.switch_to(self.log_page)
        elif index == "diagnosis":
            self.switch_to(self.diagnosis_page)
        elif index == "about" and self.about_tab is not None:
            self.switch_to(self.about_tab)

    def startup_task_tab(self):
        """Return the Tasks page, falling back to imported plugin pages."""
        if self.tasks_page is not None:
            return self.tasks_page
        if self.imported_tabs:
            return next(iter(self.imported_tabs.values()))
        controller = getattr(self, '_imported_tab_controller', None)
        if controller is not None and controller.custom_tabs:
            return next(iter(controller.custom_tabs.values()))[0]
        return None

    def show_task(self, task):
        """Open the page that lists ``task`` and select it."""
        if self.tasks_page is not None and self.tasks_page.has_task(task):
            self.switch_to(self.tasks_page)
            self.tasks_page.select_task(task)
            return True
        for tab in self.imported_tabs.values():
            if tab.in_current_list(task):
                self.switch_to(tab)
                return True
        return False

    def executor_exclusive_changed(self, owner):
        if self.exclusive_toast is not None:
            try:
                self.exclusive_toast.close()
            except RuntimeError:
                # Already deleted by Qt.
                pass
            self.exclusive_toast = None
        if owner is None:
            return
        self.exclusive_toast = show_toast(
            self,
            self.tr('{owner} is controlling the app. Other tasks are stopped.').format(owner=owner),
            self.tr('Remote Control'), "warning", duration=0,
            action=(self.tr('Disconnect'), lambda: self.executor.release_exclusive(owner)))

    def _check_okscript_args(self):
        """Check sys.argv for .okscript files and import them."""
        import sys
        for arg in sys.argv[1:]:
            if arg.lower().endswith('.okscript') and os.path.exists(arg):
                logger.info(f'Found .okscript file in args: {arg}')
                try:
                    if hasattr(self, 'edit_task_tab'):
                        self.edit_task_tab._do_import(arg)
                    else:
                        from ok.ui.qt.tasks.ScriptPackager import import_script
                        success, message, import_folder = import_script(arg)
                        if success:
                            from ok import og
                            og.task_manager.load_import_folder(import_folder)
                            show_toast(self, message, self.tr('Success'), "success")
                        else:
                            alert_error(self.tr("Import failed: {error}").format(error=message))
                except Exception as e:
                    logger.error(f'Error importing .okscript file: {e}')

    def dispose(self):
        """Release app-wide hooks so a replacement window can take over, e.g. after a language change."""
        for timer in (self.game_process_poll_timer, self.update_check_timer):
            if timer is not None:
                timer.stop()
        self.tray.hide()
        self.run_bar.dispose()
        notification_manager = getattr(self, 'notification_manager', None)
        if notification_manager is not None:
            # Stopping waits for the pipeline thread; keep the GUI thread free.
            threading.Thread(target=notification_manager.stop, name='NotificationStop', daemon=True).start()
        controller = getattr(self, '_imported_tab_controller', None)
        if controller is not None:
            controller.dispose()
        for page in list(self._pages.values()):
            cleanup = getattr(page, 'dispose', None) or getattr(page, 'stop_worker', None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception as error:
                    logger.error(f'Failed to dispose page {page.objectName()}', error)
        # The event bus holds strong references; drop the ones owned by this window's widgets.
        owners = {id(obj) for obj in (self, *self.findChildren(QObject))}
        communicate.disconnect_where(lambda callback: id(getattr(callback, '__self__', None)) in owners)

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
                # Arm this before callbacks such as aboutToQuit can run. If a
                # native cleanup call wedges the GUI thread, the process still
                # has a bounded shutdown time and a diagnostic thread dump.
                from ok.util.process import start_exit_watchdog
                start_exit_watchdog()
                self.exit_event.set()
                self.executor.request_destroy()
            event.accept()
            if not self.do_not_quit:
                request_pyappify_shutdown()
                QApplication.instance().exit()
