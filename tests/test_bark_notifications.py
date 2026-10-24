import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from ok.core.config_schema import build_config_fields
from ok.notification.providers import BarkProvider
from ok.notification.manager import NotificationManager
from ok.util.GlobalConfig import (
    BARK_ARCHIVE, BARK_DEVICE_KEY, BARK_GROUP, BARK_ICON, BARK_LEVEL, BARK_SOUND,
    BARK_NOTIFICATION_ENABLED, BARK_SERVER_URL, BARK_URL,
    DISCORD_NOTIFICATION_ENABLED, create_notification_options,
    GlobalConfig, register_notification_options,
)
from ok.util.config import Config


@pytest.fixture
def accepted():
    return SimpleNamespace(status_code=200, json=lambda: {'code': 200, 'message': 'success'})


@pytest.fixture
def manager():
    instance = NotificationManager(
        SimpleNamespace(get_config=lambda _: dict(create_notification_options().default_config)),
        SimpleNamespace(ocr_lib=Mock()), app_name='Example App', system_notifier=None)
    instance.pipeline.interval = 0
    instance.config[BARK_DEVICE_KEY] = 'private-key'
    try:
        yield instance
    finally:
        instance.stop()


def test_bark_json_preserves_text_and_does_not_upload_images(accepted):
    text = '中文 / ? & #\nsecond line 😀'
    with patch('ok.notification.providers.requests.post', return_value=accepted) as post:
        assert BarkProvider().send(
            'https://example.invalid/bark///', ' private-key ', '标题', text, [object()],
            group='Example App', sound='minuet', level='critical', archive='Save',
            icon='https://example.invalid/icon.png', url='https://example.invalid/report?result=done')
    post.assert_called_once_with(
        'https://example.invalid/bark/push',
        json={'device_key': 'private-key', 'title': '标题', 'body': text,
              'group': 'Example App', 'sound': 'minuet', 'level': 'critical', 'isArchive': '1',
              'icon': 'https://example.invalid/icon.png', 'url': 'https://example.invalid/report?result=done'},
        timeout=(2, 2), allow_redirects=False)


def test_bark_round_trip_to_self_hosted_http_endpoint():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            received.append((self.path, self.headers['Content-Type'], json.loads(body)))
            response = b'{"code": 200, "message": "success"}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    worker.start()
    try:
        assert BarkProvider().send(
            f'http://127.0.0.1:{server.server_port}/bark/', 'local-test-key',
            '测试', '多行正文\nsecond line', group='test-group')
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    assert not worker.is_alive()
    assert received == [('/bark/push', 'application/json', {
        'device_key': 'local-test-key', 'title': '测试',
        'body': '多行正文\nsecond line', 'group': 'test-group', 'sound': '', 'level': 'active',
        'icon': '', 'url': '',
    })]


@pytest.mark.parametrize('archive, expected', [('App Default', None), ('Save', '1'), ('Do Not Save', '0')])
def test_bark_optional_settings_follow_app_by_default(accepted, archive, expected):
    with patch('ok.notification.providers.requests.post', return_value=accepted) as post:
        assert BarkProvider().send('http://localhost:8080', 'key', '', 'body', archive=archive)
    payload = post.call_args.kwargs['json']
    assert payload.get('isArchive') == expected
    assert payload['group'] == ''
    assert payload['sound'] == ''
    assert payload['icon'] == ''
    assert payload['url'] == ''


@pytest.mark.parametrize('status, payload', [
    (302, {'code': 200}), (400, {'code': 400}), (500, {'code': 500}),
    (200, {'code': 400, 'message': 'private-key'}), (200, []), (200, {}),
])
def test_bark_rejects_unsuccessful_responses_without_logging_payload(status, payload, caplog):
    response = SimpleNamespace(status_code=status, json=lambda: payload)
    with patch('ok.notification.providers.requests.post', return_value=response) as post:
        assert not BarkProvider().send('https://example.invalid', 'private-key', '', 'private-body')
    post.assert_called_once()
    assert caplog.records
    assert 'private-key' not in caplog.text
    assert 'private-body' not in caplog.text


@pytest.mark.parametrize('error', [
    requests.Timeout('private-key'), requests.ConnectionError('private-key'),
    requests.RequestException('private-key'), ValueError('private-key'), RuntimeError('private-key'),
])
def test_bark_network_errors_do_not_log_exception_secrets(error, caplog):
    with patch('ok.notification.providers.requests.post', side_effect=error) as post:
        assert not BarkProvider().send('https://example.invalid', 'private-key', '', 'private-body')
    post.assert_called_once()
    assert caplog.records
    assert 'private-key' not in caplog.text
    assert 'private-body' not in caplog.text


def test_bark_invalid_json_is_failure(accepted):
    accepted.json = Mock(side_effect=ValueError('private-key'))
    with patch('ok.notification.providers.requests.post', return_value=accepted):
        assert not BarkProvider().send('https://example.invalid', 'private-key', '', 'body')


def test_only_bark_enabled_delivers_configured_parameters(manager, accepted):
    manager.config[BARK_NOTIFICATION_ENABLED] = True
    manager.config[BARK_ICON] = 'https://example.invalid/icon.png'
    manager.config[BARK_URL] = 'https://example.invalid/report'
    manager.config[BARK_LEVEL] = 'critical'
    assert manager.external_provider_enabled
    with patch('ok.notification.providers.requests.post', return_value=accepted) as post:
        manager.submit('', 'body', [object()])
        manager.pipeline.queue.join()
    post.assert_called_once()
    assert post.call_args.kwargs['json']['title'] == ''
    assert post.call_args.kwargs['json']['group'] == ''
    assert post.call_args.kwargs['json']['icon'] == 'https://example.invalid/icon.png'
    assert post.call_args.kwargs['json']['url'] == 'https://example.invalid/report'
    assert post.call_args.kwargs['json']['level'] == 'critical'


def test_bark_and_existing_provider_each_receive_once(manager, accepted):
    manager.config[BARK_NOTIFICATION_ENABLED] = True
    manager.config[DISCORD_NOTIFICATION_ENABLED] = True
    with (patch('ok.notification.providers.requests.post', return_value=accepted) as bark,
          patch('ok.notification.manager.DiscordProvider.send', return_value=True) as discord):
        manager.submit('title', 'body')
        manager.pipeline.queue.join()
    bark.assert_called_once()
    discord.assert_called_once()


def test_bark_exception_does_not_block_existing_provider(manager):
    manager.config[BARK_NOTIFICATION_ENABLED] = True
    manager.config[DISCORD_NOTIFICATION_ENABLED] = True
    with (patch('ok.notification.providers.BarkProvider.send', side_effect=RuntimeError('simulated failure')),
          patch('ok.notification.manager.DiscordProvider.send', return_value=True) as discord):
        manager.submit('title', 'body')
        manager.pipeline.queue.join()
    discord.assert_called_once()


def test_disabled_and_stopped_manager_does_not_send(manager):
    with patch('ok.notification.providers.requests.post') as post:
        manager.submit('disabled', 'body')
        manager.stop()
        manager.config[BARK_NOTIFICATION_ENABLED] = True
        manager.submit('stopped', 'body')
    post.assert_not_called()


def test_old_notification_config_keeps_values_and_bark_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'config_folder', str(tmp_path))
    config = Config('Notification', {
        'Discord Notification': True, 'Discord Webhook': 'old-webhook',
        BARK_GROUP: 'saved-group',
    })
    upgraded = register_notification_options(GlobalConfig(None))
    assert upgraded['Discord Notification']
    assert upgraded['Discord Webhook'] == config['Discord Webhook']
    assert upgraded[BARK_NOTIFICATION_ENABLED] is False
    assert upgraded[BARK_SERVER_URL] == 'https://api.day.app'
    assert upgraded[BARK_LEVEL] == 'active'
    assert upgraded[BARK_GROUP] == 'saved-group'
    upgraded[BARK_DEVICE_KEY] = 'private-key'
    reloaded = register_notification_options(GlobalConfig(None))
    assert reloaded[BARK_DEVICE_KEY] == 'private-key'
    assert reloaded[BARK_GROUP] == 'saved-group'


def test_bark_visibility_and_hidden_values():
    option = create_notification_options()
    config = {**option.default_config, BARK_DEVICE_KEY: 'key', BARK_GROUP: 'saved-group'}
    bark_order = [BARK_SERVER_URL, BARK_DEVICE_KEY, BARK_GROUP, BARK_ICON,
                  BARK_SOUND, BARK_LEVEL, BARK_URL, BARK_ARCHIVE]
    bark_fields = set(bark_order)
    def fields():
        return {field['key']: field for field in build_config_fields(
            config, option.config_description, option.config_type, option.default_config)}
    assert option.config_type[BARK_NOTIFICATION_ENABLED]['sub_configs'][True] == bark_order
    assert 'critical' in option.config_type[BARK_LEVEL]['options']
    assert not bark_fields.intersection(fields())
    config[BARK_NOTIFICATION_ENABLED] = True
    assert bark_fields.issubset(fields())
    assert [key for key in fields() if key in bark_fields] == bark_order
    assert fields()[BARK_DEVICE_KEY]['kind'] == 'text'
    assert fields()[BARK_GROUP]['value'] == 'saved-group'
    config[BARK_NOTIFICATION_ENABLED] = False
    assert config[BARK_GROUP] == 'saved-group'
    assert not bark_fields.intersection(fields())
