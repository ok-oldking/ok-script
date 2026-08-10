import io
import hashlib
import base64

import cv2
import requests
from PIL import Image

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


def _png_bytes(frame):
    image = frame
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    else:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format='PNG')
    return buffer.getvalue()


def _content(title, message):
    return f'{title}\n{message}' if title else message


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


class TelegramBotProvider:
    """Telegram Bot API provider using sendMessage/sendPhoto."""

    def send(self, token, chat_id, title, message, images):
        token = (token or '').strip()
        chat_id = str(chat_id or '').strip()
        if not token or not chat_id:
            logger.warning('Telegram notification is enabled but token or chat ID is empty')
            return False
        base_url = f'https://api.telegram.org/bot{token}'
        text = _content(title, message)
        try:
            if text:
                response = requests.post(
                    f'{base_url}/sendMessage',
                    json={'chat_id': chat_id, 'text': text}, timeout=30)
                response.raise_for_status()
                if response.json().get('ok') is False:
                    raise RuntimeError(response.text)
            for frame in images or []:
                response = requests.post(
                    f'{base_url}/sendPhoto',
                    data={'chat_id': chat_id},
                    files={'photo': ('notification.png', io.BytesIO(_png_bytes(frame)), 'image/png')},
                    timeout=30)
                response.raise_for_status()
                if response.json().get('ok') is False:
                    raise RuntimeError(response.text)
            return True
        except Exception as e:
            logger.error('Telegram notification failed', e)
            return False


class WeComWebhookProvider:
    """Enterprise WeChat (WeCom) group robot webhook provider."""

    def send(self, webhook, title, message, images):
        webhook = (webhook or '').strip()
        if not webhook:
            logger.warning('WeCom notification is enabled but webhook is empty')
            return False
        text = _content(title, message)
        try:
            if text:
                response = requests.post(
                    webhook,
                    json={'msgtype': 'markdown', 'markdown': {'content': text}},
                    timeout=30)
                response.raise_for_status()
                self._check_response(response)
            for frame in images or []:
                payload = base64.b64encode(_png_bytes(frame)).decode('ascii')
                response = requests.post(
                    webhook,
                    json={'msgtype': 'image', 'image': {
                        'base64': payload,
                        'md5': hashlib.md5(base64.b64decode(payload)).hexdigest(),
                    }}, timeout=30)
                response.raise_for_status()
                self._check_response(response)
            return True
        except Exception as e:
            logger.error('WeCom notification failed', e)
            return False

    @staticmethod
    def _check_response(response):
        data = response.json()
        if data.get('errcode', 0) != 0:
            raise RuntimeError(data.get('errmsg', response.text))


class QQBotProvider:
    """QQ Guild Bot API provider for channel messages."""

    def send(self, app_id, token, channel_id, title, message, images=None):
        app_id = str(app_id or '').strip()
        token = str(token or '').strip()
        channel_id = str(channel_id or '').strip()
        if not app_id or not token or not channel_id:
            logger.warning('QQ Bot notification is enabled but credentials are incomplete')
            return False
        text = _content(title, message)
        if images:
            text = f'{text}\n[{len(images)} image(s) attached]' if text else f'[{len(images)} image(s) attached]'
        try:
            response = requests.post(
                f'https://api.sgroup.qq.com/channels/{channel_id}/messages',
                headers={'Authorization': f'Bot {app_id}.{token}'},
                json={'content': text}, timeout=30)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error('QQ Bot notification failed', e)
            return False
