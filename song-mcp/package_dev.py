"""Package maintained source for use with existing environments (not an installer)."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def package(target):
    repo = Path(__file__).resolve().parents[1]
    files = []
    for folder in ('song-mcp', 'desktop'):
        for path in (repo / folder).rglob('*'):
            if path.is_file() and not path.name.startswith('client-config') and not any(part in ('.venv', '__pycache__', '.pytest_cache', 'model-cache', 'node_modules') for part in path.relative_to(repo).parts) and path.suffix in ('.py', '.md', '.txt', '.json', '.mjs', '.js', '.css', '.html'):
                files.append(path)
    files += [repo / name for name in ('song-service.cmd', 'song-project.cmd', 'analyze-song.cmd', 'song-mcp.cmd', 'LICENSE', 'ATTRIBUTION.md', 'SETUP.md')]
    manifest = {str(path.relative_to(repo)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    target = Path(target).resolve(); target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            # Fixed zip metadata makes repeated builds reproducible.
            entry = zipfile.ZipInfo(str(path.relative_to(repo)).replace('\\', '/'), (2026, 10, 13, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())
        archive.writestr(zipfile.ZipInfo('PACKAGE-MANIFEST.json', (2026, 10, 13, 0, 0, 0)), json.dumps({'kind': 'existing-runtime-companion', 'schema_version': 1, 'files': manifest}, indent=2))
    return {'path': str(target), 'files': len(files), 'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(json.dumps(package(parser.parse_args().output), indent=2))
