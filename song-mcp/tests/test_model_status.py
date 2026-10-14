import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_status import model_status


def make(root, repo, *files):
    folder = Path(root) / repo / 'snapshots' / 'abc'
    folder.mkdir(parents=True)
    for name in files:
        (folder / name).write_bytes(b'x')


def test_empty_cache_is_not_offline_ready(tmp_path):
    status = model_status(tmp_path / 'models', tmp_path / 'hub')
    assert not status['offline_ready'] and not status['alignment_model']
    assert status['lyric_models'] == {'tiny': False, 'base': False, 'small': False, 'medium': False}
    assert status['music_models'] == {'harmonix-fold0': False, 'harmonix-all': False}


def test_cached_models_are_reported_without_downloading(tmp_path):
    models, hub = tmp_path / 'models', tmp_path / 'hub'
    make(models, 'models--Systran--faster-whisper-base', 'model.bin')
    (models / 'wav2vec2_fairseq_base_ls960_asr_ls960.pth').write_bytes(b'x')
    make(hub, 'models--taejunkim--allinone', *(f'harmonix-fold{i}-abc.pth' for i in range(8)))
    status = model_status(models, hub)
    assert status['lyric_models']['base'] and not status['lyric_models']['tiny']
    assert status['alignment_model'] and status['music_models']['harmonix-all'] and status['offline_ready']


def test_single_fold_is_not_the_full_ensemble(tmp_path):
    make(tmp_path / 'hub', 'models--taejunkim--allinone', 'harmonix-fold0-abc.pth')
    music = model_status(tmp_path / 'models', tmp_path / 'hub')['music_models']
    assert music == {'harmonix-fold0': True, 'harmonix-all': False}
