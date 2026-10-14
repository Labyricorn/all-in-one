"""Persistent jobs and strict local media validation (no heavyweight imports)."""
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import psutil

SOURCE_DIR = Path(__file__).resolve().parent
REPO = SOURCE_DIR.parent
ROOT = Path(os.environ.get('MGMV_WORKSPACE_ROOT', REPO)).resolve()
ANALYZER_ROOT = Path(os.environ.get('MGMV_ANALYZER_ROOT', REPO)).resolve()
MODEL_CACHE = Path(os.environ.get('MGMV_MODEL_CACHE', SOURCE_DIR / 'model-cache')).resolve()
JOBS = ROOT / 'song-jobs'
ANALYZER_PYTHON = ANALYZER_ROOT / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
ANALYZER = ANALYZER_ROOT / ('.venv/Scripts/allin1.exe' if os.name == 'nt' else '.venv/bin/allin1')


def worker_command(job_id, detached=False):
    # WMI does not inherit the MCP server's environment. Pass runtime locations
    # explicitly so detached jobs use the same lock, caches and environments.
    import sys
    command = [sys.executable, '-u', str(SOURCE_DIR / 'worker.py'), job_id,
               '--runtime-root', str(ROOT), '--analyzer-root', str(ANALYZER_ROOT),
               '--model-cache', str(MODEL_CACHE)]
    if detached:
        command.append('--detached')
    return command
SUFFIXES = {'.wav', '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.aiff', '.aif', '.wma', '.mp4', '.mov', '.mkv', '.webm', '.avi'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def job_dir(job_id):
    if not re.fullmatch(r'[0-9a-f]{32}', job_id):
        raise ValueError('Invalid job ID; use the ID returned by submit_song.')
    path = JOBS / job_id
    if not path.is_dir():
        raise ValueError('Unknown job ID.')
    return path


def probe_media(path):
    if not isinstance(path, str) or not path or '://' in path or path.startswith('\\\\'):
        raise ValueError('Provide an existing absolute local audio/video file path, not a URL or network share.')
    source = Path(path)
    if not source.is_absolute() or not source.is_file():
        raise ValueError('Audio/video path must be an absolute path to an existing file.')
    source = source.resolve()
    if source.suffix.lower() not in SUFFIXES:
        raise ValueError('Unsupported file extension. Use an audio/video file such as WAV, MP3, FLAC, MP4, or MOV.')
    proc = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_streams', '-show_format', '-of', 'json', str(source)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    if proc.returncode:
        raise ValueError('FFprobe could not read this media: ' + proc.stderr[-1500:])
    meta = json.loads(proc.stdout)
    audio = next((s for s in meta.get('streams', []) if s.get('codec_type') == 'audio'), None)
    if audio is None:
        raise ValueError('This file has no decodable audio stream.')
    return source, {'audio_stream_index': audio['index'], 'container_start_seconds': meta.get('format', {}).get('start_time'), 'audio_stream_start_seconds': audio.get('start_time'), 'container_duration_seconds': meta.get('format', {}).get('duration')}


def alive(path):
    try:
        info = read_json(path / 'process.json')
        p = psutil.Process(info['pid'])
        return p.is_running() and abs(p.create_time() - info['created']) < 1
    except (OSError, ValueError, psutil.Error):
        return False


def status(job_id):
    path = job_dir(job_id)
    value = read_json(path / 'status.json')
    if value['status'] in ('queued', 'running') and not alive(path) and time.time() - value['updated'] > 30:
        value.update(status='failed', stage='worker_lost', error='The background worker exited unexpectedly. See the job log; submit a new job to retry.', updated=time.time())
        write_json(path / 'status.json', value)
    return value


def acquire_slot(job_id):
    JOBS.mkdir(exist_ok=True)
    lock = JOBS / 'active.lock'
    for _ in range(2):
        try:
            with lock.open('x', encoding='utf-8') as file:
                file.write(job_id)
            return
        except FileExistsError:
            current = lock.read_text(encoding='utf-8').strip()
            try:
                old = status(current)
                if old['status'] in ('queued', 'running'):
                    raise ValueError('CPU analysis is already running. Poll job ' + current + ' before submitting another song.')
            except ValueError as error:
                if str(error).startswith('CPU analysis'):
                    raise
                # A newly created lock can precede its job directory briefly.
                if time.time() - lock.stat().st_mtime < 30:
                    raise ValueError('Another job is being submitted. Retry shortly.') from error
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
    raise ValueError('Could not acquire the analysis slot; retry.')


def release_slot(job_id):
    lock = JOBS / 'active.lock'
    try:
        if lock.read_text(encoding='utf-8').strip() == job_id:
            lock.unlink()
    except FileNotFoundError:
        pass
