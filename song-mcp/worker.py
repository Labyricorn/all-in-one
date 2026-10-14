"""Detached CPU analysis, with durable status and per-job logs."""
import os
import subprocess
import sys
import time
import traceback
import hashlib
import shutil
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

# Configure paths before importing common (including WMI-launched workers).
for flag, variable in [('--runtime-root', 'MGMV_WORKSPACE_ROOT'),
                       ('--analyzer-root', 'MGMV_ANALYZER_ROOT'),
                       ('--model-cache', 'MGMV_MODEL_CACHE')]:
    if flag in sys.argv:
        os.environ[variable] = sys.argv[sys.argv.index(flag) + 1]

from common import ANALYZER, ANALYZER_PYTHON, SOURCE_DIR, MODEL_CACHE, ROOT, job_dir, read_json, release_slot, write_json
from lyrics import run_lyrics
from songmap import combine


def fingerprint(file):
    value=hashlib.sha256()
    with Path(file).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def main(job_id):
    path = job_dir(job_id)
    request = read_json(path / 'request.json')
    if request.get('offline'):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
    state = read_json(path / 'status.json')

    def update(stage, status='running', **extra):
        state.update(stage=stage, status=status, updated=time.time(), **extra)
        write_json(path / 'status.json', state)

    try:
        update('decode_original_audio')
        source = Path(request['path'])
        if request.get('source_sha256') and fingerprint(source)!=request['source_sha256']:
            raise ValueError('Source audio changed after submission; retry with the current file.')
        original = path / 'original.wav'
        # Resampling changes sample count but never trims silence or resets chunks.
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe', '-i', str(source), '-map', '0:' + str(request['probe']['audio_stream_index']), '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', str(original)], check=True, stdout=sys.stdout, stderr=sys.stderr)
        if request.get('source_sha256') and fingerprint(source)!=request['source_sha256']:
            raise ValueError('Source audio changed during decoding; refusing mixed-timebase output.')
        import soundfile as sf
        duration = sf.info(original).duration
        if duration <= .1:
            raise ValueError('Audio is too short to analyze.')
        if request.get('reuse_stems_job'):
            previous=job_dir(request['reuse_stems_job'])
            old=read_json(previous/'request.json')
            stems=['bass.wav','drums.wav','other.wav','vocals.wav']
            origin=previous/'demix/htdemucs/original'
            if old.get('source_sha256')==request.get('source_sha256') and (previous/'original.wav').is_file() and fingerprint(previous/'original.wav')==fingerprint(original) and all((origin/name).is_file() and abs(sf.info(origin/name).duration-duration)<.05 for name in stems):
                target=path/'demix/htdemucs/original';target.mkdir(parents=True,exist_ok=True)
                for name in stems:
                    try:os.link(origin/name,target/name)
                    except OSError:shutil.copy2(origin/name,target/name)
                print('Reusing separated stems: matching source SHA-256 and decoded WAV hash.',flush=True)
        update('music_structure_and_demixing', duration_seconds=duration)
        if request.get('reuse_structure'):
            subprocess.run([str(ANALYZER_PYTHON),str(SOURCE_DIR/'analyzer_stage.py'),str(path)],check=True,cwd=str(ROOT),stdout=sys.stdout,stderr=sys.stderr)
        else:
            subprocess.run([str(ANALYZER), str(original), '-o', str(path / 'music'), '--demix-dir', str(path / 'demix'), '--spec-dir', str(path / 'spec'), '-k', '--no-multiprocess', '-d', 'cpu', '-m', request['music_model']], check=True, cwd=str(ROOT), stdout=sys.stdout, stderr=sys.stderr)
        music = read_json(path / 'music/original.json')
        update('lyrics_' + request['lyrics_mode'])
        lyric_audio = path / 'demix/htdemucs/original/vocals.wav'
        try:
            if request['lyrics_mode'] in ('auto','align') and abs(sf.info(lyric_audio).duration - duration) > .05:
                raise ValueError('Vocal-stem duration does not match the original audio; refusing a misleading combined timebase.')
            lyrics = run_lyrics(lyric_audio, duration, request['lyrics_mode'], request['lyrics_text'], request['language'], request['lyric_model'], MODEL_CACHE, offline=request.get('offline', False))
            lyrics['audio_basis'] = 'Demucs vocals stem; full duration preserved'
            lyrics['engine'] = 'faster-whisper ASR + WhisperX CTC alignment' if request['lyrics_mode'] in ('auto', 'align') else None
            completed = 'complete'
        except Exception as error:
            traceback.print_exc()
            from lyrics import convert_result
            lyrics = convert_result({'segments': [], 'language': request['language']}, duration, request['lyrics_text'] if request['lyrics_mode'] == 'align' else None)
            lyrics.update(status='failed', error=f'{type(error).__name__}: {error}')
            completed = 'partial'
        if request.get('lyrics_source_text') is not None:
            lyrics['alignment_text']=lyrics.get('text')
            lyrics['text']=request['lyrics_source_text']
            lyrics['annotations']=request.get('lyric_annotations',[])
        write_json(path / 'analysis.json', combine(music, lyrics, source, duration, request['probe']))
        update('finished', completed, analysis_path=str(path / 'analysis.json'))
    except Exception as error:
        traceback.print_exc()
        update('failed', 'failed', error=f'{type(error).__name__}: {error}')
    finally:
        release_slot(job_id)


if __name__ == '__main__':
    os.environ['OMP_NUM_THREADS'] = '4'
    os.environ['MKL_NUM_THREADS'] = '4'
    if '--detached' in sys.argv:
        with (job_dir(sys.argv[1]) / 'worker.log').open('a', encoding='utf-8', buffering=1) as log:
            with redirect_stdout(log), redirect_stderr(log):
                main(sys.argv[1])
    else:
        main(sys.argv[1])
