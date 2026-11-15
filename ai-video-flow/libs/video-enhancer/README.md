# Bit & Byte Video Enhancer

Free, local **720p → 1440p AI video enhancement** for macOS Apple Silicon using [Real-ESRGAN NCNN Vulkan](https://github.com/xinntao/Real-ESRGAN) and [FFmpeg](https://ffmpeg.org/). No subscriptions, cloud upload, or watermark.

> **Scope:** This script accepts **1280×720 constant-frame-rate** MOV/MP4 video, enhances each frame 2× with `realesr-animevideov3-x2`, and produces a **2560×1440 H.264 MP4**. It is intended for animated content. AI models may change details or create temporal flicker; compare the output with your source before publishing.

## Features

- 2× Real-ESRGAN GPU upscaling (720p → 1440p)
- Uses the `realesr-animevideov3-x2` model (`-s 2 -z 2`)
- Keeps source frame rate for constant-frame-rate videos
- Carries over the first audio track if present, re-encoded as AAC 320 kbps at 48 kHz
- Lossless PNG intermediates; H.264 `libx264` slow preset, CRF 15 by default
- Temporary frames removed **only on success** (retained after failure for debugging)
- Fails safely if input is not 720p, output exists, model is missing, or frame counts differ

## Requirements

- macOS on Apple Silicon (tested by project creator on **M3 Pro**, macOS 26.7)
- [Homebrew](https://brew.sh/)
- FFmpeg with `ffprobe` and `libx264`
- A working `realesrgan-ncnn-vulkan` binary with the `-z` native model-scale option (such as the Apple Silicon-compatible [yetidevworks fork](https://github.com/yetidevworks/Real-ESRGAN-ncnn-vulkan))
- The matching `realesr-animevideov3-x2.bin` and `.param` files
- Significant free disk space for PNG frame sequences; longer videos may require many GB

## 1. Install FFmpeg

```bash
brew install ffmpeg
ffmpeg -version | head -n 2
```

## 2. Build the AI engine (Apple Silicon)

The AI executable and weights are **not included** in this repository. Build the engine separately from its upstream source and check that it supports `-z`:

```bash
brew install git cmake vulkan-headers vulkan-loader molten-vk glslang
git clone --recursive https://github.com/yetidevworks/Real-ESRGAN-ncnn-vulkan.git
cd Real-ESRGAN-ncnn-vulkan
mkdir -p build
cd build
cmake ../src \
  -DUSE_STATIC_MOLTENVK=ON \
  -DVulkan_INCLUDE_DIR="$(brew --prefix vulkan-headers)/include" \
  -DVulkan_LIBRARY="$(brew --prefix molten-vk)/lib/libMoltenVK.a" \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build . --parallel "$(sysctl -n hw.ncpu)"
./realesrgan-ncnn-vulkan -h
```

Build steps are provided as a starting point, not guaranteed for every future macOS/toolchain version. Check the fork's current build documentation if CMake options change. Review third-party source and downloads before running them.

## 3. Obtain the model files

Obtain the **NCNN Vulkan** `realesr-animevideov3-x2` weights from the [Real-ESRGAN project/releases](https://github.com/xinntao/Real-ESRGAN/releases) or the compatible project's published model bundle. You need these **exact filenames** in the model directory:

```text
realesr-animevideov3-x2.bin
realesr-animevideov3-x2.param
```

By default the script looks for the model directory alongside the executable (`build/models/`). Alternatively set `REALESRGAN_MODELS` to the folder containing the two files.

Do not confuse `src/ncnn/benchmark/*.param` with the enhancement weights. No direct model ZIP URL is hardcoded because release asset names and locations can change.

## 4. Set up this repository

Suggested layout:

```text
bit-byte-video-enhancer/
├── README.md
├── LICENSE
├── .gitignore
├── bit-byte-enhance.sh
└── Real-ESRGAN-ncnn-vulkan/    # external clone; ignored by Git
    └── build/
        ├── realesrgan-ncnn-vulkan
        └── models/
            ├── realesr-animevideov3-x2.bin
            └── realesr-animevideov3-x2.param
```

```bash
chmod +x bit-byte-enhance.sh
```

If you built the engine elsewhere, specify the paths using environment variables (recommended for sharing this script across machines):

```bash
export REALESRGAN_BIN="$HOME/path/to/Real-ESRGAN-ncnn-vulkan/build/realesrgan-ncnn-vulkan"
export REALESRGAN_MODELS="$HOME/path/to/Real-ESRGAN-ncnn-vulkan/build/models"
```

## 5. Enhance a video

```bash
./bit-byte-enhance.sh "/path/to/intro-720p.mov"
```

Default output is created next to the source: `intro-720p-AI-1440p.mp4`.

Choose a destination:

```bash
./bit-byte-enhance.sh "/path/to/intro-720p.mov" "/path/to/intro-final-1440p.mp4"
```

Keep intermediate PNG frames after successful processing:

```bash
KEEP_FRAMES=1 ./bit-byte-enhance.sh "/path/to/intro-720p.mov"
```

Use a slightly smaller output file (may reduce fine detail):

```bash
CRF=17 ./bit-byte-enhance.sh "/path/to/intro-720p.mov"
```

**Important:** Do not run the script on an already upscaled 1440p/4K export. Start from the original 720p source when possible. The script refuses non-720p inputs.

## Processing pipeline

1. Probe resolution and frame rate with `ffprobe`.
2. Extract lossless PNG frames with FFmpeg.
3. Run the Apple GPU-enabled Real-ESRGAN executable using `-n realesr-animevideov3 -s 2 -z 2`.
4. Check that output and input frame counts match.
5. Encode 1440p H.264 (`libx264`, `-preset slow`, `-crf 15`, `yuv420p`) and optional AAC audio.
6. Verify output dimensions and remove temporary frames after success.

The script uses the first audio track, if any. Other audio, subtitle, and timecode tracks are not copied. It is designed for constant-frame-rate video and checks for a common VFR indicator, but this check cannot prove every source is CFR. Audio/video sync should be checked after encoding, particularly for unusual files.

## Verify the result

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate \
  -of default=noprint_wrappers=1 \
  "/path/to/intro-final-1440p.mp4"
```

Expected resolution: `2560×1440`. Frame rate should match the original (e.g., `24/1`). Inspect motion, faces, text, and edges for artifacts and flicker. Upscaling does not guarantee that YouTube playback looks better than a high-quality conventional export.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| `zsh: no matches found: 1:a:0?` | In manual FFmpeg commands, quote the optional audio map: `-map '1:a:0?'`. The script already does this. |
| `Real-ESRGAN executable not found` | Set `REALESRGAN_BIN` to the full path of your compiled executable. |
| `Missing model` | Set `REALESRGAN_MODELS` to the folder with the `-x2.bin` and `-x2.param` files. |
| `model scale: 4` | Confirm the engine supports `-z 2` and the correct x2 weights exist. |
| GPU/Vulkan errors | Check the fork's Apple Silicon build instructions and MoltenVK dependencies. |
| `Input is ... not 1280x720` | Use the 720p source, not a 1440p or 4K export. |
| Source may be variable frame rate | Convert to a constant-frame-rate intermediate first; review audio sync. |
| Output already exists | Rename or move the existing output; the script will not overwrite it. |
| Processing fails midway | The temporary directory path is printed; inspect logs and ensure adequate free disk space. |

## GitHub publishing

```bash
git init
git add README.md LICENSE .gitignore bit-byte-enhance.sh
git commit -m "Initial release: local 720p to 1440p AI video enhancer"
```

Create an empty repository on GitHub, then follow the remote URL instructions shown by GitHub to push your local repository. Do not commit model weights, third-party compiled binaries, private videos, or temporary PNG frames.

## License and attribution

The **wrapper script and README in this repository** are MIT licensed (see `LICENSE`). The upstream Real-ESRGAN, NCNN, MoltenVK, and FFmpeg projects are separate dependencies governed by their own licenses. This repository does **not** relicense them. Check their licenses and any codec distribution requirements if you redistribute binaries or model weights.

## Credits

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) — AI super-resolution models and research
- [Real-ESRGAN NCNN Vulkan](https://github.com/nihui/realesrgan-ncnn-vulkan) — Vulkan inference implementation
- [Apple Silicon-compatible fork](https://github.com/yetidevworks/Real-ESRGAN-ncnn-vulkan) — Mac build used in this workflow
- [FFmpeg](https://ffmpeg.org/) — frame extraction, audio and video encoding

This is an independent community wrapper, not an official Real-ESRGAN or FFmpeg release.
