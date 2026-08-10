import time

import win32api
import win32con
import win32gui
import win32process


def insert_messenger_image(automation, method, hwnd, input_target, input_point, frame):
    """Insert one frame using the provider's background-safe native UI path."""
    if method == 'context_menu':
        return _paste_from_context_menu(automation, hwnd, input_point, frame)

    automation._set_clipboard_image(frame)
    automation._hotkey(input_target, win32con.VK_CONTROL, ord('V'))
    time.sleep(1)
    return True


def _paste_from_context_menu(automation, hwnd, input_point, frame):
    automation._set_clipboard_image(frame)
    _left_click(hwnd, input_point)
    time.sleep(1)
    _right_click(hwnd, input_point)
    # Let Chromium finish drawing the menu before PrintWindow/OCR begins;
    # capturing too early can keep a background QQ renderer from presenting it.
    time.sleep(1)
    popup, paste = _wait_popup_text(
        automation, hwnd, {'Paste', '粘贴', '貼上'}, timeout=5,
        match_end=automation.paste_match_end)
    if paste is None:
        # A throttled background Chromium renderer may present the menu only
        # after the first RenderFull polling pass yields.
        time.sleep(.5)
        popup, paste = _wait_popup_text(
            automation, hwnd, {'Paste', '粘贴', '貼上'}, timeout=3,
            match_end=automation.paste_match_end)
    if paste is None:
        try:
            automation._save_error_screenshot('paste_menu')
        except Exception:
            pass
        raise RuntimeError('Could not find Paste/粘贴 in the messenger context menu')
    if popup == hwnd:
        _click_render_surface(hwnd, paste)
    else:
        automation._click(popup, paste, focus=False)
    time.sleep(1)
    return True


def _left_click(hwnd, point):
    """Synchronously focus the composer before opening its context menu."""
    target = _render_surface(hwnd)
    local = (int(point[0]), int(point[1]))
    lparam = win32api.MAKELONG(*local)
    win32gui.SendMessage(target, win32con.WM_MOUSEMOVE, 0, lparam)
    win32gui.SendMessage(target, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    win32gui.SendMessage(target, win32con.WM_LBUTTONUP, 0, lparam)


def _right_click(hwnd, point):
    target = _render_surface(hwnd)
    local = (int(point[0]), int(point[1]))
    lparam = win32api.MAKELONG(*local)
    # Keep this sequence synchronous so the menu exists before OCR starts.
    # QQ can otherwise defer queued background clicks until after the timeout.
    win32gui.SendMessage(target, win32con.WM_MOUSEMOVE, 0, lparam)
    win32gui.SendMessage(target, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lparam)
    win32gui.SendMessage(target, win32con.WM_RBUTTONUP, 0, lparam)


def _click_render_surface(hwnd, point):
    """Click Chromium-rendered context menus without foreground activation."""
    target = _render_surface(hwnd)
    local = (int(point[0]), int(point[1]))
    lparam = win32api.MAKELONG(*local)
    win32gui.PostMessage(target, win32con.WM_MOUSEMOVE, 0, lparam)
    win32gui.PostMessage(
        target, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    win32gui.PostMessage(target, win32con.WM_LBUTTONUP, 0, lparam)


def _render_surface(hwnd):
    targets = []

    def callback(candidate, _):
        if win32gui.GetClassName(candidate) == 'Chrome_RenderWidgetHostHWND':
            targets.append(candidate)
        return True

    win32gui.EnumChildWindows(hwnd, callback, None)
    return targets[0] if targets else hwnd


def _wait_popup_text(automation, hwnd, names, timeout, match_end=False):
    wanted = {name.casefold() for name in names}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            candidates = _tool_popups(hwnd)
        except Exception:
            candidates = []
        try:
            render_surface = _render_surface(hwnd)
            if render_surface not in candidates:
                candidates.insert(0, render_surface)
        except Exception:
            pass
        candidates.append(hwnd)
        for popup in candidates:
            try:
                frame = automation._capture(popup)
                automation._last_frame = frame
                for text, x, y, width, height in automation._ocr(frame):
                    normalized = text.strip().casefold()
                    matched = (any(normalized.endswith(name) for name in wanted)
                               if match_end else normalized in wanted)
                    if matched:
                        return popup, (x + width // 2, y + height // 2)
            except Exception:
                continue
        time.sleep(.15)
    return hwnd, None


def _tool_popups(hwnd):
    _, root_pid = win32process.GetWindowThreadProcessId(hwnd)
    root_left, root_top, root_right, root_bottom = win32gui.GetWindowRect(hwnd)
    root_area = max(1, (root_right - root_left) * (root_bottom - root_top))
    popups = []

    def callback(candidate, _):
        if candidate == hwnd or not win32gui.IsWindowVisible(candidate):
            return True
        _, pid = win32process.GetWindowThreadProcessId(candidate)
        owner = win32gui.GetWindow(candidate, win32con.GW_OWNER)
        if pid == root_pid or owner == hwnd:
            left, top, right, bottom = win32gui.GetWindowRect(candidate)
            area = max(0, right - left) * max(0, bottom - top)
            if area and area < root_area // 2:
                popups.append((area, candidate))
        return True

    win32gui.EnumWindows(callback, None)
    return [candidate for _, candidate in sorted(popups)]
