import asyncio
import importlib.util
import unittest

from ok.device.capture_methods.browser_webrtc import (
    PEER_CONNECTION_REGISTRY_JS,
    STATUS_FRAME,
    TAP_JS,
    WebRtcFrameReceiver,
    parse_message,
    place_in_viewport,
)

# Mimics a cloud game SDK in canvas player mode: the remote WebRTC track is never attached to a
# <video>; the page draws it on a canvas. Headless browsers may gather no ICE candidates (no usable
# network interface), so a real connection cannot be relied on: the page creates a real connection
# and its receiver returns a live canvas stream track (solid green, 320x240) standing in for the game
# stream, shown in a 400x300 canvas at (50, 20).
CANVAS_PLAYER_PAGE = '''<body style="margin:0">
<video id="unused" style="position:absolute;left:0;top:0;width:10px;height:10px"></video>
<canvas id="player" width="400" height="300" style="position:absolute;left:50px;top:20px"></canvas>
<script>
window.ready = (async () => {
  const src = document.createElement('canvas');
  src.width = 320; src.height = 240;
  const g = src.getContext('2d');
  setInterval(() => { g.fillStyle = '#00ff00'; g.fillRect(0, 0, 320, 240); }, 30);
  const track = window.remoteTrack = src.captureStream(30).getVideoTracks()[0];
  const pc = window.gamePc = new RTCPeerConnection();
  pc.getReceivers = () => [{track}];
  return true;
})();
</script></body>'''


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Optional Playwright browser dependency is not installed')
class TestPeerConnectionTapInEdge(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.addAsyncCleanup(self.playwright.stop)
        try:
            self.browser = await self.playwright.chromium.launch(channel='msedge', headless=True)
        except Exception as error:
            self.skipTest(f'Edge is not available: {error}')
        self.addAsyncCleanup(self.browser.close)
        self.context = await self.browser.new_context(viewport={'width': 640, 'height': 360})
        self.receiver = WebRtcFrameReceiver()
        self.addCleanup(self.receiver.close)

    async def open_player(self, registry):
        if registry:
            await self.context.add_init_script(script=f'({PEER_CONNECTION_REGISTRY_JS})()')
        page = await self.context.new_page()
        await page.set_content(CANVAS_PLAYER_PAGE)
        self.assertTrue(await page.evaluate('window.ready'))
        return page

    async def frame(self, page):
        for _ in range(50):
            message = await asyncio.to_thread(self.receiver.request)
            if message is not None:
                status, frame, content, element = parse_message(message)
                if status == STATUS_FRAME:
                    return frame, content, element
            await page.wait_for_timeout(100)
        self.fail('no frame from the tap')

    async def test_without_registry_there_is_no_video(self):
        page = await self.open_player(registry=False)
        self.assertEqual('no-video', await page.evaluate(TAP_JS, {'wsUrl': self.receiver.url}))

    async def test_registry_keeps_constructor_native(self):
        page = await self.open_player(registry=True)
        self.assertEqual(1, await page.evaluate('window.__okPeerConnections.length'))
        self.assertTrue(await page.evaluate(
            '(new RTCPeerConnection()) instanceof RTCPeerConnection && RTCPeerConnection.name === "RTCPeerConnection"'))

    async def test_received_track_is_tapped_and_placed_on_canvas(self):
        page = await self.open_player(registry=True)
        self.assertEqual('ok', await page.evaluate(TAP_JS, {'wsUrl': self.receiver.url}))
        self.assertEqual('ok', await page.evaluate(TAP_JS, {'wsUrl': self.receiver.url}))  # kept
        frame, content, element = await self.frame(page)
        self.assertEqual((240, 320), frame.shape[:2])
        self.assertEqual((50, 20, 400, 300), tuple(round(x) for x in content))
        self.assertEqual(content, element)
        placed = place_in_viewport(frame, content, element, (640, 360))
        b, g, r = placed[170, 250]
        self.assertGreater(g, 200)
        self.assertLess(max(b, r), 60)
        self.assertEqual(0, placed[5, 5].max())  # outside the canvas

    async def test_stopped_track_ends_tap(self):
        page = await self.open_player(registry=True)
        self.assertEqual('ok', await page.evaluate(TAP_JS, {'wsUrl': self.receiver.url}))
        await self.frame(page)
        await page.evaluate('window.remoteTrack.stop()')
        self.assertEqual('no-video', await page.evaluate(TAP_JS, {'wsUrl': self.receiver.url}))

    async def test_closed_connection_is_dropped(self):
        page = await self.open_player(registry=True)
        await page.evaluate('window.gamePc.close()')
        self.assertEqual('no-video', await page.evaluate(TAP_JS, {'wsUrl': self.receiver.url}))
        self.assertEqual(0, await page.evaluate('window.__okPeerConnections.length'))


if __name__ == '__main__':
    unittest.main()
