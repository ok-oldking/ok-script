import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, Mock

from ok.device.browser_audio import BrowserAudioMute, SET_MEDIA_MUTED
from ok.device.capture_methods.browser import BrowserCaptureMethod


class TestBrowserAudioMute(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.frames = [Mock(evaluate=AsyncMock()), Mock(evaluate=AsyncMock())]
        self.page = Mock(frames=self.frames)
        self.page.is_closed.return_value = False
        self.foreground = False
        self.enabled = True
        self.exit_event = threading.Event()
        self.controller = BrowserAudioMute(
            self.page, lambda: self.foreground, lambda: self.enabled, self.exit_event)

    async def test_background_mutes_every_frame_through_playwright(self):
        await self.controller.update()
        for frame in self.frames:
            frame.evaluate.assert_awaited_once_with(SET_MEDIA_MUTED, True)

    async def test_foreground_restores_page_media(self):
        self.foreground = True
        await self.controller.update()
        for frame in self.frames:
            frame.evaluate.assert_awaited_once_with(SET_MEDIA_MUTED, False)

    async def test_disabling_setting_restores_page_media(self):
        self.enabled = False
        await self.controller.update()
        for frame in self.frames:
            frame.evaluate.assert_awaited_once_with(SET_MEDIA_MUTED, False)

    async def test_detached_frame_does_not_prevent_muting_remaining_frames(self):
        self.frames[0].evaluate.side_effect = RuntimeError('Frame detached')
        self.frames[0].is_detached.return_value = True
        await self.controller.update()
        self.frames[1].evaluate.assert_awaited_once_with(SET_MEDIA_MUTED, True)

    async def test_live_frame_error_is_reported_for_retry(self):
        self.frames[0].evaluate.side_effect = RuntimeError('Navigation')
        self.frames[0].is_detached.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'Navigation'):
            await self.controller.update()

    async def test_monitor_close_restores_media_and_stops_polling(self):
        self.controller.start()
        await asyncio.sleep(0)
        await self.controller.close()
        self.assertIsNone(self.controller._task)
        for frame in self.frames:
            self.assertEqual([True, False], [call.args[1] for call in frame.evaluate.await_args_list])

    async def test_application_exit_restores_media(self):
        self.exit_event.set()
        await self.controller._run()
        for frame in self.frames:
            frame.evaluate.assert_awaited_once_with(SET_MEDIA_MUTED, False)

    async def test_closed_page_is_not_evaluated(self):
        self.page.is_closed.return_value = True
        await self.controller._run()
        for frame in self.frames:
            frame.evaluate.assert_not_awaited()

    async def test_capture_close_stops_mute_controller_before_closing_page(self):
        capture = BrowserCaptureMethod.__new__(BrowserCaptureMethod)
        controller = Mock(close=AsyncMock())
        capture._audio_mute = controller
        capture.page = Mock(close=AsyncMock())
        capture.browser = None
        capture.playwright = None
        await capture._close_async()
        controller.close.assert_awaited_once()
        capture.page.close.assert_awaited_once()
        self.assertIsNone(capture._audio_mute)


if __name__ == '__main__':
    unittest.main()
