import ctypes
import hashlib
import locale
import random
import uuid

import requests
import wmi

import ok.gui
from ok.config.Config import Config
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler

logger = get_logger(__name__)


class Analytics:
    def __init__(self, app_config, exit_event):
        self.report_url = app_config.get('analytics').get('report_url')
        self.app_config = app_config
        self._config = None
        self._handler = Handler(exit_event, __name__)
        self._handler.post(self.send_alive, 20)
        self._user_properties = None
        self._fv = 1

    @property
    def user_properties(self):
        if self._user_properties is None:
            c = wmi.WMI()

            # Get OS information
            os_info = c.Win32_OperatingSystem()[0]
            os_version = os_info.Version.split(".")[0]
            os_build = int(os_info.BuildNumber)

            if os_version == "10" and os_build >= 22000:  # Windows 11 starts from build 22000
                os_version = "11"

            # Get CPU information
            cpu_info = c.Win32_Processor()[0]
            cpu_name = cpu_info.Name.strip()

            # Get total memory (in GB)
            total_memory = float(os_info.TotalVisibleMemorySize) / 1048576  # KB to GB

            # Get graphics card information
            gpu_info = c.Win32_VideoController()
            gpu_name = None
            for gpu in reversed(gpu_info):
                if "intel" not in gpu.Name.lower() and "microsoft" not in gpu.Name.lower():
                    gpu_name = gpu.Name
                    break
            if not gpu_name and gpu_info:
                gpu_name = gpu_info[0].Name

            # Put the information into a dictionary
            self._user_properties = {
                "os": 'windows',
                "os_version": os_version,
                "os_build": str(os_build),
                "cpu": cpu_name,
                "memory": str(int(total_memory)),
                "gpu": gpu_name,
            }
            config = ok.gui.device_manager.config
            if config:
                self._user_properties["device"] = config.get('preferred')
                self._user_properties["device_capture"] = config.get('capture')
            capture = ok.gui.device_manager.capture_method
            if capture:
                width, height = ok.gui.device_manager.capture_method._size
                if width and height:
                    self._user_properties["device_sr"] = f'{width}x{height}'
        return self._user_properties

    #
    # def report_open(self):
    #     self._handler.post(self.send_gtag, 5)
    #     # self.send_event('app_open', {'version': self.app_config.get('version'), 'debug': self.app_config.get('debug')})

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

        params = {
            "device_id": self.client_id,
            "app_version": self.app_config.get('version'),
            "app_name": self.app_config.get('app_id') or self.app_config.get('gui_title'),
            'locale': locale.getdefaultlocale()[0],
            'sr': get_screen_resolution(),
            "os": 'windows',
        }

        params.update(self.user_properties)

        logger.info(f'send report {params}')

        response = requests.post(self.report_url, json=params, timeout=10)

        if response.status_code == 200:
            logger.debug(f'Successfully send report')
        else:
            logger.error(f'Failed to send event: {response.status_code} - {response.text}')

        self._handler.post(self.send_alive, 3600)

    def get_unique_client_id(self):
        user_dict = self.user_properties.copy()
        user_dict['mac'] = uuid.getnode()
        del user_dict['os_build']
        return hash_dict_keys_values(user_dict)


def get_bios_serial_number():
    try:
        c = wmi.WMI()
        for bios in c.Win32_BIOS():
            return bios.SerialNumber.strip()
    except Exception as e:
        print(f"Error retrieving BIOS serial number: {e}")
        return None


def random_number():
    return random.randint(0, 2147483647)


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


if __name__ == '__main__':
    # Generate a unique client ID (UUID)
    client_id = str(uuid.uuid4())
    analytics = Analytics('G-9W3F3EQ19G', api_secret='eAkNmhrERiGg8Q3Riuxerw')
    # Send a test event
    analytics.send_event('app_open')
    analytics.send_event('test1')
    analytics.send_event('test2')
