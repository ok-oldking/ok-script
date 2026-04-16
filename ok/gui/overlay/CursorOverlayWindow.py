import win32api
import win32con
import win32gui
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QGuiApplication
from PySide6.QtWidgets import QWidget

from ok import Logger

logger = Logger.get_logger(__name__)


class CursorOverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Set translucent background
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Set window flag to handle mouse events properly with translucent background
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)

        self.target_hwnd = 0
        self.capture_mode = False
        self.recorded_points = []
        self.cursor_pos = (0, 0)
        self.prev_alt_state = 0
        self.prev_rbutton_state = 0
        self.prev_mbutton_state = 0
        
        self.text_position = 'left'

        self.notification_text = ""
        self.notification_timer = QTimer(self)
        self.notification_timer.setSingleShot(True)
        self.notification_timer.timeout.connect(self.clear_notification)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_state)
        self.poll_timer.start(16)  # ~60fps

    def clear_notification(self):
        self.notification_text = ""
        self.update()

    def show_notification(self, text):
        self.notification_text = text
        self.notification_timer.start(5000)
        self.update()

    def update_overlay(self, visible):
        logger.debug(f'update_overlay: {visible}')
        if visible:
            screen_geo = QGuiApplication.primaryScreen().virtualGeometry()
            self.setGeometry(screen_geo)
        if visible and not self.isVisible():
            self.show()
            return
        if not visible and self.isVisible():
            self.hide()
            self.capture_mode = False
            self.recorded_points = []

    def poll_state(self):
        if not self.isVisible():
            return

        # 1. Update active window based on user focus
        fg_hwnd = win32gui.GetForegroundWindow()
        if fg_hwnd and fg_hwnd != int(self.winId()):
            try:
                cls = win32gui.GetClassName(fg_hwnd)
                if cls not in ['Progman', 'WorkerW', 'Shell_TrayWnd']:
                    self.target_hwnd = fg_hwnd
            except Exception:
                pass

        # Ensure the overlay is always topmost, counteracting fullscreen exclusivity
        win32gui.SetWindowPos(int(self.winId()), win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

        # 2. Check Shift key for capture mode toggle
        shift_state = win32api.GetAsyncKeyState(win32con.VK_SHIFT)
        if (shift_state & 0x8000) and not (self.prev_alt_state & 0x8000):
            self.toggle_capture_mode()
        self.prev_alt_state = shift_state

        # 3. Update cursor pos
        cursor_pos = win32api.GetCursorPos()
        self.cursor_pos = cursor_pos

        # 4. Check mouse clicks if in capture mode
        if self.capture_mode:
            rbutton_state = win32api.GetAsyncKeyState(win32con.VK_RBUTTON)
            mbutton_state = win32api.GetAsyncKeyState(win32con.VK_MBUTTON)

            clicked = False
            if (rbutton_state & 0x8000) and not (self.prev_rbutton_state & 0x8000): clicked = True
            if (mbutton_state & 0x8000) and not (self.prev_mbutton_state & 0x8000): clicked = True

            if clicked:
                self.record_point(self.cursor_pos)

            self.prev_rbutton_state = rbutton_state
            self.prev_mbutton_state = mbutton_state

        self.update()

    def toggle_capture_mode(self):
        if not self.capture_mode:
            # Enter capture mode
            self.capture_mode = True
            self.recorded_points = []
        else:
            # Manual exit capture mode
            if self.recorded_points:
                self.finish_capture()
            else:
                self.capture_mode = False

    def record_point(self, pos):
        if pos not in self.recorded_points:
            self.recorded_points.append(pos)
        if len(self.recorded_points) >= 2:
            self.finish_capture()

    def finish_capture(self):
        points = list(self.recorded_points)
        self.capture_mode = False
        self.recorded_points = []

        if not points:
            return

        caps_on = win32api.GetKeyState(win32con.VK_CAPITAL) & 1

        try:
            rect = win32gui.GetClientRect(self.target_hwnd)
            pt_tl = win32gui.ClientToScreen(self.target_hwnd, (0, 0))
            pt_br = win32gui.ClientToScreen(self.target_hwnd, (rect[2], rect[3]))
            client_x, client_y = pt_tl
            client_w = pt_br[0] - pt_tl[0]
            client_h = pt_br[1] - pt_tl[1]

            if client_w <= 0 or client_h <= 0:
                self.show_notification(self.tr("Target client rect is invalid"))
                return
        except Exception as e:
            logger.error(f"Cannot get client rect: {e}")
            return

        if not caps_on:
            # Coordinate capture
            res = []
            for px, py in points:
                px_prop = (px - client_x) / client_w
                py_prop = (py - client_y) / client_h
                res.append(f"{px_prop:.4f}, {py_prop:.4f}")
            clipboard_text = ", ".join(res)
            QGuiApplication.clipboard().setText(clipboard_text)
            self.show_notification(self.tr("Copied Coordinates:\n{clipboard_text}").format(clipboard_text=clipboard_text))
        else:
            # Pixel Color capture
            self.hide()
            # Wait briefly to let the overlay disappear so we don't capture its green crosshair
            QTimer.singleShot(100, lambda: self._do_pixel_capture(points))

    def _do_pixel_capture(self, points):
        try:
            import numpy as np

            # Using bitblt approach to get multimonitor desktop pixel
            # Get dimensions of the virtual screen bounding all monitors
            left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
            top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
            width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
            height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)

            from ok.device.capture import capture_by_bitblt, BitBltCtxDummy
            ctx = BitBltCtxDummy()
            desktop_hwnd = win32gui.GetDesktopWindow()
            img_bgra = capture_by_bitblt(ctx, desktop_hwnd, width, height, left, top, False)

            if img_bgra is None:
                self.show_notification(self.tr("Failed to capture screen image."))
                return

            arr_rgb = img_bgra[:, :, :3][:, :, ::-1]  # from BGRA to RGB

            if len(points) == 1:
                px, py = points[0]
                idx_x, idx_y = px - left, py - top
                if 0 <= idx_y < arr_rgb.shape[0] and 0 <= idx_x < arr_rgb.shape[1]:
                    r, g, b = arr_rgb[idx_y, idx_x]
                    # To follow the identical format for 1 point
                    clipboard_text = f"color = {{\n    \"r\": ({int(r)}, {int(r)}),\n    \"g\": ({int(g)}, {int(g)}),\n    \"b\": ({int(b)}, {int(b)}),\n}}"
                else:
                    clipboard_text = self.tr("Point out of bounds")
            else:
                p1, p2 = points
                idx_x1, idx_y1 = p1[0] - left, p1[1] - top
                idx_x2, idx_y2 = p2[0] - left, p2[1] - top

                x1, x2 = min(idx_x1, idx_x2), max(idx_x1, idx_x2)
                y1, y2 = min(idx_y1, idx_y2), max(idx_y1, idx_y2)

                x1 = max(0, x1); x2 = min(arr_rgb.shape[1] - 1, x2)
                y1 = max(0, y1); y2 = min(arr_rgb.shape[0] - 1, y2)

                roi = arr_rgb[y1:y2+1, x1:x2+1]
                if roi.size > 0:
                    mean = np.mean(roi, axis=(0, 1))
                    std = np.std(roi, axis=(0, 1))

                    lower = np.clip(mean - 2 * std, 0, 255).astype(int)
                    upper = np.clip(mean + 2 * std, 0, 255).astype(int)

                    r_l, g_l, b_l = lower
                    r_h, g_h, b_h = upper
                    clipboard_text = f"color = {{\n    \"r\": ({int(r_l)}, {int(r_h)}),\n    \"g\": ({int(g_l)}, {int(g_h)}),\n    \"b\": ({int(b_l)}, {int(b_h)}),\n}}"
                else:
                    clipboard_text = self.tr("Empty region selected")

            if clipboard_text and not clipboard_text.startswith("Point") and not clipboard_text.startswith("Empty"):
                QGuiApplication.clipboard().setText(clipboard_text)
                self.show_notification(self.tr("Copied Color:\n{clipboard_text}").format(clipboard_text=clipboard_text))
            else:
                self.show_notification(self.tr("Pixel capture failed: {clipboard_text}").format(clipboard_text=clipboard_text))
        except Exception as e:
            logger.error(f"Error checking pixels: {e}")
        finally:
            self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.transparent)

        if not self.target_hwnd:
            return

        try:
            rect = win32gui.GetClientRect(self.target_hwnd)
            pt_tl = win32gui.ClientToScreen(self.target_hwnd, (0, 0))
            pt_br = win32gui.ClientToScreen(self.target_hwnd, (rect[2], rect[3]))
            client_x, client_y = pt_tl
            client_w = pt_br[0] - pt_tl[0]
            client_h = pt_br[1] - pt_tl[1]
        except Exception:
            return

        ratio = self.screen().devicePixelRatio()
        screen_geo = self.geometry()
        x = (client_x / ratio) - screen_geo.x()
        y = (client_y / ratio) - screen_geo.y()
        client_rect = QRect(x, y, client_w / ratio, client_h / ratio)

        # Draw red border
        pen_border = QPen(Qt.red, 2)
        pen_border.setStyle(Qt.DashLine) if not self.capture_mode else pen_border.setStyle(Qt.SolidLine)
        painter.setPen(pen_border)
        painter.drawRect(client_rect)

        # Determine mode text and color
        caps_on = win32api.GetKeyState(win32con.VK_CAPITAL) & 1
        if caps_on:
            mode_text = self.tr("Pixel Color")
            mode_color = QColor(0, 255, 255) # Cyan
        else:
            mode_text = self.tr("Coordinates")
            mode_color = QColor(0, 255, 0) # Green

        crosshair_color = QColor(mode_color.red(), mode_color.green(), mode_color.blue(), 150)

        painter.setFont(QFont("Arial", 12, QFont.Bold))
        title = win32gui.GetWindowText(self.target_hwnd)
        if len(title) > 30: title = title[:30] + "..."

        texts = [
            (self.tr("Target: {title}").format(title=title), Qt.yellow),
            (self.tr("Shift: Enter/Exit Capture Mode"), Qt.yellow)
        ]

        if self.capture_mode:
            texts.append((self.tr("Mode: {mode_text} (Capslock to switch)").format(mode_text=mode_text), mode_color))
            texts.append((self.tr("Right/Middle click to mark [Max 2]"), Qt.yellow))
            if self.recorded_points:
                texts.append((self.tr("Recorded: {count}").format(count=len(self.recorded_points)), Qt.yellow))

        # Calculate bounding box for text
        fm = painter.fontMetrics()
        max_w = max([fm.horizontalAdvance(t[0]) for t in texts]) if texts else 0
        texts_h = len(texts) * 20

        noti_rect_bound = QRect()
        if self.notification_text:
            noti_rect_bound = painter.boundingRect(QRect(0, 0, 600, 300), Qt.AlignLeft | Qt.AlignTop, self.notification_text)
            max_w = max(max_w, noti_rect_bound.width())

        bg_width = max_w + 30
        bg_height = texts_h + (noti_rect_bound.height() + 10 if self.notification_text else 0) + 15

        base_x = (client_x / ratio) - screen_geo.x()
        base_y = (client_y / ratio) - screen_geo.y()
        client_w_logical = client_w / ratio

        def get_clamped_x(pos_mode):
            proposed_x = base_x + 10 if pos_mode == 'left' else base_x + client_w_logical - bg_width - 10
            if proposed_x < 10: proposed_x = 10
            if proposed_x + bg_width + 10 > screen_geo.width(): proposed_x = screen_geo.width() - bg_width - 10
            return proposed_x

        text_x = get_clamped_x(self.text_position)
        text_y = base_y + 10
        if text_y < 10: text_y = 10
        if text_y + bg_height + 10 > screen_geo.height(): text_y = screen_geo.height() - bg_height - 10

        bg_rect = QRect(int(text_x), int(text_y), int(bg_width), int(bg_height))

        # Check collision with mouse
        cx_logical = self.cursor_pos[0] / ratio
        cy_logical = self.cursor_pos[1] / ratio
        mx = cx_logical - screen_geo.x()
        my = cy_logical - screen_geo.y()

        hover_rect = bg_rect.adjusted(-10, -10, 10, 10)
        if hover_rect.contains(int(mx), int(my)):
            self.text_position = 'right' if self.text_position == 'left' else 'left'
            text_x = get_clamped_x(self.text_position)
            bg_rect = QRect(int(text_x), int(text_y), int(bg_width), int(bg_height))

        # Draw Background
        painter.fillRect(bg_rect, QColor(0, 0, 0, 180))

        # Draw Texts
        draw_x, draw_y = text_x + 15, text_y + 20
        for t_str, t_color in texts:
            # Shadow
            painter.setPen(QPen(Qt.black, 1))
            painter.drawText(int(draw_x + 1), int(draw_y + 1), t_str)
            # Text
            painter.setPen(QPen(t_color, 1))
            painter.drawText(int(draw_x), int(draw_y), t_str)
            draw_y += 20

        # Draw notification if any
        if self.notification_text:
            noti_y = draw_y + 5
            painter.setPen(QPen(Qt.black, 1))
            painter.drawText(QRect(int(draw_x + 1), int(noti_y + 1), 600, 300), Qt.AlignLeft | Qt.AlignTop, self.notification_text)
            painter.setPen(QPen(Qt.green, 1))
            painter.drawText(QRect(int(draw_x), int(noti_y), 600, 300), Qt.AlignLeft | Qt.AlignTop, self.notification_text)

        # Draw crosshair if capture mode
        if self.capture_mode:
            wx = cx_logical - screen_geo.x()
            wy = cy_logical - screen_geo.y()

            painter.setPen(QPen(crosshair_color, max(1, int(1/ratio))))
            painter.drawLine(0, wy, screen_geo.width(), wy)
            painter.drawLine(wx, 0, wx, screen_geo.height())

            for px, py in self.recorded_points:
                px_w = (px / ratio) - screen_geo.x()
                py_w = (py / ratio) - screen_geo.y()
                painter.setPen(QPen(Qt.red, 2))
                painter.drawLine(px_w - 6, py_w, px_w + 6, py_w)
                painter.drawLine(px_w, py_w - 6, px_w, py_w + 6)
