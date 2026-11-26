"""The agent's work inside the child session. Started by ``agent.py``."""

import ctypes
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback

from ok.child_session import protocol, win_api

AGENT_VERSION = 1
STARTUP_CLEANUP_SECONDS = 180
LOG_MAX_BYTES = 2 * 1024 * 1024


class AgentLog:
    def __init__(self, project_dir):
        folder = os.path.join(project_dir, 'logs')
        os.makedirs(folder, exist_ok=True)
        self.path = os.path.join(folder, 'child_session_agent.log')
        self._lock = threading.Lock()
        try:
            if os.path.getsize(self.path) > LOG_MAX_BYTES:
                os.replace(self.path, self.path + '.1')
        except OSError:
            pass

    def __call__(self, *parts):
        line = time.strftime('%Y-%m-%d %H:%M:%S ') + ' '.join(str(p) for p in parts)
        with self._lock:
            try:
                with open(self.path, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
            except OSError:
                pass


class GameWindow:
    """Finds the game window in this session and gives WGC the window object it needs."""

    def __init__(self, exit_event):
        self.app_exit_event = exit_event
        self.hwnds = None
        self.exe_names = []
        self.hwnd_class = None
        self.title = None
        self._hwnd = 0

    def configure(self, spec):
        exe = spec.get('exe') or []
        self.exe_names = [e.lower() for e in ([exe] if isinstance(exe, str) else exe)]
        self.hwnd_class = spec.get('hwnd_class')
        self.title = spec.get('title')
        self._hwnd = 0

    def _matches(self, hwnd):
        import win32gui
        import win32process
        if not win32gui.IsWindowVisible(hwnd):
            return False
        if self.hwnd_class and win32gui.GetClassName(hwnd) != self.hwnd_class:
            return False
        if self.title and self.title not in win32gui.GetWindowText(hwnd):
            return False
        if self.exe_names:
            import psutil
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if psutil.Process(pid).name().lower() not in self.exe_names:
                    return False
            except Exception:
                return False
        return bool(self.exe_names or self.hwnd_class or self.title)

    @property
    def hwnd(self):
        import win32gui
        if self._hwnd and win32gui.IsWindow(self._hwnd) and win32gui.IsWindowVisible(self._hwnd):
            return self._hwnd
        best, best_area = 0, 0
        found = []
        win32gui.EnumWindows(lambda h, _: found.append(h), None)
        for h in found:
            if self._matches(h):
                left, top, right, bottom = win32gui.GetClientRect(h)
                area = (right - left) * (bottom - top)
                if area > best_area:
                    best, best_area = h, area
        self._hwnd = best
        return best

    @property
    def exists(self):
        return bool(self.hwnd)

    def client_size(self):
        import win32gui
        hwnd = self.hwnd
        if not hwnd:
            return 0, 0
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        return right - left, bottom - top

    @property
    def width(self):
        return self.client_size()[0]

    @property
    def height(self):
        return self.client_size()[1]

    @property
    def capture_target_signature(self):
        return (self.hwnd,) + self.client_size()


class Agent:
    def __init__(self, project_dir, log):
        self.project_dir = project_dir
        self.log = log
        self.exit_event = threading.Event()
        self.window = GameWindow(self.exit_event)
        self.token = secrets.token_hex(16)
        self.session = win_api.current_session_id()
        self.elevated = win_api.is_elevated()
        self._capture = None
        self._capture_hwnd = 0
        self._capture_lock = threading.Lock()
        from ok.child_session.agent_input import Input
        self.input = Input(log)
        config = protocol.read_json(protocol.config_file(project_dir)) or {}
        self.window.configure(config.get('window') or {})
        self.close_apps = [name.lower() for name in config.get('close_apps') or []]

    # --- capture --------------------------------------------------------------

    def frame(self):
        with self._capture_lock:
            if self._capture is None or self._capture_hwnd != self.window.hwnd:
                if self._capture is not None:
                    self._capture.close()
                from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod
                self._capture = WindowsGraphicsCaptureMethod(self.window)
                self._capture_hwnd = self.window.hwnd
            return self._capture.do_get_frame_wait(2)

    # --- windows in this session ---------------------------------------------

    def top_windows(self, limit=12):
        import win32gui
        result = []

        def collect(h, _):
            if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h):
                result.append({'hwnd': h, 'class': win32gui.GetClassName(h), 'title': win32gui.GetWindowText(h),
                               'rect': list(win32gui.GetWindowRect(h))})
        win32gui.EnumWindows(collect, None)
        return result[:limit]

    def window_info(self):
        import win32gui
        hwnd = self.window.hwnd
        info = {'session': self.session, 'elevated': self.elevated, 'hwnd': hwnd, 'exists': bool(hwnd)}
        if hwnd:
            width, height = self.window.client_size()
            foreground = win32gui.GetForegroundWindow()
            info.update(title=win32gui.GetWindowText(hwnd), width=width, height=height,
                        foreground=foreground == hwnd,
                        foreground_window=None if foreground == hwnd else {
                            'class': win32gui.GetClassName(foreground) if foreground else '',
                            'title': win32gui.GetWindowText(foreground) if foreground else ''})
        info['screen'] = [ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)]
        return info

    def close_windows(self, cls, title_contains=None):
        import win32con
        import win32gui
        targets = []

        def collect(h, _):
            if (win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == cls
                    and (not title_contains or title_contains.lower() in win32gui.GetWindowText(h).lower())):
                targets.append(h)
        win32gui.EnumWindows(collect, None)
        for h in targets:
            win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
        return len(targets)

    # --- background cleanup (this session only) -------------------------------

    def close_startup_apps(self):
        import psutil
        if not self.close_apps:
            return
        deadline = time.time() + STARTUP_CLEANUP_SECONDS
        closed = 0
        while time.time() < deadline and not self.exit_event.is_set():
            for proc in psutil.process_iter(['pid', 'name']):
                name = (proc.info['name'] or '').lower()
                if name in self.close_apps and win_api.process_session_id(proc.info['pid']) == self.session:
                    try:
                        proc.kill()
                        closed += 1
                        self.log(f'closed startup app {proc.info["name"]} pid={proc.info["pid"]}')
                    except Exception as e:
                        self.log(f'could not close {proc.info["name"]}: {e}')
            time.sleep(2)
        self.log(f'startup app cleanup finished, closed {closed}')

    def dismiss_system_app_errors(self):
        """Windows keeps retrying packaged system apps that cannot run in a child session
        (ClickToDo, AIXHost, CrossDeviceResume); each failure leaves an error box over the
        game that can take focus. Close only visible dialogs titled with a SystemApps path."""
        import win32con
        import win32gui
        marker = '\\systemapps\\'
        while not self.exit_event.is_set():
            found = []

            def collect(h, _):
                if (win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == '#32770'
                        and marker in win32gui.GetWindowText(h).lower()):
                    found.append(h)
            try:
                win32gui.EnumWindows(collect, None)
                for h in found:
                    title = win32gui.GetWindowText(h)
                    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
                    self.log('dismissed system app error box:', title.rsplit('\\', 1)[-1])
            except Exception as e:
                self.log('dismiss error:', repr(e))
            self.exit_event.wait(2)

    # --- commands -------------------------------------------------------------

    def handle(self, cmd, req):
        hwnd = self.window.hwnd
        if cmd in ('hello', 'ping'):
            return {'ok': True, 'version': AGENT_VERSION, 'session': self.session, 'elevated': self.elevated}, None
        if cmd == 'configure':
            self.window.configure(req.get('window') or {})
            return {'ok': True}, None
        if cmd == 'window_info':
            return self.window_info(), None
        if cmd == 'top_windows':
            return {'windows': self.top_windows()}, None
        if cmd == 'launch':
            kwargs = {'arguments': req.get('args') or ''}
            if req.get('cwd'):
                kwargs['cwd'] = req['cwd']
            os.startfile(req['path'], **kwargs)
            self.log(f'launched {req["path"]} {req.get("args") or ""}')
            return {'ok': True}, None
        if cmd == 'frame':
            if not hwnd:
                return {'error': 'game window not found in the child session'}, None
            import numpy as np
            frame = self.frame()
            if frame is None:
                return {'ok': False, 'w': 0, 'h': 0}, None
            frame = np.ascontiguousarray(frame)
            return {'ok': True, 'w': frame.shape[1], 'h': frame.shape[0]}, frame.tobytes()
        if cmd == 'close_windows':
            return {'closed': self.close_windows(req['cls'], req.get('title_contains'))}, None
        if cmd == 'front':
            return {'ok': self.input.bring_to_front(hwnd)}, None
        input_commands = {
            'click': lambda: self.input.click(hwnd, req.get('x', -1), req.get('y', -1), req.get('key', 'left'),
                                              req.get('down_time', 0.05)),
            'mouse_down': lambda: self.input.mouse_down(hwnd, req.get('x', -1), req.get('y', -1),
                                                        req.get('key', 'left')),
            'mouse_up': lambda: self.input.mouse_up(hwnd, req.get('key', 'left')),
            'move': lambda: self.input.move(hwnd, req['x'], req['y']),
            'move_relative': lambda: self.input.move_relative(hwnd, req['dx'], req['dy']),
            'scroll': lambda: self.input.scroll(hwnd, req.get('x', -1), req.get('y', -1), req['amount']),
            'swipe': lambda: self.input.swipe(hwnd, req['from_x'], req['from_y'], req['to_x'], req['to_y'],
                                              req.get('duration', 0.5), req.get('settle_time', 0)),
            'key_down': lambda: self.input.key_down(hwnd, req['key']),
            'key_up': lambda: self.input.key_up(hwnd, req['key']),
            'send_key': lambda: self.input.send_key(hwnd, req['key'], req.get('down_time', 0.02)),
            'input_text': lambda: self.input.input_text(hwnd, req['text']),
        }
        if cmd in input_commands:
            if not hwnd and cmd not in ('mouse_up', 'key_up'):
                return {'error': 'game window not found in the child session'}, None
            input_commands[cmd]()
            return {'ok': True}, None
        if cmd == 'restart':
            self.restart()
            return {'ok': True}, None
        if cmd == 'quit':
            self.exit_event.set()
            return {'ok': True}, None
        return {'error': f'unknown command {cmd}'}, None

    def restart(self):
        """Start a fresh copy in this session (it inherits elevation) once the port is free."""
        agent = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent.py')
        flag = ' --elevated' if self.elevated else ''
        command = (f'cmd.exe /c timeout /t 2 /nobreak >nul & start "" "{sys.executable}" "{agent}" '
                   f'--project "{self.project_dir}"{flag}')
        subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
        self.log('restarting')
        self.exit_event.set()

    def serve_connection(self, conn):
        reader = conn.makefile('rb')
        authed = False
        try:
            while not self.exit_event.is_set():
                line = reader.readline()
                if not line:
                    return
                req = json.loads(line)
                cmd = req.pop('cmd', None)
                if not authed:
                    if cmd != 'hello' or req.get('token') != self.token:
                        protocol.send_message(conn, {'error': 'unauthorized'})
                        return
                    authed = True
                try:
                    reply, payload = self.handle(cmd, req)
                except Exception as e:
                    self.log(f'command {cmd} failed: {e!r}')
                    reply, payload = {'error': f'{cmd} failed: {e!r}'}, None
                protocol.send_message(conn, reply, payload)
                if cmd == 'quit' or cmd == 'restart':
                    return
        except (OSError, ValueError) as e:
            self.log(f'connection closed: {e!r}')
        finally:
            conn.close()

    def serve(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        server.bind((protocol.HOST, 0))
        server.listen(4)
        server.settimeout(1)
        port = server.getsockname()[1]
        protocol.write_json(protocol.agent_file(self.project_dir), {
            'port': port, 'token': self.token, 'pid': os.getpid(), 'session': self.session,
            'elevated': self.elevated, 'version': AGENT_VERSION, 'started': time.time()})
        self.log(f'listening on {port}, session={self.session} elevated={self.elevated}')
        try:
            while not self.exit_event.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                conn.settimeout(None)
                threading.Thread(target=self.serve_connection, args=(conn,), daemon=True).start()
        finally:
            server.close()
            info = protocol.read_json(protocol.agent_file(self.project_dir)) or {}
            if info.get('pid') == os.getpid():
                try:
                    os.remove(protocol.agent_file(self.project_dir))
                except OSError:
                    pass
            if self._capture is not None:
                self._capture.close()
            self.log('agent stopped')


def _relaunch_elevated(project_dir, log) -> bool:
    agent = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent.py')
    params = f'"{agent}" --project "{project_dir}" --elevated'
    result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, params, project_dir, 0)
    if result > 32:
        log('relaunched elevated (UAC prompt in the child session)')
        return True
    log(f'elevated relaunch declined or failed ({result}); continuing without admin')
    return False


def _single_instance(project_dir):
    """A per-session mutex so only one agent of a project runs in a session."""
    name = f'Local\\ok-script-child-session-agent-{protocol.project_key(project_dir)}'
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def run(project_dir, elevated_relaunch=False, any_session=False):
    log = AgentLog(project_dir)
    is_child, reason = win_api.in_child_session()
    log(f'agent start pid={os.getpid()} session={win_api.current_session_id()} child={is_child} ({reason}) '
        f'elevated={win_api.is_elevated()}')
    if not is_child and not any_session:
        log('not in a child session, exiting')
        return 0
    config = protocol.read_json(protocol.config_file(project_dir)) or {}
    if config.get('elevate', True) and not win_api.is_elevated() and not elevated_relaunch:
        if _relaunch_elevated(project_dir, log):
            return 0
    mutex = _single_instance(project_dir)
    if mutex is None:
        # A restart may still be shutting down the previous agent; try again briefly.
        time.sleep(3)
        mutex = _single_instance(project_dir)
        if mutex is None:
            log('another agent of this project is running in this session, exiting')
            return 0
    try:
        agent = Agent(project_dir, log)
        threading.Thread(target=agent.close_startup_apps, daemon=True).start()
        threading.Thread(target=agent.dismiss_system_app_errors, daemon=True).start()
        agent.serve()
    except Exception:
        log('agent failed:\n' + traceback.format_exc())
        return 1
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)
    return 0
