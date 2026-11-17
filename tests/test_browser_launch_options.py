import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from ok.device.capture_methods.browser import BrowserCaptureMethod


class TestBrowserLaunchOptions(unittest.IsolatedAsyncioTestCase):
    async def launch(self, config, fail_first=False):
        page = Mock()
        page.url = 'about:blank'
        page.goto = AsyncMock()
        page.bring_to_front = AsyncMock()
        page.set_viewport_size = AsyncMock()
        page.title = AsyncMock(return_value='Cloud Game')
        page.evaluate = AsyncMock(return_value=True)
        context = Mock(pages=[page])
        context.add_init_script = AsyncMock()
        launch_context = AsyncMock(return_value=context)
        if fail_first:
            launch_context.side_effect = [RuntimeError('Browser not installed'), context]
        playwright = Mock()
        playwright.chromium.launch_persistent_context = launch_context
        api = types.ModuleType('playwright.async_api')
        api.async_playwright = Mock(return_value=Mock(start=AsyncMock(return_value=playwright)))

        capture = BrowserCaptureMethod.__new__(BrowserCaptureMethod)
        capture.config = config
        capture._size = (1920, 1080)
        capture.browser = None
        capture.update_window_geometry = Mock(return_value=True)
        with patch.dict(sys.modules, {'playwright': types.ModuleType('playwright'),
                                      'playwright.async_api': api}), \
                patch('ok.device.capture_methods.browser.asyncio.sleep', new=AsyncMock()), \
                patch('ok.device.capture_methods.browser.find_hwnd',
                      return_value=('Cloud Game', 123, 'browser.exe', 0, 0, 1920, 1080)), \
                patch('ok.device.capture_methods.browser.BrowserWGC'):
            await capture._start_browser_async()
        self.assertIs(capture.browser, context)
        self.assertIs(capture.page, page)
        self.context, self.page = context, page
        return launch_context

    async def test_default_channel_and_background_arguments_are_preserved(self):
        launch = await self.launch({})
        launch.assert_awaited_once()
        self.assertEqual('msedge', launch.call_args.kwargs['channel'])
        self.assertIn('--disable-background-timer-throttling', launch.call_args.kwargs['args'])

    async def test_configured_channel_and_arguments_reach_playwright(self):
        args = ['--webrtc-ip-handling-policy=default']
        launch = await self.launch({'channels': ['chrome'], 'args': args})
        launch.assert_awaited_once()
        self.assertEqual('chrome', launch.call_args.kwargs['channel'])
        self.assertIn(args[0], launch.call_args.kwargs['args'])
        self.assertIn('--disable-background-timer-throttling', launch.call_args.kwargs['args'])
        self.assertEqual(['--webrtc-ip-handling-policy=default'], args)

    async def test_fallback_uses_configured_order_and_keeps_arguments(self):
        args = ['--webrtc-ip-handling-policy=default']
        launch = await self.launch({'channels': ['chrome', 'msedge'], 'args': args}, fail_first=True)
        self.assertEqual(['chrome', 'msedge'], [call.kwargs['channel'] for call in launch.await_args_list])
        for call in launch.await_args_list:
            self.assertIn(args[0], call.kwargs['args'])

    async def test_fake_pointer_lock_is_installed_by_default(self):
        await self.launch({})
        self.context.add_init_script.assert_awaited_once()
        self.assertIn('requestPointerLock', self.context.add_init_script.call_args.kwargs['script'])
        self.page.evaluate.assert_awaited_once()

    async def test_fake_pointer_lock_can_be_disabled(self):
        await self.launch({'fake_pointer_lock': False})
        self.context.add_init_script.assert_not_awaited()
        self.page.evaluate.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
