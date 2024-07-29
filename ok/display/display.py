import winreg

from ok.display.custom_types import DisplayMonitor
from ok.display.display_monitors import get_all_display_monitors
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


def is_night_light_enabled():
    try:
        key_path = 'Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\default$windows.data.bluelightreduction.bluelightreductionstate\windows.data.bluelightreduction.bluelightreductionstate'
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        value, type = winreg.QueryValueEx(key, "Data")
        winreg.CloseKey(key)
        if len(value) > 18:
            enabled = (value[18] == 0x15)
        else:
            logger.warning(f'is_night_light_enabled index of out bounds')
            enabled = False
        logger.info(f'is_night_light_enabled is {enabled}')
        return enabled
    except Exception as e:
        logger.error(f'is_night_light_enabled error', e)
        return False


def is_hdr_enabled():
    try:
        all_monitors: list[DisplayMonitor] = get_all_display_monitors()
        for monitor in all_monitors:
            if monitor.is_hdr_enabled():
                logger.info(f'is_hdr_enabled is enabled {monitor.name}')
                return True
    except Exception as e:
        logger.error(f'is_hdr_enabled error', e)
        return False
