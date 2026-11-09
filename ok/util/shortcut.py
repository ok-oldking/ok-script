import sys
import threading

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


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

    import pyappify

    def run():
        try:
            paths = pyappify.create_shortcut(start_menu=start_menu, desktop=desktop)
            logger.info(f'pyappify.create_shortcut created {paths}')
        except Exception as error:
            logger.warning(f'pyappify.create_shortcut failed: {error}')

    thread = threading.Thread(target=run, name='PyAppifyCreateShortcut', daemon=True)
    thread.start()
    return thread
