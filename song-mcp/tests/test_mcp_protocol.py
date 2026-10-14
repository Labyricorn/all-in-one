import asyncio
import json
import os
from pathlib import Path

import tomli
import sys
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'song-mcp'))
from configure_client import render


async def check(parameters):
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) >= 6
            response = await session.call_tool('server_info', {})
            assert not response.is_error
            info = response.structured_content
            assert info['lyric_engine'] == 'faster-whisper ASR + WhisperX CTC alignment'
            response = await session.call_tool('submit_song', {'path': 'relative.mp3'})
            assert response.is_error
            assert 'absolute' in response.content[0].text
            response = await session.call_tool('get_job', {'job_id': '../escape'})
            assert response.is_error
            assert 'Invalid job ID' in response.content[0].text


def test_project_config():
    config = tomli.loads(render('toml'))['mcp_servers']['mgmv_song']
    asyncio.run(asyncio.wait_for(check(StdioServerParameters(command=config['command'], args=config['args'], cwd=config['cwd'], env=dict(os.environ, **config['env']))), 30))


def test_generic_config():
    config = json.loads(render('json'))['mcpServers']['mgmv_song']
    asyncio.run(asyncio.wait_for(check(StdioServerParameters(**{**config, 'env': dict(os.environ, **config['env'])})), 30))


@pytest.mark.skipif(os.name != 'nt', reason='Windows .cmd launcher')
def test_launcher():
    asyncio.run(asyncio.wait_for(check(StdioServerParameters(command='cmd.exe', args=['/d', '/c', str(ROOT / 'song-mcp.cmd')], cwd=str(ROOT), env=dict(os.environ, MGMV_SONG_PYTHON=sys.executable))), 30))
