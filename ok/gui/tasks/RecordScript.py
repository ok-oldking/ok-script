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
                return x - (hw.x + hw.real_x_offset), y - (hw.y + hw.real_y_offset)
            if not self.target_hwnd:
                return x, y
            # Fallback using win32gui for non-HwndWindow cases
            # ClientToScreen with (0,0) gives the top-left of the content area in screen coordinates
            client_pos = win32gui.ClientToScreen(self.target_hwnd, (0, 0))
            return x - client_pos[0], y - client_pos[1]
        except:
            return x, y

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
        if any(e['type'] == 'key_down' and e['key'] == self._key_to_str(key) for e in self.events):
            return
            
        self.events.append({'type': 'key_down', 'key': self._key_to_str(key), 'time': current_time, 'latency': latency})
        self.last_event_time = current_time

    def on_release(self, key):
        if not self.is_recording or not self.is_active:
            return
            
        current_time = time.time()
        key_str = self._key_to_str(key)
        
        for i in range(len(self.events) - 1, -1, -1):
            e = self.events[i]
            if e['type'] == 'key_down' and e['key'] == key_str:
                e['type'] = 'key_press'
                e['down_time'] = current_time - e['time']
                break
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
                    init_lines.append(f"        'interaction': '{interaction}',")
                if capture:
                    init_lines.append(f"        'capture_method': '{capture}',")
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
                    init_lines.append(f"        'capture_method': '{capture}',")
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
                    init_lines.append(f"        'interaction': '{interaction}',")
                if capture:
                    init_lines.append(f"        'capture_method': '{capture}',")
                if resolution and resolution[0] > 0 and resolution[1] > 0:
                    init_lines.append(f"        # 'resolution': ({resolution[0]}, {resolution[1]}),")
                init_lines.append(f"    }}")
            init_lines.append("}")
            init_lines.append("")

        for e in self.events:
            if 'latency' in e and e['latency'] > 0.1:
                lines.append(f"self.sleep({e['latency']:.2f}) # wait for {e['latency']:.2f}s")
                
            if e['type'] == 'click':
                down_time = e.get('down_time', 0.05)
                line = f"self.click({int(e['x'])}, {int(e['y'])}"
                if e["button"] != "left":
                    line += f', key="{e["button"]}"'
                line += f', down_time={down_time:.2f}'
                line += f") # {e['button']} click at ({int(e['x'])}, {int(e['y'])})"
                lines.append(line)
            elif e['type'] == 'key_press':
                down_time = e.get('down_time', 0.05)
                line = f"self.send_key('{e['key']}'"
                line += f", down_time={down_time:.2f}"
                line += f") # press key '{e['key']}'"
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
