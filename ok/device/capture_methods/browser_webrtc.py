"""Capture the decoded frames of a page's WebRTC video track.

A script injected into the page keeps the newest decoded VideoFrame of the largest live WebRTC
video and copies it to Python over a loopback WebSocket when asked. Python places the frame where
the video is drawn in the page, so frames use the same coordinates as Playwright input.

Some pages (e.g. the cloud game SDK in its canvas player mode) draw the stream on a <canvas> and
leave no <video> playing it. For those the tap reads the video track a peer connection receives,
which PEER_CONNECTION_REGISTRY_JS records when the page creates the connection.

Unlike Windows Graphics Capture this keeps working while the browser window is minimized, but it
only sees the video: page elements drawn over or around it are not captured.
"""
import base64
import hashlib
import os
import socket
import struct
import threading

import cv2
import numpy as np

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

WS_GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
MAGIC = 0x4f4b5450

STATUS_FRAME = 1
STATUS_NO_FRAME = 2
STATUS_ENDED = 3

FORMAT_BGRA = 1
FORMAT_I420 = 2
FORMAT_NV12 = 3

# Header (u32 unless noted): magic, status, width, height, format, (offset, stride) x3,
# then f32 x, y, width, height of the drawn video content in CSS pixels of the page viewport,
# then f32 x, y, width, height of the visible video element (clips object-fit: cover).
HEADER_SIZE = 80

# Init script: remember every RTCPeerConnection the page creates, so the tap can find the received
# video track when the page draws it without a <video>. Must run before the page creates its
# connection; connections created earlier are not found.
PEER_CONNECTION_REGISTRY_JS = '''() => {
  const Native = window.RTCPeerConnection;
  if (!Native || window.__okPeerConnections) return true;
  const connections = window.__okPeerConnections = [];
  const Registered = new Proxy(Native, {
    construct(target, args, newTarget) {
      const pc = Reflect.construct(target, args, newTarget);
      connections.push(new WeakRef(pc));
      return pc;
    }
  });
  if (window.webkitRTCPeerConnection === Native) window.webkitRTCPeerConnection = Registered;
  window.RTCPeerConnection = Registered;
  return true;
}'''

# Returns 'ok' when a tap is streaming from the current video, 'no-video', or 'ws-failed' when the
# page cannot connect to the receiver.
# Runs in each frame of the page; the rectangles are relative to that frame's viewport.
# Prefers the largest <video> playing a live WebRTC stream. Without one, it reads the largest live
# video track received by a registered peer connection and assumes it fills the page's largest
# canvas or video element (the whole viewport if there is none).
TAP_JS = r'''async ({wsUrl}) => {
  const liveTrack = (s) => s instanceof MediaStream ?
    s.getVideoTracks().find(t => t.readyState === 'live') : undefined;
  const area = (el) => { const r = el.getBoundingClientRect(); return r.width * r.height; };
  const pick = () => {
    let best = null, bestArea = 0;
    for (const v of document.querySelectorAll('video')) {
      const source = liveTrack(v.srcObject);
      if (!source || !v.videoWidth || area(v) <= bestArea) continue;
      bestArea = area(v);
      best = {source, video: v, element: v};
    }
    if (best) return best;
    const connections = window.__okPeerConnections || [];
    let source = null, pixels = -1;
    for (let i = connections.length - 1; i >= 0; i--) {
      const pc = connections[i].deref();
      if (!pc || pc.signalingState === 'closed') { connections.splice(i, 1); continue; }
      for (const r of pc.getReceivers()) {
        const t = r.track;
        if (!t || t.kind !== 'video' || t.readyState !== 'live' || t.muted) continue;
        const s = t.getSettings();
        if ((s.width || 0) * (s.height || 0) > pixels) { pixels = (s.width || 0) * (s.height || 0); source = t; }
      }
    }
    if (!source) return null;
    let element = null;
    bestArea = 0;
    for (const el of document.querySelectorAll('canvas, video')) {
      if (area(el) > bestArea) { bestArea = area(el); element = el; }
    }
    return {source, video: null, element};
  };
  const old = window.__okWebRtcTap;
  const current = pick();
  if (old) {
    if (old.wsUrl === wsUrl && old.ws.readyState === WebSocket.OPEN && !old.ended && current &&
        current.source === old.source && current.element === old.element) {
      return 'ok';
    }
    old.close();
  }
  if (!current) return 'no-video';
  const {source, video, element} = current;
  const track = source.clone();
  const reader = new MediaStreamTrackProcessor({track}).readable.getReader();
  const tap = {wsUrl, source, video, element, latest: null, ended: false};
  tap.close = () => {
    tap.ended = true;
    try { reader.cancel(); } catch (e) {}
    track.stop();
    if (tap.latest) { tap.latest.close(); tap.latest = null; }
    try { tap.ws.close(); } catch (e) {}
  };
  (async () => {
    try {
      for (;;) {
        const {value, done} = await reader.read();
        if (done) break;
        if (tap.latest) tap.latest.close();
        tap.latest = value;
      }
    } catch (e) {}
    tap.ended = true;
  })();
  const contentRect = () => {
    const r = element ? element.getBoundingClientRect() :
      {left: 0, top: 0, width: window.innerWidth, height: window.innerHeight};
    const vw = video ? video.videoWidth : 0, vh = video ? video.videoHeight : 0;
    let fit = video ? getComputedStyle(video).objectFit : 'fill';
    let w = r.width, h = r.height;
    if (fit === 'scale-down') fit = (vw <= r.width && vh <= r.height) ? 'none' : 'contain';
    if (vw && vh && fit !== 'fill') {
      const s = fit === 'none' ? 1 : (fit === 'cover' ? Math.max : Math.min)(r.width / vw, r.height / vh);
      w = vw * s; h = vh * s;
    }
    return [r.left + (r.width - w) / 2, r.top + (r.height - h) / 2, w, h, r.left, r.top, r.width, r.height];
  };
  const FORMATS = {BGRA: 1, BGRX: 1, I420: 2, NV12: 3};
  const reply = (status) => {
    const buf = new ArrayBuffer(80);
    new Uint32Array(buf, 0, 2).set([0x4f4b5450, status]);
    tap.ws.send(buf);
  };
  tap.ws = new WebSocket(wsUrl);
  tap.ws.binaryType = 'arraybuffer';
  tap.ws.onmessage = async () => {
    if (tap.ended) return reply(3);
    if (!tap.latest) return reply(2);
    const f = tap.latest.clone();
    try {
      const nativeFormat = f.format === 'I420' || f.format === 'NV12';
      const opts = nativeFormat ? {} : {format: 'BGRA'};
      const buf = new ArrayBuffer(80 + f.allocationSize(opts));
      const layout = await f.copyTo(new Uint8Array(buf, 80), opts);
      const header = new Uint32Array(buf, 0, 11);
      header.set([0x4f4b5450, 1, f.visibleRect.width, f.visibleRect.height,
                  FORMATS[nativeFormat ? f.format : 'BGRA']]);
      layout.forEach((p, i) => { header[5 + i * 2] = p.offset; header[6 + i * 2] = p.stride; });
      new Float32Array(buf, 48, 8).set(contentRect());
      tap.ws.send(buf);
    } catch (e) {
      reply(2);
    } finally {
      f.close();
    }
  };
  tap.ws.onclose = () => { tap.ended = true; };
  // A blocked loopback connection (e.g. Local Network Access not granted) may never open or fail.
  const opened = await new Promise(resolve => {
    tap.ws.onopen = () => resolve(true);
    tap.ws.onerror = () => resolve(false);
    setTimeout(() => resolve(false), 3000);
  });
  if (!opened) { tap.close(); return 'ws-failed'; }
  window.__okWebRtcTap = tap;
  return 'ok';
}'''


class WebRtcFrameReceiver:
    """Loopback WebSocket server for one page tap at a time.

    The browser's WebSocket stack is the throughput limit (about 12 ms per 720p frame), so this
    reads each message straight into one reused buffer instead of using a general WebSocket library.
    """

    def __init__(self):
        self.token = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip('=')
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(4)
        self.url = f'ws://127.0.0.1:{self.listener.getsockname()[1]}/{self.token}'
        self.lock = threading.Lock()
        self.sock = None
        self.buf = bytearray(8 << 20)
        self.closed = False
        threading.Thread(target=self._accept_loop, daemon=True, name='WebRtcFrameReceiver').start()

    @property
    def connected(self):
        return self.sock is not None

    def _accept_loop(self):
        while not self.closed:
            try:
                sock, _ = self.listener.accept()
            except OSError:
                return
            try:
                self._handshake(sock)
            except Exception as e:
                logger.debug(f'WebRTC tap handshake rejected: {e}')
                sock.close()
                continue
            with self.lock:
                old, self.sock = self.sock, sock
            if old is not None:
                old.close()

    def _handshake(self, sock):
        sock.settimeout(5)
        request = b''
        while b'\r\n\r\n' not in request:
            chunk = sock.recv(4096)
            if not chunk or len(request) > 65536:
                raise ConnectionError('incomplete handshake')
            request += chunk
        lines = request.split(b'\r\n')
        if lines[0].split(b' ')[1].lstrip(b'/') != self.token.encode():
            raise ConnectionError('wrong token')
        key = next(line.split(b':', 1)[1].strip() for line in lines
                   if line.lower().startswith(b'sec-websocket-key:'))
        accept = base64.b64encode(hashlib.sha1(key + WS_GUID).digest())
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
        sock.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                     b'Sec-WebSocket-Accept: ' + accept + b'\r\n\r\n')

    def _read_exact(self, sock, view):
        got = 0
        while got < len(view):
            n = sock.recv_into(view[got:])
            if n == 0:
                raise ConnectionError('WebRTC tap disconnected')
            got += n

    def _read_message(self, sock):
        total = 0
        small = bytearray(8)
        while True:
            self._read_exact(sock, memoryview(small)[:2])
            first, second = small[0], small[1]
            length = second & 0x7f
            if length == 126:
                self._read_exact(sock, memoryview(small)[:2])
                length = struct.unpack('>H', small[:2])[0]
            elif length == 127:
                self._read_exact(sock, memoryview(small))
                length = struct.unpack('>Q', small)[0]
            mask = bytearray(4)
            if second & 0x80:
                self._read_exact(sock, memoryview(mask))
            opcode = first & 0x0f
            if opcode == 0x8:
                raise ConnectionError('WebRTC tap closed')
            if opcode in (0x9, 0xA):
                self._read_exact(sock, memoryview(bytearray(length)))
                continue
            if total + length > len(self.buf):
                self.buf.extend(bytearray(total + length - len(self.buf)))
            self._read_exact(sock, memoryview(self.buf)[total:total + length])
            if second & 0x80:
                unmask(self.buf, total, length, mask)
            total += length
            if first & 0x80:
                return memoryview(self.buf)[:total]

    def request(self, timeout=2.0):
        """Ask the page for its newest frame. Returns the raw message or None without a tap."""
        with self.lock:
            sock = self.sock
            if sock is None:
                return None
            try:
                sock.settimeout(timeout)
                sock.sendall(b'\x81\x00')  # empty text frame; servers must not mask
                return self._read_message(sock)
            except (OSError, ConnectionError) as e:
                logger.info(f'WebRTC tap lost: {e}')
                sock.close()
                if self.sock is sock:
                    self.sock = None
                return None

    def disconnect(self):
        with self.lock:
            if self.sock is not None:
                self.sock.close()
                self.sock = None

    def close(self):
        self.closed = True
        try:
            self.listener.close()
        except OSError:
            pass
        with self.lock:
            if self.sock is not None:
                self.sock.close()
                self.sock = None


def unmask(buf, start, length, mask):
    data = np.frombuffer(buf, np.uint8, length, start)
    words = length // 4
    if words:
        data[:words * 4].view(np.uint32)[:] ^= np.frombuffer(bytes(mask), np.uint32)[0]
    for i in range(words * 4, length):
        data[i] ^= mask[i % 4]


def parse_message(message):
    """Return (status, frame_bgr, content_rect, element_rect) from a tap message."""
    header = np.frombuffer(message, np.uint32, 12)
    if len(message) < HEADER_SIZE or header[0] != MAGIC:
        return STATUS_NO_FRAME, None, None, None
    status = int(header[1])
    if status != STATUS_FRAME:
        return status, None, None, None
    w, h, fmt = int(header[2]), int(header[3]), int(header[4])
    offsets = [int(header[5 + i * 2]) + HEADER_SIZE for i in range(3)]
    strides = [int(header[6 + i * 2]) for i in range(3)]
    rects = np.frombuffer(message, np.float32, 8, 48)
    return status, to_bgr(message, w, h, fmt, offsets, strides), tuple(rects[:4]), tuple(rects[4:])


def to_bgr(message, w, h, fmt, offsets, strides):
    def plane(i, rows, row_bytes):
        return np.frombuffer(message, np.uint8, rows * strides[i], offsets[i]).reshape(rows, strides[i])[:, :row_bytes]

    if fmt == FORMAT_BGRA:
        return cv2.cvtColor(plane(0, h, w * 4).reshape(h, w, 4), cv2.COLOR_BGRA2BGR)
    if fmt == FORMAT_I420:
        cw, ch = (w + 1) // 2, (h + 1) // 2
        if w % 2 == 0 and h % 2 == 0 and strides == [w, cw, cw] and offsets[1] == offsets[0] + w * h \
                and offsets[2] == offsets[1] + cw * ch:
            yuv = np.frombuffer(message, np.uint8, w * h * 3 // 2, offsets[0]).reshape(h * 3 // 2, w)
        else:
            u = np.ascontiguousarray(plane(1, ch, cw))[:h // 2, :w // 2]
            v = np.ascontiguousarray(plane(2, ch, cw))[:h // 2, :w // 2]
            h2, w2 = h // 2 * 2, w // 2 * 2
            yuv = np.concatenate([plane(0, h2, w2), u.reshape(-1, w2), v.reshape(-1, w2)])
        return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
    if fmt == FORMAT_NV12:
        h2, w2 = h // 2 * 2, w // 2 * 2
        y = plane(0, h2, w2)
        uv = plane(1, h2 // 2, w2).reshape(h2 // 2, w2 // 2, 2)
        return cv2.cvtColorTwoPlane(y, uv, cv2.COLOR_YUV2BGR_NV12)
    raise ValueError(f'unsupported WebRTC frame format {fmt}')


def place_in_viewport(frame, content_rect, element_rect, viewport_size, offset=(0, 0)):
    """Draw the video frame where the page shows it, on a black viewport-sized image.

    content_rect is where the whole video content is drawn (it can extend past the element with
    object-fit: cover); element_rect clips it. Both are CSS pixels of the frame's viewport;
    offset moves them into the top-level page (iframes).
    """
    vw, vh = viewport_size
    fh, fw = frame.shape[:2]
    cx, cy, cw, ch = content_rect
    cx, cy = cx + offset[0], cy + offset[1]
    ex, ey, ew, eh = element_rect
    ex, ey = ex + offset[0], ey + offset[1]
    if cw <= 0 or ch <= 0:
        return None
    if (fw, fh) == (vw, vh) and abs(cx) < 0.5 and abs(cy) < 0.5 and abs(cw - vw) < 0.5 and abs(ch - vh) < 0.5:
        return frame
    left, top = max(cx, ex, 0), max(cy, ey, 0)
    right, bottom = min(cx + cw, ex + ew, vw), min(cy + ch, ey + eh, vh)
    x0, y0, x1, y1 = int(round(left)), int(round(top)), int(round(right)), int(round(bottom))
    if x1 <= x0 or y1 <= y0:
        return None
    sx, sy = fw / cw, fh / ch
    src = frame[max(0, int((y0 - cy) * sy)):min(fh, int(np.ceil((y1 - cy) * sy))),
                max(0, int((x0 - cx) * sx)):min(fw, int(np.ceil((x1 - cx) * sx)))]
    if src.size == 0:
        return None
    out = np.zeros((vh, vw, 3), np.uint8)
    if src.shape[1] == x1 - x0 and src.shape[0] == y1 - y0:
        out[y0:y1, x0:x1] = src
    else:
        shrinking = src.shape[1] > x1 - x0
        out[y0:y1, x0:x1] = cv2.resize(src, (x1 - x0, y1 - y0),
                                       interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR)
    return out
