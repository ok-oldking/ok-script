import importlib.util
import unittest

from ok.device.browser_audio import SET_MEDIA_MUTED


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Optional Playwright browser dependency is not installed')
class TestBrowserAudioInEdge(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.addAsyncCleanup(self.playwright.stop)
        try:
            self.browser = await self.playwright.chromium.launch(channel='msedge', headless=True)
        except Exception as error:
            self.skipTest(f'Edge is not available: {error}')
        self.addAsyncCleanup(self.browser.close)
        self.page = await self.browser.new_page()

    async def test_sdk_startup_unmute_and_new_media_restore_their_volume(self):
        page = self.page
        await page.set_content('<audio id="game" muted></audio><video id="video" muted></video>')
        await page.locator('#game').evaluate('(e) => e.volume = 0.4')
        await page.evaluate(SET_MEDIA_MUTED, True)
        # The cloud SDK unmutes its stream after connecting. Background silence
        # must survive that transition without changing the SDK's mute flag.
        await page.locator('#game').evaluate('(e) => e.muted = false')
        self.assertTrue(await page.locator('#game').evaluate('(e) => e.volume === 0 && !e.muted'))
        await page.evaluate("const audio = new Audio(); audio.id = 'late'; document.body.append(audio)")
        await page.wait_for_function("document.querySelector('#late').volume === 0")
        await page.locator('#game').evaluate('(e) => e.volume = 0.6')
        await page.wait_for_function("document.querySelector('#game').volume === 0")
        await page.evaluate(SET_MEDIA_MUTED, False)
        states = await page.locator('audio,video').evaluate_all(
            '(els) => els.map(e => ({muted:e.muted, volume:e.volume}))')
        self.assertEqual([False, True, False], [state['muted'] for state in states])
        self.assertEqual([0.6, 1, 1], [state['volume'] for state in states])


if __name__ == '__main__':
    unittest.main()
