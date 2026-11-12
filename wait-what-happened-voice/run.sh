#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v conda >/dev/null 2>&1; then
  echo 'Conda not found. Install Miniforge and reopen Terminal.' >&2
  exit 1
fi
conda run --no-capture-output -n wwh-voice python generate.py "$@"
