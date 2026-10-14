# Shared backend and playback milestone

This milestone uses the existing two Python environments. It includes a headless
project CLI, SQLite revision storage, a versioned authenticated loopback API,
Streamable HTTP MCP alongside the existing stdio tools, a Web Audio playback
module, a browser debugging harness and reproducible companion source packaging.
It does not yet include the Tauri shell/editor or a standalone Windows installer.

From the parent MGMV workspace, use the new `song-project.cmd` and
`song-service.cmd` wrappers. In a portable fork installation use the same launchers
at the fork root. Set `MGMV_SONG_PYTHON` when the lyric interpreter lives elsewhere.
`MGMV_PROJECT_ROOT` relocates the SQLite database and project-owned PCM artifacts;
default storage is `MGMV_WORKSPACE_ROOT/song-projects`. The existing job root,
analyzer environment and model-cache overrides continue to work.

## Headless project workflow (terminal commands)

Run full music/lyrics analysis with `analyze-song.cmd` first; it remains independent
of the service. `analyze-music.cmd` remains structure-only. To create an editable
project from an existing combined result without another analysis pass:

```powershell
.\song-project.cmd import '.\.videos\My_Own_Song\My Own Song.analysis.json' `
  --mix '.\song-jobs\b85ea352c7934969b5d32b7ec6899725\original.wav' `
  --vocals '.\song-jobs\b85ea352c7934969b5d32b7ec6899725\demix\htdemucs\original\vocals.wav'
.\song-project.cmd list
.\song-project.cmd read PROJECT_ID
.\song-project.cmd validate PROJECT_ID
.\song-project.cmd apply PROJECT_ID 'C:\Projects\correction.json'
.\song-project.cmd history PROJECT_ID
.\song-project.cmd restore PROJECT_ID 0 --expected-revision 1 --transaction-id undo-1
.\song-project.cmd restore PROJECT_ID 1 --expected-revision 2 --transaction-id redo-1
.\song-project.cmd export PROJECT_ID 'C:\Projects\corrected.analysis.json'
```

The sample job paths above refer to this workspace's cached supplied-lyrics run.
For other media, use its job ID. Importing JSON without `--mix/--vocals` is allowed,
but playback needs a mix artifact. Media are copied into the project so retained
projects do not depend on the job cache lifetime. Hashes, sample rates, channel
counts, durations and processing identity are recorded. No separator runs on import.
Project reads expose stable word/line/beat/section/event IDs; use those IDs in edits.
IDs imported from identical raw analysis are identical across independent projects.

Example correction file (replace placeholders with the project read values):

```json
{
  "schema_version": 1,
  "project_id": "PROJECT_ID",
  "base_revision": 0,
  "base_analysis_sha256": "RAW_ANALYSIS_HASH",
  "transaction_id": "edit-1",
  "operations": [
    {"op": "replace_word", "word_id": "WORD_ID", "text": "Or"},
    {"op": "set_word_interval", "word_id": "WORD_ID", "start": 1.2, "end": 2.1}
  ]
}
```

`schemas/correction.schema.json` and `schemas/project.schema.json` define version 1.
`set_word_interval` also accepts `method: "guessed"` (with optional `basis`: `midpoint` or
`even_spread`) so an estimated time is stored as `timing_status: "guessed"`, provenance
method `guessed` and review state `needs_review`, and appears as a `guessed_word_timing`
review item. A later `set_tags` with `review_state: "reviewed"` on that word, or any
ordinary interval edit, makes it `user_set`. Guesses are interpolations, not alignments.
Corrections support insert/delete/replace words and lines, split/merge adjacent
lines, intervals, beat markers, selected-grid shift/stretch, section labels/bounds,
voice/delivery tags and riff/event records. `set_tags` uses `kind` and `id` plus a
`value` object. `insert_word` requires an existing `line_id`, a `value.text`, and
optionally `after_id`. `split_line` uses `line_id` and `word_index`; `merge_lines`
uses `line_id` and adjacent `other_line_id`. `transform_grid` uses `start`, `end`,
`scale` and `shift`; it transforms only selected beat times, preserving their IDs.
The current bar editor assumes the analyzer's 4/4 positions (1..4).

SQLite serializes writers across processes. Every accepted edit creates a complete
revision, audit record, retry transaction and revision event atomically. A failed
operation rolls back the whole transaction. Repeating an identical transaction ID
returns its original revision; different content with that ID fails. Stale edits
return CLI exit 4 / HTTP 409 / an actionable MCP error. Undo and redo restore a
selected snapshot as a new revision; use explicit expected revisions. All raw
predictions and previous corrections remain available in the store.

The selected result includes refreshed phrase bounds, display lyrics, grid indexes,
bar bounds, nearest-downbeat and preceding-beat references, and review diagnostics.
The uncovered tail is no longer absorbed into the final bar. Quantized animation
cue values are not inferred in this milestone. Legacy section rounding beyond
duration by at most 50 ms is clipped with the original interval in provenance.
Larger discrepancies fail import. Exact source lyrics and raw predictions remain
distinct from selected display text. Reanalysis continues to create separate jobs;
automatic candidate merging/rebasing onto edited projects is future work.

## Live service and playback (terminal and browser)

```powershell
.\song-service.cmd
```

The service binds only to `127.0.0.1`, selects a free port by default and writes
`song-service.json` containing API version, base URL, MCP URL and a per-run bearer
token. `--port 8765` selects an explicit port; occupied ports fail with diagnostics.
A healthy compatible service in the discovery file is reused. An OS-held startup
lease prevents competing launches sharing that discovery file and releases on
process exit/crash. Stale records are
health-checked; remote discovery URLs are rejected. Keep discovery/config files
local and outside Git. The service is a foreground development process; stop it
with Ctrl+C. Accepted detached analysis workers survive UI or service disconnects.
There is no automatic Windows background-service installation in this milestone.

The launcher opens and connects the browser review UI automatically, and prints
its direct URL. Use `--no-browser` for a console-only launch. Running the launcher
again opens the existing compatible service's UI. Open `BASE_URL/debug` for the smaller
playback debugger. The review UI imports/opens projects, plays project-owned PCM,
filters and selects lyric words, edits word text/timing, beat times and section
labels/bounds, and commits changes as revision-checked transactions through the
shared core. Two-In-One Music and Lyric Analysis Studio starts on Analyze:
select audio/video, choose a lyric
workflow and start a detached job. Jobs shows actual stages, errors/cancellation
and opens completed/partial results in Review with cached audio. Review adds
a waveform, section bands, downbeat ticks and loops. Export downloads corrected
JSON. The debugger remains useful for playback diagnostics.
Neither page is the planned Tauri editor.

`desktop/src/playback.mjs` starts both decoded tracks on the same AudioContext
clock and switches gains without resetting time. Reduced speed currently changes
pitch. Looping and metronome clicks use audio scheduling; UI repaint only displays
the cursor. `getOutputTimestamp()` drives the audible cursor when available;
latency fallback and a configurable measured correction are supported. Physical
speaker latency and device-specific compensation still need measurement. Browser
testing does not certify future Tauri/WebView behavior. Long tracks currently load
fully into memory. Two-In-One renders a peak overview from decoded PCM;
streamed playback and waveform zoom remain future work.

## Versioned API

All API and MCP requests require `Authorization: Bearer TOKEN`. Host/origin checks
reject non-local hosts and unrelated websites. The debug shell/health route reveals
no project data. A future Tauri bridge should issue authenticated native requests;
cross-origin browser CORS is not enabled here. Media routes accept project/role IDs,
never caller-supplied media paths. Hash checks precede serving project-owned WAVs.

| Method / path | Operation |
|---|---|
| GET `/health` | Compatible service identity and API version. |
| GET/POST `/api/v1/projects` | List, or import `analysis_path` / completed `job_id`. |
| POST `/api/v1/projects` with `analysis_data` | Import parsed JSON selected through the browser file picker, using shared migration/storage. |
| GET `/api/v1/projects/ID` | Complete selected snapshot. |
| POST `/api/v1/projects/ID/corrections` | Apply correction body with expected revision/hash. |
| GET/POST `/api/v1/projects/ID/proposals` | Inspect or save reviewable suggestions. |
| POST `/api/v1/projects/ID/restore` | Restore body `{correction, target_revision}` as a new revision. |
| GET `/api/v1/projects/ID/history` | Revision audit records. |
| POST `/api/v1/projects/ID/export` | Return selected analysis; optional body `revision`. |
| GET `/api/v1/projects/ID/artifacts/mix` or `/vocals` | Validated PCM artifact, with range responses. |
| GET `/api/v1/models` | Advisory report of cached lyric, alignment and music models (no downloads); the studio uses it to choose offline defaults. |
| GET/POST `/api/v1/jobs` | List jobs or submit normalized analysis request. |
| POST `/api/v1/media` | Copy a selected audio/video file from the browser, validate its stream, and return a path usable by job submission. |
| GET `/api/v1/jobs/ID` | Durable progress and failure/log details. |
| POST `/api/v1/jobs/ID/cancel` | Cancel selected worker tree; retain diagnostics. |
| GET `/api/v1/events?after=N` | SSE revision events and changed job state; reconnect from last revision event ID. |
| POST `/mcp` | Streamable HTTP MCP transport. |

The API executes file/database work in threads; heavy inference remains detached.
Revision events live in SQLite, so CLI and stdio edits reach HTTP subscribers.
Job changes are observed through the existing durable status files. Suggestions
can be polled through the proposals endpoint; proposal-notification events are not
implemented yet.

## MCP actions (connected chat, not terminal commands)

Existing tools remain available, including `submit_song`, `get_job`, `get_analysis`
and `get_song_map`. Added tools: `cancel_job`, `open_project`, `list_projects`,
`read_project`, `propose_correction`, `apply_correction`, `accept_correction` and
`export_project`. Use `read_project` to page stable IDs/history/proposals/review
items. Assistant suggestions use `propose_correction` by default; explicit user
authorization permits application. Accepted proposals still check the base revision.
Stdio clients access the same store without a running service.

Generate HTTP client settings in a terminal while the service is running:

```powershell
.\song-mcp\.venv\Scripts\python.exe .\all-in-one\song-mcp\configure_client.py --http-discovery .\song-service.json --format json
```

Use `--format toml` for Codex client settings. This prints a separate
`mgmv_song_live` entry; it does not edit any client configuration. Regenerate it
when the service restarts because its port/token can change. Keep the existing
stdio configuration for service-independent use.

## Debugging and development packaging

From the MGMV workspace:

```powershell
$env:MGMV_WORKSPACE_ROOT = (Get-Location).Path
$env:MGMV_ANALYZER_ROOT = Join-Path (Get-Location) 'all-in-one'
$env:MGMV_MODEL_CACHE = Join-Path (Get-Location) 'song-mcp\model-cache'
.\song-mcp\.venv\Scripts\python.exe .\all-in-one\song-mcp\doctor.py --imports
.\song-mcp\.venv\Scripts\python.exe -m pytest .\all-in-one\song-mcp\tests -q --basetemp .\verification\backend-tests
node --test .\all-in-one\desktop\tests\playback.test.mjs
.\song-mcp\.venv\Scripts\python.exe .\all-in-one\song-mcp\package_dev.py .\verification\packages\mgmv-backend-dev.zip
```

Doctor inspects runtime/dependency availability and optional analyzer/lyric imports
without downloads. Service `--log-level debug` adds transport/API diagnostics;
per-job `worker.log` remains the source for inference errors. HTTP/stdio tests
need unrestricted loopback and process communication. The zip has reproducible
metadata and a SHA-256 manifest. It contains companion source, contracts, launchers,
tests and attribution; no environments, weights, media, projects or machine-specific
client configuration. Extract it into a matching fork checkout and point the
launchers at the existing lyric environment. It is a companion development bundle,
not a complete analyzer/runtime distribution or installer.
