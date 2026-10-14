"""One explicit timebase; compact paged facts for a model to author a video."""


def combine(music, lyrics, source, duration, probe):
    beats = [{'index': i + 1, 'time': float(t), 'position_in_bar': music['beat_positions'][i]} for i, t in enumerate(music['beats'])]
    bars = [{'index': i + 1, 'start': float(t), 'end': float(music['downbeats'][i + 1]) if i + 1 < len(music['downbeats']) else duration, 'status': 'model_estimated'} for i, t in enumerate(music['downbeats'])]
    sections = [dict(s, index=i + 1, status='model_estimated') for i, s in enumerate(music['segments'])]
    warnings = ['Beats, bars and functional labels are model predictions; inspect musically ambiguous boundaries.', 'No emotion, visual treatment, story or creative interpretation is inferred by this server.'] + lyrics.get('warnings', [])
    return {'schema_version': '1.0', 'source': str(source), 'duration_seconds': duration, 'timebase': {'unit': 'seconds', 'origin': 'first decoded sample of original selected audio stream', 'offset_seconds': 0, 'vocal_stem_trimmed': False, 'video_container_timestamps': probe, 'video_note': 'Audio-stream-relative timing; container/audio PTS metadata is preserved. Check stream offsets before placing cues on a video container timeline.'}, 'tempo': {'bpm': music['bpm'], 'status': 'model_estimated'}, 'beats': beats, 'bars': bars, 'sections': sections, 'lyrics': lyrics, 'warnings': warnings}


def planning_page(result, start, end, offset=0, limit=20):
    sections = [s for s in result['sections'] if s['end'] > start and s['start'] < end]
    rows = []
    for section in sections:
        phrases = [{'text': p['text'], 'start': p['start'], 'end': p['end'], 'timing_status': p['timing_status']} for p in result['lyrics']['phrases'] if p['start'] is not None and p['end'] > section['start'] and p['start'] < section['end']]
        bar_ids = [b['index'] for b in result['bars'] if section['start'] <= b['start'] < section['end']]
        rows.append({**section, 'bar_count': len(bar_ids), 'first_bar': min(bar_ids) if bar_ids else None, 'last_bar': max(bar_ids) if bar_ids else None, 'lyric_phrases': phrases[:30], 'lyric_phrases_total': len(phrases)})
    missing = [p['text'] for p in result['lyrics']['phrases'] if p['start'] is None]
    return {'schema_version': result['schema_version'], 'source': result['source'], 'duration_seconds': result['duration_seconds'], 'timebase': result['timebase'], 'tempo': result['tempo'], 'lyric_status': result['lyrics']['status'], 'warnings': result['warnings'], 'sections': rows[offset:offset + limit], 'total_sections_in_window': len(rows), 'next_offset': offset + limit if offset + limit < len(rows) else None, 'untimed_lyric_phrases': missing[:30], 'untimed_lyric_phrases_total': len(missing), 'detail_hint': 'Use get_analysis for paged beats, bars, lyric words and phrases. Write the video plan yourself; do not present estimated lyrics/timing as verified facts.'}
