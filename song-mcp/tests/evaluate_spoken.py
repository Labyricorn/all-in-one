"""User speech fixture evaluation through actual MCP; SRT is segment ground truth."""
import asyncio
import csv
import hashlib
import json
import os
import re
import shutil
import statistics
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import tomli
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT
from configure_client import configuration
OUT = ROOT / 'verification/spoken-fixture'
INPUT = ROOT / 'test-transcription-audio'


def tokens(text):
    text = unicodedata.normalize('NFKC', text).casefold().replace('’', "'")
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", text, flags=re.UNICODE)


def clock(text):
    h, m, rest = text.replace(',', '.').split(':')
    return int(h)*3600 + int(m)*60 + float(rest)


def parse_srt(text):
    pattern = r'(?m)^([0-9]+)\s*\n([0-9:,]+)\s*-->\s*([0-9:,]+)[^\n]*\n(.*?)(?=\n\s*\n|\Z)'
    return [{'index': int(m[0]), 'start': clock(m[1]), 'end': clock(m[2]), 'text': m[3].strip().replace('\n', ' ')} for m in re.findall(pattern, text.replace('\r\n', '\n'), flags=re.DOTALL)]


def wer(reference, prediction):
    # Full edit-distance alignment, with operation counts and substitutions.
    a, b = tokens(reference), tokens(prediction)
    dp = [[0]*(len(b)+1) for _ in range(len(a)+1)]
    for i in range(len(a)+1): dp[i][0] = i
    for j in range(len(b)+1): dp[0][j] = j
    for i in range(1,len(a)+1):
        for j in range(1,len(b)+1):
            dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+(a[i-1]!=b[j-1]))
    i,j=len(a),len(b)
    changes=[]
    while i or j:
        if i and j and dp[i][j] == dp[i-1][j-1]+(a[i-1]!=b[j-1]):
            if a[i-1]!=b[j-1]: changes.append({'operation':'substitution','reference':a[i-1],'recognized':b[j-1]})
            i-=1;j-=1
        elif i and dp[i][j]==dp[i-1][j]+1:
            changes.append({'operation':'deletion','reference':a[i-1]});i-=1
        else:
            changes.append({'operation':'insertion','recognized':b[j-1]});j-=1
    changes.reverse()
    return {'reference_words':len(a),'recognized_words':len(b),'edit_distance':dp[-1][-1],'word_error_rate':dp[-1][-1]/len(a), 'operation_counts':{name:sum(c['operation']==name for c in changes) for name in ['substitution','deletion','insertion']},'differences':changes}


def payload(result):
    if result.is_error:
        raise RuntimeError(result.content[0].text)
    return result.structured_content or json.loads(result.content[0].text)


async def run_mode(audio, cues, mode):
    saved=OUT/(mode+'-mcp.json')
    parameters=configuration()
    params=StdioServerParameters(command=parameters['command'],args=parameters['args'],cwd=parameters['cwd'],env=dict(os.environ,**parameters['env']))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            handshake=await session.initialize()
            if saved.is_file():
                record=json.loads(saved.read_text())
                job_id=record['job_id']
            else:
                args={'path':str(audio),'lyrics_mode':mode,'language':'en','lyric_model':'base','music_model':'harmonix-fold0','offline':True}
                if mode=='align':args['lyrics_text']='\n'.join(c['text'] for c in cues)
                record=payload(await session.call_tool('submit_song',args))
                record['handshake']=handshake.model_dump(mode='json')
                saved.write_text(json.dumps(record,indent=2),encoding='utf-8')
                job_id=record['job_id']
                print(mode,'submitted',job_id,flush=True)
            stage=None
            for _ in range(1200):
                state=payload(await session.call_tool('get_job',{'job_id':job_id}))
                if state['stage']!=stage:
                    print(mode,state['status'],state['stage'],flush=True);stage=state['stage']
                if state['status'] not in ('queued','running'):break
                await asyncio.sleep(3)
            if state['status'] not in ('complete','partial'):
                raise RuntimeError(json.dumps(state))
            overview=payload(await session.call_tool('get_analysis',{'job_id':job_id}))
            pages=[];offset=0
            while True:
                page=payload(await session.call_tool('get_analysis',{'job_id':job_id,'component':'lyric_words','offset':offset,'limit':100}))
                pages.extend(page['items'])
                if page['next_offset'] is None:break
                offset=page['next_offset']
            full=json.loads(Path(state['analysis_path']).read_text(encoding='utf-8'))
            assert pages==full['lyrics']['words']
            (OUT/(mode+'-analysis.json')).write_text(json.dumps(full,indent=2),encoding='utf-8')
            record.update(status=state,overview=overview,paged_words_count=len(pages))
            saved.write_text(json.dumps(record,indent=2),encoding='utf-8')
            return full


def timing_comparison(cues,result,mode):
    words=result['lyrics']['words']
    rows=[]
    if mode=='align':
        cursor=0
        for cue in cues:
            n=len(cue['text'].split())
            part=words[cursor:cursor+n];cursor+=n
            rows.append(cue_row(cue,part))
    else:
        # Match lexical content, not timestamp overlap, to avoid hiding drift.
        refs=[t for cue in cues for t in tokens(cue['text'])]
        pred=[t for word in words for t in tokens(word['text'])]
        pred_words=[word for word in words for _ in tokens(word['text'])]
        matched={}
        for block in SequenceMatcher(None,refs,pred,autojunk=False).get_matching_blocks():
            for i in range(block.size):matched[block.a+i]=pred_words[block.b+i]
        cursor=0
        for cue in cues:
            n=len(tokens(cue['text']))
            part=[matched[i] for i in range(cursor,cursor+n) if i in matched];cursor+=n
            rows.append(cue_row(cue,part))
    valid=[r for r in rows if r['estimated_start'] is not None]
    return {'comparison_basis':'first/last accepted aligned word in each subtitle segment; subtitle display bounds may contain silence','segments_total':len(rows),'segments_with_any_timed_matching_words':len(valid),'median_absolute_start_difference_seconds':statistics.median(abs(r['start_difference_seconds']) for r in valid) if valid else None,'median_absolute_end_difference_seconds':statistics.median(abs(r['end_difference_seconds']) for r in valid) if valid else None,'max_absolute_start_difference_seconds':max((abs(r['start_difference_seconds']) for r in valid),default=None),'max_absolute_end_difference_seconds':max((abs(r['end_difference_seconds']) for r in valid),default=None),'segments':rows}


def cue_row(cue,part):
    valid=[w for w in part if w['start'] is not None]
    start=min((w['start'] for w in valid),default=None)
    end=max((w['end'] for w in valid),default=None)
    return {'segment':cue['index'],'reference_start':cue['start'],'reference_end':cue['end'],'estimated_start':start,'estimated_end':end,'start_difference_seconds':round(start-cue['start'],4) if start is not None else None,'end_difference_seconds':round(end-cue['end'],4) if end is not None else None,'expected_whitespace_words':len(cue['text'].split()),'matched_word_records':len(part),'timed_word_records':len(valid),'word_midpoints_inside_reference_segment':sum(cue['start'] <= (w['start']+w['end'])/2 <= cue['end'] for w in valid)}


async def main():
    OUT.mkdir(exist_ok=True,parents=True)
    pairs=[(p,p.with_suffix('.srt')) for p in INPUT.glob('*.mp3') if p.with_suffix('.srt').is_file()]
    if len(pairs)!=1:raise ValueError('This evaluation expects the discovered single MP3/SRT pair.')
    audio,subtitle=pairs[0]
    cues=parse_srt(subtitle.read_text(encoding='utf-8-sig'))
    assert len(cues)==11
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [audio,subtitle]}
    inventory={'pairs':[{'audio':str(audio),'transcript':str(subtitle),'reference_granularity':'subtitle segments, not words','segment_count':len(cues)}],'input_sha256':hashes,'cues':cues}
    (OUT/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    automatic=await run_mode(audio,cues,'auto')
    aligned=await run_mode(audio,cues,'align')
    report={'fixture_kind':'spoken audio with subtitle references; not singing','reference_granularity':'11 SRT subtitle segments; no word-boundary ground truth','transcription':wer(' '.join(c['text'] for c in cues),automatic['lyrics']['text'] or ''),'automatic_segment_timing':timing_comparison(cues,automatic,'auto'),'supplied_text_segment_timing':timing_comparison(cues,aligned,'align'),'alignment_word_coverage':{'supplied_words':len(aligned['lyrics']['words']),'accepted_timed_words':sum(w['start'] is not None for w in aligned['lyrics']['words'])},'decoded_duration_seconds':automatic['duration_seconds'],'container_timebase':automatic['timebase'],'input_sha256':hashes,'inputs_preserved':all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.name] for p in [audio,subtitle]),'scope':'Transcription and phrase synchronization for typography/scene cues; lip-sync excluded by user.','limits':['SRT display intervals are not necessarily precise acoustic phrase onsets/offsets.','No word-time accuracy can be established from these references.','Music-structure predictions on speech are not evaluated and must not be treated as meaningful musical beats/sections.','Speech results do not establish singing transcription/timing performance.']}
    report['alignment_word_coverage']['complete_phrases']=sum(p['start'] is not None for p in aligned['lyrics']['phrases'])
    report['normalization']='Unicode NFKC, case-folding, apostrophe normalization, punctuation removed; no number expansion or paraphrase equivalence.'
    original=OUT/'original-audio-diagnostic-metrics.json'
    if original.is_file():report['direct_original_audio_diagnostic']=json.loads(original.read_text())
    # The independent FFmpeg decode verifies no trimming/time shift was introduced
    # by the application, without pretending SRT bounds are acoustic ground truth.
    import soundfile as sf
    import numpy as np
    independent, sr=sf.read(OUT/'independent-decode.wav',dtype='int16')
    waveform_path=Path(json.loads((OUT/'auto-mcp.json').read_text())['status']['analysis_path']).parent/'original.wav'
    actual, actual_sr=sf.read(waveform_path,dtype='int16')
    equal=independent.shape==actual.shape and sr==actual_sr and np.array_equal(independent,actual)
    report['timebase_check']={'independent_decode_equals_mcp_original_sample_for_sample':bool(equal),'sample_rate':sr,'decoded_samples':len(actual),'decoded_duration_seconds':len(actual)/actual_sr,'reference_last_segment_end':cues[-1]['end'],'audio_tail_after_final_reference_seconds':len(actual)/actual_sr-cues[-1]['end'],'no_application_shift_introduced':bool(equal)}
    (OUT/'evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    for mode in ['automatic','supplied_text']:
        rows=report[mode+'_segment_timing']['segments']
        with (OUT/(mode+'-segments.csv')).open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:v for k,v in report.items() if k not in ('input_sha256','container_timebase')},indent=2),flush=True)


if __name__=='__main__':asyncio.run(main())
