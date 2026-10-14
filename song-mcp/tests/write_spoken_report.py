"""Render the completed evaluation into a compact report and timing plot."""
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get('MGMV_WORKSPACE_ROOT', Path(__file__).resolve().parents[2])).resolve()
OUT = ROOT / 'verification/spoken-fixture'


def main():
    result=json.loads((OUT/'evaluation.json').read_text())
    auto=result['automatic_segment_timing']
    supplied=result['supplied_text_segment_timing']
    words=result['alignment_word_coverage']
    lines=['# Spoken-audio MCP evaluation', '', 'Fixture: `2026-08-27_21-38-31.mp3` paired with its supplied SRT.', '', 'The reference contains 11 subtitle segments, not word-boundary timestamps. These comparisons measure differences from subtitle display bounds, not exact acoustic word/phrase accuracy.', '', '## Results', '', '| Measure | Result |', '|---|---|', f"| Automatic word error rate | {result['transcription']['word_error_rate']:.1%} ({result['transcription']['edit_distance']} edits / {result['transcription']['reference_words']} normalized reference words) |", f"| Automatic median absolute segment start/end difference | {auto['median_absolute_start_difference_seconds']:.3f} / {auto['median_absolute_end_difference_seconds']:.3f} seconds |", f"| Supplied-text median absolute segment start/end difference | {supplied['median_absolute_start_difference_seconds']:.3f} / {supplied['median_absolute_end_difference_seconds']:.3f} seconds |", f"| Supplied word records with accepted estimated timing | {words['accepted_timed_words']} / {words['supplied_words']} |", f"| Fully timed supplied phrases | {words['complete_phrases']} / 11 |", f"| Independent vs MCP PCM decode | {'Identical sample-for-sample' if result['timebase_check']['independent_decode_equals_mcp_original_sample_for_sample'] else 'Mismatch'} |", f"| Input SHA-256 verification | {'Both inputs unchanged' if result['inputs_preserved'] else 'Mismatch'} |", '', 'Word-error normalization: '+result['normalization'], '', '## Per-segment synchronization', '', 'Positive differences mean the estimate occurs later than the subtitle boundary. Bounds use the first/last accepted matching word; incomplete phrases remain incomplete in the actual MCP output.', '', '| Segment | Auto start difference | Auto end difference | Supplied start difference | Supplied end difference | Supplied timed words |', '|---|---:|---:|---:|---:|---:|']
    for a,b in zip(auto['segments'],supplied['segments']):
        def number(v):return 'missing' if v is None else f'{v:+.3f} s'
        lines.append(f"| {a['segment']} | {number(a['start_difference_seconds'])} | {number(a['end_difference_seconds'])} | {number(b['start_difference_seconds'])} | {number(b['end_difference_seconds'])} | {b['timed_word_records']} / {b['expected_whitespace_words']} |")
    lines += ['', f'![Timing discrepancies]({(OUT / "timing-discrepancies.png").as_posix()})', '', '## Interpretation and limits', '', 'The MCP retained the decoded audio origin and complete sample sequence. Segment differences are therefore not an application-added global trimming/offset. Subtitle intervals can include pauses or group text differently from the detected speech. Poor word scores and missing matches remain null; no timestamps were spread evenly or snapped to the SRT.', '', 'The speech fixture does not validate singing, musical beats, or song-section labeling. Lip-sync is outside the requested scope. The supplied transcript/times were not independently checked against human word-boundary annotations.', '', '## Artifacts', '', '- `evaluation.json`: complete metrics, edit operations, timing rows, decode checks, and input hashes.', '- `automatic-segments.csv` and `supplied_text-segments.csv`: timing discrepancies and coverage by cue.', '- `auto-analysis.json` and `align-analysis.json`: combined MCP result snapshots with word/phrase records.', '- `auto-mcp.json` and `align-mcp.json`: actual initialized MCP sessions, job IDs, status, and paged retrieval counts.', '- `original-audio-diagnostic-metrics.json`: diagnostic comparison before vocal separation.', '- `regression-tests.log`: current contract/protocol/evaluation checks.', '', 'The original files in `test-transcription-audio` were preserved. Test-generated audio and job artifacts remain separate under `verification/spoken-fixture` and `song-jobs`.', '']
    (OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True)
    for axis,field,title in zip(axes,['start_difference_seconds','end_difference_seconds'],['Segment starts','Segment ends']):
        for data,label,color in [(auto,'Automatic transcription','#2563eb'),(supplied,'Supplied-text alignment','#c2410c')]:
            axis.plot([r['segment'] for r in data['segments']],[r[field] for r in data['segments']],marker='o',label=label,color=color)
        axis.axhline(0,color='#374151',linestyle='--',linewidth=1)
        axis.set_title(title,loc='left');axis.set_ylabel('Estimate âˆ’ SRT (seconds)');axis.grid(alpha=.2)
    axes[0].legend();axes[1].set_xlabel('SRT segment');axes[1].set_xticks(range(1,12))
    fig.suptitle('Speech fixture: discrepancies from supplied subtitle boundaries')
    fig.tight_layout();fig.savefig(OUT/'timing-discrepancies.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
