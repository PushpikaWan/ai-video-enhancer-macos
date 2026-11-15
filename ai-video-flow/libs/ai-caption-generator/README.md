# AI Caption Generator

Local SRT subtitles using Python 3.11, MLX Whisper, and the Apple Silicon Metal
GPU. No paid API, server, or source-file changes. WAV, MP3, M4A, MP4, and MOV
inputs are decoded to a temporary mono 16 kHz WAV with FFmpeg.

Install from the repository root with Miniforge (native ARM64, not Rosetta):

```bash
conda env create -f ai-video-flow/libs/ai-caption-generator/environment.yml
conda activate ai-caption-generator
cd ai-video-flow/libs/ai-caption-generator
ffmpeg -version
python generate_captions.py /path/to/narration.wav
```

This creates a separate environment and does not change `base`. Your existing
FFmpeg must be on PATH; Homebrew FFmpeg 9 is supported. If necessary:
`conda install -n ai-caption-generator -c conda-forge ffmpeg`.

The default model is `mlx-community/whisper-large-v3-turbo`. The first run downloads
weights into Hugging Face's normal cache (typically `~/.cache/huggingface/hub`).
Subsequent runs reuse them. Internet is needed for the initial model download.
Model loading/download messages are followed by Whisper's transcription progress.
The workflow also reports elapsed time while waiting.

Examples (from this directory):

```bash
python generate_captions.py narration.wav
python generate_captions.py narration.wav --max-chars 22 --max-words 4 \
  --max-duration 2.5 --uppercase --remove-punctuation
python generate_captions.py narration.wav --max-words 1 --uppercase
python generate_captions.py video.mp4 --max-chars 25 --max-words 5 --output captions.srt
python generate_captions.py video.mov --language auto
python generate_captions.py narration.m4a --language Sinhala --offset 150
python generate_captions.py narration.wav --force-transcribe
```

| Option | CLI default | Meaning |
| --- | --- | --- |
| `--max-chars` | 22 | Total caption character budget, including spaces; a long word stays intact |
| `--max-words` | 4 | Maximum words per caption |
| `--max-lines` | 1 | Maximum display lines; additional lines are balanced without splitting words |
| `--max-duration` | 2.5 | Maximum seconds, unless a single timed word lasts longer |
| `--min-duration` | 0.5 | Preferred minimum seconds, constrained by the next caption and synchronization |
| `--pause` | 0.5 | Split when the pause exceeds this many seconds |
| `--uppercase` | off | Uppercase caption text |
| `--remove-punctuation` | off | Remove Unicode punctuation, keeping letters and combining marks |
| `--language` | English (`en`) | English/en, Sinhala/si, auto, or another Whisper language code |
| `--offset` | 0 | Timing offset in milliseconds; negative times are clamped or skipped |
| `--output` | input basename + `.srt` | Custom UTF-8 SRT path; existing SRT is replaced |
| `--model` | mlx-community/whisper-large-v3-turbo | MLX Whisper model repository or local model directory |
| `--force-transcribe` | off | Ignore cached transcription |
| `--config` | none | Optional JSON defaults; explicit CLI arguments override them |

Sentence endings and natural pauses split captions even when punctuation is
removed. Word alignment uses Whisper's estimated word timestamps; it is not
guaranteed frame-perfect. Review captions against speech in Resolve, especially
music, noise, names, and Sinhala speech. Sinhala is a Whisper language option;
accuracy depends on the model/audio and has not been validated here.

The generator retains whole timed words instead of cutting speech to satisfy a
character or duration limit. Timing corrections remove model timestamp overlaps.
Captions are rounded to milliseconds, have positive durations, and never overlap.
SRT uses standard numbered blocks with `HH:MM:SS,mmm` timestamps and UTF-8 text.
Import it onto a subtitle track in DaVinci Resolve. SRT does not store visual styling.

Raw model results, including segment words and timestamps, are stored as JSON in
`cache/`. A SHA-256 of the entire input plus the model and transcription language
identifies a cache entry. Caption settings do not affect that key. Reformatting,
single-word captions, case, punctuation, or offsets reuse the same transcription.
Changed file content/model/language creates a new cache entry. Delete cache JSONs
to reclaim disk space. If replacing weights inside the same local model directory,
use `--force-transcribe` because the model path itself has not changed.

Workflow integration:

```bash
./ai-video-flow/run.sh
```

Open a project and choose **5. Generate subtitles**, then choose audio/video in
Finder. It uses the dedicated environment automatically, saves SRTs under the
project's `subtitles/`, and preserves previous SRTs. Workflow defaults come from
`defaults.json`: 22 characters, 4 words, 1 line, 2.5 seconds, English, punctuation
removed, normal case. CLI defaults preserve punctuation unless requested.

Choose **6. Edit subtitle defaults** only when you want overrides. Paste a JSON
object, then `END` on its own line, for example:

```json
{"max_words": 1, "uppercase": true, "language": "en"}
```

The resulting full config persists in that project's `subtitles/config.json`.
Unknown keys and invalid values are rejected before saving. Sentence and pause
splitting are automatic; `pause` controls how much silence starts a new caption.

Run the standard-library tests without MLX or downloading a model:

```bash
python -m unittest discover -s ai-video-flow/libs/ai-caption-generator -p 'test_*.py'
```

Implementation reference: [Apple MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper).
