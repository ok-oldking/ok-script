import importlib.util
import unittest

from ok.device.capture_methods.browser import FAKE_POINTER_LOCK_JS

# Mimics the cloud game SDK: caches requestPointerLock on the element, locks on mouse down and
# sends Esc (records 'esc') when the lock is lost or refused.
SDK_PAGE = '''<video id="game" style="width:400px;height:300px;display:block"></video><script>
  window.events = [];
  const v = document.getElementById('game');
  v.requestPointerLock = v.requestPointerLock || v.webkitRequestPointerLock;
  v.onmousedown = e => { events.push('down' + e.button);
    if (document.pointerLockElement !== v) v.requestPointerLock().catch(() => events.push('rejected')); };
  document.onpointerlockchange = () => events.push(document.pointerLockElement === v ? 'locked' : 'esc');
  document.onpointerlockerror = () => events.push('esc');
</script>'''

# Chromium refuses pointer lock when the browser window is not the OS foreground window, which is
# the normal case for automation. Headless grants it, so reproduce the refusal explicitly.
REFUSE_LOCK = '''Element.prototype.requestPointerLock = function () {
  setTimeout(() => document.dispatchEvent(new Event('pointerlockerror')));
  return Promise.reject(new DOMException('not focused', 'WrongDocumentError'));
};'''


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Optional Playwright browser dependency is not installed')
class TestFakePointerLockInEdge(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.addAsyncCleanup(self.playwright.stop)
        try:
            self.browser = await self.playwright.chromium.launch(channel='msedge', headless=True)
        except Exception as error:
            self.skipTest(f'Edge is not available: {error}')
        self.addAsyncCleanup(self.browser.close)
        self.context = await self.browser.new_context()
        await self.context.add_init_script(script=REFUSE_LOCK)
        self.page = await self.context.new_page()

    async def middle_click_events(self):
        await self.page.mouse.click(200, 150, button='middle')
        await self.page.wait_for_timeout(100)
        return await self.page.evaluate('window.events')

    async def test_background_window_refuses_lock_without_fake(self):
        await self.page.set_content(SDK_PAGE)
        self.assertEqual(['down1', 'esc', 'rejected'], sorted(await self.middle_click_events()))

    async def test_init_script_grants_lock_on_click(self):
        await self.context.add_init_script(script=f'({FAKE_POINTER_LOCK_JS})()')
        self.page = await self.context.new_page()  # init scripts run when a document is created
        await self.page.set_content(SDK_PAGE)
        self.assertEqual(['down1', 'locked'], await self.middle_click_events())
        await self.page.evaluate('document.exitPointerLock()')
        self.assertIsNone(await self.page.evaluate('document.pointerLockElement'))

    async def test_patching_already_loaded_page_replaces_cached_function(self):
        await self.page.set_content(SDK_PAGE)
        self.assertTrue(await self.page.evaluate(FAKE_POINTER_LOCK_JS))
        self.assertTrue(await self.page.evaluate(FAKE_POINTER_LOCK_JS))  # idempotent
        self.assertEqual(['down1', 'locked'], await self.middle_click_events())


if __name__ == '__main__':
    unittest.main()
