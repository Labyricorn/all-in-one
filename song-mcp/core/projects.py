"""SQLite transactions coordinate independent CLI, HTTP and stdio processes.

Raw analysis is immutable. Every accepted edit saves a complete snapshot, an
operation record and a durable event in the same transaction. Undo/redo create
new revisions (revision numbers never go backwards). Artifacts are project-owned.
"""
import copy
import contextlib
import hashlib
import json
import math
import os
import shutil
import sqlite3
import time
import uuid
import wave
from pathlib import Path

from core.requests import digest
from jsonschema import Draft202012Validator

SCHEMAS = Path(__file__).resolve().parents[1] / 'schemas'
CORRECTION_SCHEMA = json.loads((SCHEMAS / 'correction.schema.json').read_text())
PROJECT_SCHEMA = json.loads((SCHEMAS / 'project.schema.json').read_text())


def validate_schema(value, schema):
    error = next(Draft202012Validator(schema).iter_errors(value), None)
    if error:
        raise ValueError('Schema validation: ' + error.message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def analysis_hash(value):
    return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()


class Conflict(ValueError):
    def __init__(self, expected, actual):
        super().__init__(f'Stale project revision: expected {expected}, current {actual}. Read the current revision and rebase the edit.')
        self.expected, self.actual = expected, actual


def number(value, duration):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= duration:
        raise ValueError('Timing must be finite seconds within the original duration.')
    return value


def migrate(raw):
    if str(raw.get('schema_version')) != '1.0':
        raise ValueError('Only combined analysis schema 1.0 is supported; convert timing references explicitly first.')
    data = copy.deepcopy(raw)
    if data.get('timebase', {}).get('offset_seconds') != 0 or data.get('timebase', {}).get('unit') != 'seconds' or data.get('timebase', {}).get('vocal_stem_trimmed', False):
        raise ValueError('Projects require untrimmed seconds from the original decoded audio origin.')
    duration = data['duration_seconds']
    if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid original duration.')
    namespace = uuid.UUID(analysis_hash(raw)[:32])
    ids = set()
    for kind, rows in [('word', data['lyrics']['words']), ('line', data['lyrics']['phrases']),
                       ('beat', data['beats']), ('section', data['sections']), ('event', data.setdefault('events', []))]:
        for i, row in enumerate(rows):
            row['id'] = row.get('id') or str(uuid.uuid5(namespace, f'{kind}:{i}'))
            if row['id'] in ids:
                raise ValueError('Duplicate stable ID.')
            ids.add(row['id'])
            row.setdefault('provenance', {'method': 'imported_prediction', 'review_state': 'unreviewed'})
            # Legacy analyzer section boundaries are rounded to tenths; retain
            # their raw bounds and normalize only the sub-50ms trailing excess.
            if kind == 'section' and duration < row.get('end', 0) <= duration + .05:
                row['provenance']['original_interval'] = {'start': row['start'], 'end': row['end']}
                row['provenance']['normalization'] = 'legacy_rounding_clipped_to_duration'
                row['end'] = duration
            if kind == 'line':
                start = row.get('word_start_index', 0)
                row['word_ids'] = [w['id'] for w in data['lyrics']['words'][start:start + row.get('word_count', 0)]]
                row.setdefault('occurrence_id', row['id'])
    refresh(data)
    return data


GUESS_BASES = ('midpoint', 'even_spread')


def refresh(data):
    duration = data['duration_seconds']
    words = data['lyrics']['words']
    lookup = {w['id']: w for w in words}
    claimed = set()
    for line in data['lyrics']['phrases']:
        for key in line['word_ids']:
            if key not in lookup: raise ValueError('Line refers to an unknown word ID.')
            if key in claimed: raise ValueError('A word ID cannot belong to multiple lines; repeated performances need independent IDs.')
            claimed.add(key)
    for row in words + data['lyrics']['phrases'] + data['sections'] + data.get('events', []):
        start, end = row.get('start'), row.get('end')
        if (start is None) != (end is None):
            raise ValueError('Intervals require both start and end, or both null.')
        if start is not None:
            number(start, duration); number(end, duration)
            if start >= end:
                raise ValueError('Interval end must exceed start; ordered overlaps are allowed.')
        if row.get('morph_at') is not None:
            number(row['morph_at'], duration)
            if start is None or not start <= row['morph_at'] <= end:
                raise ValueError('Riff morph must fall within its event interval.')
    for line in data['lyrics']['phrases']:
        part = [lookup[key] for key in line['word_ids']]
        line['word_ids'] = [w['id'] for w in part]
        line['word_count'] = len(part)
        line['word_start_index'] = next((i for i, w in enumerate(words) if part and w['id'] == part[0]['id']), len(words))
        if not line.get('bounds_user_set'):
            complete = part and all(w['start'] is not None for w in part)
            line['start'] = min(w['start'] for w in part) if complete else None
            line['end'] = max(w['end'] for w in part) if complete else None
        if not line.get('text_user_set'):
            line['text'] = ' '.join(w['text'] for w in part)
    data['lyrics']['display_text'] = '\n'.join(line['text'] for line in data['lyrics']['phrases'])
    beats = data['beats']
    for beat in beats:
        number(beat['time'], duration)
        if beat.get('position_in_bar', 1) not in (1, 2, 3, 4):
            raise ValueError('position_in_bar must be 1..4 for the current 4/4 grid.')
    beats.sort(key=lambda b: b['time'])
    if any(a['time'] == b['time'] for a, b in zip(beats, beats[1:])):
        raise ValueError('Duplicate beat times.')
    for i, beat in enumerate(beats, 1):
        beat['index'] = i
    downbeats = [b for b in beats if b.get('position_in_bar') == 1]
    intervals = [b['time'] - a['time'] for a, b in zip(beats, beats[1:])]
    step = sorted(intervals)[len(intervals) // 2] if intervals else 0
    data['bars'] = [{'id': b['id'], 'index': i + 1, 'start': b['time'],
                     'end': downbeats[i + 1]['time'] if i + 1 < len(downbeats) else min(duration, beats[-1]['time'] + step),
                     'status': 'derived_from_grid'} for i, b in enumerate(downbeats)]
    for row in words + data['lyrics']['phrases'] + data['sections'] + data.get('events', []):
        t = row.get('start')
        row['nearest_downbeat'] = min(downbeats, key=lambda b: abs(b['time'] - t))['time'] if t is not None and downbeats else None
        prior = [b for b in beats if t is not None and b['time'] <= t]
        row['beat_id'] = prior[-1]['id'] if prior else None
    issues = []
    if not beats:
        issues.append({'code': 'missing_beat_grid'})
    if beats and duration - beats[-1]['time'] > max(2, step * 2):
        issues.append({'code': 'uncovered_beat_tail', 'seconds': duration - beats[-1]['time']})
    for i, word in enumerate(words):
        if word['start'] is None:
            issues.append({'code': 'missing_word_timing', 'id': word['id']})
        elif word.get('timing_status') == 'guessed':
            issues.append({'code': 'guessed_word_timing', 'id': word['id']})
        elif word.get('model_score') is not None and word['model_score'] < .5 and word.get('provenance', {}).get('method') != 'user_set':
            issues.append({'code': 'weak_word_timing', 'id': word['id'], 'model_score': word['model_score']})
        if i and word['start'] is not None and words[i - 1]['end'] is not None and word['start'] < words[i - 1]['end']:
            issues.append({'code': 'overlapping_words', 'id': word['id']})
    data['review_items'] = issues


def apply_operations(data, operations, transaction='preview'):
    if not isinstance(operations, list) or not 1 <= len(operations) <= 1000:
        raise ValueError('Supply 1..1000 correction operations.')
    groups = {'word': data['lyrics']['words'], 'line': data['lyrics']['phrases'],
              'beat': data['beats'], 'section': data['sections'], 'event': data['events']}
    for operation_index, operation in enumerate(operations):
        op = operation['op']
        required = {'replace_word': ('text',), 'replace_line': ('text',),
                    'set_word_interval': ('start', 'end'), 'set_line_interval': ('start', 'end'),
                    'set_section_interval': ('start', 'end'), 'set_event_interval': ('start', 'end'),
                    'set_beat': ('time',), 'transform_grid': ('start', 'end'), 'mark_riff': ('start', 'end')}.get(op, ())
        if any(field not in operation for field in required):
            raise ValueError('Missing required fields for ' + op + ': ' + ', '.join(required))
        if op in ('split_line', 'merge_lines'):
            lines = groups['line']
            line = next((r for r in lines if r['id'] == operation.get('line_id')), None)
            if line is None: raise ValueError('Unknown line ID.')
            if op == 'split_line':
                index = operation.get('word_index')
                if not isinstance(index, int) or isinstance(index, bool) or not 0 < index < len(line['word_ids']):
                    raise ValueError('Split requires a word_index inside the line.')
                new = copy.deepcopy(line)
                new['id'] = operation.get('id') or str(uuid.uuid5(uuid.NAMESPACE_URL, f'mgmv:{transaction}:{operation_index}'))
                if any(new['id'] == row['id'] for values in groups.values() for row in values): raise ValueError('Stable ID already exists.')
                new['word_ids'] = line['word_ids'][index:]; line['word_ids'] = line['word_ids'][:index]
                new['occurrence_id'] = new['id']
                lines.insert(lines.index(line) + 1, new)
                changed = (line, new)
            else:
                other = next((r for r in lines if r['id'] == operation.get('other_line_id')), None)
                if other is None or lines.index(other) != lines.index(line) + 1: raise ValueError('Merge requires the next adjacent line.')
                line['word_ids'] += other['word_ids']; lines.remove(other); changed = (line,)
            for row in changed:
                row.pop('bounds_user_set', None); row.pop('text_user_set', None)
                row['provenance'] = {'method': 'user_set', 'review_state': 'reviewed'}
            continue
        if op == 'transform_grid':
            start, end = number(operation['start'], data['duration_seconds']), number(operation['end'], data['duration_seconds'])
            scale, shift = operation.get('scale', 1), operation.get('shift', 0)
            if start >= end or isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0 or isinstance(shift, bool) or not isinstance(shift, (int, float)) or not math.isfinite(shift):
                raise ValueError('Grid transform requires an ordered range, positive finite scale and finite shift.')
            for beat in groups['beat']:
                if start <= beat['time'] <= end:
                    beat['time'] = start + (beat['time'] - start) * scale + shift
                    beat['provenance'] = {'method': 'user_set', 'review_state': 'reviewed'}
            continue
        kind = operation.get('kind') or next((k for k in groups if f'_{k}' in op), None)
        if op == 'mark_riff':
            kind, op = 'event', 'insert_event'
        if kind not in groups:
            raise ValueError('Unknown correction entity.')
        if operation.get('kind') and op != 'set_tags' and not op.endswith('_' + kind) and not op.startswith('set_' + kind):
            raise ValueError('Operation/entity kind mismatch.')
        rows = groups[kind]
        key = operation.get('id', operation.get(kind + '_id'))
        if op.startswith('insert_'):
            row = copy.deepcopy(operation.get('value', {}))
            row['id'] = key or str(uuid.uuid5(uuid.NAMESPACE_URL, f'mgmv:{transaction}:{operation_index}'))
            if any(row['id'] == r['id'] for values in groups.values() for r in values):
                raise ValueError('Stable ID already exists.')
            if kind == 'word':
                row.setdefault('start', None); row.setdefault('end', None)
                line = next((r for r in groups['line'] if r['id'] == operation.get('line_id')), None)
                if line is None:
                    raise ValueError('Inserted word requires an existing line_id.')
                after = operation.get('after_id')
                index = line['word_ids'].index(after) + 1 if after else 0
                line['word_ids'].insert(index, row['id'])
                global_index = next((i + 1 for i, w in enumerate(rows) if w['id'] == after), line['word_start_index'])
                rows.insert(global_index, row)
            else:
                if kind == 'line':
                    row.setdefault('word_ids', []); row.setdefault('start', None); row.setdefault('end', None)
                if operation['op'] == 'mark_riff':
                    row.update(type='riff', start=operation['start'], end=operation['end'])
                    for field in ('morph_to', 'morph_at', 'word_id'):
                        if field in operation: row[field] = operation[field]
                after = operation.get('after_id')
                if after is not None:
                    index = next((i for i, existing in enumerate(rows) if existing['id'] == after), None)
                    if index is None: raise ValueError('Unknown insertion after_id.')
                    rows.insert(index + 1, row)
                else: rows.append(row)
        else:
            row = next((r for r in rows if r['id'] == key), None)
            if row is None:
                raise ValueError(f'Unknown {kind} ID: {key}')
            if op.startswith('delete_'):
                rows.remove(row)
                if kind == 'word':
                    for line in groups['line']:
                        line['word_ids'] = [word for word in line['word_ids'] if word != key]
                if kind == 'line':
                    groups['word'][:] = [w for w in groups['word'] if w['id'] not in row['word_ids']]
                continue
            if op in ('replace_word', 'replace_line'):
                row['text'] = operation['text']
                if kind == 'line': row['text_user_set'] = True
            elif op in ('set_word_interval', 'set_line_interval', 'set_section_interval', 'set_event_interval'):
                row.update(start=operation['start'], end=operation['end'])
                if kind == 'line': row['bounds_user_set'] = True
                if operation.get('method') is not None and not (op == 'set_word_interval' and operation['method'] == 'guessed'):
                    raise ValueError('Only word intervals may be marked as guessed.')
                if operation.get('basis') is not None and operation['basis'] not in GUESS_BASES:
                    raise ValueError('Unknown guess basis.')
            elif op == 'set_beat':
                row['time'] = operation['time']
                if 'position_in_bar' in operation: row['position_in_bar'] = operation['position_in_bar']
            elif op in ('set_tags', 'set_section', 'set_event'):
                fields = operation.get('value', {})
                if set(fields) - {'label', 'voice', 'delivery', 'review_state', 'type', 'morph_to', 'morph_at'}:
                    raise ValueError('Unsupported tag field.')
                row.update(fields)
            else:
                raise ValueError('Unsupported correction operation: ' + op)
        if kind in ('word', 'line') and not isinstance(row.get('text'), str):
            raise ValueError('Lyric text must be a string.')
        guessed = op == 'set_word_interval' and operation.get('method') == 'guessed' and row['start'] is not None
        if kind == 'word': row['timing_status'] = 'guessed' if guessed else 'user_set' if row['start'] is not None else 'missing'
        row['provenance'] = ({'method': 'guessed', 'review_state': 'needs_review', 'basis': operation.get('basis', 'midpoint')}
                             if guessed else {'method': 'user_set', 'review_state': 'reviewed'})
    refresh(data)


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1): raise ValueError('Unsupported project database version; open with a compatible application.')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, metadata TEXT NOT NULL, raw TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (project TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL, correction TEXT NOT NULL, PRIMARY KEY(project, revision));
                CREATE TABLE IF NOT EXISTS transactions (project TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(project,id));
                CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, project TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, revision INTEGER NOT NULL, created REAL NOT NULL);
            ''')
            db.execute('PRAGMA user_version=1')

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'projects.sqlite3', timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=30000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_analysis(self, path, artifacts=None):
        source = Path(path).resolve()
        raw = json.loads(source.read_text(encoding='utf-8-sig'))
        return self.import_data(raw, artifacts)

    def import_data(self, raw, artifacts=None):
        """Import parsed analysis using the same migration and persistence as files."""
        if not isinstance(raw, dict):
            raise ValueError('Analysis JSON must be an object.')
        data = migrate(raw)
        project = uuid.uuid4().hex
        folder = self.root / project
        folder.mkdir()
        manifest = []
        try:
            for role, path in (artifacts or {}).items():
                if role not in ('mix', 'vocals'):
                    raise ValueError('Playback artifact roles must be mix or vocals.')
                original = Path(path).resolve()
                # Only full-timebase decoded PCM WAVs are eligible for playback.
                with wave.open(str(original), 'rb') as wav:
                    rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
                    if abs(frames / rate - data['duration_seconds']) > .05:
                        raise ValueError('Playback artifact duration differs from the original timebase.')
                target = folder / (role + '.wav')
                shutil.copy2(original, target)
                manifest.append({'id': role, 'path': target.name, 'sha256': digest(target),
                                 'sample_rate': rate, 'channels': channels, 'duration_seconds': frames / rate,
                                 'offset_seconds': 0, 'processing_identity': raw.get('run', {}).get('job_id', 'imported_pcm')})
            source_hash = raw.get('run', {}).get('source_sha256')
            if not source_hash and Path(raw.get('source', '')).is_file():
                source_hash = digest(raw['source'])
            metadata = {'schema_version': 1, 'project_id': project, 'source_sha256': source_hash,
                        'source_hash_status': 'known' if source_hash else 'unavailable',
                        'base_analysis_sha256': analysis_hash(raw), 'timebase': raw['timebase'],
                        'artifacts': manifest, 'analysis_configuration': raw.get('run', {}), 'created': time.time()}
            validate_schema({**metadata, 'revision': 0, 'current_revision': 0, 'analysis': data}, PROJECT_SCHEMA)
            with self.connect() as db:
                db.execute('INSERT INTO projects VALUES (?,0,?,?)', (project, encoded(metadata), encoded(raw)))
                db.execute('INSERT INTO revisions VALUES (?,0,?,?)', (project, encoded(data), '{}'))
                db.execute('INSERT INTO events(project,revision,created) VALUES (?,0,?)', (project, time.time()))
            return self.read(project)
        except Exception:
            shutil.rmtree(folder)
            raise

    def read(self, project, revision=None):
        with self.connect() as db:
            row = db.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone()
            if row is None: raise ValueError('Unknown project ID.')
            selected = row['revision'] if revision is None else revision
            snapshot = db.execute('SELECT data FROM revisions WHERE project=? AND revision=?', (project, selected)).fetchone()
            if snapshot is None: raise ValueError('Unknown revision.')
            return {**json.loads(row['metadata']), 'revision': selected, 'current_revision': row['revision'], 'analysis': json.loads(snapshot['data'])}

    def list(self):
        with self.connect() as db:
            return [{'project_id': r['id'], 'revision': r['revision'],
                     'name': Path(json.loads(r['raw']).get('source') or r['id']).stem}
                    for r in db.execute('SELECT id,revision,raw FROM projects ORDER BY rowid DESC')]

    def apply(self, project, correction, actor='cli', target_revision=None):
        validate_schema(correction, CORRECTION_SCHEMA)
        if correction.get('schema_version') != 1 or correction.get('project_id') != project:
            raise ValueError('Correction schema_version/project_id mismatch.')
        transaction = correction.get('transaction_id')
        if not isinstance(transaction, str) or not 1 <= len(transaction) <= 128:
            raise ValueError('A stable transaction_id is required for retry-safe corrections.')
        payload = encoded({'correction': correction, 'target_revision': target_revision})
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM transactions WHERE project=? AND id=?', (project, transaction)).fetchone()
            if old:
                if old['payload'] != payload: raise ValueError('transaction_id was already used for a different correction.')
                return {'project_id': project, 'revision': old['revision'], 'replayed': True}
            row = db.execute('SELECT * FROM projects WHERE id=?', (project,)).fetchone()
            if row is None: raise ValueError('Unknown project ID.')
            if correction.get('base_revision') != row['revision']: raise Conflict(correction.get('base_revision'), row['revision'])
            if correction.get('base_analysis_sha256') != json.loads(row['metadata'])['base_analysis_sha256']:
                raise ValueError('Correction does not match the immutable raw analysis hash.')
            selected = row['revision'] if target_revision is None else target_revision
            snapshot = db.execute('SELECT data FROM revisions WHERE project=? AND revision=?', (project, selected)).fetchone()
            if snapshot is None: raise ValueError('Unknown restore revision.')
            data = json.loads(snapshot['data'])
            if target_revision is None: apply_operations(data, correction.get('operations'), transaction)
            revision = row['revision'] + 1
            record = {**correction, 'actor': actor, 'created': time.time(), 'restored_revision': target_revision}
            db.execute('INSERT INTO revisions VALUES (?,?,?,?)', (project, revision, encoded(data), encoded(record)))
            db.execute('UPDATE projects SET revision=? WHERE id=?', (revision, project))
            db.execute('INSERT INTO transactions VALUES (?,?,?,?)', (project, transaction, payload, revision))
            db.execute('INSERT INTO events(project,revision,created) VALUES (?,?,?)', (project, revision, time.time()))
        return {'project_id': project, 'revision': revision, 'replayed': False}

    def propose(self, project, correction):
        validate_schema(correction, CORRECTION_SCHEMA)
        current = self.read(project)
        if correction.get('project_id') != project or correction.get('schema_version') != 1 or correction.get('base_analysis_sha256') != current['base_analysis_sha256']:
            raise ValueError('Proposal project/schema/hash mismatch.')
        if correction.get('base_revision') != current['revision']: raise Conflict(correction.get('base_revision'), current['revision'])
        apply_operations(copy.deepcopy(current['analysis']), correction.get('operations'), correction['transaction_id'])
        key = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO proposals VALUES (?,?,?)', (key, project, encoded(correction)))
        return {'proposal_id': key, 'project_id': project, 'base_revision': current['revision'], 'applied': False}

    def accept(self, proposal, actor='mcp'):
        with self.connect() as db:
            row = db.execute('SELECT * FROM proposals WHERE id=?', (proposal,)).fetchone()
            if row is None: raise ValueError('Unknown proposal ID.')
        return self.apply(row['project'], json.loads(row['payload']), actor)

    def proposals(self, project):
        self.read(project)
        with self.connect() as db:
            items = []
            for row in db.execute('SELECT id,payload FROM proposals WHERE project=? ORDER BY rowid', (project,)):
                payload = json.loads(row['payload'])
                accepted = db.execute('SELECT revision FROM transactions WHERE project=? AND id=?', (project, payload['transaction_id'])).fetchone()
                items.append({'proposal_id': row['id'], 'correction': payload, 'applied_revision': accepted['revision'] if accepted else None})
            return items

    def history(self, project):
        self.read(project)
        with self.connect() as db:
            return [{'revision': r['revision'], 'correction': json.loads(r['correction'])} for r in db.execute('SELECT revision,correction FROM revisions WHERE project=? ORDER BY revision', (project,))]

    def events(self, after=0):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM events WHERE sequence>? ORDER BY sequence LIMIT 100', (after,))]

    def artifact(self, project, role):
        entry = next((a for a in self.read(project)['artifacts'] if a['id'] == role), None)
        if entry is None: raise ValueError('Unknown artifact ID.')
        path = (self.root / project / entry['path']).resolve()
        if path.parent != (self.root / project).resolve() or digest(path) != entry['sha256']:
            raise ValueError('Artifact path/hash integrity check failed.')
        return path

    def export(self, project, path, revision=None):
        selected = self.read(project, revision)
        data = selected['analysis']
        data['project_revision'] = {'project_id': project, 'revision': selected['revision'], 'base_analysis_sha256': selected['base_analysis_sha256']}
        from common import write_json
        write_json(Path(path), data)
        return {'path': str(Path(path).resolve()), 'revision': selected['revision'], 'sha256': digest(path)}
