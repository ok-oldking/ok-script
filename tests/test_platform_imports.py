import importlib
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from ok.platform import PlatformUnavailableError, require_macos_foreground_host
from ok.util.handler import ExitEvent


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PREFIXES = ('win32', 'pythoncom', 'pywintypes', 'ok.rotypes')


def _is_forbidden(module_name):
    return module_name.startswith(FORBIDDEN_PREFIXES)


@pytest.mark.skipif(sys.platform != 'darwin', reason='Darwin import isolation check')
def test_darwin_shared_import_graph_does_not_load_win32_modules():
    script = textwrap.dedent(
        """
        import importlib
        import sys

        modules = [
            'ok',
            'ok.platform',
            'ok.device.DeviceManager',
            'ok.task.TaskExecutor',
            'ok.core.start_controller',
            'ok.device.capture',
            'ok.device.capture_methods.screencapturekit_core',
            'ok.device.capture_methods.screencapturekit',
            'ok.device.interaction',
            'ok.device.window_target',
            'ok.device.services.permissions',
            'ok.notification',
            'ok.ui.qt.MainWindow',
            'ok.ui.qt.start.StartTab',
            'ok.ui.qt.about.AboutTab',
            'ok.ui.qt.tasks.RecordScript',
            'ok.ui.qt.debug.OverlayWidget',
            'ok.ui.qt.overlay.OverlayWindow',
        ]
        for module_name in modules:
            importlib.import_module(module_name)

        forbidden = sorted(
            name for name in sys.modules
            if name.startswith(('win32', 'pythoncom', 'pywintypes', 'ok.rotypes'))
        )
        if forbidden:
            raise SystemExit('forbidden modules loaded: ' + ', '.join(forbidden))
        """
    )
    env = os.environ.copy()
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows import isolation check')
def test_windows_shared_import_graph_does_not_load_pyobjc_modules():
    script = textwrap.dedent(
        """
        import importlib
        import sys

        modules = [
            'ok',
            'ok.platform',
            'ok.device.DeviceManager',
            'ok.task.TaskExecutor',
            'ok.core.start_controller',
            'ok.device.capture',
            'ok.device.interaction',
            'ok.device.window_target',
            'ok.device.services.permissions',
            'ok.notification',
            'ok.ui.qt.MainWindow',
            'ok.ui.qt.start.StartTab',
        ]
        for module_name in modules:
            importlib.import_module(module_name)

        forbidden = sorted(
            name for name in sys.modules
            if name.startswith((
                'objc', 'AppKit', 'Quartz', 'ScreenCaptureKit',
                'ApplicationServices'))
        )
        if forbidden:
            raise SystemExit('macOS implementation modules loaded: ' + ', '.join(forbidden))
        """
    )
    env = os.environ.copy()
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(sys.platform == 'win32', reason='Non-Windows contract check')
def test_windows_capture_and_interaction_exports_fail_explicitly():
    capture = importlib.import_module('ok.device.capture')
    interaction = importlib.import_module('ok.device.interaction')
    keys = importlib.import_module('ok.device.interaction_methods.keys')

    assert 'HwndWindow' not in capture.__all__
    assert 'PostMessageInteraction' not in interaction.__all__

    with pytest.raises(PlatformUnavailableError, match='Windows capture export HwndWindow'):
        getattr(capture, 'HwndWindow')
    with pytest.raises(PlatformUnavailableError, match='Windows interaction export PostMessageInteraction'):
        getattr(interaction, 'PostMessageInteraction')
    with pytest.raises(PlatformUnavailableError, match='Win32 virtual-key map'):
        getattr(keys, 'vk_key_dict')


@pytest.mark.skipif(sys.platform == 'win32', reason='Non-Windows provider-selection check')
def test_device_manager_does_not_construct_windows_providers(monkeypatch):
    device_manager_module = importlib.import_module('ok.device.DeviceManager')

    class MemoryConfig(dict):
        def __init__(self, _name, default):
            super().__init__(default)

    monkeypatch.setattr(device_manager_module, 'Config', MemoryConfig)
    exit_event = ExitEvent()
    manager = device_manager_module.DeviceManager(
        {
            'windows': {
                'exe': 'game.exe',
                'interaction': 'PostMessage',
                'capture_method': ['WGC'],
            },
            'browser': {'url': 'https://example.invalid'},
        },
        exit_event=exit_event,
    )

    try:
        assert manager.windows_capture_config is None
        assert manager.browser_config is None
        assert manager.hwnd_window is None
        assert manager.win_interaction_class is None
        assert manager.config['capture'] == ''
        assert not manager.cursor_service.available
    finally:
        exit_event.set()
        manager.handler.join(2)


@pytest.mark.skipif(sys.platform == 'win32', reason='Non-Windows cursor boundary check')
def test_cursor_service_is_explicitly_unavailable_before_bound_quartz_backend():
    from ok.device.services import create_cursor_service

    service = create_cursor_service()
    assert not service.available
    with pytest.raises(PlatformUnavailableError, match='bound Quartz foreground'):
        service.get_position()


def test_current_import_state_contains_no_unexpected_win32_modules_on_non_windows():
    if sys.platform == 'win32':
        pytest.skip('Win32 modules are expected on Windows')
    assert not sorted(name for name in sys.modules if _is_forbidden(name))


def test_macos_foreground_host_gate_requires_arm64_and_macos_13():
    require_macos_foreground_host(
        'test', platform_name='darwin', machine_name='arm64',
        version_string='13.0')
    with pytest.raises(PlatformUnavailableError, match='Apple Silicon arm64'):
        require_macos_foreground_host(
            'test', platform_name='darwin', machine_name='x86_64',
            version_string='15.0')
    with pytest.raises(PlatformUnavailableError, match='macOS 13.0'):
        require_macos_foreground_host(
            'test', platform_name='darwin', machine_name='arm64',
            version_string='12.6')
    with pytest.raises(PlatformUnavailableError, match='valid macOS version'):
        require_macos_foreground_host(
            'test', platform_name='darwin', machine_name='arm64',
            version_string='')
    with pytest.raises(PlatformUnavailableError, match='valid macOS version'):
        require_macos_foreground_host(
            'test', platform_name='darwin', machine_name='arm64',
            version_string='latest')
