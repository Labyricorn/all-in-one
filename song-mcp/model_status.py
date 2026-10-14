"""Advisory report of which analysis models are already cached locally.

Nothing is downloaded or imported here; the studio uses the result to choose
safe defaults and to explain why an offline job could not start.
"""
import os
from pathlib import Path

from common import MODEL_CACHE

LYRIC_MODELS = ('tiny', 'base', 'small', 'medium')
MUSIC_FOLDS = tuple(f'harmonix-fold{i}' for i in range(8))


def hub_cache():
    """Hugging Face hub cache used by the music analyzer (its cache_dir is unset)."""
    if os.environ.get('HF_HUB_CACHE'):
        return Path(os.environ['HF_HUB_CACHE'])
    home = Path(os.environ['HF_HOME']) if os.environ.get('HF_HOME') else Path.home() / '.cache' / 'huggingface'
    return home / 'hub'


def snapshot_files(root, repo_dir):
    snapshots = Path(root) / repo_dir / 'snapshots'
    try:
        return {item.name for snapshot in snapshots.iterdir() if snapshot.is_dir() for item in snapshot.iterdir()}
    except OSError:
        return set()


def model_status(cache=MODEL_CACHE, hub=None):
    cache, hub = Path(cache), Path(hub) if hub else hub_cache()
    lyric = {name: bool(snapshot_files(cache, f'models--Systran--faster-whisper-{name}')) for name in LYRIC_MODELS}
    try:
        alignment = any(cache.glob('*.pth')) or any(cache.glob('models--*wav2vec2*'))
    except OSError:
        alignment = False
    files = snapshot_files(hub, 'models--taejunkim--allinone')
    folds = {fold: any(name.startswith(fold + '-') for name in files) for fold in MUSIC_FOLDS}
    music = {'harmonix-fold0': folds['harmonix-fold0'], 'harmonix-all': all(folds.values())}
    ready = alignment and any(lyric.values()) and any(music.values())
    return {'lyric_models': lyric, 'alignment_model': bool(alignment), 'music_models': music,
            'offline_ready': bool(ready)}
