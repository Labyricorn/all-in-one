"""Read-only runtime diagnostics. No model downloads or environment mutation."""
import argparse
import importlib.metadata
import json
import shutil
import subprocess
import sys

from common import ROOT, ANALYZER, ANALYZER_PYTHON, MODEL_CACHE


def report(check_imports=False):
    checks = {'lyric_python': sys.executable, 'runtime_root': str(ROOT),
              'analyzer_python_present': ANALYZER_PYTHON.is_file(), 'analyzer_cli_present': ANALYZER.is_file(),
              'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe'),
              'model_cache_present': MODEL_CACHE.is_dir(), 'device': 'cpu'}
    for name in ('mcp', 'uvicorn', 'starlette', 'jsonschema', 'whisperx', 'faster-whisper'):
        try: checks[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: checks[name] = None
    if check_imports:
        for name, interpreter, code in [('analyzer_import', ANALYZER_PYTHON, 'import allin1,demucs,natten'),
                                        ('lyric_import', sys.executable, 'import whisperx,faster_whisper')]:
            try:
                proc = subprocess.run([str(interpreter), '-c', code], capture_output=True, text=True, timeout=90)
                checks[name] = {'ok': proc.returncode == 0, 'diagnostic': proc.stderr[-3000:]}
            except (OSError, subprocess.TimeoutExpired) as error: checks[name] = {'ok': False, 'diagnostic': str(error)}
    checks['ok'] = bool(checks['analyzer_python_present'] and checks['analyzer_cli_present'] and checks['ffmpeg'] and checks['ffprobe'] and all(checks[name] for name in ('mcp', 'uvicorn', 'starlette', 'jsonschema')))
    if check_imports: checks['ok'] &= checks['analyzer_import']['ok'] and checks['lyric_import']['ok']
    return checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--imports', action='store_true')
    value = report(parser.parse_args().imports)
    print(json.dumps(value, indent=2))
    raise SystemExit(0 if value['ok'] else 1)
