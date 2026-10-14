# Song Studio

Run song-service.cmd (or double-click it). It opens Song Studio in your default
browser and connects automatically. The console prints a direct Review UI link;
keep the service running while using the studio. Use --no-browser for console-only
startup. Launching again reconnects to an existing compatible service.

## Analyze

The initial tab starts a new analysis directly from an audio/video file picker.
Listen to a local preview before starting. Choose a lyric workflow:

- **Transcribe automatically**: music structure plus recognized lyric candidates.
- **Align my supplied lyrics**: paste lyrics or choose a UTF-8 text file and select
  the language. Keep line breaks and repeated choruses.
- **Instrumental**: explicitly declare that there are no lyrics.
- **Music structure only**: skip lyric processing.

Select the full ensemble or faster single music model, a lyric model and language.
Cached-model mode is enabled initially; clear it to permit missing model downloads.
Start analysis copies and validates the selected file locally, then submits the
same persistent worker used by CLI/MCP. One CPU analysis runs at a time. Accepted
work survives browser or service disconnects.

## Jobs

Actual job stages/status update every three seconds while the page is visible.
Cancel an active job, inspect failure/partial-result details or open a completed
result in Review. A partial result retains available music analysis and shows its
errors. Opening a job imports cached PCM mix/vocals without another separation
pass. That tab session remembers the imported project for subsequent opens.

## Review

Choose a saved project or import combined analysis JSON with the file picker.
JSON-only imports are editable without audio; job imports retain available tracks.
The waveform uses original-origin decoded mix PCM with section bands and downbeat
ticks. Click the waveform or a timed word to seek. Playback supports synchronized
mix/vocals, slower playback, region loops and a metronome. Slower playback changes
pitch. Long tracks load fully into memory.

Filter words by text/phrase, select a word and save its text/timing, adjust a beat
time or edit section label/bounds. Saves use revision/hash preconditions and create
durable correction transactions. Stale edits are rejected; **Reload latest**
retrieves the current revision. Displayed timings are rounded for forms; untouched
values retain their original precision.

## Export

Download the selected project's latest saved corrected analysis JSON. Downloads
include the selected timeline and saved corrections, using seconds from the
original decoded audio origin.

## Connection and storage

The launcher passes its token in a URL fragment, which is never sent in HTTP
requests. The page removes the fragment and keeps the token in tab session storage
so reload remains connected. Manual entry lives under Connection settings.

Selected media copies live in MGMV_WORKSPACE_ROOT/song-inputs; jobs in song-jobs;
projects and copied playback artifacts in song-projects (or MGMV_PROJECT_ROOT).
These are runtime data outside source. The authenticated media route streams files
up to 2 GB, validates an audio stream and removes rejected/incomplete copies.
Accepted files remain available for detached workers. Source files are preserved.

This is an initial working browser workflow. Native Tauri dialogs/installer,
waveform zoom, line/event/grid forms, undo/redo controls, candidate audition,
autosave and automatic reanalysis merging remain later work. The /debug page
remains available for focused playback diagnostics.
