# Purpose
Shared request preparation and durable editable song projects, independent of any interface.

## Ownership
- `requests.py`: exact source text, normalized alignment input, annotations and fingerprints.
- `projects.py`: legacy combined-analysis migration, immutable raw predictions, stable IDs, artifact manifests, SQLite revisions/transactions/proposals and derived diagnostics.
- Schemas belong in `../schemas`; tests belong in `../tests`.

## Local Contracts
- All interface adapters use this core. Never duplicate correction logic in a frontend or tool.
- SQLite `BEGIN IMMEDIATE` serializes cross-process writes. Revision numbers only increase; expected revisions and raw-analysis hashes must match.
- Transaction IDs are mandatory; identical retries return their original revision, differing payloads are rejected.
- Raw imported JSON is immutable. Preserve normalization provenance; user timings may overlap.
- Only original-origin, full-duration PCM playback files enter project-owned artifacts. Validate hashes before serving them.
- Undo/redo restore snapshots as new revisions. Proposals never change the selected result until accepted.
- Reject unknown future database/project versions. Runtime data is outside tracked source.

## Verification
- Test rollback, retry, stale edits, cross-process contention, restore, deterministic insert IDs, line edits and artifact integrity.
- Verify real-song migration and retain original evidence separately.
