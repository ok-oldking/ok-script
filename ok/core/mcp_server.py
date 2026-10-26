"""Optional localhost MCP transport for task development and explicit reloading."""

import asyncio
import json
import os
import secrets
import socket
import threading
import time
from typing import Any

from ok import og
from ok.core.mcp_runner import McpTaskRunner
from ok.core.skills import get_skill as read_skill, list_skills as discover_skills
from ok.util.logger import Logger


logger = Logger.get_logger(__name__)


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


def create_mcp_app(runner, token, port):
    """Build the task and skill ASGI app, importing the optional SDK only here."""
    try:
        from mcp.server import MCPServer
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError as error:
        raise RuntimeError('Install the MCP profile: pip install "ok-script[mcp]"') from error

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
            self._socket = socket.create_server(('127.0.0.1', self.port))
            self.port = self._socket.getsockname()[1]
            app = create_mcp_app(self.runner, self.token, self.port)
            import uvicorn
            self._server = uvicorn.Server(uvicorn.Config(
                app, host='127.0.0.1', port=self.port, log_level='warning', access_log=False,
                timeout_graceful_shutdown=5))

            def serve():
                try:
                    self._server.run(sockets=[self._socket])
                except BaseException as error:
                    self._error = error

            self._thread = threading.Thread(target=serve, name='ok-mcp', daemon=True)
            self._thread.start()
            deadline = time.monotonic() + 10
            while not self._server.started:
                if not self._thread.is_alive():
                    raise RuntimeError(f'MCP server failed to start: {self._error}')
                if time.monotonic() >= deadline or self.runtime.exit_event.wait(0.02):
                    raise RuntimeError('MCP server startup interrupted or timed out')
            self.runner.artifact_directory.mkdir(parents=True, exist_ok=True)
            connection_file = self.runner.artifact_directory / 'connection.json'
            connection_file.write_text(json.dumps({
                'url': f'http://127.0.0.1:{self.port}/mcp', 'token': self.token, 'pid': os.getpid(),
            }, indent=2), encoding='utf-8')
            self.runtime.exit_event.bind_stop(self)
            logger.info(f'MCP ready at http://127.0.0.1:{self.port}/mcp; connection details: {connection_file}')
        except BaseException:
            self.stop()
            self.join()
            if self._socket is not None and (self._thread is None or not self._thread.is_alive()):
                self._socket.close()
            raise

    def stop(self):
        self.runner.close()
        if self._server is not None:
            self._server.should_exit = True

    def join(self, timeout=6):
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)
