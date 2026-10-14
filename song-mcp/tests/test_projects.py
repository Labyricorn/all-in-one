import copy
import json
import multiprocessing
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.projects import ProjectStore, Conflict, migrate, analysis_hash
from core.requests import prepare_request


def fixture():
    return {'schema_version': '1.0', 'source': 'unavailable.wav', 'duration_seconds': 10.,
            'timebase': {'unit': 'seconds', 'offset_seconds': 0}, 'tempo': {'bpm': 120},
            'beats': [{'time': t, 'position_in_bar': i % 4 + 1} for i, t in enumerate([0., .5, 1., 1.5, 2.])],
            'bars': [{'start': 0., 'end': 10.}], 'sections': [{'start': 0., 'end': 10., 'label': 'verse'}],
            'lyrics': {'text': 'hi there', 'words': [
                {'text': 'hi', 'start': 1., 'end': 2., 'flags': []},
                {'text': 'there', 'start': 1.8, 'end': 3., 'flags': []}],
                'phrases': [{'text': 'hi there', 'word_start_index': 0, 'word_count': 2, 'start': 1., 'end': 3.}]}}


@pytest.fixture
def imported(tmp_path):
    path = tmp_path / 'analysis.json'; path.write_text(json.dumps(fixture()))
    store = ProjectStore(tmp_path / 'projects')
    return store, store.import_analysis(path)


def correction(project, operations, transaction='edit-1'):
    return {'schema_version': 1, 'project_id': project['project_id'], 'base_revision': project['revision'],
            'base_analysis_sha256': project['base_analysis_sha256'], 'transaction_id': transaction, 'operations': operations}


def test_migration_raw_preservation_and_derived_tail(imported):
    store, project = imported
    assert migrate(fixture()) == migrate(fixture())
    data = project['analysis']
    assert data['bars'][-1]['end'] == 2.5
    assert any(r['code'] == 'uncovered_beat_tail' for r in data['review_items'])
    assert data['lyrics']['words'][0]['nearest_downbeat'] == 0
    with store.connect() as db:
        assert json.loads(db.execute('SELECT raw FROM projects').fetchone()[0]) == fixture()


def test_atomic_conflicts_retry_restore_and_export(imported, tmp_path):
    store, project = imported; key = project['project_id']
    word = project['analysis']['lyrics']['words'][0]['id']
    edit = correction(project, [{'op': 'replace_word', 'word_id': word, 'text': 'hello'},
                                {'op': 'set_word_interval', 'word_id': word, 'start': 1.2, 'end': 2.2}])
    assert store.apply(key, edit)['revision'] == 1
    assert store.apply(key, edit)['replayed']
    with pytest.raises(Conflict): store.apply(key, {**edit, 'transaction_id': 'stale'})
    reopened = ProjectStore(store.root).read(key)
    assert reopened['analysis']['lyrics']['phrases'][0]['text'] == 'hello there'
    assert reopened['analysis']['lyrics']['phrases'][0]['start'] == 1.2
    before = store.export(key, tmp_path / 'before.json')['sha256']
    undo = correction(reopened, [], 'undo'); del undo['operations']
    store.apply(key, undo, target_revision=0)
    redo = correction(store.read(key), [], 'redo'); del redo['operations']
    store.apply(key, redo, target_revision=1)
    assert store.read(key)['analysis'] == reopened['analysis']
    store.export(key, tmp_path / 'repeat.json', revision=1)
    assert (tmp_path / 'before.json').read_bytes() == (tmp_path / 'repeat.json').read_bytes()
    with pytest.raises(ValueError): store.apply(key, {**edit, 'operations': []})
    assert len(store.events()) == 4


def test_failed_multi_edit_rolls_back_and_proposals_do_not_apply(imported):
    store, project = imported; key = project['project_id']; word = project['analysis']['lyrics']['words'][0]['id']
    bad = correction(project, [{'op': 'replace_word', 'word_id': word, 'text': 'changed'},
                               {'op': 'set_word_interval', 'word_id': word, 'start': float('nan'), 'end': 2}])
    with pytest.raises(ValueError): store.apply(key, bad)
    assert store.read(key) == project
    edit = correction(project, [{'op': 'replace_word', 'word_id': word, 'text': 'proposal'}])
    proposed = store.propose(key, edit)
    assert store.read(key)['revision'] == 0
    store.accept(proposed['proposal_id'])
    assert store.read(key)['revision'] == 1
    invalid = correction(store.read(key), [{'op': 'insert_line', 'value': {'word_ids': [word]}}], 'duplicate-membership')
    with pytest.raises(ValueError): store.apply(key, invalid)
    assert store.read(key)['revision'] == 1


def test_word_insert_delete_grid_and_metadata_refresh(imported):
    store, project = imported; key = project['project_id']; data = project['analysis']
    first = data['lyrics']['words'][0]['id']; line = data['lyrics']['phrases'][0]['id']
    operations = [{'op': 'insert_word', 'id': 'new-word', 'line_id': line, 'after_id': first, 'value': {'text': 'my'}},
                  {'op': 'set_word_interval', 'word_id': 'new-word', 'start': 1.4, 'end': 2.1},
                  {'op': 'delete_word', 'word_id': data['lyrics']['words'][1]['id']},
                  {'op': 'transform_grid', 'start': 0., 'end': 2., 'shift': .25, 'scale': 1.5}]
    store.apply(key, correction(project, operations))
    result = store.read(key)['analysis']
    assert result['lyrics']['phrases'][0]['text'] == 'hi my'
    assert result['lyrics']['words'][0]['nearest_downbeat'] == .25
    assert result['beats'][-1]['time'] == 3.25
    assert result['bars'][-1]['end'] == 4.


def worker_edit(root, key, edit, output):
    try: output.put(ProjectStore(root).apply(key, edit)['revision'])
    except Conflict: output.put('conflict')


def test_cross_process_revision_serialization(imported):
    store, project = imported; key = project['project_id']; word = project['analysis']['lyrics']['words'][0]['id']
    ctx = multiprocessing.get_context('spawn'); output = ctx.Queue()
    processes = [ctx.Process(target=worker_edit, args=(store.root, key, correction(project, [{'op': 'replace_word', 'word_id': word, 'text': str(i)}], str(i)), output)) for i in range(2)]
    for process in processes: process.start()
    for process in processes:
        process.join(15); assert process.exitcode == 0
    assert sorted([output.get(timeout=2), output.get(timeout=2)], key=str) == [1, 'conflict']
    assert store.read(key)['revision'] == 1


def test_artifact_integrity_duration_and_traversal(imported, tmp_path):
    store, project = imported
    audio = tmp_path / 'mix.wav'
    with wave.open(str(audio), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000); wav.writeframes(b'\0\0' * 80000)
    path = tmp_path / 'analysis.json'
    loaded = store.import_analysis(path, {'mix': audio})
    artifact = store.artifact(loaded['project_id'], 'mix')
    assert loaded['artifacts'][0]['sample_rate'] == 8000
    with pytest.raises(ValueError): store.artifact(loaded['project_id'], '../mix')
    artifact.write_bytes(b'changed')
    with pytest.raises(ValueError): store.artifact(loaded['project_id'], 'mix')
    path.write_text(json.dumps({**fixture(), 'duration_seconds': 8}))
    with pytest.raises(ValueError): store.import_analysis(path, {'mix': audio})


def test_shared_markup_and_source_fingerprint(tmp_path):
    path = tmp_path / 'sample.wav'; path.write_bytes(b'test')
    prepared = prepare_request(path, {}, 'align', '[AI Voice:] hello\n(world)', 'en', 'base', 'harmonix-all', True)
    assert prepared['lyrics_text'] == 'hello\n(world)'
    assert prepared['lyrics_source_text'] == '[AI Voice:] hello\n(world)'
    assert len(prepared['source_sha256']) == 64
    with pytest.raises(ValueError): prepare_request(path, {}, 'auto', 'ignored', None, 'base', 'harmonix-all', False)


def test_legacy_section_rounding_is_normalized_with_evidence():
    raw = fixture(); raw['sections'][0]['end'] = 10.04
    derived = migrate(raw)
    assert derived['sections'][0]['end'] == 10
    assert derived['sections'][0]['provenance']['original_interval']['end'] == 10.04
    assert raw['sections'][0]['end'] == 10.04
    raw['sections'][0]['end'] = 10.2
    with pytest.raises(ValueError): migrate(raw)
    raw = fixture(); raw['timebase']['offset_seconds'] = 1
    with pytest.raises(ValueError): migrate(raw)


def test_split_merge_and_repeat_inserts_are_deterministic(imported):
    store, project = imported; line = project['analysis']['lyrics']['phrases'][0]['id']
    edit = correction(project, [{'op': 'split_line', 'line_id': line, 'word_index': 1}])
    store.apply(project['project_id'], edit)
    split = store.read(project['project_id'])
    assert [r['text'] for r in split['analysis']['lyrics']['phrases']] == ['hi', 'there']
    other = split['analysis']['lyrics']['phrases'][1]['id']
    store.apply(project['project_id'], correction(split, [{'op': 'merge_lines', 'line_id': line, 'other_line_id': other}], 'merge'))
    assert store.read(project['project_id'])['analysis']['lyrics']['phrases'][0]['text'] == 'hi there'
    from core.projects import apply_operations
    a, b = migrate(fixture()), migrate(fixture())
    operation = [{'op': 'insert_word', 'line_id': line, 'after_id': a['lyrics']['words'][0]['id'], 'value': {'text': 'same'}}]
    apply_operations(a, operation, 'deterministic'); apply_operations(b, operation, 'deterministic')
    assert a == b


def test_project_cli_uses_same_store_and_exports_identical_revision(imported, tmp_path):
    import subprocess
    store, project = imported; key = project['project_id']
    word = project['analysis']['lyrics']['words'][0]['id']
    payload = correction(project, [{'op': 'replace_word', 'word_id': word, 'text': 'cli'}])
    path = tmp_path / 'correction.json'; path.write_text(json.dumps(payload))
    cli = [sys.executable, str(Path(__file__).resolve().parents[1] / 'project_cli.py'), '--project-root', str(store.root)]
    response = subprocess.run([*cli, 'apply', key, str(path)], capture_output=True, text=True, timeout=10)
    assert response.returncode == 0 and json.loads(response.stdout)['revision'] == 1
    exported = tmp_path / 'cli.json'
    response = subprocess.run([*cli, 'export', key, str(exported)], capture_output=True, text=True, timeout=10)
    assert response.returncode == 0
    store.export(key, tmp_path / 'core.json')
    assert exported.read_bytes() == (tmp_path / 'core.json').read_bytes()
