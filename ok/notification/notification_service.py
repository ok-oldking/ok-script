import threading

from qfluentwidgets import FluentIcon

from ok.notification.discord_webhook import DiscordWebhookNotifier
from ok.util.config import ConfigOption
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


def send_discord_test_notification() -> None:
    from ok import og

    config = dict(og.global_config.get_config(notification_config_option))
    if not config.get('Discord Webhook URL'):
        logger.error('Discord Webhook URL is empty')
        return
    config['Enable Discord Webhook'] = True

    message = 'Discord webhook test notification'
    if og.app is not None:
        message = og.app.tr(message)
    NotificationService(config).notify('INFO', message)


notification_config_option = ConfigOption(
    'Notification Config',
    {
        'Enable Discord Webhook': False,
        'Discord Webhook URL': '',
        'Discord Username': '',
        'Mention User ID': '',
        'Notify On Info': True,
        'Notify On Error': True,
        'Attach Screenshot': True,
    },
    description='Send external task notifications',
    config_description={
        'Enable Discord Webhook': 'Send task notifications to a Discord webhook',
        'Discord Webhook URL': 'Discord webhook URL',
        'Discord Username': 'Webhook display name',
        'Mention User ID': 'Optional Discord user ID to mention',
        'Notify On Info': 'Send notifications for informational task events',
        'Notify On Error': 'Send notifications for task errors',
        'Attach Screenshot': 'Attach the latest captured frame when available',
        'Send Test Notification': 'Send a test notification to Discord',
    },
    config_type={
        'Discord Webhook URL': {'type': 'text_edit'},
        'Send Test Notification': {
            'type': 'button',
            'text': 'Send Test Notification',
            'callback': send_discord_test_notification,
        },
    },
    icon=FluentIcon.MESSAGE,
)


class NotificationService:

    def __init__(self, config: dict | None, title: str = 'OK'):
        self.config = config or {}
        self.title = title

    def notify(self, level: str, message: str, task=None, title: str | None = None, params: dict | None = None) -> None:
        if not self.config.get('Enable Discord Webhook'):
            return
        if level == 'INFO' and not self.config.get('Notify On Info', True):
            return
        if level == 'ERROR' and not self.config.get('Notify On Error', True):
            return

        webhook_url = self.config.get('Discord Webhook URL', '')
        if not webhook_url:
            return

        if params:
            message = str(message).format(**params)

        screenshot = self._get_screenshot(task)
        task_name = ''
        if task is not None:
            task_name = getattr(task, 'name', '') or task.__class__.__name__
        notifier = DiscordWebhookNotifier(
            webhook_url=webhook_url,
            username=self.config.get('Discord Username', ''),
        )
        thread = threading.Thread(
            target=self._send_safely,
            args=(notifier, level, title or self.title, message, task_name, screenshot,
                  self.config.get('Mention User ID', '')),
            daemon=True,
            name='DiscordNotification',
        )
        thread.start()

    def _get_screenshot(self, task):
        if not self.config.get('Attach Screenshot', True) or task is None:
            return None
        try:
            frame = task.executor.nullable_frame()
            return frame.copy() if frame is not None else None
        except Exception:
            logger.debug('Could not capture notification screenshot')
            return None

    @staticmethod
    def _send_safely(
            notifier: DiscordWebhookNotifier,
            level: str,
            title: str,
            message: str,
            task_name: str,
            screenshot,
            mention_user_id: str,
    ) -> None:
        try:
            notifier.send(
                title=title,
                message=message,
                level=level,
                task_name=task_name,
                screenshot=screenshot,
                mention_user_id=mention_user_id,
            )
        except Exception as e:
            logger.error(f'Discord notification failed: {e}')


def notify_from_task(task, level: str, message: str, title: str | None = None, params: dict | None = None) -> None:
    try:
        from ok import og

        if og.global_config is None:
            return
        config = og.global_config.get_config(notification_config_option)
        app_title = og.config.get('gui_title', 'OK') if og.config else 'OK'
        NotificationService(config, title=app_title).notify(level, message, task=task, title=title, params=params)
    except Exception as e:
        logger.debug(f'External notification skipped: {e}')
