import io

import cv2
import requests
from PIL import Image

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class DiscordProvider:
    def send(self, webhook, title, message, images, sender=None, sender_icon=None):
        webhook = (webhook or '').strip()
        if not webhook:
            logger.warning('Discord notification is enabled but its webhook is empty')
            return False

        content = f'**{title}**\n{message}' if title else message
        files = []
        buffers = []
        try:
            for index, frame in enumerate(images or []):
                image = frame
                if len(image.shape) == 2:
                    image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
                else:
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                buffer = io.BytesIO()
                Image.fromarray(image).save(buffer, format='PNG')
                buffer.seek(0)
                buffers.append(buffer)
                files.append(('files', (f'notification_{index + 1}.png', buffer, 'image/png')))
            data = {'content': content}
            if sender:
                data['username'] = str(sender)[:80]
            if sender_icon and str(sender_icon).lower().startswith(('https://', 'http://')):
                data['avatar_url'] = str(sender_icon)
            response = requests.post(webhook, data=data, files=files or None, timeout=30)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error('Discord notification failed', e)
            return False
        finally:
            for buffer in buffers:
                buffer.close()
