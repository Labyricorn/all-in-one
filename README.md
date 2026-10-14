# All-In-One Music Structure Analyzer — maintained Labyricorn fork

This fork continues [Taejun Kim's original All-In-One analyzer](https://github.com/mir-aidj/all-in-one)
and adds **Song Studio**, a local browser application for analyzing audio,
following jobs, reviewing playback and correcting song timelines. The full CLI
and MCP interfaces share the same analysis and project backend: automatic lyrics,
supplied-text alignment, estimated word/phrase timing, combined song maps,
persistent jobs, versioned corrections and offline cached-model operation.
Windows Demucs compatibility fixes and a NATTEN build patch are included.

**Start with [SETUP.md](SETUP.md)** to install the two isolated Python environments
and run the full song/lyrics workflow. Once installed, double-click
`song-service.cmd` to open Song Studio, or use the terminal commands below.

## Full song analysis with lyrics

From PowerShell in the fork checkout:

```powershell
.\analyze-song.cmd 'C:\Music\song.mp3' --language en -o '.\song-results'
.\analyze-song.cmd 'C:\Music\song.mp3' --lyrics-file 'C:\Music\lyrics.txt' --language en -o '.\song-results'
```

The first command transcribes automatically; the second aligns your supplied
UTF-8 lyric text. Results include combined analysis/song-map JSON, lyric files,
word CSV and a report. Add `--offline` to use cached models only, `-v` for a
timeline PDF or `-s` for a timing-cue WAV. These terminal commands work with the
browser and service closed. `analyze-music.cmd` is the **structure-only** CLI.

## Song Studio

Start the local application from PowerShell, or double-click its launcher:

```powershell
.\song-service.cmd
```

The launcher opens your browser, connects it automatically and prints a direct
UI link. An existing compatible service is reused. Keep the service console
running while using the application; use `--no-browser` for console-only startup.

| Tab | Workflow |
| --- | --- |
| **Analyze** | Choose audio/video with a file picker, preview it, select automatic transcription or supplied lyrics, choose language/models and start analysis. |
| **Jobs** | Follow actual processing stages, cancel active jobs, inspect errors and open completed or partial results in Review. |
| **Review** | Open saved projects or import analysis JSON. Inspect waveform, sections and downbeats; play mix/vocals, seek, loop, slow playback and audition a metronome. Save word text/timing, beat-time and section corrections. |
| **Export** | Download the selected project's latest corrected analysis JSON. |

Saves create durable project revisions and reject stale concurrent edits.
Completed jobs reuse cached audio when opened for review. Accepted analysis jobs
continue after browser or service disconnects. Media, uploaded copies, projects,
models and caches stay in local runtime directories outside source control.

Singing timings are estimates and may need review. The current browser application
loads audio into memory; slower playback changes pitch. Native Tauri packaging,
waveform zoom, line/event/grid editing and undo/redo controls are future work.
See the [Song Studio guide](desktop/README.md) for controls and storage details.

## Headless projects and connected MCP

For terminal project import, revision history, corrections and export:

```powershell
.\song-project.cmd --help
.\song-project.cmd list
```

Connected MCP chat actions use the same durable jobs and projects. The existing
stdio MCP server works independently; the running local service also provides
authenticated Streamable HTTP MCP for project reads, correction proposals,
explicit applications and exports. See [backend and MCP setup](song-mcp/BACKEND.md)
for connection configuration and the versioned API.

## Source and upstream guide

The maintained application sources live in `desktop/` and `song-mcp/`, with
repository launchers selecting the installed environments. The companion is run
from this checkout and is not bundled into the `allin1` wheel. The upstream Python
API and package name remain `allin1`. See [ATTRIBUTION.md](ATTRIBUTION.md) for provenance.

The original MIT copyright/license and research citation below are retained.
The following upstream guide describes the underlying structure analyzer.


[![Visual Demo](https://img.shields.io/badge/Visual-Demo-8A2BE2)](https://taejun.kim/music-dissector/)
[![arXiv](https://img.shields.io/badge/arXiv-2307.16425-B31B1B)](http://arxiv.org/abs/2307.16425/)
[![Hugging Face Space](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-f9f107)](https://huggingface.co/spaces/taejunkim/all-in-one/)
[![PyPI - Version](https://img.shields.io/pypi/v/allin1.svg)](https://pypi.org/project/allin1)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/allin1.svg)](https://pypi.org/project/allin1)

This package provides models for music structure analysis, predicting:
1. Tempo (BPM)
2. Beats
3. Downbeats
4. Functional segment boundaries
5. Functional segment labels (e.g., intro, verse, chorus, bridge, outro)


-----


**Table of Contents**

- [Installation](#installation)
- [Usage for CLI](#usage-for-cli)
- [Usage for Python](#usage-for-python)
- [Visualization & Sonification](#visualization--sonification)
- [Available Models](#available-models)
- [Speed](#speed)
- [Advanced Usage for Research](#advanced-usage-for-research)
- [Concerning MP3 Files](#concerning-mp3-files)
- [Training](TRAINING.md)
- [Citation](#citation)

## Installation

### 1. Install PyTorch

Visit [PyTorch](https://pytorch.org/) and install the appropriate version for your system.

### 2. Install NATTEN (Required for Linux and Windows; macOS will auto-install)
* **Linux**: Download from [NATTEN website](https://www.shi-labs.com/natten/)
* **macOS**: Auto-installs with `allin1`.
* **Windows**: Build from source:
```shell
pip install ninja # Recommended, not required
git clone https://github.com/SHI-Labs/NATTEN
cd NATTEN
make
```

### 3. Install the package

```shell
pip install git+https://github.com/CPJKU/madmom  # install the latest madmom directly from GitHub
pip install allin1  # install this package
```

### 4. (Optional) Install FFmpeg for MP3 support

For ubuntu:

```shell
sudo apt install ffmpeg
```

For macOS:

```shell
brew install ffmpeg
```


## Usage for CLI

To analyze audio files:
```shell
allin1 your_audio_file1.wav your_audio_file2.mp3
```
Results will be saved in the `./struct` directory by default:
```shell
./struct
└── your_audio_file1.json
└── your_audio_file2.json
```
The analysis results will be saved in JSON format:
```json
{
  "path": "/path/to/your_audio_file.wav",
  "bpm": 100,
  "beats": [ 0.33, 0.75, 1.14, ... ],
  "downbeats": [ 0.33, 1.94, 3.53, ... ],
  "beat_positions": [ 1, 2, 3, 4, 1, 2, 3, 4, 1, ... ],
  "segments": [
    {
      "start": 0.0,
      "end": 0.33,
      "label": "start"
    },
    {
      "start": 0.33,
      "end": 13.13,
      "label": "intro"
    },
    {
      "start": 13.13,
      "end": 37.53,
      "label": "chorus"
    },
    {
      "start": 37.53,
      "end": 51.53,
      "label": "verse"
    },
    ...
  ]
}
```
All available options are as follows:
```shell
$ allin1 -h

usage: allin1 [-h] [-o OUT_DIR] [-v] [--viz-dir VIZ_DIR] [-s] [--sonif-dir SONIF_DIR] [-a] [-e] [-m MODEL] [-d DEVICE] [-k]
              [--demix-dir DEMIX_DIR] [--spec-dir SPEC_DIR]
              paths [paths ...]

positional arguments:
  paths                 Path to tracks

options:
  -h, --help            show this help message and exit
  -o OUT_DIR, --out-dir OUT_DIR
                        Path to a directory to store analysis results (default: ./struct)
  -v, --visualize       Save visualizations (default: False)
  --viz-dir VIZ_DIR     Directory to save visualizations if -v is provided (default: ./viz)
  -s, --sonify          Save sonifications (default: False)
  --sonif-dir SONIF_DIR
                        Directory to save sonifications if -s is provided (default: ./sonif)
  -a, --activ           Save frame-level raw activations from sigmoid and softmax (default: False)
  -e, --embed           Save frame-level embeddings (default: False)
  -m MODEL, --model MODEL
                        Name of the pretrained model to use (default: harmonix-all)
  -d DEVICE, --device DEVICE
                        Device to use (default: cuda if available else cpu)
  -k, --keep-byproducts
                        Keep demixed audio files and spectrograms (default: False)
  --demix-dir DEMIX_DIR
                        Path to a directory to store demixed tracks (default: ./demix)
  --spec-dir SPEC_DIR   Path to a directory to store spectrograms (default: ./spec)
```

## Usage for Python

Available functions:
- [`analyze()`](#analyze)
- [`load_result()`](#load_result)
- [`visualize()`](#visualize)
- [`sonify()`](#sonify)

### `analyze()`
Analyzes the provided audio files and returns the analysis results.

```python
import allin1

# You can analyze a single file:
result = allin1.analyze('your_audio_file.wav')

# Or multiple files:
results = allin1.analyze(['your_audio_file1.wav', 'your_audio_file2.mp3'])
```
A result is a dataclass instance containing:
```python
AnalysisResult(
  path='/path/to/your_audio_file.wav', 
  bpm=100,
  beats=[0.33, 0.75, 1.14, ...],
  beat_positions=[1, 2, 3, 4, 1, 2, 3, 4, 1, ...],
  downbeats=[0.33, 1.94, 3.53, ...], 
  segments=[
    Segment(start=0.0, end=0.33, label='start'), 
    Segment(start=0.33, end=13.13, label='intro'), 
    Segment(start=13.13, end=37.53, label='chorus'), 
    Segment(start=37.53, end=51.53, label='verse'), 
    Segment(start=51.53, end=64.34, label='verse'), 
    Segment(start=64.34, end=89.93, label='chorus'), 
    Segment(start=89.93, end=105.93, label='bridge'), 
    Segment(start=105.93, end=134.74, label='chorus'), 
    Segment(start=134.74, end=153.95, label='chorus'), 
    Segment(start=153.95, end=154.67, label='end'),
  ]),
```
Unlike CLI, it does not save the results to disk by default. You can save them as follows:
```python
result = allin1.analyze(
  'your_audio_file.wav',
  out_dir='./struct',
)
```

#### Parameters:

- `paths` : `Union[PathLike, List[PathLike]]`  
List of paths or a single path to the audio files to be analyzed.
  
- `out_dir` : `PathLike` (optional)  
Path to the directory where the analysis results will be saved. By default, the results will not be saved.
  
- `visualize` : `Union[bool, PathLike]` (optional)  
Whether to visualize the analysis results or not. If a path is provided, the visualizations will be saved in that directory. Default is False. If True, the visualizations will be saved in './viz'.
  
- `sonify` : `Union[bool, PathLike]` (optional)  
Whether to sonify the analysis results or not. If a path is provided, the sonifications will be saved in that directory. Default is False. If True, the sonifications will be saved in './sonif'.
  
- `model` : `str` (optional)  
Name of the pre-trained model to be used for the analysis. Default is 'harmonix-all'. Please refer to the documentation for the available models.
  
- `device` : `str` (optional)  
Device to be used for computation. Default is 'cuda' if available, otherwise 'cpu'.
  
- `include_activations` : `bool` (optional)  
Whether to include activations in the analysis results or not.
  
- `include_embeddings` : `bool` (optional)  
Whether to include embeddings in the analysis results or not.
  
- `demix_dir` : `PathLike` (optional)  
Path to the directory where the source-separated audio will be saved. Default is './demix'.
  
- `spec_dir` : `PathLike` (optional)  
Path to the directory where the spectrograms will be saved. Default is './spec'.
  
- `keep_byproducts` : `bool` (optional)  
Whether to keep the source-separated audio and spectrograms or not. Default is False.
  
- `multiprocess` : `bool` (optional)  
Whether to use multiprocessing for extracting spectrograms. Default is True.

#### Returns:

- `Union[AnalysisResult, List[AnalysisResult]]`  
Analysis results for the provided audio files.


### `load_result()`

Loads the analysis results from the disk.

```python
result = allin1.load_result('./struct/24k_Magic.json')
```


### `visualize()`

Visualizes the analysis results.

```python
fig = allin1.visualize(result)
fig.show()
```

#### Parameters:

- `result` : `Union[AnalysisResult, List[AnalysisResult]]`  
List of analysis results or a single analysis result to be visualized.

- `out_dir` : `PathLike` (optional)  
Path to the directory where the visualizations will be saved. By default, the visualizations will not be saved.

#### Returns:

- `Union[Figure, List[Figure]]`
List of figures or a single figure containing the visualizations. `Figure` is a class from `matplotlib.pyplot`.


### `sonify()`

Sonifies the analysis results.
It will mix metronome clicks for beats and downbeats, and event sounds for segment boundaries
to the original audio file.

```python
y, sr = allin1.sonify(result)
# y: sonified audio with shape (channels=2, samples)
# sr: sampling rate (=44100)
```

#### Parameters:

- `result` : `Union[AnalysisResult, List[AnalysisResult]]`  
List of analysis results or a single analysis result to be sonified.
- `out_dir` : `PathLike` (optional)  
Path to the directory where the sonifications will be saved. By default, the sonifications will not be saved.

#### Returns:

- `Union[Tuple[NDArray, float], List[Tuple[NDArray, float]]]`  
List of tuples or a single tuple containing the sonified audio and the sampling rate.


## Visualization & Sonification
This package provides a simple visualization (`-v` or `--visualize`) and sonification (`-s` or `--sonify`) function for the analysis results.
```shell
allin1 -v -s your_audio_file.wav
```
The visualizations will be saved in the `./viz` directory by default:
```shell
./viz
└── your_audio_file.pdf
```
The sonifications will be saved in the `./sonif` directory by default:
```shell
./sonif
└── your_audio_file.sonif.wav
```
For example, a visualization looks like this:
![Visualization](./assets/viz.png)

You can try it at [Hugging Face Space](https://huggingface.co/spaces/taejunkim/all-in-one).


## Available Models
The models are trained on the [Harmonix Set](https://github.com/urinieto/harmonixset) with 8-fold cross-validation.
For more details, please refer to the [paper](http://arxiv.org/abs/2307.16425).
* `harmonix-all`: (Default) An ensemble model averaging the predictions of 8 models trained on each fold.
* `harmonix-foldN`: A model trained on fold N (0~7). For example, `harmonix-fold0` is trained on fold 0.

By default, the `harmonix-all` model is used. To use a different model, use the `--model` option:
```shell
allin1 --model harmonix-fold0 your_audio_file.wav
```


## Speed
With an RTX 4090 GPU and Intel i9-10940X CPU (14 cores, 28 threads, 3.30 GHz),
the `harmonix-all` model processed 10 songs (33 minutes) in 73 seconds.


## Advanced Usage for Research
This package provides researchers with advanced options to extract **frame-level raw activations and embeddings** 
without post-processing. These have a resolution of 100 FPS, equivalent to 0.01 seconds per frame.

### CLI

#### Activations
The `--activ` option also saves frame-level raw activations from sigmoid and softmax:
```shell
$ allin1 --activ your_audio_file.wav
```
You can find the activations in the `.npz` file:
```shell
./struct
└── your_audio_file1.json
└── your_audio_file1.activ.npz
```
To load the activations in Python:
```python
>>> import numpy as np
>>> activ = np.load('./struct/your_audio_file1.activ.npz')
>>> activ.files
['beat', 'downbeat', 'segment', 'label']
>>> beat_activations = activ['beat']
>>> downbeat_activations = activ['downbeat']
>>> segment_boundary_activations = activ['segment']
>>> segment_label_activations = activ['label']
```
Details of the activations are as follows:
* `beat`: Raw activations from the **sigmoid** layer for **beat tracking** (shape: `[time_steps]`)
* `downbeat`: Raw activations from the **sigmoid** layer for **downbeat tracking** (shape: `[time_steps]`)
* `segment`: Raw activations from the **sigmoid** layer for **segment boundary detection** (shape: `[time_steps]`)
* `label`: Raw activations from the **softmax** layer for **segment labeling** (shape: `[label_class=10, time_steps]`)

You can access the label names as follows:
```python
>>> allin1.HARMONIX_LABELS
['start',
 'end',
 'intro',
 'outro',
 'break',
 'bridge',
 'inst',
 'solo',
 'verse',
 'chorus']
```


#### Embeddings
This package also provides an option to extract raw embeddings from the model.
```shell
$ allin1 --embed your_audio_file.wav
```
You can find the embeddings in the `.npy` file:
```shell
./struct
└── your_audio_file1.json
└── your_audio_file1.embed.npy
```
To load the embeddings in Python:
```python
>>> import numpy as np
>>> embed = np.load('your_audio_file1.embed.npy')
```
Each model embeds for every source-separated stem per time step, 
resulting in embeddings shaped as `[stems=4, time_steps, embedding_size=24]`:
1. The number of source-separated stems (the order is bass, drums, other, vocals).
2. The number of time steps (frames). The time step is 0.01 seconds (100 FPS).
3. The embedding size of 24.

Using the `--embed` option with the `harmonix-all` ensemble model will stack the embeddings, 
saving them with the shape `[stems=4, time_steps, embedding_size=24, models=8]`.

### Python
The Python API `allin1.analyze()` offers the same options as the CLI:
```python
>>> allin1.analyze(
      paths='your_audio_file.wav',
      include_activations=True,
      include_embeddings=True,
    )

AnalysisResult(
  path='/path/to/your_audio_file.wav', 
  bpm=100, 
  beats=[...],
  downbeats=[...],
  segments=[...],
  activations={
    'beat': array(...), 
    'downbeat': array(...), 
    'segment': array(...), 
    'label': array(...)
  }, 
  embeddings=array(...),
)
```

## Concerning MP3 Files
Due to variations in decoders, MP3 files can have slight offset differences.
I recommend you to first convert your audio files to WAV format using FFmpeg (as shown below), 
and use the WAV files for all your data processing pipelines.
```shell
ffmpeg -i your_audio_file.mp3 your_audio_file.wav
```
In this package, audio files are read using [Demucs](https://github.com/facebookresearch/demucs).
To my understanding, Demucs converts MP3 files to WAV using FFmpeg before reading them.
However, using a different MP3 decoder can yield different offsets. 
I've observed variations of about 20~40ms, which is problematic for tasks requiring precise timing like beat tracking, 
where the conventional tolerance is just 70ms. 
Hence, I advise standardizing inputs to the WAV format for all data processing, 
ensuring straightforward decoding.


## Training
Please refer to [TRAINING.md](TRAINING.md).

## Citation
If you use this package for your research, please cite the following paper:
```bibtex
@inproceedings{taejun2023allinone,
  title={All-In-One Metrical And Functional Structure Analysis With Neighborhood Attentions on Demixed Audio},
  author={Kim, Taejun and Nam, Juhan},
  booktitle={IEEE Workshop on Applications of Signal Processing to Audio and Acoustics (WASPAA)},
  year={2023}
}
```
