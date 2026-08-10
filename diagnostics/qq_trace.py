"""Trace QQ notification navigation without sending a message.

Usage: .venv\\Scripts\\python.exe diagnostics\\qq_trace.py [nickname]
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ok.notification.windows_messenger import MessengerAutomation


OUT = Path(__file__).resolve().parents[1] / "logs" / "qq_trace"
OUT.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=OUT / "trace.log",
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("qq_trace")


def snap(automation: MessengerAutomation, hwnd: int, label: str) -> None:
    try:
        frame = automation._capture(hwnd)
        path = OUT / f"{time.time_ns()}_{label}.png"
        cv2.imwrite(str(path), frame)
        log.info("screenshot label=%s path=%s shape=%s", label, path, frame.shape)
    except Exception:
        log.exception("screenshot_failed label=%s", label)


def main() -> int:
    nickname = (sys.argv[1] if len(sys.argv) > 1 else "文件传输助手").strip()
    log.info("START nickname=%r", nickname)
    automation = MessengerAutomation(
        ("QQ.exe",), SimpleNamespace(), window_titles=("QQ",),
        dismiss_search_after_contact=True, post_activate=False,
    )
    hwnd = automation._find_hwnd()
    log.info("find_hwnd hwnd=%s foreground=%s", hwnd, __import__("win32gui").GetForegroundWindow())
    if not hwnd:
        log.error("QQ window not found")
        return 2
    snap(automation, hwnd, "01_initial")
    if not automation._wait_until_background(hwnd):
        log.warning("wait_until_background returned false")
        return 3
    log.info("background_ready foreground=%s", __import__("win32gui").GetForegroundWindow())
    snap(automation, hwnd, "02_background_ready")
    search_region, contact_region, send_region = automation._layout_regions(hwnd)
    log.info("layout search=%s contact=%s send=%s", search_region, contact_region, send_region)
    search = automation._wait_text(hwnd, {"Search", "搜索"}, region=search_region, timeout=1.5)
    log.info("search_ocr point=%s", search)
    if search is None:
        search = automation._search_field_point(hwnd)
        log.info("search_fallback point=%s", search)
    snap(automation, hwnd, "03_before_search_click")
    target = automation._click(hwnd, search)
    log.info("click search target=%s point=%s", target, search)
    snap(automation, hwnd, "04_after_search_click")
    time.sleep(1)
    automation._clear_text(target)
    log.info("clear search")
    time.sleep(1)
    automation._type_text(target, nickname)
    log.info("type nickname=%r", nickname)
    time.sleep(1)
    snap(automation, hwnd, "05_after_typing")
    contact_hwnd, contact = automation._wait_contact(hwnd, nickname, contact_region, timeout=8)
    log.info("contact_result hwnd=%s point=%s", contact_hwnd, contact)
    if contact is None:
        log.error("contact not found")
        automation._send_key(hwnd, 0x1B)
        snap(automation, hwnd, "06_contact_not_found_escape")
        return 4
    automation._click(contact_hwnd, contact, focus=contact_hwnd == hwnd)
    log.info("click contact target=%s point=%s", contact_hwnd, contact)
    snap(automation, hwnd, "06_after_contact_click")
    time.sleep(1)
    automation._send_key(hwnd, 0x1B)
    log.info("send escape to dismiss search overlay")
    time.sleep(1)
    snap(automation, hwnd, "07_after_escape")
    send_box = automation._wait_text(hwnd, {"Send", "发送"}, region=send_region, timeout=3)
    log.info("send_box=%s (dry-run; no message sent)", send_box)
    snap(automation, hwnd, "08_final_dry_run")
    log.info("END")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
