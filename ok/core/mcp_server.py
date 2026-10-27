"""Localhost MCP transport for task development and explicit reloading."""

import asyncio
import errno
import json
import os
import secrets
import socket
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psutil

from ok import og
from ok.core.mcp_runner import McpTaskRunner
from ok.core.skills import get_skill as read_skill, list_skills as discover_skills
from ok.util.logger import Logger


logger = Logger.get_logger(__name__)


def bind_mcp_socket(port):
    """Reserve the first available loopback port, incrementing on conflicts only."""
    if not 0 <= port <= 65535:
        raise ValueError('mcp.port must be between 0 and 65535')
    while True:
        try:
            return socket.create_server(('127.0.0.1', port))
        except OSError as error:
            if error.errno != errno.EADDRINUSE and getattr(error, 'winerror', None) != 10048:
                raise
            if port == 65535:
                raise OSError(errno.EADDRINUSE, 'No available MCP port up to 65535') from error
            port += 1


def discover_mcp_servers(project_directories=None, *, artifact_directory='logs/mcp'):
    """Read live servers from project connection files, without scanning ports.

    Pass one project directory or an iterable of directories; defaults to cwd.
    For projects with a custom artifact directory, pass that path explicitly.
    Results include credentials, project paths and instance connection-file paths.
    """
    if project_directories is None:
        project_directories = [Path.cwd()]
    elif isinstance(project_directories, (str, os.PathLike)):
        project_directories = [project_directories]
    servers = {}
    for project in project_directories:
        directory = (Path(project) / artifact_directory).resolve()
        paths = sorted((directory / 'connections').glob('*.json'))
        paths.append(directory / 'connection.json')  # Also support older servers.
        for path in paths:
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
                url = urlsplit(record['url'])
                pid = record['pid']
                if (url.scheme != 'http' or url.hostname != '127.0.0.1'
                        or url.path != '/mcp' or not url.port
                        or url.username or url.password or url.query or url.fragment
                        or type(pid) is not int or pid <= 0
                        or not isinstance(record['token'], str) or not record['token']):
                    continue
                process = psutil.Process(pid)
                if ('process_start_time' in record
                        and record['process_start_time'] != process.create_time()):
                    continue
                if not any(connection.status == psutil.CONN_LISTEN
                           and connection.laddr.ip == '127.0.0.1'
                           and connection.laddr.port == url.port
                           for connection in process.net_connections(kind='tcp')):
                    continue
                servers.setdefault((pid, record['url']), {
                    **record, 'project_directory': record.get('project_directory', str(Path(project).resolve())),
                    'connection_file': str(path),
                })
            except (OSError, ValueError, KeyError, TypeError, psutil.Error):
                continue
    return list(servers.values())


class _BearerAuth:
    def __init__(self, app, token):
        self.app = app
        self.expected = f'Bearer {token}'.encode('utf-8')

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            values = [value for key, value in scope['headers'] if key.lower() == b'authorization']
            if len(values) != 1 or not secrets.compare_digest(values[0], self.expected):
                from starlette.responses import PlainTextResponse
                response = PlainTextResponse('Unauthorized', status_code=401,
                                             headers={'WWW-Authenticate': 'Bearer'})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_mcp_app(runner, token, port, request_exit=None):
    """Build the task and skill ASGI app, loading the SDK only when the server is enabled."""
    try:
        from mcp.server import MCPServer
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError as error:
        raise RuntimeError("The required MCP dependency is missing or incompatible. Reinstall this project's pinned ok-script dependencies.") from error

    mcp = MCPServer('ok-script', instructions=(
        'Call list_skills to discover packaged ok-script instructions, then get_skill '
        'with the relevant skill ID before working. Skills are also MCP resources. '
        'These skills are for the consuming application: its tasks, config, assets, '
        'environment and tests, not for developing or publishing the ok-script library. '
        'For existing tasks, prefer list_tasks, edit the returned source files in place, '
        'then reload_tasks with task_ids (omit task_ids to reload all). Poll get_run_status '
        'until the reload finishes before testing. Read the reload-tasks skill for this workflow. '
        'Write a local Python file defining class Task(BaseTask) with reset_to_start(), '
        'verify_start_state(), and run(). Call run_task with its absolute path. '
        'Read logs and screenshots directly from the returned local paths. '
        'Use assertions in run() to verify success. A stopping run still owns the executor. '
        'If runtime state cannot be cleared or reset, code is stuck, or cached dependencies '
        'require a restart, call exit_process with the reason. Wait for the returned PID '
        'to exit, relaunch the project, reconnect, then restore and verify the target state. '
        'screenshot returns a saved image path; during execution it returns the latest cached frame.'))

    @mcp.tool()
    def list_skills() -> list[dict[str, str]]:
        """Discover bundled skills with IDs, names, descriptions, resource URIs and local paths."""
        return discover_skills()

    @mcp.tool()
    def get_skill(skill_id: str) -> dict[str, str]:
        """Read a discovered skill's instructions. Relative links resolve from its local path."""
        return read_skill(skill_id)

    def register_skill_resource(skill):
        @mcp.resource(skill['uri'], name=skill['name'],
                      description=skill['description'], mime_type='text/markdown')
        def skill_content() -> str:
            return read_skill(skill['id'])['content']

    for skill in discover_skills():
        register_skill_resource(skill)

    @mcp.tool()
    async def list_tasks() -> list[dict[str, Any]]:
        """List registered task IDs, absolute source paths, types and plugin ownership.

        Use these IDs with reload_tasks after editing existing tasks in place.
        """
        return await asyncio.to_thread(runner.list_tasks)

    @mcp.tool()
    async def reload_tasks(task_ids: list[str] | None = None) -> dict[str, Any]:
        """Reload registered task source after editing; preferred for existing tasks.

        Pass IDs from list_tasks, or omit task_ids to reload all tasks/plugins.
        Returns a run ID immediately. Poll get_run_status until terminal before
        testing; failures preserve existing instances. Shares executor ownership
        with run_task, so wait for active runs to finish first. Module siblings
        and whole plugins reload together. This does not run automation actions.
        """
        return await asyncio.to_thread(runner.reload_tasks, task_ids)

    @mcp.tool()
    async def run_task(file_path: str) -> dict[str, Any]:
        """Load a Python task file, reset and verify the starting state, then run it.

        Returns a run ID immediately. Task files run as trusted local Python.
        Edit the file and invoke again to load a fresh task instance.
        """
        return await asyncio.to_thread(runner.run_task, file_path)

    @mcp.tool()
    async def get_run_status(run_id: str) -> dict[str, Any]:
        """Return state, phase, brief error, and local artifact paths for a run."""
        return await asyncio.to_thread(runner.get_run_status, run_id)

    @mcp.tool()
    async def stop_task(run_id: str) -> dict[str, Any]:
        """Request cooperative cancellation. Wait for a terminal state before retrying."""
        return await asyncio.to_thread(runner.stop_task, run_id)

    @mcp.tool()
    async def exit_process(reason: str) -> dict[str, Any]:
        """Exit this ok-script runtime when state cannot be reset or a restart is needed.

        Requires a nonempty diagnostic reason. Returns the current process PID
        and schedules shutdown, including forced termination if cleanup hangs.
        Works even when a task is stuck. This also closes the GUI if present.
        Wait for that PID to exit before relaunching and reconnecting. The target
        application is not restarted or reset by this tool.
        """
        if request_exit is None:
            raise RuntimeError('Process exit is not configured for this MCP app')
        return request_exit(reason)

    @mcp.tool()
    async def screenshot() -> dict[str, Any]:
        """Save the target UI and return its absolute path, size, capture time and cached flag.

        Idle captures are fresh. During execution, the latest frame is returned
        without calling the capture backend from another thread.
        """
        return await asyncio.to_thread(runner.screenshot)

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f'127.0.0.1:{port}', f'localhost:{port}'],
        allowed_origins=[f'http://127.0.0.1:{port}', f'http://localhost:{port}'])
    app = mcp.streamable_http_app(json_response=True, transport_security=security)
    return _BearerAuth(app, token)


class LocalMcpServer:
    def __init__(self, runtime, config):
        self.runtime = runtime
        self.port = int(config.get('port', 8765))
        if not 0 <= self.port <= 65535:
            raise ValueError('mcp.port must be between 0 and 65535')
        self.token = os.environ.get('OK_SCRIPT_MCP_TOKEN') or secrets.token_urlsafe(32)
        app = runtime.headless_app if runtime.should_init_task_manager_headless() else runtime.app
        self.runner = McpTaskRunner(runtime.task_executor, app, runtime.screenshot,
                                    config.get('artifact_directory', 'logs/mcp'), self._prepare_device,
                                    task_manager=og.task_manager)
        self._server = None
        self._socket = None
        self._thread = None
        self._error = None
        self._connection = None
        self._connection_file = None
        self._exit_lock = threading.Lock()
        self._exit_request = None
        self._exit_timer = None

    def exit_process(self, reason):
        """Schedule exit without waiting on executor ownership or runner locks."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('A nonempty reason is required to exit the process')
        with self._exit_lock:
            if self._exit_request is None:
                self._exit_request = {'state': 'exiting', 'pid': os.getpid(), 'reason': reason.strip()}
                # Give the HTTP transport time to deliver the acknowledgement.
                self._exit_timer = threading.Timer(0.25, self._exit_process)
                self._exit_timer.daemon = True
                self._exit_timer.start()
            return dict(self._exit_request)

    def _exit_process(self):
        from ok.util.process import start_exit_watchdog

        # Arm before any logging or cleanup: either can be blocked by bad state.
        start_exit_watchdog(grace_period=5.0)
        logger.warning(f"MCP requested process exit: {self._exit_request['reason']}")
        self.runtime.quit()

    def _prepare_device(self):
        executor = self.runtime.task_executor
        executor.check_enabled()
        manager = self.runtime.device_manager
        manager.do_refresh(True)
        if manager.get_preferred_device() is None:
            raise RuntimeError('No target device selected in the project configuration')
        controller = self.runner.app.start_controller
        if controller.start_exe:
            if not controller.start_device(initial_refresh_done=True):
                raise RuntimeError('Target device could not be started; inspect the application log')
        else:
            error = controller.check_device_error()
            if error:
                raise RuntimeError(error)
        executor.check_enabled()

    def start(self):
        if self._thread is not None:
            return
        try:
            self._socket = bind_mcp_socket(self.port)
            self.port = self._socket.getsockname()[1]
            app = create_mcp_app(self.runner, self.token, self.port, self.exit_process)
            import uvicorn
            self._server = uvicorn.Server(uvicorn.Config(
                app, host='127.0.0.1', port=self.port, log_level='warning', access_log=False,
                timeout_graceful_shutdown=5))

            def serve():
                try:
                    self._server.run(sockets=[self._socket])
                except BaseException as error:
                    self._error = error
                finally:
                    self._remove_connection_files()

            self._thread = threading.Thread(target=serve, name='ok-mcp', daemon=True)
            self._thread.start()
            deadline = time.monotonic() + 10
            while not self._server.started:
                if not self._thread.is_alive():
                    raise RuntimeError(f'MCP server failed to start: {self._error}')
                if time.monotonic() >= deadline or self.runtime.exit_event.wait(0.02):
                    raise RuntimeError('MCP server startup interrupted or timed out')
            directory = self.runner.artifact_directory
            (directory / 'connections').mkdir(parents=True, exist_ok=True)
            self._connection = {
                'url': f'http://127.0.0.1:{self.port}/mcp', 'token': self.token, 'pid': os.getpid(),
                'process_start_time': psutil.Process().create_time(),
                'project_directory': str(Path.cwd()),
            }
            self._connection_file = directory / 'connections' / f'{os.getpid()}-{self.port}.json'
            for path in (self._connection_file, directory / 'connection.json'):
                temporary = path.with_suffix(f'.{os.getpid()}-{self.port}.tmp')
                temporary.write_text(json.dumps(self._connection, indent=2), encoding='utf-8')
                temporary.replace(path)
            self.runtime.exit_event.bind_stop(self)
            logger.info(f'MCP ready at http://127.0.0.1:{self.port}/mcp; connection details: {self._connection_file}')
        except BaseException:
            self.stop()
            self.join()
            if self._socket is not None and (self._thread is None or not self._thread.is_alive()):
                self._socket.close()
            raise

    def stop(self):
        self.runner.close()
        self._remove_connection_files()
        if self._server is not None:
            self._server.should_exit = True

    def _remove_connection_files(self):
        if self._connection_file is None:
            return
        # connection.json is a compatibility snapshot shared by instances. Leave
        # it alone here: another process may replace it while we are stopping.
        for path in (self._connection_file,):
            try:
                if json.loads(path.read_text(encoding='utf-8')) == self._connection:
                    path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as error:
                logger.error(f'Could not remove MCP connection file {path}: {error}')

    def join(self, timeout=6):
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)
        if self._thread is None or not self._thread.is_alive():
            if self._socket is not None:
                self._socket.close()
            self.runtime.exit_event.unbind_stop(self)
