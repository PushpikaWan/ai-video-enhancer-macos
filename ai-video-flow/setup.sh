#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if ! command -v conda >/dev/null 2>&1; then
  echo 'Conda not found. Install and initialize Miniforge or Miniconda first.' >&2
  exit 1
fi
if conda env list --json | python3 -c 'import json,sys; from pathlib import Path; sys.exit(not any(Path(p).name == "ai-workflow" for p in json.load(sys.stdin)["envs"]))'; then
  echo 'ai-workflow already exists. Updating workflow dependencies.'
  conda env update -n ai-workflow -f "$ROOT/environment.yml"
elif conda env list --json | python3 -c 'import json,sys; from pathlib import Path; sys.exit(not any(Path(p).name == "wwh-voice" for p in json.load(sys.stdin)["envs"]))'; then
  echo '[Setup 1/2] Cloning existing voice packages into ai-workflow'
  conda create -y -n ai-workflow --clone wwh-voice
  echo '[Setup 2/2] Installing video and speech tools'
  conda install -y -n ai-workflow -c conda-forge ffmpeg
  conda run --no-capture-output -n ai-workflow python -m pip install espeakng-loader
else
  echo 'Creating ai-workflow from environment.yml'
  conda env create -f "$ROOT/environment.yml"
fi
echo 'Checking audio imports'
conda run --no-capture-output -n ai-workflow python -c 'import numpy, soundfile; from kokoro import KPipeline; print("Audio dependencies OK")'
conda run --no-capture-output -n ai-workflow ffmpeg -version
conda run --no-capture-output -n ai-workflow ffprobe -version
echo 'Setup complete. Start with: bash ai-video-flow/run.sh'
