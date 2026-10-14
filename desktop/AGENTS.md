# Purpose
Browser Song Studio workflow and playback synchronization for the future Tauri editor.

## Ownership
- `src/playback.mjs`: shared original-audio clock, mix/vocals, seek/rate/loop and audio-scheduled metronome.
- `tests/`: deterministic clock and playback regressions.
- `debug.html`: browser playback diagnostic harness served by the local backend.
- `app.html`, `src/app.js`, `src/app.css`: Analyze/Jobs/Review/Export tabs,
  media submission, job progress/cancellation, waveform/playback,
  word/beat/section forms and revision-aware correction commits.

## Local Contracts
- Seconds always refer to decoded original audio; never trim a stem or restart time on track selection.
- Overlapping words highlight together. Playback rate currently changes pitch too.
- This is a playback module/developer harness, not the completed Tauri editor or Windows installer.
- All edits go through the shared authenticated API and project correction core.
- Uploaded media stays under the runtime song-inputs directory, never source.
- Keep audio, projects and environments outside source.

## Verification
- `node --test desktop/tests/*.test.mjs`
- Exercise the service's `/debug` harness with aligned PCM artifacts; distinguish clock tests from measured speaker latency.
