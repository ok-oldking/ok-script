"""Mute the cloud page through Playwright without changing system audio."""

import asyncio

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


SET_MEDIA_MUTED = """muted => {
    const key = Symbol.for('ok-script.background-audio');
    if (!window[key]) {
        const saved = new Map();
        const state = {active: false};
        const apply = element => {
            if (!state.active || !(element instanceof HTMLMediaElement)) return;
            if (!saved.has(element) || element.volume > 0) saved.set(element, element.volume);
            if (element.volume !== 0) element.volume = 0;
        };
        state.setMuted = value => {
            state.active = value;
            if (value) {
                document.querySelectorAll('audio,video').forEach(apply);
            } else {
                for (const [element, original] of saved) element.volume = original;
                saved.clear();
            }
        };
        new MutationObserver(records => {
            if (!state.active) return;
            for (const record of records) {
                for (const node of record.addedNodes) {
                    if (!(node instanceof Element)) continue;
                    apply(node);
                    node.querySelectorAll('audio,video').forEach(apply);
                }
            }
        }).observe(document, {childList: true, subtree: true});
        document.addEventListener('volumechange', event => apply(event.target), true);
        window[key] = state;
    }
    window[key].setMuted(muted);
}"""


class BrowserAudioMute:
    def __init__(self, page, is_foreground, is_enabled, exit_event):
        self.page = page
        self.is_foreground = is_foreground
        self.is_enabled = is_enabled
        self.exit_event = exit_event
        self._task = None

    def start(self):
        self._task = asyncio.create_task(self._run(), name='BrowserAudioMute')

    async def close(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def set_muted(self, muted):
        for frame in self.page.frames:
            try:
                await frame.evaluate(SET_MEDIA_MUTED, muted)
            except Exception:
                # Navigation can destroy an execution context between polls.
                if frame.is_detached() or self.page.is_closed():
                    continue
                raise

    async def update(self):
        await self.set_muted(bool(self.is_enabled() and not self.is_foreground()))

    async def _run(self):
        last_error = None
        try:
            while not self.exit_event.is_set() and not self.page.is_closed():
                try:
                    await self.update()
                    last_error = None
                except Exception as error:
                    if str(error) != last_error:
                        logger.warning(f'Browser background mute failed: {error}')
                        last_error = str(error)
                await asyncio.sleep(0.5)
        finally:
            if not self.page.is_closed():
                try:
                    await self.set_muted(False)
                except Exception as error:
                    logger.debug(f'Could not restore closed browser media: {error}')
