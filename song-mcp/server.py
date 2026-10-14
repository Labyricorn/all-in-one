"""Stdio MCP control plane: heavy computation never blocks a tool call."""
import os
import subprocess
import sys
import time
import uuid
import math
from functools import wraps
from typing import Literal, Any

import psutil
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from common import JOBS, ROOT, ANALYZER, worker_command, acquire_slot, job_dir, probe_media, read_json, release_slot, status, write_json
from songmap import planning_page

mcp = MCPServer('MGMV Song Analysis', version='1.0', instructions='Submit local audio/video with submit_song; poll get_job until complete or partial; retrieve get_song_map and paged get_analysis. All timings are seconds from original decoded audio start. Lyrics and singing word timings are estimates: review them, retain null timings, and do not invent lyrics or emotional interpretations. You author the motion-graphics video plan; this server does not render it.')


def tool_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, subprocess.TimeoutExpired, psutil.Error) as error:
            raise ToolError(str(error)) from error
    return wrapped


@mcp.tool(structured_output=True)
@tool_errors
def server_info() -> dict[str, Any]:
    """Check installed backends and supported workflow without downloading models."""
    return {'name': 'MGMV Song Analysis', 'version': '1.0', 'device': 'cpu', 'job_directory': str(JOBS), 'analyzer_present': ANALYZER.is_file(), 'lyric_engine': 'faster-whisper ASR + WhisperX CTC alignment', 'lyric_models': ['tiny', 'base', 'small', 'medium'], 'default_lyric_model': 'base', 'modes': ['auto', 'align', 'instrumental', 'none'], 'network': 'Public model weights download on first use; song media and lyrics remain local.', 'workflow': ['submit_song', 'get_job', 'get_song_map', 'get_analysis']}


@mcp.tool(structured_output=True)
@tool_errors
def submit_song(path: str, lyrics_mode: Literal['auto', 'align', 'instrumental', 'none'] = 'auto', lyrics_text: str | None = None, language: str | None = None, lyric_model: Literal['tiny', 'base', 'small', 'medium'] = 'base', music_model: Literal['harmonix-all', 'harmonix-fold0'] = 'harmonix-all', offline: bool = False) -> dict[str, Any]:
    """Start a persistent background job for an absolute local audio/video file.

    auto transcribes separated vocals as unverified lyric candidates. align requires
    correct lyrics_text (line breaks define phrases) and an explicit language code
    such as en; text is preserved and failed word timings are null. instrumental is
    a user declaration, never inferred from empty ASR. none skips lyric processing.
    CPU jobs run one at a time and survive MCP disconnects. Poll get_job; do not
    keep this tool call open awaiting analysis. No video rendering is performed.
    Set offline=true to require cached models and prevent model-network access.
    """
    source, probe = probe_media(path)
    if lyrics_mode == 'align' and (not lyrics_text or not lyrics_text.strip() or not language):
        raise ValueError('Alignment requires nonempty lyrics_text and a language code, for example en.')
    if lyrics_mode != 'align' and lyrics_text is not None:
        raise ValueError('Supplied lyrics require lyrics_mode=align; they will not be silently ignored.')
    if lyrics_text is not None and len(lyrics_text) > 100000:
        raise ValueError('Lyrics exceed the 100,000 character limit.')
    if language is not None:
        from faster_whisper.tokenizer import _LANGUAGE_CODES
        if language not in _LANGUAGE_CODES:
            raise ValueError('Unsupported language code. Use a Whisper language code such as en, es, or ja.')
    job_id = uuid.uuid4().hex
    acquire_slot(job_id)
    directory = JOBS / job_id
    try:
        directory.mkdir()
        write_json(directory / 'request.json', {'path': str(source), 'probe': probe, 'lyrics_mode': lyrics_mode, 'lyrics_text': lyrics_text, 'language': language, 'lyric_model': lyric_model, 'music_model': music_model, 'offline': offline})
        write_json(directory / 'status.json', {'job_id': job_id, 'status': 'queued', 'stage': 'starting_worker', 'created': time.time(), 'updated': time.time(), 'source': str(source), 'log_path': str(directory / 'worker.log')})
        env = dict(os.environ, OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
        if os.name == 'nt':
            # MCP clients may taskkill /T their stdio process tree on disconnect.
            # WMI creates a hidden worker owned by WmiPrvSE rather than this server,
            # so long CPU jobs survive that client cleanup as well as reconnects.
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                service = win32com.client.GetObject(r'winmgmts:\\.\root\cimv2')
                process = service.Get('Win32_Process')
                startup = service.Get('Win32_ProcessStartup').SpawnInstance_()
                startup.ShowWindow = 0
                parameters = process.Methods_('Create').InParameters.SpawnInstance_()
                parameters.CommandLine = subprocess.list2cmdline(worker_command(job_id, detached=True))
                parameters.CurrentDirectory = str(ROOT)
                parameters.ProcessStartupInformation = startup
                launched = service.ExecMethod('Win32_Process', 'Create', parameters)
                if launched.ReturnValue != 0:
                    raise RuntimeError('Windows could not start a detached worker (WMI error ' + str(launched.ReturnValue) + ').')
                pid = launched.ProcessId
                launched = parameters = startup = process = service = None
            finally:
                pythoncom.CoUninitialize()
        else:
            with (directory / 'worker.log').open('ab') as log:
                proc = subprocess.Popen(worker_command(job_id), stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=str(ROOT), env=env, start_new_session=True)
                pid = proc.pid
        write_json(directory / 'process.json', {'pid': pid, 'created': psutil.Process(pid).create_time()})
        return {'job_id': job_id, 'status': 'queued', 'next_tool': 'get_job', 'poll_after_seconds': 5, 'output_directory': str(directory)}
    except Exception as error:
        if (directory / 'status.json').is_file():
            value = read_json(directory / 'status.json')
            value.update(status='failed', stage='worker_launch_failed', updated=time.time(), error=f'{type(error).__name__}: {error}')
            write_json(directory / 'status.json', value)
        release_slot(job_id)
        raise ToolError('Could not launch the analysis worker: ' + str(error)) from error


@mcp.tool(structured_output=True)
@tool_errors
def get_job(job_id: str) -> dict[str, Any]:
    """Get progress/errors immediately. complete and partial permit result retrieval."""
    result = status(job_id)
    directory = job_dir(job_id)
    if result['status'] in ('failed', 'partial') and (directory / 'worker.log').is_file():
        with (directory / 'worker.log').open('rb') as file:
            file.seek(max(0, file.seek(0, 2) - 5000))
            result['diagnostic_log_tail'] = file.read().decode('utf-8', errors='replace')
    return result


@mcp.tool(structured_output=True)
@tool_errors
def list_jobs(limit: int = 20) -> dict[str, Any]:
    """Find durable job IDs after reconnecting; newest jobs first."""
    if not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100.')
    paths = sorted(JOBS.glob('*/status.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    return {'jobs': [status(p.parent.name) for p in paths[:limit]], 'total': len(paths)}


def result_for(job_id):
    state = status(job_id)
    if state['status'] not in ('complete', 'partial'):
        raise ValueError('Analysis is not available yet; job status is ' + state['status'] + '. Use get_job for diagnostics.')
    return read_json(job_dir(job_id) / 'analysis.json')


@mcp.tool(structured_output=True)
@tool_errors
def get_analysis(job_id: str, component: Literal['overview', 'beats', 'bars', 'sections', 'lyric_words', 'lyric_phrases'] = 'overview', offset: int = 0, limit: int = 100, start_seconds: float = 0, end_seconds: float | None = None) -> dict[str, Any]:
    """Retrieve facts in bounded pages, including actual word records and null timings.

    overview supplies timebase, provenance and warnings. Arrays can be filtered by
    audio-relative time; untimed lyric records are retained in every time filter.
    The full combined JSON is available at analysis_path in get_job.
    """
    if offset < 0 or not 1 <= limit <= 500 or start_seconds < 0 or not math.isfinite(start_seconds) or (end_seconds is not None and not math.isfinite(end_seconds)):
        raise ValueError('offset/start must be nonnegative and limit must be 1..500.')
    result = result_for(job_id)
    end = result['duration_seconds'] if end_seconds is None else end_seconds
    if end <= start_seconds:
        raise ValueError('end_seconds must exceed start_seconds.')
    if component == 'overview':
        return {k: result[k] for k in ('schema_version', 'source', 'duration_seconds', 'timebase', 'tempo', 'warnings')} | {'lyrics': {k: v for k, v in result['lyrics'].items() if k not in ('words', 'phrases', 'text')}, 'counts': {k: len(result[k]) for k in ('beats', 'bars', 'sections')}, 'lyric_word_count': len(result['lyrics']['words'])}
    rows = result['lyrics']['words' if component == 'lyric_words' else 'phrases'] if component.startswith('lyric_') else result[component]
    rows = [row for row in rows if (row.get('time', row.get('start')) is None or (row.get('end', row.get('time', row.get('start'))) >= start_seconds and row.get('time', row.get('start')) < end))]
    return {'component': component, 'unit': 'seconds_from_original_audio_start', 'items': rows[offset:offset + limit], 'total_in_window': len(rows), 'next_offset': offset + limit if offset + limit < len(rows) else None}


@mcp.tool(structured_output=True)
@tool_errors
def get_song_map(job_id: str, start_seconds: float = 0, end_seconds: float | None = None, offset: int = 0, limit: int = 20) -> dict[str, Any]:
    """Get compact section/bar/lyric facts for writing a motion-graphics video plan.

    Results are paged by section; lyric phrases are estimated and untimed lines
    are explicitly separated. Use get_analysis for words or exact beat/bar arrays.
    """
    if offset < 0 or not 1 <= limit <= 50 or start_seconds < 0 or not math.isfinite(start_seconds) or (end_seconds is not None and not math.isfinite(end_seconds)):
        raise ValueError('offset/start must be nonnegative and limit must be 1..50.')
    result = result_for(job_id)
    end = result['duration_seconds'] if end_seconds is None else end_seconds
    if end <= start_seconds:
        raise ValueError('end_seconds must exceed start_seconds.')
    return planning_page(result, start_seconds, end, offset, limit)


if __name__ == '__main__':
    mcp.run(transport='stdio')
