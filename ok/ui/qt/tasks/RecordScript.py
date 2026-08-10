import time

import win32gui
from pynput import mouse, keyboard

from ok import og
from ok.gui.Communicate import communicate
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

class Recorder:
    def __init__(self):
        self.is_recording = False
        self.mouse_listener = None
        self.keyboard_listener = None
        self.events = []
        self.last_event_time = 0
        self.target_hwnd = None
        self.target_title = None
        self.is_active = False
        self.inactive_start_time = 0

    def on_window(self, visible, *args):
        if self.is_recording:
            if visible != self.is_active:
                self.is_active = visible
                if visible:
                    from ok.gui.util.Alert import alert_info
                    alert_info("Target window active: Recording resumed", tray=True)
                    if not self.target_hwnd and getattr(og.device_manager, 'hwnd_window', None):
                        self.target_hwnd = og.device_manager.hwnd_window.hwnd
                    if self.inactive_start_time > 0:
                        self.last_event_time += (time.time() - self.inactive_start_time)
                        self.inactive_start_time = 0
                else:
                    from ok.gui.util.Alert import alert_info
                    alert_info("Target window inactive: Recording paused", tray=True)
                    self.drop_pending_inputs()
                    self.inactive_start_time = time.time()

    def start(self, target_title):
        self.is_recording = True
        self.events = []
        self.last_event_time = time.time()
        self.target_title = target_title
        if getattr(og.device_manager, 'hwnd_window', None):
            self.target_hwnd = og.device_manager.hwnd_window.hwnd
        else:
            self.target_hwnd = None
        self.is_active = False
        self.inactive_start_time = time.time()
        
        self.mouse_listener = mouse.Listener(
            on_click=self.on_click
        )
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.mouse_listener.start()
        self.keyboard_listener.start()
        
        # Monitor visibility via communicate.window instead of win32gui polling
        communicate.window.connect(self.on_window)

    def stop(self):
        self.is_recording = False
        self.drop_pending_inputs()
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            
        try:
            communicate.window.disconnect(self.on_window)
        except Exception:
            pass
            
        return self.generate_code()

    def get_relative_coords(self, x, y):
        try:
            if getattr(og.device_manager, 'hwnd_window', None) and og.device_manager.hwnd_window.hwnd == self.target_hwnd:
                hw = og.device_manager.hwnd_window
                rel_x = x - (hw.x + hw.real_x_offset)
                rel_y = y - (hw.y + hw.real_y_offset)
                width = hw.real_width or hw.width
                height = hw.real_height or hw.height
                return self.normalize_coords(rel_x, rel_y, width, height)
            if self.target_hwnd:
                # ClientToScreen with (0,0) gives the top-left of the content area in screen coordinates
                client_pos = win32gui.ClientToScreen(self.target_hwnd, (0, 0))
                left, top, right, bottom = win32gui.GetClientRect(self.target_hwnd)
                width = right - left
                height = bottom - top
                return self.normalize_coords(x - client_pos[0], y - client_pos[1], width, height)

            return self.normalize_coords(x, y, getattr(og.device_manager, 'width', 0),
                                         getattr(og.device_manager, 'height', 0))
        except:
            try:
                return self.normalize_coords(x, y, getattr(og.device_manager, 'width', 0),
                                             getattr(og.device_manager, 'height', 0))
            except:
                return x, y

    def normalize_coords(self, x, y, width, height):
        if width > 0 and height > 0:
            return max(0, min(1, x / width)), max(0, min(1, y / height))
        return x, y

    def format_coord(self, value):
        return f"{value:.4f}".rstrip('0').rstrip('.')

    def format_literal(self, value):
        return repr(value)

    def drop_pending_inputs(self):
        self.events = [
            e for index, e in enumerate(self.events)
            if e['type'] != 'mouse_down' and
               (e['type'] != 'key_down' or self.has_key_up_after(index, e['key']))
        ]

    def has_key_up_after(self, index, key):
        return any(e['type'] == 'key_up' and e['key'] == key for e in self.events[index + 1:])

    def find_pending_key_down_index(self, key):
        for i in range(len(self.events) - 1, -1, -1):
            e = self.events[i]
            if e['type'] == 'key_down' and e['key'] == key and not self.has_key_up_after(i, key):
                return i
        return None

    def on_click(self, x, y, button, pressed):
        if not self.is_recording or not self.is_active:
            return
            
        current_time = time.time()
        latency = current_time - self.last_event_time
        
        rel_x, rel_y = self.get_relative_coords(x, y)
        
        btn_str = "left"
        if button == mouse.Button.right:
            btn_str = "right"
        elif button == mouse.Button.middle:
            btn_str = "middle"
            
        if pressed:
            self.events.append({'type': 'mouse_down', 'x': rel_x, 'y': rel_y, 'button': btn_str, 'time': current_time, 'latency': latency})
        else:
            # Find the corresponding mouse_down
            for i in range(len(self.events) - 1, -1, -1):
                e = self.events[i]
                if e['type'] == 'mouse_down' and e['button'] == btn_str:
                    e['type'] = 'click'
                    e['down_time'] = current_time - e['time']
                    break
        self.last_event_time = current_time

    def on_press(self, key):
        if not self.is_recording or not self.is_active:
            return
        
        current_time = time.time()
        latency = current_time - self.last_event_time
        
        # Avoid recording repeating keys if already pressed
        key_str = self._key_to_str(key)
        if self.find_pending_key_down_index(key_str) is not None:
            return
            
        self.events.append({'type': 'key_down', 'key': key_str, 'time': current_time, 'latency': latency})
        self.last_event_time = current_time

    def on_release(self, key):
        if not self.is_recording or not self.is_active:
            return
            
        current_time = time.time()
        key_str = self._key_to_str(key)
        
        i = self.find_pending_key_down_index(key_str)
        if i is not None:
            e = self.events[i]
            e['down_time'] = current_time - e['time']
            if i == len(self.events) - 1:
                e['type'] = 'key_press'
            else:
                self.events.append({'type': 'key_up', 'key': key_str, 'time': current_time,
                                    'latency': current_time - self.last_event_time})
        self.last_event_time = current_time

    def _key_to_str(self, key):
        if hasattr(key, 'char') and key.char:
            return key.char
        elif hasattr(key, 'name'):
            return key.name
        return str(key).replace("'", "")

    def generate_code(self):
        init_lines = []
        lines = []
        from ok import og
        device = og.device_manager.get_preferred_device()
        if device is not None:
            dm = og.device_manager
            current_device_type = device.get('device')
            interaction = dm.config.get('interaction')
            capture = dm.config.get('capture')
            resolution = (dm.width, dm.height)
            
            init_lines.append("self.capture_config = {")
            if current_device_type == 'windows':
                exes = dm.windows_capture_config.get('exe')
                if not exes and device.get('exe'):
                    exes = [device.get('exe')]
                if isinstance(exes, str):
                    exes = [exes]
                exes_str = repr(exes) if len(exes) > 1 else repr(exes[0]) if exes else "''"
                
                hwnd_class = dm.windows_capture_config.get('hwnd_class')
                if not hwnd_class and device.get('real_hwnd'):
                    try:
                        hwnd_class = win32gui.GetClassName(device.get('real_hwnd'))
                    except Exception:
                        pass
                
                init_lines.append(f"    'windows': {{")
                if exes:
                    init_lines.append(f"        'exe': {exes_str},")
                if hwnd_class:
                    init_lines.append(f"        'hwnd_class': {repr(hwnd_class)},")
                if interaction:
                    init_lines.append(f"        'interaction': {self.format_literal(interaction)},")
                if capture:
                    init_lines.append(f"        'capture_method': {self.format_literal(capture)},")
                if resolution and resolution[0] > 0 and resolution[1] > 0:
                    init_lines.append(f"        # 'resolution': ({resolution[0]}, {resolution[1]}),")
                init_lines.append(f"    }}")
                
            elif current_device_type == 'adb':
                # Get the current foreground package from the ADB device
                packages = []
                try:
                    if dm.device is not None:
                        front = dm.device.app_current()
                        if front and front.package:
                            packages = [front.package]
                except Exception as e:
                    logger.error(f'Failed to get foreground package: {e}')
                if not packages:
                    packages = dm.packages or []
                packages_str = repr(packages) if packages else "[]"
                init_lines.append(f"    'adb': {{")
                init_lines.append(f"        'packages': {packages_str},")
                init_lines.append(f"        'interaction': 'adb',")
                if capture:
                    init_lines.append(f"        'capture_method': {self.format_literal(capture)},")
                if resolution and resolution[0] > 0 and resolution[1] > 0:
                    init_lines.append(f"        # 'resolution': ({resolution[0]}, {resolution[1]}),")
                init_lines.append(f"    }}")
                
            elif current_device_type == 'browser':
                url = repr(dm.browser_config.get('url', ''))
                nick = repr(dm.browser_config.get('nick', ''))
                init_lines.append(f"    'browser': {{")
                if dm.browser_config.get('url'):
                    init_lines.append(f"        'url': {url},")
                if dm.browser_config.get('nick'):
                    init_lines.append(f"        'nick': {nick},")
                if interaction:
                    init_lines.append(f"        'interaction': {self.format_literal(interaction)},")
                if capture:
                    init_lines.append(f"        'capture_method': {self.format_literal(capture)},")
                if resolution and resolution[0] > 0 and resolution[1] > 0:
                    init_lines.append(f"        # 'resolution': ({resolution[0]}, {resolution[1]}),")
                init_lines.append(f"    }}")
            init_lines.append("}")
            init_lines.append("")

        action_events = [e for e in self.events if e['type'] in ('click', 'key_press', 'key_down', 'key_up')]
        for index, e in enumerate(action_events):
            after_sleep = 0
            if index + 1 < len(action_events):
                after_sleep = action_events[index + 1].get('latency', 0)

            if e['type'] == 'click':
                down_time = e.get('down_time', 0.05)
                line = f"self.click_relative({self.format_coord(e['x'])}, {self.format_coord(e['y'])}"
                if e["button"] != "left":
                    line += f', key="{e["button"]}"'
                line += f', down_time={down_time:.2f}'
                if after_sleep > 0.1:
                    line += f', after_sleep={after_sleep:.2f}'
                line += f") # {e['button']} click at ({self.format_coord(e['x'])}, {self.format_coord(e['y'])})"
                lines.append(line)
            elif e['type'] == 'key_press':
                down_time = e.get('down_time', 0.05)
                key = self.format_literal(e['key'])
                line = f"self.send_key({key}"
                line += f", down_time={down_time:.2f}"
                if after_sleep > 0.1:
                    line += f", after_sleep={after_sleep:.2f}"
                line += f") # press key {key}"
                lines.append(line)
            elif e['type'] == 'key_down':
                key = self.format_literal(e['key'])
                line = f"self.send_key_down({key}"
                if after_sleep > 0.1:
                    line += f", after_sleep={after_sleep:.2f}"
                line += f") # key down {key}"
                lines.append(line)
            elif e['type'] == 'key_up':
                key = self.format_literal(e['key'])
                line = f"self.send_key_up({key}"
                if after_sleep > 0.1:
                    line += f", after_sleep={after_sleep:.2f}"
                line += f") # key up {key}"
                lines.append(line)
                
        if not lines:
            run_code = "pass"
        else:
            run_code = "\n".join(lines)
            
        if not init_lines:
            init_code = ""
        else:
            init_code = "\n".join(init_lines)
            
        return init_code, run_code

recorder = Recorder()
