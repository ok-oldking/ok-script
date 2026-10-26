import asyncio
import json
from types import SimpleNamespace

import pytest

from ok.core.mcp_server import LocalMcpServer, create_mcp_app
from ok.util.handler import ExitEvent
from test_mcp_runner import development, write_task, register_task


@pytest.mark.parametrize('mode', ['auto', 'legacy'])
def test_http_connection_and_tools_end_to_end(development, mode):
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
    server.runner.prepare = None  # Real executor, fake target device.
    path = write_task(dev.root, "self.log_info('MCP call succeeded')")
    server.start()
    connection = json.loads((server.runner.artifact_directory / 'connection.json').read_text())

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
                    'list_skills', 'get_skill', 'list_tasks', 'reload_tasks'}
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

    try:
        asyncio.run(exercise())
    finally:
        server.stop()
        server.join()
    assert not server._thread.is_alive()


def test_missing_optional_sdk_has_install_instructions(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'mcp', None)
    monkeypatch.setitem(sys.modules, 'mcp.server', None)
    with pytest.raises(RuntimeError, match=r'ok-script\[mcp\]'):
        create_mcp_app(None, 'test-token', 8765)
