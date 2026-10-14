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
from core.requests import prepare_request
from core.projects import ProjectStore


def project_store():
    return ProjectStore(os.environ.get('MGMV_PROJECT_ROOT', str(ROOT / 'song-projects')))

mcp = MCPServer('MGMV Song Analysis', version='1.0', instructions='Submit local audio/video with submit_song; poll get_job until complete or partial; retrieve get_song_map and paged get_analysis. All timings are seconds from original decoded audio start. Lyrics and singing word timings are estimates: review them, retain null timings, and do not invent lyrics or emotional interpretations. You author the motion-graphics video plan; this server does not render it.')


def tool_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired, psutil.Error) as error:
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
    request = prepare_request(source, probe, lyrics_mode, lyrics_text, language, lyric_model, music_model, offline)
    job_id = uuid.uuid4().hex
    acquire_slot(job_id)
    directory = JOBS / job_id
    try:
        directory.mkdir()
        write_json(directory / 'request.json', request)
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


@mcp.tool(structured_output=True)
@tool_errors
def cancel_job(job_id: str) -> dict[str, Any]:
    """Cancel an explicitly selected active job; leave its partial artifacts and log for debugging."""
    directory = job_dir(job_id)
    value = status(job_id)
    if value['status'] not in ('queued', 'running'): return value
    info = read_json(directory / 'process.json')
    try:
        process = psutil.Process(info['pid'])
        if abs(process.create_time() - info['created']) >= 1: raise ValueError('Worker PID was reused; refusing to terminate an unrelated process.')
        children = process.children(recursive=True)
        for child in children: child.terminate()
        process.terminate()
        _, survivors = psutil.wait_procs([process, *children], timeout=5)
        for survivor in survivors: survivor.kill()
    except psutil.NoSuchProcess: pass
    value.update(status='cancelled', stage='cancelled', updated=time.time())
    write_json(directory / 'status.json', value)
    release_slot(job_id)
    return value


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


@mcp.tool(structured_output=True)
@tool_errors
def list_projects() -> dict[str, Any]:
    """List persistent editable projects shared with the GUI and CLI."""
    return {'projects': project_store().list()}


@mcp.tool(structured_output=True)
@tool_errors
def open_project(analysis_path: str | None = None, job_id: str | None = None) -> dict[str, Any]:
    """Import a combined analysis or completed job; retain raw predictions and cached PCM artifacts without separation."""
    if (analysis_path is None) == (job_id is None):
        raise ValueError('Supply exactly one of analysis_path or job_id.')
    artifacts = {}
    if job_id:
        result_for(job_id)
        directory = job_dir(job_id)
        analysis_path = str(directory / 'analysis.json')
        for role, relative in [('mix', 'original.wav'), ('vocals', 'demix/htdemucs/original/vocals.wav')]:
            if (directory / relative).is_file(): artifacts[role] = str(directory / relative)
    project = project_store().import_analysis(analysis_path, artifacts)
    return {k: v for k, v in project.items() if k != 'analysis'}


@mcp.tool(structured_output=True)
@tool_errors
def read_project(project_id: str, component: Literal['overview', 'words', 'lines', 'beats', 'sections', 'events', 'review_items', 'history', 'proposals'] = 'overview', offset: int = 0, limit: int = 100, revision: int | None = None) -> dict[str, Any]:
    """Read a project revision or bounded records with stable IDs for correction proposals."""
    if offset < 0 or not 1 <= limit <= 500: raise ValueError('offset >= 0 and limit 1..500 required.')
    store = project_store()
    project = store.read(project_id, revision)
    if component == 'overview': return {k: v for k, v in project.items() if k != 'analysis'}
    data = project['analysis']
    if component == 'proposals': rows = store.proposals(project_id)
    elif component == 'history': rows = store.history(project_id)
    elif component in ('words', 'lines'): rows = data['lyrics']['words' if component == 'words' else 'phrases']
    else: rows = data[component]
    return {'project_id': project_id, 'revision': project['revision'], 'items': rows[offset:offset + limit], 'total': len(rows), 'next_offset': offset + limit if offset + limit < len(rows) else None}


@mcp.tool(structured_output=True)
@tool_errors
def propose_correction(project_id: str, correction: dict[str, Any]) -> dict[str, Any]:
    """Save a validated suggestion for review, without changing the current project."""
    return project_store().propose(project_id, correction)


@mcp.tool(structured_output=True)
@tool_errors
def apply_correction(project_id: str, correction: dict[str, Any]) -> dict[str, Any]:
    """Apply an explicitly user-authorized correction; requires base revision/hash and retry-safe transaction_id."""
    return project_store().apply(project_id, correction, actor='mcp')


@mcp.tool(structured_output=True)
@tool_errors
def accept_correction(proposal_id: str) -> dict[str, Any]:
    """Apply a saved proposal only when explicitly authorized by the user. Stale proposals conflict."""
    return project_store().accept(proposal_id)


@mcp.tool(structured_output=True)
@tool_errors
def export_project(project_id: str, output_path: str, revision: int | None = None) -> dict[str, Any]:
    """Export reproducible corrected combined JSON while preserving raw project predictions."""
    return project_store().export(project_id, output_path, revision)


if __name__ == '__main__':
    mcp.run(transport='stdio')
