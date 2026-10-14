"""Research-only evaluation; segment annotations are NOT word-time ground truth."""
import json
import os
import re
import sys
from pathlib import Path

os.environ['OMP_NUM_THREADS'] = os.environ['MKL_NUM_THREADS'] = '4'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT, MODEL_CACHE
from lyrics import key, run_lyrics


def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, word in enumerate(a, 1):
        current = [i]
        for j, candidate in enumerate(b, 1):
            current.append(min(current[-1] + 1, row[j] + 1, row[j - 1] + (word != candidate)))
        row = current
    return row[-1]


def seconds(clock):
    m, s = clock.split(':')
    return 60 * int(m) + int(s)


def main():
    folder = ROOT / 'verification/research-musdb'
    references = []
    for line in (folder / 'Music Delta - Reggae.txt').read_text().splitlines():
        begin, finish, kind, text = line.split(maxsplit=3)
        references.append({'start': seconds(begin), 'end': seconds(finish), 'kind': kind, 'text': text})
    text = '\n'.join(line['text'] for line in references if line['kind'] == 'a')
    duration = 17.0
    cache = MODEL_CACHE
    aligned = run_lyrics(folder / 'reggae-vocals.wav', duration, 'align', text, 'en', 'base', cache)
    automatic = run_lyrics(folder / 'reggae-vocals.wav', duration, 'auto', None, 'en', 'base', cache)
    no_singing = run_lyrics(folder / 'country1-no-singing-vocals.wav', 4., 'auto', None, 'en', 'base', cache)
    for name, result in [('reggae-alignment', aligned), ('reggae-transcription', automatic), ('no-singing-transcription', no_singing)]:
        (folder / (name + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    expected = [key(t) for t in text.split()]
    predicted = [key(w['text']) for w in automatic['words']]
    total = 0
    coverage = []
    for phrase, annotation in zip(aligned['phrases'], references):
        words = aligned['words'][phrase['word_start_index']:phrase['word_start_index'] + phrase['word_count']]
        within = int(sum(w['start'] is not None and annotation['start'] <= (w['start'] + w['end']) / 2 <= annotation['end'] for w in words))
        total += within
        coverage.append({'annotation_interval': [annotation['start'], annotation['end']], 'expected_words': len(words), 'estimated_word_midpoints_in_segment': within})
    summary = {'source_lyrics': 'https://zenodo.org/records/3989267', 'source_audio': 'https://zenodo.org/records/1117372', 'research_only': True, 'singing_track': 'Music Delta - Reggae', 'singing_seconds': duration, 'vocal_type': 'a (single singer)', 'asr_model': 'base / CPU int8', 'alignment_model': 'WAV2VEC2_ASR_BASE_960H', 'reference_word_count': len(expected), 'recognized_candidate_count': len(predicted), 'word_error_rate_against_supplied_annotations': edit_distance(expected, predicted) / len(expected), 'supplied_words_with_accepted_estimated_timing': sum(w['start'] is not None for w in aligned['words']), 'segment_coverage': coverage, 'no_singing_reference': {'track': 'Music Delta - Country1', 'original_interval': [14, 18], 'vocal_type': 'd'}, 'no_singing_false_positive_candidates': len(no_singing['words']), 'no_singing_accepted_timed_words': sum(w['start'] is not None for w in no_singing['words']), 'no_singing_status': no_singing['status'], 'word_timing_accuracy': 'NOT measured: annotations contain segment times, no word boundaries', 'limits': ['Two small clips, one singing excerpt; no broad singing accuracy claim.', 'Dataset transcripts may contain errors.', 'No-singing ASR candidates are retained for review; low CTC scores reject their timings rather than prove the track is instrumental.']}
    (folder / 'evaluation-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
