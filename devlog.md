# Development log

## 2026-10-13 — Authorized Song Studio publication

- User explicitly requested commit and push of the current implementation to
  Labyricorn/all-in-one. Included the shared project/API/MCP backend required by
  the studio, Analyze/Jobs/Review/Export UI, playback, source packaging, tests,
  canonical launchers and documentation.
- Origin main matched the local base before publication. Full companion suite
  passes: 41 Python tests and four playback tests, plus frontend syntax checking.
  Runtime projects, uploaded media, models, caches, discovery credentials and
  parent-workspace verification artifacts remain excluded from Git.

## 2026-10-13 — Song Studio process tabs and new analysis

- Replaced the review-only page with Analyze, Jobs, Review and Export tabs.
  Analyze selects/ previews audio/video, loads optional lyric text, chooses
  language/models/offline mode and submits the existing detached worker.
- Added authenticated streamed media import into runtime song-inputs, audio-stream
  validation and rejection/interruption cleanup. Jobs displays actual stages,
  cancellation, diagnostics and direct result opening with cached PCM tracks.
- Added decoded mix waveform, section bands, downbeat ticks, seek-on-word/ waveform,
  loops and corrected JSON downloads. Fixed phrase filtering via stable phrase
  membership and form rounding without changing untouched timestamp precision.
- Source packaging now includes frontend JS/CSS. Sixteen backend/project/package
  tests and four playback tests pass; syntax and whitespace checks pass.
- Verified a real offline single-model analysis on an 8-second generated rhythm
  fixture in verification/studio-smoke, opened its result in the browser, saved
  a section revision and downloaded the corrected JSON. My Own Song filtering/
  word selection verified without edits. Screenshots under verification/studio-ui.
  Automated Chrome file selection was blocked by extension file-URL permission;
  upload and real submission were verified through the local API.

## 2026-10-13 — File picker and usable project startup

- Added a browser JSON picker and parsed-data import through the shared project
  store; retained local paths as an optional fallback. JSON-only projects can be
  edited without failing audio initialization.
- Moved the automatic service token behind Advanced connection, kept it in tab
  session storage for refresh, added an empty-project message and song names.
- Imported the existing cached My Own Song job into the default store with its
  two original-origin audio tracks. Fourteen project/HTTP tests plus JavaScript
  syntax and whitespace checks pass.

## 2026-10-13 — Direct review UI launch

- Launcher opens the browser after API startup and reconnects to an existing
  compatible service. Console prints a direct UI link. Added --no-browser.
- Browser consumes the connection token from the URL fragment, clears it from
  the address bar and loads the project list automatically.
- Verified real browser startup: page/assets and authenticated project list return
  200. Three HTTP/MCP tests pass outside sandbox restrictions; sandbox runs timed
  out before startup. JavaScript syntax and diff whitespace checks pass.

## 2026-10-13 — Browser project review UI

- Added a local browser editor at the service's `/app` route for importing/listing
  projects, playing project mix/vocals, selecting words, editing word text/timing,
  beat times and section labels/bounds, and reading review flags. Saves use shared
  core correction transactions with revision/hash preconditions.
- Kept `/debug` as a focused playback harness. Documented UI startup and scope in
  the workspace/fork guides. This is not the planned Tauri shell; waveform,
  undo/redo controls, line/event forms and analysis-job UI remain future work.

## 2026-10-13 — Shared projects, local API/MCP and playback

- Implemented the user-requested existing-runtime backend milestone: shared request
  normalization; versioned SQLite projects/raw predictions/corrections/proposals;
  stable IDs, atomic revisions, retry handling, restore and artifact validation.
- Added project CLI, loopback API and live Streamable HTTP MCP alongside stdio,
  durable revision events/job polling, cancellation and startup discovery leases.
  Parent workspace launchers select its existing runtime paths and environments.
- Added desktop playback module/debugger and clock/loop/metronome regressions,
  doctor, development source packaging and song-mcp/BACKEND.md. Tauri editor,
  installer and automatic reanalysis rebasing remain subsequent milestones.
- Migrated a verification copy of the real song and cached mix/vocals, caught the
  legacy rounded section overrun with preserved provenance, and exercised browser
  half-speed vocals/loop playback. User media and published exports remain intact.
- Verification: 39 Python tests and four Node tests pass; actual HTTP/stdio MCP,
  cross-process revisions, cancellation and CLI export parity are covered. Both
  environments' imports/dependency consistency and launcher help pass. No installed
  packages changed; no commit or push performed. Workspace devlog records artifacts.

## 2026-10-13 — Incorporate Labyricorn's song-analysis additions

- User requested a maintained fork that also includes the existing CLI and lyric/MCP
  additions. Migrated canonical source, dependency manifests and tests from the
  parent MGMV workspace into `song-mcp/`. Existing installed environments, cached
  weights, job history and user media/exports remain in the workspace.
- Added repository launchers, a portable installation/usage guide, a client-config
  generator and attribution. Kept the original analyzer package/API and upstream
  license/citation. Added a NATTEN v0.14.6 Windows patch and its original MIT notice;
  kept that dependency checkout independent. Updated project URLs to the fork.
- Separated source paths from runtime/analyzer/cache paths. Existing workspace
  entry scripts now dispatch into canonical source. Passing explicit locations to
  workers preserves configuration across Windows WMI launches, which do not
  inherit the server's environment. A legacy worker entry path also preserves
  already-running clients during migration.
- Kept the two incompatible PyTorch environments isolated. No package versions
  changed and no environments were relocated. Models/jobs/output/media are ignored
  by Git. The companion is checkout-based; the original `allin1` wheel continues
  to contain only its analyzer package.
- Replaced machine-specific MCP config tests with generated JSON/TOML configurations
  and made CLI fixtures temporary and synthetic. A stale usage-error test initially
  depended on a workspace WAV; it now creates valid local audio before checking the
  missing-language error. The original upstream tests still require missing fixtures.
- Validation: 25 companion tests passed, including actual MCP stdio handshakes,
  Windows launchers, synthetic CLI modes and detached-runtime location propagation.
  The sandbox prevented initial MCP process/temp-folder tests; running that suite
  outside those process restrictions passed. Focused tests also pass in the sandbox
  with an explicit workspace temporary folder.
- Analyzer imports and workspace CLI help pass. NATTEN reverse-apply check passes
  against the installed patched checkout; upstream LICENSE is unchanged. Additional
  real-song cache/render checks and source review are recorded in the workspace log.
- DOX indexes now delegate implementation to this repository's song-mcp child;
  parent workspace runtime ownership is explicit. No remote publication performed.
- Existing workspace CLI reused the real-song cache and successfully regenerated
  timeline PDF/timing-cue WAV into a separate verification folder. Project exports
  remain untouched. Metadata parsing and Git whitespace review pass.
- Both legacy workspace MCP entry points pass actual handshake/validation checks.
  Cached real-song JSON matches the previously published result and the original
  source SHA-256 remains unchanged.

## 2026-10-13 — Publish maintained-fork additions

- User explicitly authorized committing and pushing these integrated changes to
  Labyricorn/all-in-one. Preserved the original remote as `upstream` and configured
  the user's fork as `origin`. Fetched fork main and confirmed it matches the
  original local base, allowing a normal fast-forward push without rewriting history.
- Commit includes source, launchers, tests, dependency manifests, installation
  documentation, attribution and compatibility patches. Existing 25-test and
  real-song/MCP verification remains applicable; no implementation changed since
  those checks. Environments, models, media and generated results remain excluded.
