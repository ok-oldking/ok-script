import asyncio
import json
import errno
import logging
import os
import socket
import threading
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok.core.mcp_server import LocalMcpServer, bind_mcp_socket, create_mcp_app, discover_mcp_servers
from ok.util.handler import ExitEvent
from ok.util.logger import SafeFileHandler
from test_mcp_runner import development, write_task, register_task


@pytest.mark.parametrize('mode', ['auto', 'legacy'])
def test_http_connection_and_tools_end_to_end(development, mode, monkeypatch):
    pytest.importorskip('mcp')
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    dev = development
    registered_path, old = register_task(dev, 'http_registered')
    runtime = SimpleNamespace(task_executor=dev.executor, screenshot=dev.screens,
                              headless_app=dev.app, exit_event=ExitEvent(),
                              should_init_task_manager_headless=lambda: True)
    server = LocalMcpServer(runtime, {'port': 0, 'artifact_directory': str(dev.root / 'http')})
    exit_started = threading.Event()
    # Never arm a process-killing watchdog inside the pytest process.
    monkeypatch.setattr(server, '_exit_process', exit_started.set)
    server.runner.prepare = None  # Real executor, fake target device.
    path = write_task(dev.root, "self.log_info('MCP call succeeded')")
    server.start()
    connection = json.loads((server.runner.artifact_directory / 'connection.json').read_text())
    discovered = discover_mcp_servers(dev.root, artifact_directory='http')
    assert len(discovered) == 1
    assert discovered[0]['url'] == connection['url']
    assert discovered[0]['token'] == connection['token']

    async def exercise():
        async with httpx2.AsyncClient() as http:
            assert (await http.post(connection['url'])).status_code == 401
            headers = {'Authorization': f"Bearer {connection['token']}",
                       'Content-Type': 'application/json', 'Origin': 'https://untrusted.example'}
            assert (await http.post(connection['url'], headers=headers, json={})).status_code == 403
            headers.pop('Origin')
            headers['Host'] = 'untrusted.example'
            assert (await http.post(connection['url'], headers=headers, json={})).status_code == 421
        async with httpx2.AsyncClient(headers={'Authorization': f"Bearer {connection['token']}"}) as http:
            transport = streamable_http_client(connection['url'], http_client=http)
            async with Client(transport, mode=mode) as client:
                listing = await client.list_tools()
                assert {tool.name for tool in listing.tools} == {
                    'run_task', 'get_run_status', 'stop_task', 'screenshot',
                    'list_skills', 'get_skill', 'list_tasks', 'reload_tasks', 'exit_process'}
                skills = await client.call_tool('list_skills')
                assert not skills.is_error, skills
                assert 'develop' in str(skills)
                assert not {'commit_changes', 'deploy_pip', 'compile_i18n'} & {
                    item['id'] for item in skills.structured_content['result']}
                skill = await client.call_tool('get_skill', {'skill_id': 'develop'})
                assert not skill.is_error, skill
                assert 'reset_to_start()' in skill.structured_content['content']
                resources = await client.list_resources()
                assert 'ok-script://skills/develop' in {str(r.uri) for r in resources.resources}
                resource = await client.read_resource('ok-script://skills/develop')
                assert resource.contents[0].text == skill.structured_content['content']
                reload_skill = await client.call_tool('get_skill', {'skill_id': 'reload-tasks'})
                assert not reload_skill.is_error, reload_skill
                reload_resource = await client.read_resource('ok-script://skills/reload-tasks')
                assert reload_resource.contents[0].text == reload_skill.structured_content['content']
                unknown = await client.call_tool('get_skill', {'skill_id': '../setup.py'})
                assert unknown.is_error
                tasks = await client.call_tool('list_tasks')
                assert not tasks.is_error, tasks
                assert tasks.structured_content['result'][0]['file_path'] == str(registered_path)
                registered_path.write_text(registered_path.read_text().replace("'first'", "'other'"))
                reloaded = await client.call_tool('reload_tasks', {
                    'task_ids': ['http_registered.RegisteredTask']})
                assert not reloaded.is_error, reloaded
                for _ in range(100):
                    status = await client.call_tool('get_run_status', {'run_id': reloaded.structured_content['run_id']})
                    if status.structured_content['state'] in {'succeeded', 'failed', 'cancelled'}:
                        break
                    await asyncio.sleep(0.01)
                assert status.structured_content['state'] == 'succeeded', status
                assert dev.executor.onetime_tasks[0] is not old
                assert dev.executor.onetime_tasks[0].value == 'other'
                invalid_reload = await client.call_tool('reload_tasks', {'task_ids': ['missing.Task']})
                assert invalid_reload.is_error
                reload_all = await client.call_tool('reload_tasks')
                assert not reload_all.is_error, reload_all
                for _ in range(100):
                    status = await client.call_tool('get_run_status', {'run_id': reload_all.structured_content['run_id']})
                    if status.structured_content['state'] in {'succeeded', 'failed', 'cancelled'}:
                        break
                    await asyncio.sleep(0.01)
                assert status.structured_content['state'] == 'succeeded', status
                assert len(status.structured_content['result']) == 1
                result = await client.call_tool('run_task', {'file_path': str(path)})
                assert not result.is_error, result
                run_id = result.structured_content['run_id']
                for _ in range(100):
                    status = await client.call_tool('get_run_status', {'run_id': run_id})
                    if status.structured_content['state'] in {'succeeded', 'failed', 'cancelled'}:
                        break
                    await asyncio.sleep(0.01)
                assert status.structured_content['state'] == 'succeeded', status
                image = await client.call_tool('screenshot')
                assert not image.is_error, image
                assert image.structured_content['cached'] is False
                stopped = await client.call_tool('stop_task', {'run_id': run_id})
                assert stopped.structured_content['state'] == 'succeeded'
                invalid = await client.call_tool('get_run_status', {'run_id': 'missing'})
                assert invalid.is_error
                invalid_exit = await client.call_tool('exit_process', {'reason': '  '})
                assert invalid_exit.is_error
                assert not exit_started.is_set()
                exiting = await client.call_tool('exit_process', {'reason': 'Runtime needs a restart'})
                assert not exiting.is_error, exiting
                assert exiting.structured_content == {
                    'state': 'exiting', 'pid': os.getpid(), 'reason': 'Runtime needs a restart'}

    try:
        asyncio.run(exercise())
        assert exit_started.wait(2)
    finally:
        server.stop()
        server.join()
    assert not server._thread.is_alive()
    assert discover_mcp_servers(dev.root, artifact_directory='http') == []


def test_start_keeps_existing_file_log_open(development, tmp_path):
    pytest.importorskip('mcp')
    dev = development
    runtime = SimpleNamespace(task_executor=dev.executor, screenshot=dev.screens,
                              headless_app=dev.app, exit_event=ExitEvent(),
                              should_init_task_manager_headless=lambda: True)
    server = LocalMcpServer(runtime, {'port': 0, 'artifact_directory': str(dev.root / 'http')})
    # The application configures ok-script.log before it starts the MCP server.
    log_file = tmp_path / 'ok-script.log'
    handler = SafeFileHandler(log_file, when='midnight', encoding='utf-8')
    ok_logger = logging.getLogger('ok')
    ok_logger.addHandler(handler)
    try:
        server.start()
        ok_logger.warning('logged after MCP start')
    finally:
        ok_logger.removeHandler(handler)
        handler.close()
        server.stop()
        server.join()
    assert 'logged after MCP start' in log_file.read_text(encoding='utf-8')


def test_exit_request_is_idempotent_and_does_not_wait_for_runner(development, monkeypatch):
    dev = development
    runtime = SimpleNamespace(task_executor=dev.executor, screenshot=dev.screens,
                              headless_app=dev.app, should_init_task_manager_headless=lambda: True)
    server = LocalMcpServer(runtime, {'artifact_directory': str(dev.root / 'http')})
    timer = Mock()
    monkeypatch.setattr('ok.core.mcp_server.threading.Timer', timer)
    monkeypatch.setattr(server.runner, 'close', Mock(side_effect=AssertionError('must not wait')))
    for reason in ('', '  ', None):
        with pytest.raises(ValueError, match='nonempty reason'):
            server.exit_process(reason)
    timer.assert_not_called()
    result = server.exit_process('  Capture state cannot be reset  ')
    assert result == {'state': 'exiting', 'pid': os.getpid(), 'reason': 'Capture state cannot be reset'}
    assert server.exit_process('Another reason') == result
    result['state'] = 'changed by caller'
    assert server.exit_process('Retry')['state'] == 'exiting'
    timer.assert_called_once_with(0.25, server._exit_process)
    assert timer.return_value.daemon is True
    timer.return_value.start.assert_called_once_with()
    server.runner.close.assert_not_called()


@pytest.mark.parametrize('mode', ['graceful', 'stuck_worker', 'stuck_cleanup'])
def test_exit_tool_terminates_only_its_server_process(tmp_path, mode):
    pytest.importorskip('mcp')
    import subprocess
    import sys
    import time
    from pathlib import Path

    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    # Exercise actual process termination in an isolated child. Blocked cleanup
    # holds the runner lock, so exit must not depend on that lock or executor jobs.
    source = '''
import os, sys, threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from ok.core.mcp_server import LocalMcpServer
from ok.util.handler import ExitEvent

os.chdir(sys.argv[1])
mode = sys.argv[2]
runtime = SimpleNamespace(task_executor=Mock(), screenshot=Mock(), headless_app=Mock(),
                          exit_event=ExitEvent(), should_init_task_manager_headless=lambda: True)
server = LocalMcpServer(runtime, {'port': 0})
def quit_runtime():
    Path('quit_requested').touch()
    server.stop()
    runtime.exit_event.set()
runtime.quit = quit_runtime
if mode != 'graceful':
    ready = threading.Event()
    def block():
        if mode == 'stuck_cleanup':
            server.runner._lock.acquire()
        ready.set()
        threading.Event().wait()
    threading.Thread(target=block, name='StuckWorker', daemon=False).start()
    assert ready.wait(2)
server.start()
runtime.exit_event.wait()
server.join()
'''
    child = subprocess.Popen([sys.executable, '-u', '-c', source, str(tmp_path), mode],
                             cwd=Path(__file__).resolve().parents[1],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        connection_file = tmp_path / 'logs/mcp/connection.json'
        deadline = time.monotonic() + 15
        while not connection_file.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert connection_file.exists(), f'Child MCP server failed to start: {child.poll()}'
        connection = json.loads(connection_file.read_text())

        async def request_exit():
            async with httpx2.AsyncClient(headers={'Authorization': f"Bearer {connection['token']}"}) as http:
                async with Client(streamable_http_client(connection['url'], http_client=http)) as client:
                    result = await client.call_tool('exit_process', {'reason': 'State cannot be reset'})
                    assert not result.is_error, result
                    assert result.structured_content == {
                        'state': 'exiting', 'pid': connection['pid'], 'reason': 'State cannot be reset'}

        asyncio.run(request_exit())
        stdout, stderr = child.communicate(timeout=12)
        assert child.returncode == 0, (stdout, stderr)
        assert (tmp_path / 'quit_requested').exists()
        assert discover_mcp_servers(tmp_path) == []
        if mode == 'graceful':
            assert list((tmp_path / 'logs/mcp/connections').glob('*.json')) == []
        else:
            assert 'forcing process exit' in stdout + stderr
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


def test_missing_required_sdk_has_repair_instructions(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'mcp', None)
    monkeypatch.setitem(sys.modules, 'mcp.server', None)
    with pytest.raises(RuntimeError, match='required MCP dependency'):
        create_mcp_app(None, 'test-token', 8765)


@pytest.fixture
def occupied_ports():
    # Reserve two consecutive ports, without assuming any fixed port is free.
    with ExitStack() as sockets:
        for _ in range(30):
            first = sockets.enter_context(socket.create_server(('127.0.0.1', 0)))
            port = first.getsockname()[1]
            if port >= 65534:
                continue
            try:
                sockets.enter_context(socket.create_server(('127.0.0.1', port + 1)))
                third = socket.create_server(('127.0.0.1', port + 2))
            except OSError:
                continue
            third.close()
            yield port
            return
    pytest.fail('Could not reserve consecutive test ports')


def test_fallback_increments_past_each_occupied_port(occupied_ports):
    with bind_mcp_socket(occupied_ports) as listener:
        assert listener.getsockname() == ('127.0.0.1', occupied_ports + 2)


@pytest.mark.parametrize('error', [PermissionError(errno.EACCES, 'denied'),
                                 OSError(errno.EAFNOSUPPORT, 'unsupported')])
def test_fallback_does_not_hide_other_bind_errors(monkeypatch, error):
    def fail(address):
        raise error
    monkeypatch.setattr(socket, 'create_server', fail)
    with pytest.raises(type(error)) as caught:
        bind_mcp_socket(8765)
    assert caught.value is error


def test_fallback_stops_at_last_valid_port(monkeypatch):
    def occupied(address):
        assert address == ('127.0.0.1', 65535)
        raise OSError(errno.EADDRINUSE, 'occupied')
    monkeypatch.setattr(socket, 'create_server', occupied)
    with pytest.raises(OSError, match='No available MCP port'):
        bind_mcp_socket(65535)


def test_multiple_instances_in_same_project_are_discovered_and_stop_independently(development, occupied_ports):
    dev = development
    runtime = SimpleNamespace(task_executor=dev.executor, screenshot=dev.screens,
                              headless_app=dev.app, exit_event=ExitEvent(),
                              should_init_task_manager_headless=lambda: True)
    config = {'port': occupied_ports, 'artifact_directory': str(dev.root / 'logs/mcp')}
    first, second = LocalMcpServer(runtime, config), LocalMcpServer(runtime, config)
    try:
        first.start()
        second.start()
        assert first.port == occupied_ports + 2
        assert second.port > first.port
        servers = discover_mcp_servers([dev.root, dev.root])
        assert len(servers) == 2
        assert {item['url'] for item in servers} == {
            f'http://127.0.0.1:{server.port}/mcp' for server in (first, second)}
        assert len({item['connection_file'] for item in servers}) == 2
        first.stop()
        first.join()
        assert len(discover_mcp_servers()) == 1
        assert discover_mcp_servers()[0]['url'] == f'http://127.0.0.1:{second.port}/mcp'
        assert second in runtime.exit_event.to_stops
        assert first not in runtime.exit_event.to_stops
    finally:
        for server in (first, second):
            server.stop()
            server.join()
    assert discover_mcp_servers() == []
    assert list((dev.root / 'logs/mcp/connections').glob('*.json')) == []


def test_discovery_handles_multiple_projects_and_invalid_or_stale_records(tmp_path):
    import psutil
    with socket.create_server(('127.0.0.1', 0)) as listener, \
            socket.create_server(('127.0.0.1', 0)) as other:
        port = listener.getsockname()[1]
        valid = {'url': f'http://127.0.0.1:{port}/mcp', 'token': 'test-token', 'pid': os.getpid(),
                 'process_start_time': psutil.Process().create_time()}
        roots = [tmp_path / 'first', tmp_path / 'second']
        for root, instance_port in zip(roots, [port, other.getsockname()[1]]):
            directory = root / 'logs/mcp'
            directory.mkdir(parents=True)
            record = {**valid, 'url': f'http://127.0.0.1:{instance_port}/mcp'}
            (directory / 'connection.json').write_text(json.dumps(record))
        assert len(discover_mcp_servers(roots)) == 2
        directory = roots[0] / 'logs/mcp/connections'
        directory.mkdir()
        records = [None, [], {'pid': -1}, {**valid, 'pid': -1},
                   {**valid, 'process_start_time': 0}, {**valid, 'token': None},
                   {**valid, 'url': 'http://untrusted.example:8765/mcp'}]
        for index, record in enumerate(records):
            (directory / f'{index}.json').write_text(json.dumps(record))
        (directory / 'broken.json').write_text('{')
        assert len(discover_mcp_servers(roots)) == 2
    # The process remains alive, but its MCP listener has gone away.
    assert discover_mcp_servers(roots) == []


def test_discovery_identifies_a_separate_process(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    source = '''
import json, os, socket, sys
from pathlib import Path
import psutil
listener = socket.create_server(('127.0.0.1', 0))
directory = Path(sys.argv[1]) / 'logs/mcp'
directory.mkdir(parents=True)
record = {'url': f'http://127.0.0.1:{listener.getsockname()[1]}/mcp',
          'token': 'child-token', 'pid': os.getpid(),
          'process_start_time': psutil.Process().create_time()}
(directory / 'connection.json').write_text(json.dumps(record))
print('ready', flush=True)
sys.stdin.readline()
listener.close()
'''
    child = subprocess.Popen([sys.executable, '-u', '-c', source, str(tmp_path)],
                             cwd=Path(__file__).resolve().parents[1],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
    try:
        assert child.stdout.readline().strip() == 'ready'
        servers = discover_mcp_servers(tmp_path)
        assert len(servers) == 1
        import psutil
        # Windows venv launchers can spawn the actual Python interpreter.
        assert servers[0]['pid'] in {child.pid, *(p.pid for p in psutil.Process(child.pid).children(recursive=True))}
        assert servers[0]['token'] == 'child-token'
        child.communicate('\n', timeout=10)
        assert child.returncode == 0
        assert discover_mcp_servers(tmp_path) == []
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)
