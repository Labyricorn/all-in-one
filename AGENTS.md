# Purpose
Maintained local source for Two-In-One Music and Lyric Analysis Studio at https://github.com/Labyricorn/two-in-one, derived from mir-aidj/all-in-one.

## Ownership
- Analyzer source, isolated `.venv`, and Windows dependency constraints.
- Canonical unified CLI/MCP source in `song-mcp/`, repository launchers, installation guide, attribution and Windows NATTEN patch.

## Local Contracts
- Preserve upstream behavior; document compatibility patches in the workspace devlog.
- Use Python 3.10 and `constraints-windows.txt` for the native Windows installation.
- Installed NATTEN and PyTorch support CPU inference; CUDA is not enabled.
- Decode visualization/sonification audio with `demucs.audio.AudioFile.read` for Demucs 4.1 compatibility.
- Retain upstream history, original MIT license/copyright and research citation. New companion project code uses MIT; dependencies/models retain their own licenses.
- Keep analyzer and lyric environments separate. Do not track environments, models, user media or generated analysis.
- This checkout owns the maintained source; parent workspace entry points are compatibility wrappers. Do not duplicate implementations there.
- Do not push commits without an explicit user instruction overriding the workspace no-push contract.

## Work Guidance
- Workspace launchers should select this environment explicitly.
- Lead repository setup with full song analysis; distinguish the structure-only CLI and connected MCP tool calls.
- Read repository and workspace devlogs before changes. Runtime path overrides must survive Windows WMI detached launches.

## Verification
- `.venv/Scripts/python.exe -m pip check`
- `.venv/Scripts/allin1.exe --help`
- Run sample audio through Demucs, spectrogram extraction, inference, and JSON output.
- Upstream tests require absent `tests/test.mp3` and `tests/test.json` fixtures; use a separate local sample.
- Run companion tests with the lyric interpreter and verify both repository and workspace launchers.

## Child DOX Index
- `song-mcp/AGENTS.md`: canonical unified CLI, server, lyric backends, jobs, adapters and tests.
- `desktop/AGENTS.md`: shared playback module, developer harness and synchronization tests.
