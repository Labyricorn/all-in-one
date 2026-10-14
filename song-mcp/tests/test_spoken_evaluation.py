from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_spoken import parse_srt, wer, timing_comparison
from types import SimpleNamespace


def test_srt_comments_and_segment_granularity():
    text = '; source metadata\n\n1\n00:00:02,000 --> 00:00:04,500\nHello world.\n\n2\n00:00:05,000 --> 00:00:06,000\nAnother line.\n'
    result = parse_srt(text)
    assert len(result) == 2
    assert result[0]['start'] == 2 and result[0]['end'] == 4.5
    assert 'words' not in result[0]


def test_edit_distance_preserves_apostrophes():
    result = wer("I don't know three names", 'I do know two names now')
    assert result['reference_words'] == 5
    assert result['edit_distance'] == 3
    assert result['operation_counts']['substitution'] == 2
    assert result['operation_counts']['insertion'] == 1


def test_segment_matching_does_not_hide_timing_shift():
    cues = [{'index': 1, 'start': 1., 'end': 2., 'text': 'Hello world'}]
    result = {'lyrics': {'words': [{'text': 'Hello', 'start': 4., 'end': 4.3}, {'text': 'world', 'start': 4.5, 'end': 4.8}]}}
    compared = timing_comparison(cues, result, 'auto')
    assert compared['segments'][0]['start_difference_seconds'] == 3
    assert compared['segments'][0]['word_midpoints_inside_reference_segment'] == 0


def test_offline_requires_cached_asr(monkeypatch, tmp_path):
    import lyrics
    calls={}
    class Model:
        def __init__(self, name, **kwargs):
            calls.update(kwargs)
        def transcribe(self, waveform, **kwargs):
            return [], SimpleNamespace(language='en')
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=Model))
    monkeypatch.setitem(sys.modules, 'whisperx.alignment', SimpleNamespace(align=None, load_align_model=None, DEFAULT_ALIGN_MODELS_TORCH={}))
    monkeypatch.setitem(sys.modules, 'whisperx.audio', SimpleNamespace(load_audio=lambda _: []))
    result=lyrics.run_lyrics('local.wav',10,'auto',None,'en','base',tmp_path,offline=True)
    assert calls['local_files_only'] is True
    assert result['status']=='no_lyrics_detected'
    assert result['instrumental_confirmed'] is False
