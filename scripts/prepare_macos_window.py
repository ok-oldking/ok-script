"""显式的一次性 macOS 16:9 窗口准备；默认只读，无键鼠事件。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def frame_report(packet):
    return {
        "frame_size": [packet.frame.shape[1], packet.frame.shape[0]],
        "display_scale": packet.geometry.display_scale,
        "outer_geometry": packet.geometry.outer_geometry.to_dict(),
        "content_geometry": packet.geometry.global_content_geometry.to_dict(),
        "target_generation": packet.geometry.target_generation,
        "capture_generation": packet.geometry.capture_generation,
    }


def wait_packet(capture, target, identity, timeout, *, expected=None, foreground=False):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if foreground and not target.is_foreground():
            raise RuntimeError("目标已失焦；不会自动激活或重新设置尺寸")
        snapshot = target.snapshot
        if (not snapshot.exists or snapshot.candidate is None
                or snapshot.candidate.runtime_identity != identity):
            raise RuntimeError("目标窗口身份已改变；请重新选择窗口")
        packet = capture.get_frame_packet()
        snapshot = target.snapshot
        if (not snapshot.exists or snapshot.candidate is None
                or snapshot.candidate.runtime_identity != identity):
            raise RuntimeError("取帧期间目标窗口身份已改变；请重新选择窗口")
        if foreground and not target.is_foreground():
            raise RuntimeError("取帧期间目标已失焦；不会自动激活或重新设置尺寸")
        if (packet is not None
                and packet.geometry.target_generation == snapshot.generation
                and 0 <= time.monotonic() - packet.captured_monotonic <= 1.0 and (
                expected is None or packet.frame.shape[:2] == (expected[1], expected[0]))):
            return packet
        time.sleep(0.05)
    raise RuntimeError(f"未在 {timeout:g} 秒内取得所需内容帧：{capture.diagnostics().last_error}")


def run(*, bundle_id, window_id, resolution="1920x1080", apply=False, timeout=12,
        wait_foreground=0):
    from ok.device.capture_methods.screencapturekit import ScreenCaptureKitCaptureMethod
    from ok.device.services import create_permission_service
    from ok.device.window_target import create_macos_window_discovery, WindowMatchHints
    from ok.platform import require_macos_foreground_host
    from ok.util.handler import ExitEvent

    report = {"apply_requested": apply, "input_events_sent": False, "verified": False}
    capture = None
    code = 0
    try:
        require_macos_foreground_host("macOS window preparation")
        width, height = (int(value) for value in resolution.split("x"))
        if width <= 0 or height <= 0 or width * 9 != height * 16 or not 0 < timeout <= 30:
            raise ValueError("需要正整数 16:9 尺寸和 0–30 秒内的有限超时")
        if not 0 <= wait_foreground <= 30:
            raise ValueError("启动前等待置前的时间必须为 0–30 秒")
        permissions = create_permission_service()
        if not all(item.granted for item in permissions.snapshot()):
            raise RuntimeError("需要用户已授予的 Screen Recording 与 Accessibility 权限")
        discovery = create_macos_window_discovery()
        hints = WindowMatchHints(bundle_identifiers=(bundle_id,))
        candidate = discovery.select(hints, manual_window_id=window_id).selected
        if candidate is None:
            raise RuntimeError("未找到指定 bundle identity 和 window ID 的唯一窗口")
        target = discovery.bind(candidate, hints)
        identity = target.snapshot.candidate.runtime_identity
        if apply and wait_foreground:
            deadline = time.monotonic() + wait_foreground
            while not target.is_foreground():
                if time.monotonic() >= deadline:
                    raise RuntimeError("等待目标置前超时；未发送尺寸请求")
                time.sleep(0.05)
            target.refresh()
            if (not target.snapshot.exists or target.snapshot.candidate is None
                    or target.snapshot.candidate.runtime_identity != identity):
                raise RuntimeError("等待置前期间窗口身份已改变")
        exit_event = ExitEvent()
        capture = ScreenCaptureKitCaptureMethod(exit_event, target, permissions)
        packet = wait_packet(capture, target, identity, timeout)
        report["before"] = frame_report(packet)
        report["requested_frame_size"] = [width, height]
        report["matches_request"] = packet.frame.shape[:2] == (height, width)
        if apply and not target.is_foreground():
            raise RuntimeError("请先将目标游戏置前；本命令不自动激活")
        if apply and report["matches_request"]:
            report["verified"] = True
            report["size_request_sent"] = False
        elif apply:
            # This permanently closes the old stream before the single AX write.
            report["request"] = capture.request_content_size(width, height)
            report["size_request_sent"] = True
            target.refresh()
            if target.snapshot.candidate is None or target.snapshot.candidate.runtime_identity != identity:
                raise RuntimeError("尺寸请求后窗口身份改变；不会向替代窗口重试")
            capture = ScreenCaptureKitCaptureMethod(exit_event, target, permissions)
            packet = wait_packet(
                capture, target, identity, timeout, expected=(width, height), foreground=True)
            if packet.geometry.display_scale != report["request"]["display_scale"]:
                raise RuntimeError("显示比例改变；本次请求不能作为尺寸验收")
            report["after"] = frame_report(packet)
            report["verified"] = True
    except Exception as error:
        report["error"] = str(error)
        code = 1
    finally:
        if capture is not None:
            try:
                capture.close()
            except Exception as error:
                report["cleanup_error"] = str(error)
                report["verified"] = False
                code = 1
    return report, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--window-id", required=True, type=int)
    parser.add_argument("--resolution", default="1920x1080",
                        choices=("1280x720", "1600x900", "1920x1080", "2560x1440"))
    parser.add_argument("--apply", action="store_true", help="显式允许一次 AXSize 请求；先停止所有自动化")
    parser.add_argument("--timeout", type=float, default=12)
    parser.add_argument("--wait-foreground", type=float, default=0,
                        help="仅在启动前等待用户置前，最多 30 秒；不自动激活")
    args = parser.parse_args()
    report, code = run(**vars(args))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
