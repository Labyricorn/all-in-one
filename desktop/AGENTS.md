# Purpose
Two-In-One Music and Lyric Analysis Studio browser workflow and playback synchronization for the future Tauri editor.

## Ownership
- `src/playback.mjs`: shared original-audio clock, mix/vocals, seek/rate/loop and audio-scheduled metronome.
- `src/guess.mjs`: pure planning of timing guesses for untimed words (close/successive, gap limit, optional beat snap) and the correction operations that save/approve them.
- `tests/`: deterministic clock, playback and guess-planning regressions.
- `debug.html`: browser playback diagnostic harness served by the local backend.
- `app.html`, `src/app.js`, `src/app.css`: Analyze/Jobs/Review/Export tabs,
  media submission, job progress/cancellation, waveform/playback,
  word/beat/section forms and revision-aware correction commits.

## Local Contracts
- Seconds always refer to decoded original audio; never trim a stem or restart time on track selection.
- Overlapping words highlight together. Playback rate currently changes pitch too.
- This is a playback module/developer harness, not the completed Tauri editor or Windows installer.
- All edits go through the shared authenticated API and project correction core.
- A guess is never alignment evidence. Guesses are saved as `set_word_interval` with `method: "guessed"` and approved through `set_tags`; the UI must keep guessed words visibly distinct until approved, never guess across gaps beyond the user's limit, and never overwrite a timed word.
- Guidance copy is for first-time users: plain language, sentence case, no jargon without a one-line explanation.
- Uploaded media stays under the runtime song-inputs directory, never source.
- Keep audio, projects and environments outside source.

## Verification
- `node --test desktop/tests/*.test.mjs`
- Drive the studio in a browser against a copy of a real project: lyric auto-follow, manual scroll pausing it, issue navigation, guess preview/apply/approve/undo, export summary and narrow layout.
- Exercise the service's `/debug` harness with aligned PCM artifacts; distinguish clock tests from measured speaker latency.
