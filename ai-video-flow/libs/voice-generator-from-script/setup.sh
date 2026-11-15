#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v conda >/dev/null 2>&1; then
  echo 'Conda not found. Install Miniforge first: https://github.com/conda-forge/miniforge' >&2
  exit 1
fi
conda env create -f environment.yml
printf '\nSetup complete. Run: ./run.sh\n'
