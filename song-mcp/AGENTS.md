# Purpose
Unified command-line and stdio MCP interfaces exposing music structure and lyric timing for video planning.

## Ownership
- CLI, server, shared job workers, lyric adapter, analyzer/render subprocess adapters, combined song-map schema, tests, and isolated `.venv`.
- Shared core, project/correction schemas, project CLI, authenticated local API/live MCP, doctor and existing-runtime development packaging.
- Runtime job data lives under `MGMV_WORKSPACE_ROOT/song-jobs`, defaulting to repository `song-jobs`.
- CLI exports go to its chosen output folder. Existing MGMV review outputs remain in the parent workspace's `.videos/My_Own_Song`.

## Local Contracts
- Preserve the independent All-In-One environment; call its CLI as a subprocess.
- Resolve source scripts from this folder, independently of runtime root. Analyzer environment defaults to repository `.venv`; lyric environment defaults to this folder's `.venv`.
- Windows WMI workers do not inherit client environment overrides: pass runtime, analyzer and model-cache locations in the worker command before importing common.
- Generate client configuration from resolved local paths; never commit machine-specific configurations.
- Use seconds from the decoded original audio start for every timing field. Never trim vocal silence or concatenate chunks.
- Transcribed lyrics are unverified candidates. Singing alignment is estimated; retain missing words with null timestamps.
- Preserve ordered word estimates that overlap and flag them for review; reject backward start times rather than requiring artificially disjoint intervals.
- No fabricated source evidence, emotional labels, interpretations, or video rendering.
- Uncertainty handling is revisable at the user's direction. A production policy may infer/interpolate missing cues or extrapolate grids; retain raw candidates and record how each chosen result was obtained. Existing null-timing behavior describes the current implementation, not an immutable future requirement.
- Server stdout is reserved for MCP. CLI stdout reports progress and exported paths. Jobs and model downloads run in a separate worker with log files.
- Keep exact supplied lyric text distinct from alignment text. Speaker prefixes such as `[AI Voice:]` are annotations; following vocal content and parenthetical lyric lines remain content. Punctuation-only tokens are not acoustic words.
- Completed CLI cache reuse requires matching source/text/settings fingerprints. Reuse legacy structure only after source-path/age/duration checks and record its missing old model/hash provenance.
- Use maintained faster-whisper and WhisperX in the separate lyric environment.
- `offline=true` jobs must use cached models/tokenizers only; propagate offline settings into detached workers and their analyzer subprocesses.

## Work Guidance
- Keep submission and status tools fast; persist each job and run one CPU job at a time.
- Validate local input files and media streams before spawning a job.
- Return partial music structure when lyrics fail, with explicit error details.

## Verification
- Run `tests/test_contracts.py` and the stdio MCP integration fixture test.
- Verify real model transcription/alignment on clearly labeled synthetic fixtures.
- Recheck both environments with `pip check` after dependency changes.
- Speech-fixture SRT references contain subtitle segment times, not word boundaries. Report edit distance and segment discrepancies separately from singing/beat accuracy.
- Generate portable CLI test fixtures in temporary folders; optional evaluation media remains external to the repository.
- Exercise actual `analyze-song.cmd` calls with spaced paths, lyric modes, invalid arguments, output folders and cached offline operation. Record real-song timing coverage without claiming word-level accuracy from untimed text.

## Child DOX Index
- `core/AGENTS.md`: normalized requests, transactional revisions/corrections, artifacts and migration contracts.
