"""Whisper lyric estimates, without turning missing alignments into invented timing."""
import math
import re
import unicodedata
import os
from difflib import SequenceMatcher

DISCLAIMER = 'Whisper and wav2vec2 are speech models. Singing, held notes, backing vocals and repeated words can produce incorrect text or timing; ASR can also hallucinate words in instrumental audio. Review against the original audio. Scores are not calibrated singing accuracy.'


def key(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def word_record(text, start, end, probability, duration):
    flags = []
    valid = isinstance(start, (int, float)) and isinstance(end, (int, float)) and math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration + .05
    if not valid:
        start = end = None
        flags.append('missing_or_invalid_alignment')
    else:
        start, end = round(float(start), 4), round(float(min(end, duration)), 4)
        if end - start > 3:
            flags.append('long_word_or_held_note')
    probability = float(probability) if isinstance(probability, (float, int)) and math.isfinite(probability) else None
    if probability is not None and probability < .5:
        flags.append('low_model_probability')
    if probability is not None and probability < .1:
        start = end = None
        flags.append('timing_rejected_very_low_alignment_score')
    return {'text': text, 'start': start, 'end': end, 'timing_status': 'estimated_unverified_singing' if start is not None else 'missing', 'model_score': probability, 'flags': flags}


def convert_result(raw, duration, supplied_text=None):
    candidates = [word_record(w['word'].strip(), w.get('start'), w.get('end'), w.get('score', w.get('probability')), duration) for s in raw.get('segments', []) for w in s.get('words', []) if w.get('word', '').strip()]
    phrases = []
    words = []
    if supplied_text is not None:
        # Preserve supplied text, line order, and every missing word. Alignment text
        # may have punctuation/case differences; only matching lexical tokens map.
        cursor = 0
        for line in supplied_text.splitlines():
            tokens = [token for token in re.findall(r'\S+', line) if key(token)]
            if not tokens:
                continue
            first = len(words)
            for token in tokens:
                match = next((i for i in range(cursor, min(cursor + 12, len(candidates))) if key(candidates[i]['text']) == key(token)), None)
                if match is None:
                    words.append(word_record(token, None, None, None, duration))
                else:
                    item = dict(candidates[match], text=token)
                    words.append(item)
                    cursor = match + 1
            part = words[first:]
            complete = all(w['start'] is not None for w in part)
            phrases.append({'text': line, 'word_start_index': first, 'word_count': len(part), 'start': part[0]['start'] if complete else None, 'end': part[-1]['end'] if complete else None, 'timing_status': 'estimated_unverified_singing' if complete else 'incomplete_alignment'})
    else:
        offset = 0
        for segment in raw.get('segments', []):
            part = [word_record(w['word'].strip(), w.get('start'), w.get('end'), w.get('score', w.get('probability')), duration) for w in segment.get('words', []) if w.get('word', '').strip()]
            words.extend(part)
            # A segment boundary alone is not a word boundary.
            complete = bool(part) and all(w['start'] is not None for w in part)
            phrases.append({'text': segment.get('text', '').strip(), 'word_start_index': offset, 'word_count': len(part), 'start': part[0]['start'] if complete else None, 'end': part[-1]['end'] if complete else None, 'timing_status': 'estimated_unverified_singing' if complete else 'missing_word_alignment'})
            offset += len(part)
    previous_start = 0
    previous_end = 0
    for word in words:
        if word['start'] is not None:
            if word['start'] < previous_start:
                word['flags'].append('non_monotonic_alignment')
                word.update(start=None, end=None, timing_status='missing')
            else:
                if word['start'] < previous_end:
                    word['flags'].append('overlapping_word_estimate')
                previous_start = word['start']
                previous_end = word['end']
    # Recompute phrase completeness after monotonicity checks.
    for phrase in phrases:
        part = words[phrase['word_start_index']:phrase['word_start_index'] + phrase['word_count']]
        if not part or any(w['start'] is None for w in part):
            phrase.update(start=None, end=None, timing_status='incomplete_alignment')
    state = 'estimated' if words else 'no_lyrics_detected'
    if words and not any(w['start'] is not None for w in words):
        state = 'no_reliable_lyric_timing'
    return {'status': state, 'text_source': 'user_supplied' if supplied_text is not None else 'automatic_unverified', 'text': supplied_text if supplied_text is not None else '\n'.join(p['text'] for p in phrases), 'language': raw.get('language'), 'words': words, 'phrases': phrases, 'warnings': [DISCLAIMER], 'instrumental_confirmed': False}


def run_lyrics(audio, duration, mode, text, language, model_name, cache, offline=False):
    if mode in ('none', 'instrumental'):
        return {'status': 'instrumental_declared' if mode == 'instrumental' else 'not_requested', 'text_source': None, 'text': None, 'words': [], 'phrases': [], 'warnings': [], 'instrumental_confirmed': mode == 'instrumental', 'instrumental_basis': 'user_declaration' if mode == 'instrumental' else None}
    from faster_whisper import WhisperModel
    from whisperx.alignment import align, load_align_model, DEFAULT_ALIGN_MODELS_TORCH
    from whisperx.audio import load_audio
    cache.mkdir(parents=True, exist_ok=True)
    waveform = load_audio(str(audio))
    anchor_warning = None
    # Whole-track CTC has quadratic memory costs. Long supplied lyrics use actual
    # ASR word matches as bounded anchors, never evenly apportioned song time.
    if mode == 'align' and duration <= 60:
        transcript = [{'text': ' '.join(text.split()), 'start': 0., 'end': duration}]
        detected = language
    else:
        model = WhisperModel(model_name, device='cpu', compute_type='int8', cpu_threads=4, download_root=str(cache), local_files_only=offline)
        segments, info = model.transcribe(waveform, language=language, word_timestamps=True, condition_on_previous_text=False, temperature=0, vad_filter=False, no_speech_threshold=.6)
        segments = list(segments)
        detected = language or info.language
        transcript = [{'text': s.text, 'start': s.start, 'end': s.end} for s in segments]
        if mode == 'align':
            supplied = [token for token in re.findall(r'\S+', text) if key(token)]
            recognized = [w for s in segments for w in (s.words or [])]
            matcher = SequenceMatcher(None, [key(w) for w in supplied], [key(w.word) for w in recognized], autojunk=False)
            anchors = {}
            for block in matcher.get_matching_blocks():
                for i in range(block.size):
                    anchors[block.a + i] = recognized[block.b + i]
            transcript, cursor = [], 0
            for line in text.splitlines():
                tokens = [token for token in re.findall(r'\S+', line) if key(token)]
                matches = [anchors[i] for i in range(cursor, cursor + len(tokens)) if i in anchors]
                cursor += len(tokens)
                if matches and (len(matches) >= 2 or len(tokens) == 1):
                    begin = max(0., matches[0].start - 1)
                    finish = min(duration, matches[-1].end + 1)
                    if 0 < finish - begin <= 60:
                        transcript.append({'text': line, 'start': begin, 'end': finish})
            anchor_warning = 'Long supplied-lyrics alignment uses matched ASR words to bound each line. Lines without reliable anchors remain untimed. No evenly distributed timing fallback is used.'
    if not transcript:
        output = convert_result({'segments': [], 'language': detected}, duration, text if mode == 'align' else None)
    else:
        if offline:
            import torch
            import torchaudio
            import nltk
            from whisperx.utils import PUNKT_LANGUAGES
            punkt = PUNKT_LANGUAGES.get(detected, 'english')
            nltk.data.find('tokenizers/punkt_tab/' + punkt)
            if detected in DEFAULT_ALIGN_MODELS_TORCH:
                bundle = getattr(torchaudio.pipelines, DEFAULT_ALIGN_MODELS_TORCH[detected])
                if not (cache / os.path.basename(bundle._path)).is_file():
                    raise FileNotFoundError('Offline alignment requires cached ' + os.path.basename(bundle._path))
        model, metadata = load_align_model(language_code=detected, device='cpu', model_dir=str(cache), model_cache_only=offline)
        # WhisperX defaults to interpolating missing word timings. Disable it.
        aligned = align(transcript, model, metadata, waveform, 'cpu', interpolate_method='ignore', return_char_alignments=False)
        aligned['language'] = detected
        output = convert_result(aligned, duration, text if mode == 'align' else None)
    output['timing_method'] = 'WhisperX wav2vec2 CTC; missing-word interpolation disabled'
    if anchor_warning:
        output['warnings'].append(anchor_warning)
    return output
