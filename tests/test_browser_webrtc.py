import base64
import hashlib
import os
import socket
import struct
import threading
import time
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from ok.device.capture_methods import browser
from ok.device.capture_methods.browser import BrowserCaptureMethod
from ok.device.capture_methods.browser_webrtc import (
    FORMAT_BGRA, FORMAT_I420, FORMAT_NV12, HEADER_SIZE, MAGIC, STATUS_ENDED, STATUS_FRAME, STATUS_NO_FRAME,
    WS_GUID, WebRtcFrameReceiver, parse_message, place_in_viewport, unmask,
)


def message(status, w=0, h=0, fmt=0, planes=(), payload=b'', content=(0, 0, 0, 0), element=(0, 0, 0, 0)):
    header = np.zeros(11, np.uint32)
    header[:5] = [MAGIC, status, w, h, fmt]
    for i, (offset, stride) in enumerate(planes):
        header[5 + i * 2], header[6 + i * 2] = offset, stride
    rects = np.array(list(content) + list(element), np.float32)
    return header.tobytes() + b'\0' * 4 + rects.tobytes() + payload


def make_image(w=64, h=48):
    rng = np.random.default_rng(1)
    # Smooth content so 4:2:0 chroma subsampling loses little.
    small = rng.integers(0, 255, (h // 8, w // 8, 3), np.uint8)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


class TestFrameDecoding(unittest.TestCase):
    def test_unmask_handles_unaligned_tail(self):
        data = bytearray(os.urandom(23))
        mask = bytearray(b'\x01\x02\x03\x04')
        masked = bytearray(b ^ mask[i % 4] for i, b in enumerate(data))
        buf = bytearray(b'xx') + masked
        unmask(buf, 2, len(data), mask)
        self.assertEqual(data, buf[2:])

    def test_bgra_frame(self):
        img = make_image()
        h, w = img.shape[:2]
        bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA).tobytes()
        status, frame, content, element = parse_message(message(
            STATUS_FRAME, w, h, FORMAT_BGRA, [(0, w * 4)], bgra, (1, 2, 3, 4), (5, 6, 7, 8)))
        self.assertEqual(STATUS_FRAME, status)
        np.testing.assert_array_equal(img, frame)
        self.assertEqual((1, 2, 3, 4), content)
        self.assertEqual((5, 6, 7, 8), element)

    def test_i420_frame(self):
        img = make_image()
        h, w = img.shape[:2]
        i420 = cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420).tobytes()
        planes = [(0, w), (w * h, w // 2), (w * h + w * h // 4, w // 2)]
        _, frame, _, _ = parse_message(message(STATUS_FRAME, w, h, FORMAT_I420, planes, i420))
        self.assertLess(np.abs(frame.astype(int) - img).mean(), 8)

    def test_nv12_frame_with_padded_rows(self):
        img = make_image()
        h, w = img.shape[:2]
        i420 = cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420)
        y = i420[:h]
        u = i420[h:h + h // 4].reshape(h // 2, w // 2)
        v = i420[h + h // 4:].reshape(h // 2, w // 2)
        stride = w + 16
        y_plane = np.zeros((h, stride), np.uint8)
        y_plane[:, :w] = y
        uv_plane = np.zeros((h // 2, stride), np.uint8)
        uv_plane[:, :w] = np.dstack([u, v]).reshape(h // 2, w)
        payload = y_plane.tobytes() + uv_plane.tobytes()
        _, frame, _, _ = parse_message(message(STATUS_FRAME, w, h, FORMAT_NV12, [(0, stride), (h * stride, stride)], payload))
        self.assertLess(np.abs(frame.astype(int) - img).mean(), 8)

    def test_status_without_frame(self):
        self.assertEqual(STATUS_NO_FRAME, parse_message(message(STATUS_NO_FRAME))[0])
        self.assertEqual(STATUS_ENDED, parse_message(message(STATUS_ENDED))[0])
        self.assertIsNone(parse_message(message(STATUS_ENDED))[1])


class TestPlaceInViewport(unittest.TestCase):
    def test_full_viewport_frame_is_returned_unchanged(self):
        frame = np.ones((72, 128, 3), np.uint8)
        self.assertIs(frame, place_in_viewport(frame, (0, 0, 128, 72), (0, 0, 128, 72), (128, 72)))

    def test_letterboxed_and_scaled(self):
        frame = np.full((72, 128, 3), 200, np.uint8)
        # 64x48 element at (10, 5); 16:9 content is 64x36 centered vertically.
        out = place_in_viewport(frame, (10, 11, 64, 36), (10, 5, 64, 48), (128, 72))
        self.assertEqual((72, 128, 3), out.shape)
        rows = np.where(out.max(2).max(1) > 0)[0]
        cols = np.where(out.max(2).max(0) > 0)[0]
        self.assertEqual((11, 46), (rows.min(), rows.max()))
        self.assertEqual((10, 73), (cols.min(), cols.max()))

    def test_cover_is_clipped_to_element_and_offset_by_iframe(self):
        frame = np.zeros((100, 100, 3), np.uint8)
        frame[:, 50:] = 255
        # Content 100x100 drawn at (-20, 0) is clipped to the 60x100 element at (0, 0), then the
        # iframe offset moves it to (30, 0).
        out = place_in_viewport(frame, (-20, 0, 100, 100), (0, 0, 60, 100), (200, 100), offset=(30, 0))
        cols = np.where(out.max(2).max(0) > 0)[0]
        self.assertEqual((60, 89), (cols.min(), cols.max()))


class WsClient:
    """Browser side of the receiver protocol: masked client frames, unmasked server frames."""

    def __init__(self, url):
        host_port, path = url[len('ws://'):].split('/', 1)
        host, port = host_port.split(':')
        self.sock = socket.create_connection((host, int(port)), timeout=5)
        key = base64.b64encode(os.urandom(16))
        self.sock.sendall(b'GET /' + path.encode() + b' HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n'
                          b'Connection: Upgrade\r\nSec-WebSocket-Key: ' + key + b'\r\nSec-WebSocket-Version: 13\r\n\r\n')
        response = b''
        while b'\r\n\r\n' not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError('closed during handshake')
            response += chunk
        expected = base64.b64encode(hashlib.sha1(key + WS_GUID).digest())
        assert expected in response, response

    def read_request(self):
        header = self.sock.recv(2)
        assert header[0] == 0x81 and header[1] & 0x80 == 0, header  # unmasked text from the server
        return header

    def send_binary(self, data, fragments=1):
        size = (len(data) + fragments - 1) // fragments
        parts = [data[i:i + size] for i in range(0, len(data), size)] or [b'']
        for i, part in enumerate(parts):
            opcode = 0x2 if i == 0 else 0x0
            first = (0x80 if i == len(parts) - 1 else 0) | opcode
            mask = os.urandom(4)
            n = len(part)
            length = bytes([0x80 | n]) if n < 126 else (
                bytes([0x80 | 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x80 | 127]) + struct.pack('>Q', n))
            self.sock.sendall(bytes([first]) + length + mask + bytes(b ^ mask[j % 4] for j, b in enumerate(part)))


class TestReceiver(unittest.TestCase):
    def setUp(self):
        self.receiver = WebRtcFrameReceiver()

    def tearDown(self):
        self.receiver.close()

    def wait_connected(self):
        deadline = time.time() + 5
        while not self.receiver.connected and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.receiver.connected)

    def test_request_returns_fragmented_masked_message(self):
        client = WsClient(self.receiver.url)
        self.wait_connected()
        payload = os.urandom(70000)

        def respond():
            client.read_request()
            client.send_binary(payload, fragments=3)

        t = threading.Thread(target=respond)
        t.start()
        self.assertEqual(payload, bytes(self.receiver.request()))
        t.join()

    def test_wrong_token_is_rejected(self):
        bad = self.receiver.url.rsplit('/', 1)[0] + '/wrong'
        with self.assertRaises((ConnectionError, OSError)):
            WsClient(bad)
        self.assertFalse(self.receiver.connected)

    def test_request_without_page_returns_none(self):
        self.assertIsNone(self.receiver.request())

    def test_lost_connection_returns_none(self):
        client = WsClient(self.receiver.url)
        self.wait_connected()
        client.sock.close()
        self.assertIsNone(self.receiver.request(timeout=1))
        self.assertFalse(self.receiver.connected)


class TestWebRtcCaptureMode(unittest.TestCase):
    def capture(self, install_results, screenshot=None):
        capture = BrowserCaptureMethod.__new__(BrowserCaptureMethod)
        capture._size = (128, 72)
        capture.capture_mode = 'webrtc'
        capture._next_tap_check = 0.0
        capture._tap_offset = (0.0, 0.0)
        capture._frame_source = None
        capture._webrtc = Mock(connected=True)
        results = iter(install_results)

        def run_quietly(coro):
            coro.close()
            return next(results)

        capture._run_quietly = run_quietly
        capture._screenshot_frame = Mock(return_value=screenshot)
        return capture

    def test_no_video_falls_back_to_screenshot(self):
        shot = np.zeros((72, 128, 3), np.uint8)
        capture = self.capture([('no-video', None)], screenshot=shot)
        self.assertIs(shot, capture._webrtc_or_screenshot_frame())
        capture._webrtc.disconnect.assert_called_once()
        capture._webrtc.request.assert_not_called()
        self.assertEqual('Playwright screenshot', capture._frame_source)

    def test_video_frame_is_used(self):
        img = np.full((72, 128, 3), 9, np.uint8)
        capture = self.capture([('ok', (0.0, 0.0))])
        bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA).tobytes()
        capture._webrtc.request.return_value = memoryview(message(
            STATUS_FRAME, 128, 72, FORMAT_BGRA, [(0, 128 * 4)], bgra, (0, 0, 128, 72), (0, 0, 128, 72)))
        np.testing.assert_array_equal(img, capture._webrtc_or_screenshot_frame())
        capture._screenshot_frame.assert_not_called()
        self.assertEqual('WebRTC video', capture._frame_source)

    def test_receiver_failure_backs_off(self):
        capture = self.capture([('ws-failed', None)])
        capture._webrtc_or_screenshot_frame()
        self.assertGreater(capture._next_tap_check - time.monotonic(), browser.TAP_RETRY_AFTER_FAILURE - 1)

    def test_ended_track_is_rechecked_immediately(self):
        capture = self.capture([('ok', (0.0, 0.0))], screenshot=None)
        capture._webrtc.request.return_value = memoryview(message(STATUS_ENDED))
        self.assertIsNone(capture._webrtc_or_screenshot_frame())
        capture._webrtc.disconnect.assert_called_once()
        self.assertEqual(0.0, capture._next_tap_check)


if __name__ == '__main__':
    unittest.main()
