import json
import uuid

import requests
import wmi

from ok.config.Config import Config
from ok.logging.Logger import get_logger
from ok.util.Handler import Handler

FIREBASE_ENDPOINT = 'https://www.google-analytics.com/mp/collect'

logger = get_logger(__name__)


class FireBaseAnalytics:
    def __init__(self, app_config, exit_event):
        self.measurement_id = app_config.get('firebase').get('measurement_id')
        self.api_secret = app_config.get('firebase').get('api_secret')
        self.app_config = app_config
        self._config = None
        self._handler = Handler(exit_event, __name__)
        self._handler.post(self.report_open, 10)
        self._user_properties = None

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
                "os_build": os_build,
                "cpu": cpu_name,
                "memory": int(total_memory),
                "gpu": gpu_name
            }
        return self._user_properties

    def report_open(self):
        self.send_event('app_open', {'version': self.app_config.get('version'), 'debug': self.app_config.get('debug')})

    @property
    def client_id(self):
        if self._config is None:
            self._config = Config({'client_id': ''}, self.app_config.get("config_folder") or "config", 'statistics')
        if not self._config.get('client_id'):
            self._config['client_id'] = get_unique_client_id()
        return self._config.get('client_id')

    def send_event(self, event_name, params=None):
        if params is None:
            params = dict()
        payload = {
            'client_id': self.client_id,
            'events': [
                {
                    'name': event_name,
                    'params': params
                }
            ],
            'user_properties': self.user_properties
        }

        headers = {
            'Content-Type': 'application/json'
        }

        response = requests.post(
            f'{FIREBASE_ENDPOINT}?measurement_id={self.measurement_id}&api_secret={self.api_secret}',
            data=json.dumps(payload),
            headers=headers
        )

        logger.debug(f'send {event_name} {payload}')
        if response.status_code == 204:
            logger.debug(f'Successfully sent event: {event_name}')
        else:
            logger.debug(f'Failed to send event: {response.status_code} - {response.text}')


def get_unique_client_id():
    return str(uuid.uuid4())


if __name__ == '__main__':
    # Generate a unique client ID (UUID)
    client_id = str(uuid.uuid4())
    analytics = FireBaseAnalytics('G-9W3F3EQ19G', api_secret='eAkNmhrERiGg8Q3Riuxerw')
    # Send a test event
    analytics.send_event('app_open')
    analytics.send_event('test1')
    analytics.send_event('test2')
