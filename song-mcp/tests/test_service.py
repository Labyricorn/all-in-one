"""Real HTTP and MCP handshakes against an independent local service process."""
import asyncio
import json
import os
import subprocess
import sys
import time
import io
import wave
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_projects import fixture, correction
from core.projects import ProjectStore


@pytest.fixture
def service(tmp_path):
    discovery = tmp_path / 'service.json'
    env = dict(os.environ, MGMV_WORKSPACE_ROOT=str(tmp_path), MGMV_PROJECT_ROOT=str(tmp_path / 'projects'))
    source = Path(__file__).resolve().parents[1]
    with (tmp_path / 'service.log').open('w') as log:
        process = subprocess.Popen([sys.executable, str(source / 'service.py'), '--discovery', str(discovery)], env=env, stdout=log, stderr=log)
        try:
            started = time.monotonic()
            while time.monotonic() - started < 15:
                if process.poll() is not None: pytest.fail((tmp_path / 'service.log').read_text())
                if discovery.is_file():
                    record = json.loads(discovery.read_text())
                    try:
                        urllib.request.urlopen(record['url'] + '/health', timeout=1).close()
                        break
                    except OSError: pass
                time.sleep(.05)
            else: pytest.fail('Service did not become healthy.')
            yield record, tmp_path, process, env
        finally:
            process.terminate(); process.wait(timeout=10)


def request(record, path, body=None, extra=None):
    headers = {'Authorization': 'Bearer ' + record['token'], 'Content-Type': 'application/json', **(extra or {})}
    req = urllib.request.Request(record['url'] + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


def test_http_security_conflicts_and_durable_events(service):
    record, root, process, env = service
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(record['url'] + '/api/v1/projects')
    assert error.value.code == 401
    with pytest.raises(urllib.error.HTTPError) as error:
        request(record, '/api/v1/projects', extra={'Origin': 'https://untrusted.example'})
    assert error.value.code == 403
    path = root / 'analysis.json'; path.write_text(json.dumps(fixture()))
    opened = request(record, '/api/v1/projects', {'analysis_path': str(path)})
    project = request(record, '/api/v1/projects/' + opened['project_id'])
    word = project['analysis']['lyrics']['words'][0]['id']
    edit = correction(project, [{'op': 'replace_word', 'word_id': word, 'text': 'changed'}])
    assert request(record, '/api/v1/projects/' + opened['project_id'] + '/corrections', edit)['revision'] == 1
    with pytest.raises(urllib.error.HTTPError) as error:
        request(record, '/api/v1/projects/' + opened['project_id'] + '/corrections', {**edit, 'transaction_id': 'stale'})
    assert error.value.code == 409
    assert ProjectStore(root / 'projects').read(opened['project_id'])['revision'] == 1
    req = urllib.request.Request(record['url'] + '/api/v1/events?after=1', headers={'Authorization': 'Bearer ' + record['token']})
    with urllib.request.urlopen(req, timeout=3) as response:
        assert response.readline().strip() == b'id: 2'
        assert response.readline().strip() == b'event: revision'
    second = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'service.py'), '--discovery', str(root / 'service.json')], env=env, capture_output=True, text=True, timeout=5)
    assert second.returncode == 0 and 'already running' in second.stdout


def test_browser_file_import_uses_shared_store(service):
    record, root, process, env = service
    raw = fixture()
    opened = request(record, '/api/v1/projects', {'analysis_data': raw})
    stored = request(record, '/api/v1/projects/' + opened['project_id'])
    assert stored['analysis']['lyrics']['words'][0]['text'] == 'hi'
    assert stored['revision'] == 0
    listed = request(record, '/api/v1/projects')['projects']
    assert listed[0]['name'] == 'unavailable'
    with pytest.raises(urllib.error.HTTPError) as error:
        request(record, '/api/v1/projects', {'analysis_data': []})
    assert error.value.code == 400
    assert len(request(record, '/api/v1/projects')['projects']) == 1


def test_browser_audio_upload_validates_and_retains_local_media(service):
    record, root, process, env = service
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b'\x00\x00' * 8000)
    data = audio.getvalue()
    headers = {'Authorization': 'Bearer ' + record['token'],
               'Content-Type': 'application/octet-stream', 'X-Filename': '../fixture.wav'}
    upload = urllib.request.Request(record['url'] + '/api/v1/media', data=data, headers=headers)
    with urllib.request.urlopen(upload, timeout=10) as response:
        assert response.status == 201
        result = json.load(response)
    path = Path(result['path'])
    assert path.is_relative_to(root / 'song-inputs')
    assert path.name == 'input-fixture.wav'
    assert path.read_bytes() == data
    assert result['duration_seconds'] == 1
    bad = urllib.request.Request(record['url'] + '/api/v1/media', data=b'broken', headers=headers)
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(bad, timeout=10)
    assert error.value.code == 400
    assert len(list((root / 'song-inputs').iterdir())) == 1
    anonymous = urllib.request.Request(record['url'] + '/api/v1/media', data=data)
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(anonymous, timeout=10)
    assert error.value.code == 401


def test_live_http_mcp_reads_and_proposes_same_revision(service):
    record, root, process, env = service
    path = root / 'analysis.json'; path.write_text(json.dumps(fixture()))
    opened = request(record, '/api/v1/projects', {'analysis_path': str(path)})

    async def verify():
        import httpx2
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + record['token']}) as client:
            async with streamable_http_client(record['mcp_url'], http_client=client) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert 'propose_correction' in [tool.name for tool in tools.tools]
                    result = await session.call_tool('read_project', {'project_id': opened['project_id'], 'component': 'words'})
                    assert not result.is_error
                    key = result.structured_content['items'][0]['id']
                    edit = correction({**opened, 'revision': 0}, [{'op': 'replace_word', 'word_id': key, 'text': 'mcp'}])
                    proposed = await session.call_tool('propose_correction', {'project_id': opened['project_id'], 'correction': edit})
                    assert not proposed.is_error
                    assert ProjectStore(root / 'projects').read(opened['project_id'])['revision'] == 0
                    accepted = await session.call_tool('accept_correction', {'proposal_id': proposed.structured_content['proposal_id']})
                    assert not accepted.is_error and accepted.structured_content['revision'] == 1
                    stale = await session.call_tool('apply_correction', {'project_id': opened['project_id'], 'correction': {**edit, 'transaction_id': 'stale-mcp'}})
                    assert stale.is_error and 'Stale project revision' in stale.content[0].text
                    result = await session.call_tool('read_project', {'project_id': opened['project_id'], 'component': 'words'})
                    assert result.structured_content['items'][0]['text'] == 'mcp'
    asyncio.run(asyncio.wait_for(verify(), 20))


def test_cancellation_retains_diagnostics_and_releases_shared_slot(service):
    import psutil
    record, root, _, _ = service
    key = 'a' * 32; directory = root / 'song-jobs' / key; directory.mkdir(parents=True)
    worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        (directory / 'process.json').write_text(json.dumps({'pid': worker.pid, 'created': psutil.Process(worker.pid).create_time()}))
        (directory / 'status.json').write_text(json.dumps({'job_id': key, 'status': 'running', 'stage': 'fixture', 'updated': time.time()}))
        (directory.parent / 'active.lock').write_text(key)
        (directory / 'worker.log').write_text('retained fixture diagnostics')
        response = request(record, '/api/v1/jobs/' + key + '/cancel', {})
        assert response['status'] == 'cancelled'
        worker.wait(timeout=5)
        assert not (directory.parent / 'active.lock').exists()
        assert (directory / 'worker.log').read_text() == 'retained fixture diagnostics'
    finally:
        if worker.poll() is None: worker.terminate(); worker.wait(timeout=5)
