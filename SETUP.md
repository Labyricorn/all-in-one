# Full song analysis with lyrics

Run these commands from the fork checkout after installing the two environments
below. The complete CLI runs locally and does not need an MCP connection.

```powershell
.\analyze-song.cmd 'C:\Music\song.mp3' --language en -o '.\song-results' -v -s
.\analyze-song.cmd 'C:\Music\song.mp3' --lyrics-file 'C:\Music\lyrics.txt' --language en -o '.\song-results' -v -s
```

The first command transcribes automatically. The second aligns your UTF-8 lyric
text. Both preserve the original audio and return estimated times in seconds from
its decoded start. Singing alignment may be incomplete: retain null times and
review the audio. Speaker labels such as `[AI Voice:]` are stored as annotations;
their spoken content and parenthetical vocals remain alignment content.

## Review and correct a project

Run the song service launcher; it opens and connects Two-In-One Music and Lyric
Analysis Studio automatically.
The initial Analyze tab selects new audio/video and starts full analysis with
automatic transcription or supplied lyrics. Jobs follows progress and opens
results in Review with waveform/playback and word, beat and section corrections.
Export downloads corrected JSON. Review also opens saved projects and imports
existing combined analysis JSON. See [the studio guide](desktop/README.md).
Terminal CLI workflows remain independent; connected MCP clients use the live
service, and stdio MCP remains available on its own.

## Outputs and options

All exported files go under `-o`: combined `.analysis.json`, `.song-map.json`,
`.lyrics.json`, `.lyrics.txt`, `.lyric-words.csv`, `.report.md`, and cache manifest
`.run.json`. Supplied text also produces `.reference.lyrics.txt` and
`.alignment.txt`. `-v` writes a PDF under `viz/`; `-s` writes a timing-cue WAV under
`sonif/`. No video or SRT is generated. Internal jobs, decoded audio, stems and
logs live separately in `song-jobs/`.

| Option | Meaning / default |
|---|---|
| Input | One local audio/video path; quote spaces. Video uses the first audio stream. |
| `-o`, `--out-dir` | Export folder, default `./song-results`. |
| `--lyrics` | `auto` default; `align` selected when text is supplied; `none` skips lyrics; `instrumental` records your declaration. |
| `--lyrics-file`, `--lyrics-text` | Mutually exclusive supplied untimed text; alignment requires `--language`. |
| `--language` | Language code such as `en`; auto detection for transcription if omitted. |
| `--lyric-model` | `base` default; `tiny`, `small`, `medium` also supported. |
| `-m`, `--model` | Music `harmonix-all` ensemble default, or faster `harmonix-fold0`. |
| `--offline` | Cached models/tokenizers only; missing resources produce an explicit failure. |
| `-v`, `--visualize` | Save a timeline PDF. |
| `-s`, `--sonify` | Save an audible beat/section preview. |
| `--structure-json` | Reuse a checked legacy structure JSON with matching source path, age and duration; old missing hash/model provenance stays explicit. |
| `--overwrite` | Ignore completed/legacy analysis caches and compute again. |
| `-h`, `--help` | Print actual CLI help without analyzing a song. |

Matching source/text/settings hashes allow completed-cache reuse. Matching decoded
WAV/source hashes allow stem reuse when lyrics change. One CPU job runs at a time
across CLI and MCP. Ctrl+C cancels the foreground job. Exit codes: 0 complete
(uncertain timing is still possible), 1 failure, 2 usage error, 3 partial result
after lyric/preview failure, 130 cancelled.

`analyze-music.cmd` is the **structure-only** CLI. It forwards upstream `allin1`
options and does not transcribe or align lyrics. See the upstream reference in
[README.md](README.md) for its switches and Python API.

## Editable projects, live backend and playback

The existing-runtime backend milestone adds `song-project.cmd`, `song-service.cmd`,
versioned corrections, shared stdio/HTTP MCP projects, a playback module/debugger,
doctor and reproducible development packaging. See [song-mcp/BACKEND.md](song-mcp/BACKEND.md)
for commands, schemas, API routes and verification. Tauri editor/installer work
remains a subsequent milestone.

## Windows CPU installation

The verified environment uses Python 3.10, FFmpeg on PATH, and a Visual Studio
x64 developer command prompt for the native build. Install `uv` and the Visual
Studio C++ build tools first. Run installation commands from this repository.
The original analyzer needs PyTorch 2.1.2; the companion lyric environment needs
PyTorch 2.8.0. Keep them separate. CUDA is not configured by these instructions.

```powershell
uv python install 3.10
uv venv --python 3.10 .venv
uv pip install --python .venv\Scripts\python.exe --index-url https://download.pytorch.org/whl/cpu torch==2.1.2+cpu torchaudio==2.1.2+cpu
uv pip install --python .venv\Scripts\python.exe numpy==1.23.5 Cython==0.29.37 setuptools==69.5.1 wheel ninja pip
git clone --branch v0.14.6 https://github.com/SHI-Labs/NATTEN .deps/NATTEN
git -C .deps/NATTEN apply ../../patches/natten-0.14.6-windows.patch
$env:DISTUTILS_USE_SDK = '1'
$env:MAX_JOBS = '4'
uv pip install --python .venv\Scripts\python.exe --no-build-isolation .deps/NATTEN
uv pip install --python .venv\Scripts\python.exe --no-build-isolation 'madmom @ git+https://github.com/CPJKU/madmom@27f032e8947204902c675e5e341a3faf5dc86dae'
uv pip install --python .venv\Scripts\python.exe -e . -c constraints-windows.txt --extra-index-url https://download.pytorch.org/whl/cpu
uv venv --python 3.10 song-mcp/.venv
uv pip install --python song-mcp/.venv/Scripts/python.exe -r song-mcp/requirements.txt
```

The NATTEN patch targets commit `3b54c76185904f3cb59a49fff7bc044e4513d106`
(v0.14.6). It adjusts MSVC compiler flags and two statement macros, preserving
attention mathematics. NATTEN remains an independent dependency, with its license
included beside the patch. The lyric `requirements.lock.txt` is the full known
Windows CPU environment snapshot; use the PyTorch CPU extra index if installing it.
First lyric use downloads public model weights/tokenizers into
`song-mcp/model-cache`; media and lyrics are processed locally. `--offline` becomes
useful after the required models have been cached.

The source adapters also select `.venv/bin/` executables on POSIX, where you can
invoke `song-mcp/.venv/bin/python song-mcp/cli.py ...` and `server.py` directly.
The installation and native build described here were verified on Windows.

## Connected MCP chat actions

Generate a configuration using the lyric interpreter, then copy the server entry
into your client's configuration. These terminal commands print configuration;
they do not start a song job or edit client settings:

```powershell
.\song-mcp\.venv\Scripts\python.exe .\song-mcp\configure_client.py --format json
.\song-mcp\.venv\Scripts\python.exe .\song-mcp\configure_client.py --format toml
```

JSON uses `mcpServers`; TOML uses `mcp_servers` for a project Codex configuration.
The generated configuration resolves your checkout and interpreter paths. No
machine-specific settings are committed. `song-mcp.cmd` starts a stdio server and
waits for a client; it is not a song-analysis command and takes no song arguments.

After connecting, the model calls `server_info`, `submit_song`, `get_job`,
`list_jobs`, `get_analysis`, and `get_song_map`. Submit an absolute local file path,
choose `lyrics_mode` (`auto`, `align`, `none`, `instrumental`), optionally provide
`lyrics_text`, and poll until complete or partial. `align` requires language and
text. `offline=true` requires cached resources. Retrieve paged words/phrases or the
compact planning map. Windows workers run independently of the client so jobs
survive reconnects; status, errors and logs persist on disk.

## Existing MGMV workspace and runtime locations

This checkout is the canonical source. The parent MGMV workspace keeps its existing
lyric `.venv`, model cache, job history and user outputs. Its original CLI/MCP
entry paths are compatibility wrappers into this checkout, so registered clients
and existing commands continue working. No environment or user media was moved.

For other installations, defaults are entirely within the checkout. Optional
environment variables let installations separate source and runtime data:

| Variable | Default |
|---|---|
| `MGMV_WORKSPACE_ROOT` | Repository root; owns `song-jobs`. |
| `MGMV_ANALYZER_ROOT` | Repository root; owns the analyzer `.venv`. |
| `MGMV_MODEL_CACHE` | `song-mcp/model-cache`. |
| `MGMV_SONG_PYTHON` | Windows launchers use `song-mcp/.venv/Scripts/python.exe`. |

## Verification

```powershell
.\.venv\Scripts\python.exe -c "import allin1, natten.functional"
.\analyze-music.cmd --help
.\analyze-song.cmd --help
uv pip check --python .venv/Scripts/python.exe
uv pip check --python song-mcp/.venv/Scripts/python.exe
.\song-mcp\.venv\Scripts\python.exe -m pytest song-mcp/tests -q
```

CLI tests generate temporary synthetic audio and checked structure JSON; no user
song or model download is required. They require the analyzer environment. MCP
tests exercise real stdio handshakes, tool listing and validation errors. Optional
evaluation scripts accept separately supplied research/speech media in runtime
folders; those inputs are not distributed. Subtitle segments and untimed lyrics
do not establish word-boundary accuracy. See `devlog.md` for recorded validation.
