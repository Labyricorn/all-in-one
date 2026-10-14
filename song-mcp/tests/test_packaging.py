import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package_dev import package


def test_reproducible_package_excludes_runtime_and_contains_contracts(tmp_path):
    first = package(tmp_path / 'first.zip'); second = package(tmp_path / 'second.zip')
    assert first['sha256'] == second['sha256']
    with zipfile.ZipFile(first['path']) as archive:
        names = archive.namelist()
        assert 'song-mcp/schemas/correction.schema.json' in names
        assert 'desktop/src/playback.mjs' in names
        assert 'desktop/src/app.js' in names
        assert 'desktop/src/app.css' in names
        assert 'desktop/app.html' in names
        assert all(not any(part in name for part in ('.venv/', 'model-cache/', '__pycache__/', 'song-jobs/', 'song-projects/')) for name in names)
        manifest = json.loads(archive.read('PACKAGE-MANIFEST.json'))
        assert manifest['kind'] == 'existing-runtime-companion'
