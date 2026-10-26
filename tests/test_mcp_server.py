import asyncio
import json
from types import SimpleNamespace

import pytest

from ok.core.mcp_server import LocalMcpServer, create_mcp_app
from ok.util.handler import ExitEvent
from test_mcp_runner import development, write_task


@pytest.mark.parametrize('mode', ['auto', 'legacy'])
def test_http_connection_and_tools_end_to_end(development, mode):
    pytest.importorskip('mcp')
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    dev = development
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
                    'list_skills', 'get_skill'}
                skills = await client.call_tool('list_skills')
                assert not skills.is_error, skills
                assert 'develop' in str(skills)
                skill = await client.call_tool('get_skill', {'skill_id': 'develop'})
                assert not skill.is_error, skill
                assert 'reset_to_start()' in skill.structured_content['content']
                resources = await client.list_resources()
                assert 'ok-script://skills/develop' in {str(r.uri) for r in resources.resources}
                resource = await client.read_resource('ok-script://skills/develop')
                assert resource.contents[0].text == skill.structured_content['content']
                unknown = await client.call_tool('get_skill', {'skill_id': '../setup.py'})
                assert unknown.is_error
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
