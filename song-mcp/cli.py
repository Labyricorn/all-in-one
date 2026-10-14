"""Unified foreground CLI backed by the same persistent worker as MCP."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
import csv
from pathlib import Path

import psutil
from common import ROOT,JOBS,SOURCE_DIR,ANALYZER_PYTHON,worker_command,acquire_slot,release_slot,read_json,write_json,probe_media
from songmap import planning_page
from core.requests import digest, prepare_lyrics, prepare_request


def parser():
    p=argparse.ArgumentParser(description='Analyze music structure AND lyrics into one song map. Runs locally on CPU; no MCP client required.')
    p.add_argument('path',help='Local audio/video file; quote paths containing spaces.')
    p.add_argument('-o','--out-dir',type=Path,default=Path('song-results'),help='Output folder (default: ./song-results).')
    p.add_argument('--lyrics',choices=['auto','align','instrumental','none'],default=None,help='Lyric mode (default: auto, or align when supplied text is provided).')
    group=p.add_mutually_exclusive_group()
    group.add_argument('--lyrics-file',type=Path,help='UTF-8 untimed lyrics file; selects align mode unless a mode is given.')
    group.add_argument('--lyrics-text',help='Supplied untimed lyrics text; use --lyrics-file for multiline text.')
    p.add_argument('--language',help='Language code, e.g. en. Auto-detected for automatic transcription; required for supplied-text alignment.')
    p.add_argument('--lyric-model',choices=['tiny','base','small','medium'],default='base',help='ASR model (default: base).')
    p.add_argument('-m','--model',choices=['harmonix-all','harmonix-fold0'],default='harmonix-all',help='Music model (default: harmonix-all).')
    p.add_argument('--offline',action='store_true',help='Require cached models/tokenizers; do not download weights.')
    p.add_argument('-v','--visualize',action='store_true',help='Save timeline PDF under OUT_DIR/viz.')
    p.add_argument('-s','--sonify',action='store_true',help='Save timing-cue WAV under OUT_DIR/sonif.')
    p.add_argument('--overwrite',action='store_true',help='Ignore cached combined/legacy structure results and recompute.')
    p.add_argument('--structure-json',type=Path,help='Reuse legacy structure JSON if source path/age/duration match. Otherwise recompute.')
    return p


def export(directory,out,stem,args,signature):
    result=read_json(directory/'analysis.json')
    if args._source_text is not None:
        result['lyrics'].setdefault('alignment_text',result['lyrics'].get('text'))
        result['lyrics']['text']=args._source_text
        result['lyrics']['annotations']=args._annotations
    if (directory/'structure-provenance.json').is_file():
        result['structure_provenance']=read_json(directory/'structure-provenance.json')
    result['run']={'job_id':directory.name,'job_directory':str(directory),'source_sha256':signature['source_sha256'],'lyric_mode':signature['mode']}
    target=out/f'{stem}.analysis.json'
    write_json(target,result)
    write_json(out/f'{stem}.lyrics.json',result['lyrics'])
    (out/f'{stem}.lyrics.txt').write_text(result['lyrics'].get('text') or '',encoding='utf-8')
    if args._source_text is not None:
        reference=out/f'{stem}.reference.lyrics.txt'
        if args.lyrics_file and args.lyrics_file.resolve()!=reference.resolve():
            import shutil
            shutil.copy2(args.lyrics_file,reference)
        elif not args.lyrics_file:reference.write_text(args._source_text,encoding='utf-8')
        (out/f'{stem}.alignment.txt').write_text(result['lyrics'].get('alignment_text') or '',encoding='utf-8')
    write_json(out/f'{stem}.song-map.json',planning_page(result,0,result['duration_seconds'],0,len(result['sections']) or 1))
    with (out/f'{stem}.lyric-words.csv').open('w',encoding='utf-8',newline='') as file:
        writer=csv.writer(file);writer.writerow(['index','text','start_seconds','end_seconds','timing_status','flags'])
        for i,word in enumerate(result['lyrics']['words'],1):
            writer.writerow([i,word['text'],word['start'],word['end'],word['timing_status'],','.join(word['flags'])])
    timed=sum(word['start'] is not None for word in result['lyrics']['words'])
    lines=[f'# {stem}: song analysis','',f"Source: `{result['source']}`",f"Duration: {result['duration_seconds']:.3f} seconds. Tempo estimate: {result['tempo']['bpm']} BPM.",f"Lyric mode: {args.lyrics}. Status: {result['lyrics']['status']}. Accepted estimated word times: {timed}/{len(result['lyrics']['words'])}.",'','All times are seconds from the first decoded original audio sample. Singing text and timings require review; null/overlapping/low-score estimates are not verified facts.','','## Sections','','| Start | End | Model label |','|---:|---:|---|']
    for section in result['sections']:lines.append(f"| {section['start']:.2f} | {section['end']:.2f} | {section['label']} |")
    lines += ['','## Lyric phrases','','| Start | End | Status | Text |','|---:|---:|---|---|']
    for phrase in result['lyrics']['phrases']:
        begin='untimed' if phrase['start'] is None else f"{phrase['start']:.3f}"
        end='untimed' if phrase['end'] is None else f"{phrase['end']:.3f}"
        content=phrase['text'].replace('|','\\|')
        lines.append(f"| {begin} | {end} | {phrase['timing_status']} | {content} |")
    if result['lyrics'].get('annotations'):
        lines += ['','## Speaker annotations','']
        for annotation in result['lyrics']['annotations']:
            lines.append(f"- Source line {annotation['source_line']}: {annotation['label']} {annotation['vocal_text']} (label excluded from sung words; content retained).")
            matched=[p for p in result['lyrics']['phrases'] if p['text']==annotation['vocal_text']]
            if not matched or any(p['start'] is None for p in matched):
                lines.append('  Timing for this annotated phrase is missing/incomplete; review the original audio. No timing was invented.')
    lines += ['','## Warnings','']+['- '+warning for warning in result['warnings']]
    if result['lyrics'].get('error'):lines+=['','Lyric failure: '+result['lyrics']['error']]
    (out/f'{stem}.report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    optional_error=False
    if args.visualize or args.sonify:
        print('Generating optional timeline/timing-cue audio...',flush=True)
        command=[str(ANALYZER_PYTHON),str(SOURCE_DIR/'render_outputs.py'),str(directory),str(out),stem]
        if args.visualize:command.append('--visualize')
        if args.sonify:command.append('--sonify')
        proc=subprocess.run(command)
        optional_error=proc.returncode!=0
        if optional_error:print('Optional rendering failed; combined JSON/lyrics were still saved.',file=sys.stderr)
    if result['lyrics'].get('status')!='failed':
        write_json(out/f'{stem}.run.json',{'signature':signature,'job_id':directory.name})
    print('Combined analysis:',target,flush=True)
    print('Lyrics text:',out/f'{stem}.lyrics.txt',flush=True)
    print('Lyric words/phrases:',out/f'{stem}.lyrics.json',flush=True)
    print('Song map:',out/f'{stem}.song-map.json',flush=True)
    print('Lyric status:',result['lyrics']['status'],'(estimates; review warnings)',flush=True)
    if result['lyrics'].get('error'):print('Lyric processing failed:',result['lyrics']['error'],file=sys.stderr)
    return 3 if result['lyrics'].get('status')=='failed' or optional_error else 0


def main(argv=None):
    p=parser();args=p.parse_args(argv)
    proc=None;job_id=None
    try:
        source,probe=probe_media(str(Path(args.path).resolve()))
        text=args.lyrics_file.read_text(encoding='utf-8-sig') if args.lyrics_file else args.lyrics_text
        args.lyrics=args.lyrics or ('align' if text is not None else 'auto')
        if args.lyrics=='align' and (not text or not text.strip() or not args.language):
            p.error('Alignment requires --lyrics-file/--lyrics-text and --language, e.g. en.')
        if args.lyrics!='align' and text is not None:p.error('Supplied text is only valid in align mode.')
        if text is not None and len(text)>100000:p.error('Supplied lyrics exceed 100,000 characters.')
        if args.language:
            from faster_whisper.tokenizer import _LANGUAGE_CODES
            if args.language not in _LANGUAGE_CODES:p.error('Unsupported language code: '+args.language)
        args._source_text=text
        normalized,args._annotations=prepare_lyrics(text) if text is not None else (None,[])
        out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
        signature={'source_sha256':digest(source),'source_path':str(source),'mode':args.lyrics,'lyrics_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest() if text is not None else None,'language':args.language,'lyric_model':args.lyric_model,'music_model':args.model,'pipeline_version':'unified-cli-2'}
        manifest=out/f'{source.stem}.run.json'
        reusable_job=None
        if not args.overwrite and manifest.is_file():
            cached=read_json(manifest)
            directory=JOBS/cached['job_id']
            previous=cached['signature']
            if previous.get('source_sha256')==signature['source_sha256'] and previous.get('source_path')==signature['source_path']:
                reusable_job=directory.name
            if cached['signature']==signature and (directory/'analysis.json').is_file() and (directory/'music/original.json').is_file():
                print('Reusing completed analysis with matching source/text/settings hashes.',flush=True)
                return export(directory,out,source.stem,args,signature)
        job_id=uuid.uuid4().hex;acquire_slot(job_id)
        directory=JOBS/job_id;directory.mkdir()
        legacy=args.structure_json.resolve() if args.structure_json else out/f'{source.stem}.json'
        request=prepare_request(source,probe,args.lyrics,text,args.language,args.lyric_model,args.model,args.offline)
        request.update(reuse_structure=str(legacy) if not args.overwrite and args.model=='harmonix-all' and legacy.is_file() else None,reuse_stems_job=reusable_job)
        write_json(directory/'request.json',request)
        write_json(directory/'status.json',{'job_id':job_id,'status':'queued','stage':'starting_worker','created':time.time(),'updated':time.time(),'source':str(source),'log_path':str(directory/'worker.log')})
        env=dict(os.environ,OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONUNBUFFERED='1',PYTHONIOENCODING='utf-8')
        with (directory/'worker.log').open('ab') as log:
            proc=subprocess.Popen(worker_command(job_id),stdout=log,stderr=log,stdin=subprocess.DEVNULL,cwd=str(ROOT),env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        write_json(directory/'process.json',{'pid':proc.pid,'created':psutil.Process(proc.pid).create_time()})
        print('Job:',job_id,'| Progress log:',directory/'worker.log',flush=True)
        last=None;last_print=time.time();started=last_print
        while proc.poll() is None:
            state=read_json(directory/'status.json')
            if state['stage']!=last:print('Stage:',state['stage'],flush=True);last=state['stage']
            if time.time()-last_print>=20:
                print(f"Still running {state['stage']} ({int(time.time()-started)} seconds); detailed progress is in worker.log.",flush=True)
                last_print=time.time()
            time.sleep(1)
        state=read_json(directory/'status.json')
        if state['status'] not in ('complete','partial'):
            raise RuntimeError(state.get('error','Worker failed unexpectedly. See '+str(directory/'worker.log')))
        return export(directory,out,source.stem,args,signature)
    except KeyboardInterrupt:
        if proc is not None:
            try:
                parent=psutil.Process(proc.pid)
                children=parent.children(recursive=True)
                for child in children:child.terminate()
                parent.terminate();psutil.wait_procs([parent,*children],timeout=5)
            except psutil.Error:pass
        if job_id and (JOBS/job_id/'status.json').is_file():
            cancelled=read_json(JOBS/job_id/'status.json')
            cancelled.update(status='cancelled',stage='cancelled',updated=time.time())
            write_json(JOBS/job_id/'status.json',cancelled)
        print('Cancelled; partial diagnostics remain in the job folder.',file=sys.stderr)
        return 130
    except Exception as error:
        print('Analysis failed:',error,file=sys.stderr)
        if job_id:print('See job log:',JOBS/job_id/'worker.log',file=sys.stderr)
        return 1
    finally:
        if job_id:release_slot(job_id)


if __name__=='__main__':raise SystemExit(main())
