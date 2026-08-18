from ok.notification.pipeline import NotificationPipeline
from ok.notification.ppocr import NotificationPPOCR
from ok.notification.providers import (
    DiscordProvider, QQBotProvider, TelegramBotProvider, WeComWebhookProvider)
from ok.notification.windows_messenger import MessengerAutomation
from ok.util.GlobalConfig import (
    DISCORD_NOTIFICATION_ENABLED, DISCORD_WEBHOOK, NOTIFICATION_OPTION_NAME,
    QQ_NICKNAME, QQ_NOTIFICATION_ENABLED, SYSTEM_NOTIFICATION_ENABLED,
    WECHAT_NICKNAME, WECHAT_NOTIFICATION_ENABLED,
    QQ_BOT_APP_ID, QQ_BOT_CHANNEL_ID, QQ_BOT_NOTIFICATION_ENABLED,
    QQ_BOT_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    TELEGRAM_NOTIFICATION_ENABLED, WECOM_NOTIFICATION_ENABLED, WECOM_WEBHOOK,
)
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)
_DEFAULT_SYSTEM_NOTIFIER = object()


class NotificationManager:
    def __init__(self, global_config, executor, exit_event=None, app_name=None, app_icon=None,
                 system_notifier=_DEFAULT_SYSTEM_NOTIFIER):
        self.config = global_config.get_config(NOTIFICATION_OPTION_NAME)
        self.exit_event = exit_event
        self.app_name = str(app_name or 'ok-script')
        self.app_icon = str(app_icon or '')
        if system_notifier is _DEFAULT_SYSTEM_NOTIFIER:
            from ok.notification.system import WindowsSystemNotifier
            system_notifier = WindowsSystemNotifier(self.app_name, self.app_icon)
        self.system_notifier = system_notifier
        self.ocr = NotificationPPOCR(executor.ocr_lib)
        self.pipeline = NotificationPipeline(self._send, exit_event=exit_event, interval=5)
        self.queue = self.pipeline.queue
        self.thread = self.pipeline.thread

    @property
    def system_enabled(self):
        return bool(self.config.get(SYSTEM_NOTIFICATION_ENABLED, True))

    @property
    def external_provider_enabled(self):
        return any((
            self.config.get(DISCORD_NOTIFICATION_ENABLED),
            self.config.get(QQ_NOTIFICATION_ENABLED),
            self.config.get(WECHAT_NOTIFICATION_ENABLED),
            self.config.get(TELEGRAM_NOTIFICATION_ENABLED),
            self.config.get(WECOM_NOTIFICATION_ENABLED),
            self.config.get(QQ_BOT_NOTIFICATION_ENABLED),
        ))

    def submit(self, title, message, images=None):
        if not self.external_provider_enabled:
            return
        if images is None:
            frames = []
        elif isinstance(images, (list, tuple)):
            frames = list(images)
        else:
            frames = [images]
        self.pipeline.submit(title or '', message, frames)

    def notify_system(self, title, message, error=False, tray=True):
        if not tray or not self.system_enabled or self.system_notifier is None:
            return False
        return self.system_notifier.show(title, message, error)

    def stop(self):
        stopped = self.pipeline.stop(wait=True)
        if self.system_notifier is not None:
            self.system_notifier.close()
        return stopped

    def _send(self, title, message, images):
        if self.pipeline.stop_event.is_set():
            return False
        if self.config.get(DISCORD_NOTIFICATION_ENABLED):
            self._safe_send('Discord', DiscordProvider().send,
                            self.config.get(DISCORD_WEBHOOK), title, message, images,
                            self.app_name, self.app_icon)
        messenger_message = self._messenger_message(title, message)
        if self.config.get(TELEGRAM_NOTIFICATION_ENABLED):
            self._safe_send('Telegram', TelegramBotProvider().send,
                            self.config.get(TELEGRAM_BOT_TOKEN),
                            self.config.get(TELEGRAM_CHAT_ID), title, message, images)
        if self.config.get(WECOM_NOTIFICATION_ENABLED):
            self._safe_send('WeCom', WeComWebhookProvider().send,
                            self.config.get(WECOM_WEBHOOK), title, message, images)
        if self.config.get(QQ_BOT_NOTIFICATION_ENABLED):
            self._safe_send('QQ Bot', QQBotProvider().send,
                            self.config.get(QQ_BOT_APP_ID), self.config.get(QQ_BOT_TOKEN),
                            self.config.get(QQ_BOT_CHANNEL_ID), title, message, images)
        if self.pipeline.stop_event.is_set():
            return False
        if self.config.get(QQ_NOTIFICATION_ENABLED):
            self._safe_send('QQ', MessengerAutomation(
                ('QQ.exe',), self.ocr, exit_event=self.pipeline.stop_event,
                window_titles=('QQ',),
                search_point_96dpi=(200, 65), left_panel_width_96dpi=377,
                post_activate=False, image_method='context_menu', paste_match_end=True,
                dismiss_search_after_contact=True).send,
                            self.config.get(QQ_NICKNAME), '', messenger_message, images)
        if self.pipeline.stop_event.is_set():
            return False
        if self.config.get(WECHAT_NOTIFICATION_ENABLED):
            self._safe_send('WeChat', MessengerAutomation(
                ('WeChat.exe', 'Weixin.exe'), self.ocr,
                exit_event=self.pipeline.stop_event,
                window_titles=('WeChat', 'Weixin', '微信'),
                search_point_96dpi=(163, 56), left_panel_width_96dpi=295,
                search_first_word=True, post_activate=False,
                image_method='context_menu').send,
                            self.config.get(WECHAT_NICKNAME), '', messenger_message, images)

    def _messenger_message(self, title, message):
        content = f'{title}\n{message}' if title else message
        return f'{self.app_name}:\n{content}'

    @staticmethod
    def _safe_send(name, sender, *args):
        try:
            return sender(*args)
        except Exception as e:
            logger.error(f'{name} notification failed', e)
            return False
