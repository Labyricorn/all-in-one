"""Run inside All-In-One's environment; reuse checked legacy music when possible."""
import json
import sys
from pathlib import Path

import soundfile as sf
import allin1
from allin1.demix import demix


def reusable_music(cache, source, duration):
    try:
        cache=Path(cache)
        music=json.loads(cache.read_text(encoding='utf-8'))
        if Path(music['path']).resolve()!=Path(source).resolve(): return None
        if Path(source).stat().st_mtime>cache.stat().st_mtime: return None
        if not all(k in music for k in ['bpm','beats','downbeats','beat_positions','segments']): return None
        if len(music['beats'])!=len(music['beat_positions']) or not music['segments']: return None
        if abs(float(music['segments'][-1]['end'])-duration)>.1: return None
        return music
    except (OSError,ValueError,KeyError,TypeError):
        return None


def main(directory):
    directory=Path(directory)
    request=json.loads((directory/'request.json').read_text(encoding='utf-8'))
    original=directory/'original.wav'
    duration=sf.info(original).duration
    cache=request.get('reuse_structure')
    music=reusable_music(cache,request['path'],duration) if cache else None
    if music is not None:
        print('Reusing structure JSON after source-path, source-age and duration checks:',cache,flush=True)
        music['path']=str(original)
        (directory/'music').mkdir(exist_ok=True)
        (directory/'music/original.json').write_text(json.dumps(music,indent=2),encoding='utf-8')
        (directory/'structure-provenance.json').write_text(json.dumps({'reused':True,'cache_path':cache,'validation':['same resolved source path','source not newer than result','matching decoded duration','required structure fields'],'legacy_model_identity':'not recorded in upstream JSON','legacy_hash_note':'The old result has no source hash; new CLI runs record SHA-256.'},indent=2),encoding='utf-8')
        if request['lyrics_mode'] in ('auto','align'):
            demix([original],directory/'demix','cpu')
    else:
        allin1.analyze(original,out_dir=directory/'music',demix_dir=directory/'demix',spec_dir=directory/'spec',keep_byproducts=True,multiprocess=False,model=request['music_model'],device='cpu')
        (directory/'structure-provenance.json').write_text(json.dumps({'reused':False,'model':request['music_model']}),encoding='utf-8')


if __name__=='__main__':main(sys.argv[1])
