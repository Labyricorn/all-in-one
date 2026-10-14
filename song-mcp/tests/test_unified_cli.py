import json
import subprocess
import sys
import os
import wave
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'song-mcp'))
from cli import prepare_lyrics


def test_annotations_keep_vocal_content():
    source='First line\n\n(Backing vocal content)\n[AI Voice:] “You’re welcome.”'
    normalized,annotations=prepare_lyrics(source)
    assert '(Backing vocal content)' in normalized
    assert '“You’re welcome.”' in normalized
    assert '[AI Voice:]' not in normalized
    assert annotations==[{'source_line':4,'label':'[AI Voice:]','vocal_text':'“You’re welcome.”'}]
    assert source.endswith('[AI Voice:] “You’re welcome.”')


def test_punctuation_is_preserved_in_text_not_fake_word_record():
    from lyrics import convert_result
    result=convert_result({'segments':[{'words':[{'word':'hello','start':1.,'end':2.,'score':.9},{'word':'world','start':2.,'end':3.,'score':.9}]}]},4,'hello — world')
    assert result['text']=='hello — world'
    assert [w['text'] for w in result['words']]==['hello','world']
    assert result['phrases'][0]['text']=='hello — world'


def command(args):
    launcher = ['cmd.exe','/d','/c',str(ROOT/'analyze-song.cmd')] if os.name == 'nt' else [sys.executable, str(ROOT/'song-mcp/cli.py')]
    return subprocess.run([*launcher,*args],cwd=ROOT,env=dict(os.environ,MGMV_SONG_PYTHON=sys.executable),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)


@pytest.mark.parametrize('mode,expected',[('none','not_requested'),('instrumental','instrumental_declared')])
def test_actual_cli_modes_with_spaced_output(mode,expected,tmp_path,monkeypatch):
    from common import ANALYZER_PYTHON
    if not ANALYZER_PYTHON.is_file():
        pytest.skip('Install the isolated analyzer environment for CLI integration tests.')
    # Portable generated fixture: no user media, model downloads or old absolute paths.
    audio=tmp_path/'synthetic-120bpm.wav'
    with wave.open(str(audio),'wb') as stream:
        stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(44100)
        stream.writeframes(b'\0\0\0\0'*88200)
    cache=tmp_path/'structure.json'
    cache.write_text(json.dumps({'path':str(audio),'bpm':120,'beats':[0.,.5,1.,1.5],
        'downbeats':[0.],'beat_positions':[1,2,3,4],
        'segments':[{'start':0.,'end':2.,'label':'intro'}]}))
    monkeypatch.setenv('MGMV_WORKSPACE_ROOT',str(tmp_path))
    folder=tmp_path/('mode '+mode+' outputs')
    run=command([str(audio),'--lyrics',mode,'--offline','--structure-json',str(cache),'-o',str(folder)])
    assert run.returncode==0,run.stdout+run.stderr
    result=json.loads((folder/'synthetic-120bpm.analysis.json').read_text())
    assert result['lyrics']['status']==expected
    assert result['structure_provenance']['reused'] is True
    assert result['lyrics']['words']==[]


def test_actual_cli_usage_error_for_untimed_text_without_language(tmp_path):
    audio=tmp_path/'valid audio.wav'
    with wave.open(str(audio),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(44100)
        stream.writeframes(b'\0\0'*44100)
    result=command([str(audio),'--lyrics-text','known text'])
    assert result.returncode==2
    assert '--language' in result.stderr


def test_actual_cli_missing_input_is_readable_failure():
    result=command([str(ROOT/'verification/no-such-song.wav')])
    assert result.returncode==1
    assert 'existing file' in result.stderr
