#!/usr/bin/env bash
set -eo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
echo '[Startup 1/3] Finding and initializing conda'

if ! command -v conda >/dev/null 2>&1; then
  for candidate in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" /opt/homebrew/Caskroom/miniforge/base /opt/anaconda3; do
    if [[ -f "$candidate/etc/profile.d/conda.sh" ]]; then
      source "$candidate/etc/profile.d/conda.sh"
      break
    fi
  done
fi
if ! command -v conda >/dev/null 2>&1; then
  echo 'Conda is not available. Install Miniforge or Miniconda, run conda init, and restart Terminal before launching AI Video Flow.' >&2
  exit 1
fi
if ! conda_hook=$(conda shell.bash hook); then
  echo 'Conda could not initialize. Please repair your conda installation and run conda init bash before trying again.' >&2
  exit 1
fi
eval "$conda_hook"
echo '[Startup 2/3] Activating ai-workflow conda environment'
if ! conda activate ai-workflow; then
  echo 'The ai-workflow conda environment is not available. Create it first: bash ai-video-flow/setup.sh' >&2
  exit 1
fi
export PATH="$CONDA_PREFIX/bin:$PATH"
echo '[Startup 3/3] Checking FFmpeg and Python'
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo 'ffmpeg is not available on PATH after activating ai-workflow. Install it or configure PATH first:' >&2
  echo '  conda install -n ai-workflow -c conda-forge ffmpeg' >&2
  exit 1
fi
if [[ ! -x "$CONDA_PREFIX/bin/python3" ]]; then
  echo 'Python 3 is not available in the ai-workflow conda environment. Install it first:' >&2
  echo '  conda install -n ai-workflow python' >&2
  exit 1
fi
if ! ffmpeg -version >/dev/null 2>&1; then
  echo 'ffmpeg on PATH could not start. Please repair or reinstall it before trying again.' >&2
  exit 1
fi
echo 'Using conda env: ai-workflow'
echo "Using ffmpeg: $(command -v ffmpeg)"
exec "$CONDA_PREFIX/bin/python3" "$ROOT/flow.py"
