## analytics
import ctypes
import hashlib
import platform
import uuid

import psutil
import requests

from ok.util.config import Config
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class Analytics:
    def __init__(self, app_config, exit_event, handler, device_manager):
        self.report_url = app_config.get('analytics').get('report_url')
        self.app_config = app_config
        self.device_manager = device_manager
        self._config = None
        self.handler = handler
        self.handler.post(self.send_alive, 20)
        self._user_properties = None
        self._fv = 1

    @property
    def user_properties(self):
        if self._user_properties is None:
            os_name_val = 'windows'
            os_version_val = "Unknown"
            os_build_val = 0
            cpu_name_val = "Unknown"
            total_memory_gb_val = 0
            # gpu_name_val is removed as per instruction

            try:
                # Get OS information
                kernel_ver_str = platform.win32_ver()[1]
                os_ver_intermediate = kernel_ver_str.split('.')[0]
                os_build_val = int(kernel_ver_str.split('.')[-1])

                reported_os_version = os_ver_intermediate
                if os_ver_intermediate == "10" and os_build_val >= 22000:
                    reported_os_version = "11"
                os_version_val = reported_os_version
            except Exception as e:
                logger.error(f"Error getting OS info: {e}")

            try:
                # Get CPU information using platform.processor()
                cpu_name_val = platform.processor().strip()
                if not cpu_name_val:  # Fallback if platform.processor() returns empty
                    cpu_name_val = "Unknown"
            except Exception as e:
                logger.error(f"Error getting CPU info: {e}")
                cpu_name_val = "Unknown"  # Ensure fallback on error

            try:
                # Get total memory (in GB) using psutil
                total_memory_bytes = psutil.virtual_memory().total
                total_memory_gb_val = float(total_memory_bytes) / (1024 ** 3)  # Bytes to GB
            except Exception as e:
                logger.error(f"Error getting memory info: {e}")

            # GPU information collection is removed.

            self._user_properties = {
                "os": os_name_val,
                "os_version": str(os_version_val),
                "os_build": str(os_build_val),
                "cpu": cpu_name_val,
                "memory": str(int(total_memory_gb_val)),
            }

            config = self.device_manager.config
            if config:
                self._user_properties["device"] = config.get('preferred')
                self._user_properties["device_capture"] = config.get('capture')

            capture = self.device_manager.capture_method
            if capture:
                if hasattr(capture, '_size'):
                    width, height = capture._size
                    if width and height:
                        self._user_properties["device_sr"] = f'{width}x{height}'
                else:
                    logger.warning("og.device_manager.capture_method exists but has no _size attribute.")
        return self._user_properties

    @property
    def client_id(self):
        if self._config is None:
            self._config = Config('statistics', {'client_id': ''})
        if not self._config.get('client_id'):
            self._config['client_id'] = self.get_unique_client_id()
        else:
            self._fv = 0
        return self._config.get('client_id')

    def send_alive(self):
        from ok.gui.common.config import cfg
        params = {
            "device_id": self.client_id,
            "app_version": self.app_config.get('version'),
            "app_name": self.app_config.get('app_id') or self.app_config.get('gui_title'),
            'locale': cfg.get(cfg.language).value.name(),
            'sr': get_screen_resolution(),
            "os": 'windows',
        }

        params.update(self.user_properties)

        logger.info(f'send report {params}')
        try:
            response = requests.post(self.report_url, json=params, timeout=10)
            if response.status_code == 200:
                logger.debug(f'Successfully send report')
            else:
                logger.error(f'Failed to send event: {response.status_code} - {response.text}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Failed to send report due to network error: {e}')
        self.handler.post(self.send_alive, 3600 * 6)

    def get_unique_client_id(self):
        user_dict = self.user_properties.copy()
        user_dict['mac'] = uuid.getnode()
        if 'os_build' in user_dict:
            del user_dict['os_build']
        # "gpu" key will not be in user_dict if it's not in user_properties
        global hash_dict_keys_values
        if 'hash_dict_keys_values' not in globals():
            import hashlib, json
            def hash_dict_keys_values(d):
                s = json.dumps(d, sort_keys=True)
                return hashlib.sha256(s.encode('utf-8')).hexdigest()
        return hash_dict_keys_values(user_dict)


def get_screen_resolution():
    user32 = ctypes.windll.user32
    screensize = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return f"{screensize[0]}x{screensize[1]}"


def hash_dict_keys_values(my_dict):
    # Sort the dictionary by keys
    sorted_items = sorted(my_dict.items())

    # Initialize an empty string to store concatenated key-value pairs
    concatenated_kv = ''

    # Concatenate sorted key-value pairs
    for key, value in sorted_items:
        concatenated_kv += f'{key}{value}'

    # Encode the concatenated string
    encoded_kv = concatenated_kv.encode()

    # Create a new md5 hash object
    hash_object = hashlib.md5(encoded_kv)

    # Get the hexadecimal representation of the hash
    hash_hex = hash_object.hexdigest()

    return hash_hex
