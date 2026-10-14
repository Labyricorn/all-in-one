"""Request preparation shared by CLI and MCP; preserve exact source lyrics."""
import hashlib
import re
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def prepare_lyrics(text):
    lines, annotations = [], []
    for index, line in enumerate(text.splitlines(), 1):
        match = re.match(r'^\s*(\[[^\]\n]+:\])\s*(.*)$', line)
        if match:
            annotations.append({'source_line': index, 'label': match[1], 'vocal_text': match[2]})
            lines.append(match[2])
        else:
            lines.append(line)
    return '\n'.join(lines), annotations


def prepare_request(source, probe, mode, text, language, lyric_model, music_model, offline):
    if mode not in ('auto', 'align', 'instrumental', 'none'):
        raise ValueError('Unsupported lyric mode.')
    if mode == 'align' and (not text or not text.strip() or not language):
        raise ValueError('Alignment requires nonempty lyrics and an explicit language.')
    if mode != 'align' and text is not None:
        raise ValueError('Supplied lyrics require align mode.')
    if text is not None and len(text) > 100000:
        raise ValueError('Lyrics exceed 100,000 characters.')
    if lyric_model not in ('tiny', 'base', 'small', 'medium') or music_model not in ('harmonix-all', 'harmonix-fold0'):
        raise ValueError('Unsupported model.')
    if language:
        from faster_whisper.tokenizer import _LANGUAGE_CODES
        if language not in _LANGUAGE_CODES:
            raise ValueError('Unsupported language code.')
    alignment, annotations = prepare_lyrics(text) if text is not None else (None, [])
    return {'path': str(source), 'probe': probe, 'lyrics_mode': mode,
            'lyrics_text': alignment, 'lyrics_source_text': text,
            'lyric_annotations': annotations, 'language': language,
            'lyric_model': lyric_model, 'music_model': music_model,
            'offline': offline, 'source_sha256': digest(source)}
