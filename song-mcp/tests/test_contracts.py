import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import job_dir, probe_media
from lyrics import convert_result, word_record
from songmap import combine, planning_page


def test_missing_supplied_words_stay_missing():
    raw = {'segments': [{'words': [{'word': 'Hello', 'start': 2., 'end': 2.5, 'score': .8}, {'word': 'light', 'start': 3., 'end': 3.5}]}]}
    result = convert_result(raw, 8, 'Hello missing light\nAn untimed line')
    assert result['text'] == 'Hello missing light\nAn untimed line'
    assert result['words'][1]['start'] is None
    assert result['words'][2]['start'] == 3
    assert result['phrases'][0]['start'] is None
    assert result['phrases'][1]['start'] is None
    assert result['instrumental_confirmed'] is False


def test_bad_timing_and_low_probability():
    assert word_record('bad', 9, 10, .8, 4)['start'] is None
    assert word_record('zero', 1, 1, .8, 4)['end'] is None
    assert 'low_model_probability' in word_record('quiet', 1, 2, .1, 4)['flags']
    assert word_record('likely hallucination', 1, 2, .002, 4)['start'] is None
    result = convert_result({'segments': [{'words': [{'word': 'one', 'start': 2., 'end': 3.}, {'word': 'two', 'start': 1., 'end': 2.}]}]}, 4)
    assert result['words'][1]['start'] is None
    assert result['phrases'][0]['start'] is None


def test_empty_asr_does_not_prove_instrumental():
    result = convert_result({'segments': []}, 10)
    assert result['status'] == 'no_lyrics_detected'
    assert result['words'] == [] and not result['instrumental_confirmed']


def test_overlapping_ordered_word_estimates_are_flagged_not_discarded():
    result=convert_result({'segments':[{'words':[{'word':'one','start':2.,'end':2.5,'score':.9},{'word':'two','start':2.48,'end':2.8,'score':.9}]}]},4)
    assert result['words'][1]['start']==2.48
    assert 'overlapping_word_estimate' in result['words'][1]['flags']
    assert result['phrases'][0]['start']==2.


def test_segment_timing_is_not_word_timing():
    result = convert_result({'segments': [{'text': 'some text', 'start': 1, 'end': 3}]}, 10)
    assert result['words'] == []
    assert result['phrases'][0]['start'] is None


def test_mapping_preserves_audio_offset():
    music = {'bpm': 120, 'beats': [2., 2.5, 3., 3.5], 'beat_positions': [1, 2, 3, 4], 'downbeats': [2.], 'segments': [{'start': 0., 'end': 5., 'label': 'intro'}]}
    lyrics = convert_result({'segments': [{'words': [{'word': 'light', 'start': 2., 'end': 3.}]}]}, 5)
    result = combine(music, lyrics, 'fixture.wav', 5, {})
    assert result['bars'][0]['start'] == result['lyrics']['words'][0]['start'] == 2
    assert result['timebase']['offset_seconds'] == 0
    assert planning_page(result, 0, 5)['sections'][0]['lyric_phrases'][0]['start'] == 2


@pytest.mark.parametrize('path', ['https://example.com/song.mp3', '../song.wav', r'\\server\share\song.wav'])
def test_reject_nonlocal_or_relative_inputs(path):
    with pytest.raises(ValueError):
        probe_media(path)


def test_reject_job_traversal():
    with pytest.raises(ValueError):
        job_dir('../secret')
