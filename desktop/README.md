# Two-In-One Music and Lyric Analysis Studio

Run song-service.cmd (or double-click it). It opens Two-In-One in your default
browser and connects automatically. The console prints a direct Review UI link;
keep the service running while using the studio. Use --no-browser for console-only
startup. Launching again reconnects to an existing compatible service.

The studio follows four steps, shown in the bar at the top: **Choose a song**,
**Analysis**, **Review and fix** and **Export**. You can move between steps at any
time. A welcome panel on the first step explains the flow; choose "Don't show this
again" to hide it, or reopen it from **Help**. **Help** (or the ? key) also lists the
keyboard shortcuts.

## 1. Choose a song

Pick an audio or video file and preview it. Then answer "Does the song have lyrics?":

- **Yes, find them for me**: music structure plus recognized lyric candidates.
- **Yes, and I have the lyrics**: paste them or load a UTF-8 text file and choose the
  language. Keep line breaks and repeated choruses. This gives the most reliable words.
- **No, it is instrumental**: structure only, with no lyrics expected.
- **Skip lyrics for now**: structure only.

Choose **Quick** (single music model, tiny lyric model), **Balanced** (full music
ensemble, base lyric model; the default) or **Most accurate** (full ensemble, medium
lyric model). **Advanced settings** exposes the individual models and the offline option.

The studio checks which models are already on this computer (`GET /api/v1/models`) and
says so under the presets. When everything needed is cached, "use only models already
on this computer" is turned on for you; when something is missing it is turned off, and
the first run will download it, which needs internet access. Changing it yourself is
remembered for the visit. Start analysis copies and validates the file locally, then
submits the same persistent worker used by the CLI and MCP. One CPU analysis runs at
a time, and accepted work survives browser or service disconnects.

## 2. Analysis

Each job shows four plain-language stages: preparing the audio, finding beats and
sections, working out the lyrics and saving the results. The page refreshes by itself.
You can cancel an active job, read failure details, try again, or open a finished or
partial result in Review. A partial result keeps the music analysis and explains what
failed. Opening a job imports cached PCM mix/vocals without another separation pass.

## 3. Review and fix

The song and its waveform stay pinned at the top. Under them, lyrics (the main pane)
sit beside a tool panel. This workspace never needs page scrolling.

**Player.** Play or pause (Space), listen to the full mix or vocals only, slow playback
(which also lowers pitch), turn on beat clicks, click the waveform to jump, or drag
across it to loop a region. Long tracks load fully into memory.

**Lyrics.** Lines are grouped under their section. The current line is highlighted and
the pane scrolls to keep it in view while the song plays. **Follow playback** (F) turns
that on or off; scrolling by hand turns it off and shows **Jump to now**. Click a word to
select and hear it (or jump there while playing). Underlines show timing quality: dashed
red for no timing, dotted amber with ≈ for a guessed time, dotted grey for low confidence.
Find a word dims lines without it.
Clicking any word always moves the playhead: a timed word jumps to its start, an untimed
word to the nearest timed neighbor. If a loop is active and the click is outside it, the
loop is cleared. Choose **Clear selection**, press Esc or click empty space in the lyrics
to deselect; the playhead stays where it is.

**Selected word.** Change the text and the start and end times. Nudge buttons move by
50 or 10 milliseconds, and "Use playhead" captures the current position (for an untimed
word it also proposes a typical end). Play this word, loop its line (L), save with
Ctrl+Enter, or **Save and go to next issue**. N and P step through issues.

**Needs attention.** Lists words with no timing, low confidence, overlaps and guesses,
with filters, Previous/Next and a note when the beat grid stops early.

**Guess missing times.** Turn on **Guess close untimed lyrics** and a single untimed word
between two timed words is placed in the middle of the gap. That reveals **Guess
successive untimed lyrics**, which spreads a run of untimed words evenly across the gap
between its timed neighbors, plus **Snap guesses to the nearest beat** (off by default),
**Skip gaps longer than N seconds** (default 4; longer gaps are probably instrumental
breaks) and where to guess: the whole song, the selected word's line, or its section. A
preview states how many words will be guessed and why others are skipped (neighbors
overlap or leave no room, the gap is too long, or one side has no timed word), and
highlights them in the lyrics. Applying saves one revision and marks each word as a guess
(`timing_status: "guessed"`, method `guessed`, needs review). Select a guess and choose
**Approve this time** (or **Approve and go to next**, or **Approve all guesses**) and it
becomes an ordinary user-set time. Editing a guess also makes it user-set. Undo reverses
all guesses at once.

**Beats and sections.** Step to the beat nearest the playhead, nudge it, or move it to
the playhead. Pick a section to change its label and bounds. Beats and sections edit
through the same revision-checked corrections.

**Saving.** Every change is a durable revision. Undo and redo restore earlier revisions
as new ones, for the current visit to a project. A stale edit is rejected with an
explanation; **Reload** retrieves the newest version. Displayed timings are rounded in
forms; untouched values keep their original precision.

## 4. Export

Shows how many words are untimed, still guessed or set by you, warns when any remain,
and downloads the selected project's latest saved analysis JSON, using seconds from the
original decoded audio origin.

## Connection and storage

The launcher passes its token in a URL fragment, which is never sent in HTTP
requests. The page removes the fragment and keeps the token in tab session storage
so reload remains connected. Manual entry lives under Connection. Only the hidden
state of the welcome panel is kept in browser local storage.

Selected media copies live in MGMV_WORKSPACE_ROOT/song-inputs; jobs in song-jobs;
projects and copied playback artifacts in song-projects (or MGMV_PROJECT_ROOT).
These are runtime data outside source. The authenticated media route streams files
up to 2 GB, validates an audio stream and removes rejected/incomplete copies.
Accepted files remain available for detached workers. Source files are preserved.

This is a working browser workflow. Native Tauri dialogs/installer, waveform zoom,
line/event/grid forms, candidate audition, autosave and automatic reanalysis merging
remain later work. The /debug page remains available for focused playback diagnostics.

## Developing

`src/guess.mjs` holds the pure guessing logic and is unit tested; `src/app.js` is the
interface. Run `node --test desktop/tests/*.test.mjs`.
