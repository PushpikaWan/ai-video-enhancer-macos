#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'HELP'
Usage: bit-byte-enhance.sh SOURCE_VIDEO [OUTPUT_MP4]

Enhances a 720p video to 1440p using Real-ESRGAN on Apple Silicon.
Optional environment variables:
  REALESRGAN_BIN      Full path to realesrgan-ncnn-vulkan executable
                      (default: ./Real-ESRGAN-ncnn-vulkan/build/realesrgan-ncnn-vulkan relative to script)
  REALESRGAN_MODELS   Full path to model directory (default: sibling models/ of executable)
  KEEP_FRAMES=1       Keep intermediate PNG frames after success
  CRF=15              H.264 constant rate factor (lower = larger/better)
HELP
}
if [[ $# -lt 1 || $# -gt 2 ]]; then usage; exit 2; fi
for cmd in ffmpeg ffprobe; do
  command -v "$cmd" >/dev/null || { echo "Missing command: $cmd" >&2; exit 1; }
done
SOURCE="$1"
[[ -f "$SOURCE" ]] || { echo "Source not found: $SOURCE" >&2; exit 1; }
SOURCE="$(cd "$(dirname "$SOURCE")" && pwd)/$(basename "$SOURCE")"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_BIN="$SCRIPT_DIR/Real-ESRGAN-ncnn-vulkan/build/realesrgan-ncnn-vulkan"
BIN="${REALESRGAN_BIN:-$DEFAULT_BIN}"
MODELS="${REALESRGAN_MODELS:-$(dirname "$BIN")/models}"
[[ -x "$BIN" ]] || { echo "Real-ESRGAN executable not found: $BIN" >&2; exit 1; }
for ext in bin param; do
  [[ -f "$MODELS/realesr-animevideov3-x2.$ext" ]] || { echo "Missing model: $MODELS/realesr-animevideov3-x2.$ext" >&2; exit 1; }
done

base="$(basename "$SOURCE")"; base="${base%.*}"
OUTPUT="${2:-$(dirname "$SOURCE")/${base}-AI-1440p.mp4}"
mkdir -p "$(dirname "$OUTPUT")"
OUTPUT="$(cd "$(dirname "$OUTPUT")" && pwd)/$(basename "$OUTPUT")"
[[ "$OUTPUT" != "$SOURCE" ]] || { echo "Output must differ from input" >&2; exit 1; }
[[ ! -e "$OUTPUT" ]] || { echo "Output already exists: $OUTPUT (move or rename it first)" >&2; exit 1; }

width="$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$SOURCE" | head -1)"
height="$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$SOURCE" | head -1)"
fps="$(ffprobe -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of csv=p=0 "$SOURCE" | head -1)"
[[ "$width" =~ ^[0-9]+$ && "$height" =~ ^[0-9]+$ ]] || { echo 'Cannot read video resolution' >&2; exit 1; }
[[ "$fps" != '0/0' && -n "$fps" ]] || { echo 'Cannot read frame rate' >&2; exit 1; }
if [[ "$width" != 1280 || "$height" != 720 ]]; then
  echo "Input is ${width}x${height}, not 1280x720." >&2
  echo 'Use the original 720p export for best results. No conversion performed.' >&2
  exit 1
fi

# This workflow assumes a constant-frame-rate source. Detect obvious VFR.
r_fps="$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$SOURCE" | head -1)"
if [[ "$fps" != "$r_fps" ]]; then
  echo "Warning: avg_frame_rate=$fps differs from r_frame_rate=$r_fps." >&2
  echo 'Source may be variable frame rate. Convert to CFR before using this script.' >&2
  exit 1
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bit-byte-ai.XXXXXXXX")"
mkdir -p "$WORK/input" "$WORK/output"
cleanup() {
  status=$?
  if [[ "$status" -eq 0 && "${KEEP_FRAMES:-0}" != 1 ]]; then
    rm -rf "$WORK"
  else
    echo "Intermediate frames retained: $WORK" >&2
  fi
}
trap cleanup EXIT

echo "Input:  $SOURCE"
echo "Output: $OUTPUT"
echo "Video:  ${width}x${height} at $fps fps"
echo '[1/3] Extracting lossless PNG frames...'
ffmpeg -hide_banner -loglevel error -stats -i "$SOURCE" -map 0:v:0 -fps_mode passthrough -start_number 1 "$WORK/input/frame_%06d.png"
echo '[2/3] Running Real-ESRGAN 2x on Apple GPU...'
"$BIN" -i "$WORK/input" -o "$WORK/output" -n realesr-animevideov3 -s 2 -z 2 -m "$MODELS" -g 0 -f png

input_count="$(find "$WORK/input" -maxdepth 1 -name 'frame_*.png' -type f | wc -l | tr -d ' ')"
output_count="$(find "$WORK/output" -maxdepth 1 -name 'frame_*.png' -type f | wc -l | tr -d ' ')"
[[ "$input_count" -gt 0 && "$input_count" == "$output_count" ]] || { echo "Frame mismatch: $input_count input, $output_count output" >&2; exit 1; }

echo '[3/3] Encoding YouTube-ready 1440p MP4 with original audio...'
# Explicit frame rate, no shortest: exact video duration follows number of enhanced frames.
ffmpeg -hide_banner -stats -loglevel error \
  -framerate "$fps" -start_number 1 -i "$WORK/output/frame_%06d.png" \
  -i "$SOURCE" -map 0:v:0 -map '1:a:0?' \
  -c:v libx264 -preset slow -crf "${CRF:-15}" -pix_fmt yuv420p \
  -c:a aac -b:a 320k -ar 48000 \
  -movflags +faststart -metadata:s:v:0 title="AI enhanced 1440p" \
  "$OUTPUT"

outwidth="$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$OUTPUT" | head -1)"
outheight="$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$OUTPUT" | head -1)"
[[ "$outwidth" == 2560 && "$outheight" == 1440 ]] || { echo "Unexpected output resolution ${outwidth}x${outheight}" >&2; exit 1; }
echo "SUCCESS: $OUTPUT"
