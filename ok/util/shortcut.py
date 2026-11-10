import sys
import threading

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

SHORTCUTS_CHANGED_TITLE = 'Shortcuts'
SHORTCUTS_CHANGED_MESSAGE = 'Created or updated shortcuts: {paths}'


def notify_shortcuts_changed(paths):
    """Tell the user which shortcuts were written; text is translated in the "app" context."""
    from ok.core.events import communicate
    communicate.notification.emit(SHORTCUTS_CHANGED_MESSAGE, SHORTCUTS_CHANGED_TITLE, False, True, None,
                                  {'paths': ', '.join(paths)}, None)


def create_and_notify(start_menu, desktop):
    """Create the shortcuts and notify when any was created or changed; returns those paths."""
    import pyappify
    try:
        # pyappify returns only the shortcuts it created or changed.
        paths = pyappify.create_shortcut(start_menu=start_menu, desktop=desktop)
    except Exception as error:
        logger.warning(f'pyappify.create_shortcut failed: {error}')
        return []
    if paths:
        logger.info(f'pyappify.create_shortcut created or updated {paths}')
        notify_shortcuts_changed(paths)
    else:
        logger.info('pyappify.create_shortcut: shortcuts are up to date')
    return paths or []


def create_app_shortcut(basic_config=None):
    """Create the app's shortcuts through pyappify on a background thread.

    Works without Qt so both GUI and console modes can call it. Older pyappify
    versions without ``create_shortcut`` are skipped. ``basic_config`` supplies
    the Basic Options choosing the Start Menu and Desktop shortcuts.
    """
    from ok.util.GlobalConfig import CREATE_DESKTOP_SHORTCUT, CREATE_START_MENU_SHORTCUT, shortcut_supported

    if 'pytest' in sys.modules:
        # Never write real Start Menu/Desktop shortcuts pointing at a test run.
        return None
    if not shortcut_supported():
        logger.info('skip creating shortcut because pyappify has no create_shortcut')
        return None
    basic_config = basic_config if basic_config is not None else {}
    start_menu = bool(basic_config.get(CREATE_START_MENU_SHORTCUT, True))
    desktop = bool(basic_config.get(CREATE_DESKTOP_SHORTCUT, True))
    if not start_menu and not desktop:
        logger.info('skip creating shortcut because both shortcut options are disabled')
        return None

    thread = threading.Thread(target=create_and_notify, args=(start_menu, desktop),
                              name='PyAppifyCreateShortcut', daemon=True)
    thread.start()
    return thread
