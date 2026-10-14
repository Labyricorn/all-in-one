"""Real stdio handshake, detached job, reconnect, and paged tool-call tests."""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT
from configure_client import configuration
PARAMS = StdioServerParameters(**configuration())


def payload(result):
    assert not result.is_error, result
    return result.structured_content or json.loads(result.content[0].text)


async def main(path, mode, text=None):
    async with stdio_client(PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            handshake = await session.initialize()
            listing = await session.list_tools()
            names = [t.name for t in listing.tools]
            assert {'submit_song', 'get_job', 'get_analysis', 'get_song_map'} <= set(names)
            info = payload(await session.call_tool('server_info', {}))
            invalid = await session.call_tool('submit_song', {'path': 'https://example.com/no.wav'})
            assert invalid.is_error
            arguments = {'path': str(Path(path).resolve()), 'lyrics_mode': mode, 'music_model': 'harmonix-fold0', 'lyric_model': 'tiny', 'language': 'en'}
            if text is not None:
                arguments['lyrics_text'] = text
            submitted = payload(await session.call_tool('submit_song', arguments))
            job_id = submitted['job_id']
    # Connection closes here. Computation must continue independently.
    async with stdio_client(PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for _ in range(240):
                state = payload(await session.call_tool('get_job', {'job_id': job_id}))
                if state['status'] not in ('queued', 'running'):
                    break
                await asyncio.sleep(2)
            assert state['status'] == 'complete', state
            overview = payload(await session.call_tool('get_analysis', {'job_id': job_id}))
            songmap = payload(await session.call_tool('get_song_map', {'job_id': job_id}))
            words = payload(await session.call_tool('get_analysis', {'job_id': job_id, 'component': 'lyric_words', 'limit': 5}))
            bars = payload(await session.call_tool('get_analysis', {'job_id': job_id, 'component': 'bars', 'limit': 2}))
            assert overview['timebase']['offset_seconds'] == 0
            if mode == 'align':
                full = json.loads(Path(state['analysis_path']).read_text(encoding='utf-8'))
                assert full['lyrics']['text'] == text
                assert len(full['lyrics']['words']) == len(text.split())
                assert any(w['start'] is not None for w in full['lyrics']['words'])
            report = {'handshake': handshake.model_dump(mode='json'), 'tools': names, 'server_info': info, 'job': state, 'overview': overview, 'song_map': songmap, 'first_words': words, 'first_bars': bars, 'survived_client_disconnect': True}
            destination = ROOT / 'verification' / ('mcp-' + mode + '.json')
            destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'status': 'passed', 'mode': mode, 'job_id': job_id, 'report': str(destination)}))


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1], sys.argv[2], Path(sys.argv[3]).read_text(encoding='utf-8') if len(sys.argv) > 3 else None))
