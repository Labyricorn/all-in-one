# Development log

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
