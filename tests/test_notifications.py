import os
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
import win32con

from ok.notification.providers import (
    DiscordProvider, QQBotProvider, TelegramBotProvider, WeComWebhookProvider)
from ok.notification.manager import NotificationManager
from ok.notification.pipeline import NotificationPipeline
from ok.notification.ppocr import NotificationPPOCR
from ok.notification.messenger_images import _paste_from_context_menu, _wait_popup_text
from ok.notification.windows_messenger import MessengerAutomation
from ok.gui.debug.Screenshot import remove_old_files
from ok.task.task import BaseTask
from ok.util.handler import ExitEvent
from ok.util.GlobalConfig import (
    DISCORD_NOTIFICATION_ENABLED, QQ_NICKNAME, QQ_NOTIFICATION_ENABLED,
    SYSTEM_NOTIFICATION_ENABLED, WECHAT_NOTIFICATION_ENABLED,
    GlobalConfig, create_notification_options, register_notification_options,
)
from ok.util.config import Config
from ok.util.file import get_relative_path, write_json_file


def test_notification_options_have_safe_provider_defaults():
    option = create_notification_options()

    assert option.show_at_tab
    assert option.default_config[SYSTEM_NOTIFICATION_ENABLED]
    assert not option.default_config[DISCORD_NOTIFICATION_ENABLED]
    assert not option.default_config[QQ_NOTIFICATION_ENABLED]
    assert not option.default_config[WECHAT_NOTIFICATION_ENABLED]
    assert option.config_type['Discord Webhook']['minimum_width'] == 480
    assert 'open and running' in option.config_description[QQ_NOTIFICATION_ENABLED]
    assert 'open and running' in option.config_description[WECHAT_NOTIFICATION_ENABLED]


def test_register_notification_options_creates_persistent_config():
    original_folder = Config.config_folder
    try:
        with tempfile.TemporaryDirectory() as folder:
            Config.config_folder = folder
            write_json_file(get_relative_path(folder, 'Notification.json'), {
                'QQ Notification': True,
                'QQ Nickname': 'Legacy Contact',
            })
            config = register_notification_options(GlobalConfig(None))
            assert config[SYSTEM_NOTIFICATION_ENABLED]
            assert config[QQ_NOTIFICATION_ENABLED]
            assert config[QQ_NICKNAME] == 'Legacy Contact'
            assert 'QQ Notification' not in config
    finally:
        Config.config_folder = original_folder


def test_notification_images_accept_single_and_list_and_append_current_frame():
    task = object.__new__(BaseTask)
    current = np.full((2, 2, 3), 3, dtype=np.uint8)
    task._executor = SimpleNamespace(nullable_frame=lambda: current)
    first = np.zeros((2, 2, 3), dtype=np.uint8)

    single = task._notification_images(first)
    multiple = task._notification_images([first], screenshot=True)

    assert len(single) == 1
    assert len(multiple) == 2
    assert multiple[1] is not current
    assert np.array_equal(multiple[1], current)


def test_discord_provider_uploads_images():
    response = Mock()
    response.raise_for_status = Mock()
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    with patch('ok.notification.providers.requests.post', return_value=response) as post:
        assert DiscordProvider().send(
            'https://example.invalid/webhook', 'Title', 'Message', [frame],
            'Test App', 'https://example.invalid/app.png')

    kwargs = post.call_args.kwargs
    assert kwargs['data']['content'] == '**Title**\nMessage'
    assert kwargs['data']['username'] == 'Test App'
    assert kwargs['data']['avatar_url'] == 'https://example.invalid/app.png'
    assert kwargs['files'][0][1][2] == 'image/png'
    response.raise_for_status.assert_called_once_with()


def test_telegram_bot_provider_sends_text_and_photos():
    response = Mock()
    response.json.return_value = {'ok': True}
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    with patch('ok.notification.providers.requests.post', return_value=response) as post:
        assert TelegramBotProvider().send('token', '123', 'Title', 'Message', [frame])

    assert post.call_args_list[0].args[0] == 'https://api.telegram.org/bottoken/sendMessage'
    assert post.call_args_list[0].kwargs['json'] == {
        'chat_id': '123', 'text': 'Title\nMessage'}
    assert post.call_args_list[1].args[0] == 'https://api.telegram.org/bottoken/sendPhoto'
    assert post.call_args_list[1].kwargs['data'] == {'chat_id': '123'}


def test_wecom_provider_sends_markdown_and_image_payload():
    response = Mock()
    response.json.return_value = {'errcode': 0}
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    with patch('ok.notification.providers.requests.post', return_value=response) as post:
        assert WeComWebhookProvider().send('https://wecom.invalid/hook', 'Title', 'Message', [frame])

    assert post.call_args_list[0].kwargs['json'] == {
        'msgtype': 'markdown', 'markdown': {'content': 'Title\nMessage'}}
    image_payload = post.call_args_list[1].kwargs['json']
    assert image_payload['msgtype'] == 'image'
    assert image_payload['image']['base64']
    assert len(image_payload['image']['md5']) == 32


def test_qq_bot_provider_uses_bot_authorization_header():
    response = Mock()
    response.json.return_value = {}
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    with patch('ok.notification.providers.requests.post', return_value=response) as post:
        assert QQBotProvider().send('app', 'secret', 'channel', 'Title', 'Message', [frame])

    kwargs = post.call_args.kwargs
    assert post.call_args.args[0] == 'https://api.sgroup.qq.com/channels/channel/messages'
    assert kwargs['headers'] == {'Authorization': 'Bot app.secret'}
    assert kwargs['json']['content'] == 'Title\nMessage\n[1 image(s) attached]'


def test_manager_does_not_queue_when_external_providers_are_disabled():
    manager = object.__new__(NotificationManager)
    manager.config = create_notification_options().default_config
    manager.pipeline = Mock()

    manager.submit('Title', 'Message')

    manager.pipeline.submit.assert_not_called()


def test_messenger_message_starts_with_app_name():
    manager = object.__new__(NotificationManager)
    manager.app_name = 'Test App'

    assert manager._messenger_message('Title', 'Message') == 'Test App:\nTitle\nMessage'


def test_manager_uses_context_menu_images_for_qq():
    manager = object.__new__(NotificationManager)
    manager.config = {
        DISCORD_NOTIFICATION_ENABLED: False,
        QQ_NOTIFICATION_ENABLED: True,
        QQ_NICKNAME: 'XD',
        WECHAT_NOTIFICATION_ENABLED: False,
    }
    manager.ocr = SimpleNamespace()
    manager.exit_event = None
    manager.pipeline = SimpleNamespace(
        stop_event=SimpleNamespace(is_set=lambda: False))
    manager.app_name = 'Test App'

    with patch('ok.notification.manager.MessengerAutomation') as automation:
        manager._send('Title', 'Message', [np.zeros((2, 2, 3), dtype=np.uint8)])

    assert automation.call_args.kwargs['image_method'] == 'context_menu'
    assert automation.call_args.kwargs['paste_match_end'] is True
    assert automation.call_args.kwargs['dismiss_search_after_contact'] is True
    assert automation.call_args.kwargs['post_activate'] is False


def test_local_discord_icon_is_not_sent_as_avatar_url():
    response = Mock()
    with patch('ok.notification.providers.requests.post', return_value=response) as post:
        assert DiscordProvider().send(
            'https://example.invalid/webhook', '', 'Message', [], 'Test App', 'icon.ico')

    assert 'avatar_url' not in post.call_args.kwargs['data']


def test_messenger_error_saves_last_bitblt_frame():
    from ok.gui.Communicate import communicate

    automation = MessengerAutomation(('QQ.exe',), SimpleNamespace())
    automation._last_frame = np.zeros((2, 2, 3), dtype=np.uint8)
    received = []
    receiver = lambda *args: received.append(args)
    communicate.screenshot.connect(receiver)
    try:
        automation._save_error_screenshot()
    finally:
        communicate.screenshot.disconnect(receiver)

    assert received[0][1] == 'notification/qq_error'


def test_screenshot_cleanup_removes_old_notification_subfolder_images(tmp_path):
    notification_folder = tmp_path / 'notification'
    notification_folder.mkdir()
    screenshot = notification_folder / 'old.png'
    screenshot.write_bytes(b'image')
    old_time = time.time() - 8 * 86400
    os.utime(screenshot, (old_time, old_time))

    remove_old_files(str(tmp_path), 7)

    assert not screenshot.exists()


def test_messenger_ocr_crops_region_and_restores_coordinates():
    seen = []
    ocr = SimpleNamespace(recognize=lambda frame, threshold: (
        seen.append(frame.shape),
        [('Search', 5, 6, 20, 10)],
    )[1])
    automation = MessengerAutomation(('QQ.exe',), ocr)
    frame = np.zeros((100, 200, 3), dtype=np.uint8)

    boxes = automation._ocr(frame, region=(20, 20, 120, 70))

    assert seen == [(50, 100, 3)]
    assert boxes == [('Search', 25, 26, 20, 10)]


def test_notification_ppocr_holds_only_lazy_shared_instance():
    instance = Mock()
    instance.ocr.return_value = [[
        [[[5, 6], [25, 6], [25, 16], [5, 16]], ('Search', .9)],
        [[[1, 2], [3, 2], [3, 4], [1, 4]], ('Ignored', .05)],
    ]]
    factory = Mock(return_value=instance)
    ocr = NotificationPPOCR(factory)

    boxes = ocr.recognize(np.zeros((20, 30, 3), dtype=np.uint8), threshold=.1)
    ocr.recognize(np.zeros((20, 30, 3), dtype=np.uint8), threshold=.1)

    assert boxes == [('Search', 5, 6, 20, 10)]
    factory.assert_called_once_with()


def test_notification_pipeline_processes_fifo_queue():
    received = []
    pipeline = NotificationPipeline(
        lambda title, message, images: received.append((title, message, images)),
        interval=0)
    try:
        pipeline.submit('one', '1', [])
        pipeline.submit('two', '2', [object()])
        pipeline.queue.join()
    finally:
        pipeline.stop()
        pipeline.thread.join(timeout=2)

    assert [(title, message) for title, message, _ in received] == [
        ('one', '1'), ('two', '2')]


def test_notification_pipeline_stops_with_app_exit_event():
    exit_event = ExitEvent()
    pipeline = NotificationPipeline(Mock(), exit_event=exit_event, interval=0)

    exit_event.set()
    pipeline.thread.join(timeout=2)

    assert not pipeline.thread.is_alive()
    assert pipeline.stop_event.is_set()
    assert pipeline.submit('late', 'ignored', []) is False


def test_messenger_layout_regions_are_dpi_scaled_and_edge_anchored():
    automation = MessengerAutomation(
        ('QQ.exe',), SimpleNamespace(), left_panel_width_96dpi=377)
    with patch('ok.notification.windows_messenger.win32gui.GetClientRect',
               return_value=(0, 0, 1600, 1200)), \
            patch('ok.notification.windows_messenger.ctypes.windll.user32.GetDpiForWindow',
                  return_value=144):
        search, contact, send = automation._layout_regions(123)

    assert search == (82, 0, 566, 180)
    assert contact == (82, 112, 566, 1200)
    assert send == (1210, 975, 1600, 1200)


def test_messenger_search_field_fallback_uses_client_coordinates():
    automation = MessengerAutomation(
        ('QQ.exe',), SimpleNamespace(), search_point_96dpi=(200, 65))
    frame = np.zeros((800, 1000, 3), dtype=np.uint8)
    with patch.object(automation, '_capture', return_value=frame), \
            patch('ok.notification.windows_messenger.ctypes.windll.user32.GetDpiForWindow',
                  return_value=144):
        point = automation._search_field_point(123)

    assert point == (300, 98)
    assert automation._last_frame is frame


def test_messenger_contact_search_includes_qt_popup_before_root():
    automation = MessengerAutomation(('Weixin.exe',), SimpleNamespace())

    def enumerate_windows(callback, argument):
        callback(456, argument)
        callback(789, argument)

    with patch('ok.notification.windows_messenger.win32process.GetWindowThreadProcessId',
               side_effect=lambda hwnd: (0, 10 if hwnd in (123, 456) else 20)), \
            patch('ok.notification.windows_messenger.win32gui.EnumWindows',
                  side_effect=enumerate_windows), \
            patch('ok.notification.windows_messenger.win32gui.IsWindowVisible',
                  return_value=True), \
            patch('ok.notification.windows_messenger.win32gui.GetClassName',
                  return_value='Qt51514QWindowToolSaveBits'), \
            patch('ok.notification.windows_messenger.win32gui.GetWindowRect',
                  return_value=(0, 0, 500, 600)):
        windows = automation._contact_windows(123)

    assert windows == [456, 123]


def test_messenger_wait_contact_uses_popup_local_coordinates():
    ocr = SimpleNamespace(recognize=lambda frame, threshold: [
        ('Contacts', 20, 10, 100, 20),
        ('Target', 20, 40, 100, 20),
        ('Chat History', 20, 80, 100, 20),
    ])
    automation = MessengerAutomation(('Weixin.exe',), ocr)
    popup_frame = np.zeros((200, 300, 3), dtype=np.uint8)

    with patch.object(automation, '_contact_windows', return_value=[456, 123]), \
            patch.object(automation, '_capture', return_value=popup_frame):
        contact_hwnd, point = automation._wait_contact(
            123, 'Target', (50, 50, 250, 180), timeout=.1)

    assert contact_hwnd == 456
    assert point == (70, 50)


def test_messenger_popup_does_not_click_internet_search_exact_match():
    boxes = [
        ('Internet search results', 10, 10, 200, 20),
        ('File Transfer', 20, 50, 100, 20),
    ]

    assert MessengerAutomation._matching_contact_point(
        boxes, 'file transfer', contacts_section=True) is None


def test_messenger_popup_accepts_exact_file_transfer_feature():
    boxes = [
        ('Features', 10, 10, 100, 20),
        ('File Transfer', 20, 50, 100, 20),
        ('Chat History', 10, 90, 150, 20),
        ('File Transfer', 20, 130, 100, 20),
    ]

    assert MessengerAutomation._matching_contact_point(
        boxes, 'file transfer', contacts_section=True) == (70, 60)


def test_wechat_search_uses_text_before_first_space_but_keeps_full_contact_name():
    automation = MessengerAutomation(
        ('Weixin.exe',), SimpleNamespace(), search_first_word=True)

    assert automation._search_query('File Transfer') == 'File'
    assert automation._search_query('  File   Transfer  ') == 'File'
    assert automation._search_query('Nickname') == 'Nickname'


def test_background_click_does_not_post_activate_when_disabled():
    automation = MessengerAutomation(
        ('Weixin.exe',), SimpleNamespace(), post_activate=False)

    with patch('ok.notification.windows_messenger.win32gui.PostMessage') as post:
        automation._click(123, (40, 50))

    messages = [call.args[1] for call in post.call_args_list]
    assert win32con.WM_ACTIVATE not in messages
    assert win32con.WM_SETFOCUS in messages


def test_popup_click_can_skip_focus_message():
    automation = MessengerAutomation(
        ('Weixin.exe',), SimpleNamespace(), post_activate=False)

    with patch('ok.notification.windows_messenger.win32gui.PostMessage') as post:
        automation._click(123, (40, 50), focus=False)

    messages = [call.args[1] for call in post.call_args_list]
    assert win32con.WM_SETFOCUS not in messages
    assert win32con.WM_LBUTTONDOWN in messages
    assert win32con.WM_LBUTTONUP in messages


def test_context_menu_paste_can_be_ocr_found_on_root_surface():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    automation = SimpleNamespace(
        _last_frame=None,
        _capture=Mock(return_value=frame),
        _ocr=Mock(return_value=[('Paste', 20, 30, 80, 20)]),
    )

    with patch('ok.notification.messenger_images._tool_popups', return_value=[]):
        popup, point = _wait_popup_text(automation, 123, {'Paste'}, timeout=.1)

    assert popup == 123
    assert point == (60, 40)


def test_qq_context_menu_paste_accepts_ocr_icon_prefix():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    automation = SimpleNamespace(
        _last_frame=None,
        _capture=Mock(return_value=frame),
        _ocr=Mock(return_value=[('自粘贴', 20, 30, 80, 20)]),
    )

    with patch('ok.notification.messenger_images._tool_popups', return_value=[]):
        popup, point = _wait_popup_text(
            automation, 123, {'Paste', '粘贴'}, timeout=.1, match_end=True)

    assert popup == 123
    assert point == (60, 40)


def test_context_menu_focuses_composer_before_right_click():
    events = []
    automation = SimpleNamespace(
        paste_match_end=False,
        _set_clipboard_image=lambda frame: events.append('clipboard'),
        _click=lambda hwnd, point, focus=False: events.append('paste'),
    )

    with patch('ok.notification.messenger_images._left_click',
               side_effect=lambda hwnd, point: events.append('left')), \
            patch('ok.notification.messenger_images._right_click',
                  side_effect=lambda hwnd, point: events.append('right')), \
            patch('ok.notification.messenger_images._wait_popup_text',
                  return_value=(456, (10, 20))), \
            patch('ok.notification.messenger_images.time.sleep') as sleep:
        _paste_from_context_menu(automation, 123, (100, 200), object())

    assert events == ['clipboard', 'left', 'right', 'paste']
    assert [call.args[0] for call in sleep.call_args_list] == [1, 1, 1]


def test_paste_menu_ocr_falls_back_to_render_surface_when_popup_enum_fails():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    automation = SimpleNamespace(
        _last_frame=None,
        _capture=Mock(return_value=frame),
        _ocr=Mock(return_value=[('Paste', 20, 30, 80, 20)]),
    )

    with patch('ok.notification.messenger_images._tool_popups', side_effect=OSError('desktop')), \
            patch('ok.notification.messenger_images._render_surface', return_value=456):
        popup, point = _wait_popup_text(automation, 123, {'Paste'}, timeout=.1)

    assert popup == 456
    assert point == (60, 40)


def test_paste_menu_failure_saves_last_frame():
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    automation = SimpleNamespace(
        paste_match_end=False,
        _set_clipboard_image=lambda _: None,
        _last_frame=frame,
        _save_error_screenshot=Mock(),
        _capture=Mock(return_value=frame),
        _ocr=Mock(return_value=[]),
    )

    with patch('ok.notification.messenger_images._left_click'), \
            patch('ok.notification.messenger_images._right_click'), \
            patch('ok.notification.messenger_images._wait_popup_text',
                  return_value=(123, None)), \
            patch('ok.notification.messenger_images.time.sleep'):
        with pytest.raises(RuntimeError, match='Could not find Paste'):
            _paste_from_context_menu(automation, 123, (10, 10), frame)

    automation._save_error_screenshot.assert_called_once_with('paste_menu')


def test_messenger_sends_text_then_each_image_separately():
    automation = MessengerAutomation(('QQ.exe',), SimpleNamespace())
    events = []
    automation._click = lambda hwnd, point: events.append(('click', point)) or hwnd
    automation._clear_unsent_text = lambda hwnd: events.append(('clear', hwnd))
    automation._type_text = lambda hwnd, value: events.append(('text', value))
    automation._get_clipboard_text = lambda: None
    automation._restore_clipboard_text = lambda value: None
    images = [object(), object()]

    with patch('ok.notification.messenger_images.insert_messenger_image',
               side_effect=lambda *args: events.append(('image', args[-1]))), \
            patch('ok.notification.windows_messenger.time.sleep') as sleep:
        automation._send_content(
            123, (900, 700), (800, 650), 'Title', 'Message', images)

    assert events == [
        ('click', (800, 650)),
        ('clear', 123),
        ('text', 'Title\nMessage'),
        ('click', (900, 700)),
        ('click', (800, 650)),
        ('image', images[0]),
        ('click', (900, 700)),
        ('click', (800, 650)),
        ('image', images[1]),
        ('click', (900, 700)),
    ]
    assert all(call.args[0] == 1 for call in sleep.call_args_list)


def test_qq_does_not_escape_main_window_after_root_contact_click():
    automation = MessengerAutomation(
        ('QQ.exe',), SimpleNamespace(), dismiss_search_after_contact=True)
    events = []
    automation._find_hwnd = lambda: 123
    automation._wait_until_background = lambda hwnd: True
    automation._layout_regions = lambda hwnd: ((0, 0, 100, 100), (0, 0, 100, 100), (0, 0, 100, 100))
    automation._header_region = lambda hwnd: (100, 0, 200, 120)
    automation._wait_text = Mock(side_effect=[None, None, None, (10, 10), (10, 10)])
    automation._click = lambda *args, **kwargs: events.append(('click', args[1]))
    automation._clear_text = lambda hwnd: None
    automation._type_text = lambda hwnd, text: None
    automation._wait_contact = lambda *args, **kwargs: (123, (20, 20))
    automation._send_key = lambda *args: events.append(('escape', args[1]))
    automation._send_content = lambda *args: events.append(('send_content',))

    with patch('ok.notification.windows_messenger.win32gui.IsWindowVisible', return_value=True):
        assert automation._send('Nick', '', 'Message', [])

    assert ('escape', win32con.VK_ESCAPE) not in events


def test_qq_escapes_only_when_search_popup_remains_visible():
    automation = MessengerAutomation(
        ('QQ.exe',), SimpleNamespace(), dismiss_search_after_contact=True)
    events = []
    automation._find_hwnd = lambda: 123
    automation._wait_until_background = lambda hwnd: True
    automation._layout_regions = lambda hwnd: ((0, 0, 100, 100), (0, 0, 100, 100), (0, 0, 100, 100))
    automation._header_region = lambda hwnd: (100, 0, 200, 120)
    automation._wait_text = Mock(side_effect=[None, None, None, (10, 10), (10, 10)])
    automation._click = lambda *args, **kwargs: events.append(('click', args[1]))
    automation._clear_text = lambda hwnd: None
    automation._type_text = lambda hwnd, text: None
    automation._wait_contact = lambda *args, **kwargs: (456, (20, 20))
    automation._send_key = lambda *args: events.append(('escape', args[1]))
    automation._send_content = lambda *args: events.append(('send_content',))

    with patch('ok.notification.windows_messenger.win32gui.IsWindowVisible', return_value=True):
        assert automation._send('Nick', '', 'Message', [])

    assert ('escape', win32con.VK_ESCAPE) in events


def test_messenger_left_list_shortcut_skips_search():
    automation = MessengerAutomation(('QQ.exe',), SimpleNamespace())
    events = []
    automation._find_hwnd = lambda: 123
    automation._wait_until_background = lambda hwnd: True
    automation._layout_regions = lambda hwnd: ((0, 0, 100, 100), (0, 0, 100, 100), (0, 0, 100, 100))
    automation._wait_text = lambda hwnd, names, **kwargs: (
        (20, 20) if kwargs.get('region') == (0, 0, 100, 100) and
        kwargs.get('full_match') else (30, 30))
    automation._click = lambda hwnd, point, **kwargs: events.append(('click', point)) or hwnd
    automation._send_content = lambda *args, **kwargs: events.append(('send', kwargs))

    assert automation._send('Nick', '', 'Message', [])
    assert events[0] == ('click', (20, 20))
    assert not any(event[0] == 'send' and event[1].get('focus_input') is False
                   for event in events)


def test_messenger_header_shortcut_requires_header_and_send():
    automation = MessengerAutomation(('QQ.exe',), SimpleNamespace())
    events = []
    automation._find_hwnd = lambda: 123
    automation._wait_until_background = lambda hwnd: True
    automation._layout_regions = lambda hwnd: ((0, 0, 100, 100), (0, 0, 100, 100), (80, 80, 100, 100))
    header = (100, 0, 200, 120)

    def wait_text(hwnd, names, **kwargs):
        if kwargs.get('full_match') and kwargs.get('region') == header:
            return (150, 40)
        if names == {'Send', '发送'}:
            return (90, 90)
        return None

    automation._wait_text = wait_text
    automation._header_region = lambda hwnd: header
    automation._click = lambda hwnd, point, **kwargs: events.append(('click', point)) or hwnd
    automation._send_content = lambda *args, **kwargs: events.append(('send', kwargs))

    assert automation._send('Nick', '', 'Message', [])
    assert events == [
        ('click', (20, 45)),
        ('send', {'focus_input': False, 'input_target': 123}),
    ]


def test_clear_unsent_text_uses_backspace_without_ctrl_hotkey():
    automation = MessengerAutomation(('QQ.exe',), SimpleNamespace())

    with patch.object(MessengerAutomation, '_send_key_sync') as send_key:
        automation._clear_unsent_text(123)

    keys = [call.args[1] for call in send_key.call_args_list]
    assert keys[0] == win32con.VK_END
    assert keys.count(win32con.VK_BACK) == 256
    assert keys.count(win32con.VK_DELETE) == 256
    assert win32con.VK_CONTROL not in keys


def test_clear_search_text_uses_short_synchronous_sequence():
    automation = MessengerAutomation(('QQ.exe',), SimpleNamespace())

    with patch.object(MessengerAutomation, '_hotkey_sync') as hotkey, \
            patch.object(MessengerAutomation, '_send_key_sync') as send_key:
        automation._clear_text(123)

    hotkey.assert_called_once_with(123, win32con.VK_CONTROL, ord('A'))
    assert [call.args[1] for call in send_key.call_args_list] == [
        win32con.VK_BACK, win32con.VK_DELETE]


def test_clipboard_image_sets_dib_and_png_formats():
    frame = np.zeros((2, 2, 3), dtype=np.uint8)

    with patch('ok.notification.windows_messenger.win32clipboard') as clipboard:
        clipboard.RegisterClipboardFormat.return_value = 12345
        MessengerAutomation._set_clipboard_image(frame)

    formats = [call.args[0] for call in clipboard.SetClipboardData.call_args_list]
    assert formats == [win32con.CF_DIB, 12345]
