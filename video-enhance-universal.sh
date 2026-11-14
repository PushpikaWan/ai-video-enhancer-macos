#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'HELP'
Usage: bit-byte-enhance-universal.sh INPUT [OUTPUT]
Environment:
  REALESRGAN_BIN       path to realesrgan-ncnn-vulkan
  REALESRGAN_MODELS    model directory
  TARGET_HEIGHT        optional output height (e.g. 1920 for portrait, 2160 for 4K landscape)
  CRF                  x264 quality, default 17 (lower = larger file)
  PRESET               x264 preset, default slow
  KEEP_FRAMES          1 to retain intermediates on success
  MAX_OUTPUT_PIXELS    safety cap, default 10000000 (~4K)
  ALLOW_LARGE_OUTPUT   1 to bypass pixel cap
Notes: Uses 2x AI upscaling, then optional aspect-preserving FFmpeg resize.
       Target height greater than 2x source height is rejected.
       Audio: first audio stream, encoded AAC 320k/48k. Subtitles not copied.
HELP
}
[[ $# -ge 1 && $# -le 2 ]] || { usage; exit 2; }
[[ $1 != '-h' && $1 != '--help' ]] || { usage; exit 0; }
input=$1
[[ -f $input ]] || { echo "Input not found: $input" >&2; exit 1; }
for cmd in ffmpeg ffprobe python3; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 1; }; done
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bin=${REALESRGAN_BIN:-"$script_dir/Real-ESRGAN-ncnn-vulkan/build/realesrgan-ncnn-vulkan"}
models=${REALESRGAN_MODELS:-"$(dirname -- "$bin")/models"}
[[ -x $bin ]] || { echo "Executable missing/not executable: $bin" >&2; exit 1; }
for ext in bin param; do [[ -f "$models/realesr-animevideov3-x2.$ext" ]] || { echo "Missing model: $models/realesr-animevideov3-x2.$ext" >&2; exit 1; }; done
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q 'libx264' || { echo 'FFmpeg lacks libx264' >&2; exit 1; }

stem=${input%.*}
output=${2:-"${stem}-AI-2x.mp4"}
[[ $output != "$input" ]] || { echo 'Output must differ from input' >&2; exit 1; }
[[ ${output##*.} == mp4 ]] || { echo 'Output must end in .mp4' >&2; exit 1; }
[[ ! -e $output ]] || { echo "Output already exists: $output" >&2; exit 1; }
[[ -d $(dirname -- "$output") ]] || { echo 'Output directory does not exist' >&2; exit 1; }

probe=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,avg_frame_rate,r_frame_rate,nb_frames -of json "$input")
read -r w h fps expected < <(python3 - "$probe" <<'PY'
import json,sys
s=json.loads(sys.argv[1])['streams'][0]
w,h=int(s['width']),int(s['height'])
fps=s.get('avg_frame_rate','0/0')
r=s.get('r_frame_rate','0/0')
from fractions import Fraction
if w<1 or h<1 or Fraction(fps)<=0 or Fraction(r)<=0:
    raise SystemExit('Invalid video metadata')
if abs(float(Fraction(fps))-float(Fraction(r)))>0.01:
    raise SystemExit('Likely VFR input: convert to CFR first')
print(w,h,fps,s.get('nb_frames','unknown'))
PY
)
[[ $w -gt 0 && $h -gt 0 ]] || exit 1
[[ ${TARGET_HEIGHT:-} =~ ^[0-9]+$ || -z ${TARGET_HEIGHT:-} ]] || { echo 'TARGET_HEIGHT must be a positive integer' >&2; exit 1; }
[[ ${CRF:-17} =~ ^([0-9]|[1-4][0-9]|5[0-1])$ ]] || { echo 'CRF must be 0..51' >&2; exit 1; }
[[ ${MAX_OUTPUT_PIXELS:-10000000} =~ ^[0-9]+$ ]] || { echo 'MAX_OUTPUT_PIXELS must be an integer' >&2; exit 1; }
# Final dimensions must be even for yuv420p. Aspect ratio is preserved to within rounding.
read -r outw outh < <(python3 - "$w" "$h" "${TARGET_HEIGHT:-}" <<'PY'
import sys
w,h=map(int,sys.argv[1:3]); target=sys.argv[3]
if target:
    th=int(target)
    if th<2 or th>h*2: raise SystemExit('TARGET_HEIGHT must be between 2 and 2x source height')
    oh=2*round(th/2)
    ow=2*round((w*oh/h)/2)
else:
    ow,oh=w*2,h*2
if ow<2 or oh<2: raise SystemExit('Output dimensions too small')
print(ow,oh)
PY
)
if (( outw * outh > ${MAX_OUTPUT_PIXELS:-10000000} )) && [[ ${ALLOW_LARGE_OUTPUT:-0} != 1 ]]; then
  echo "Output ${outw}x${outh} exceeds safety cap. Set ALLOW_LARGE_OUTPUT=1 to proceed." >&2
  exit 1
fi
printf 'Input: %sx%s at %s fps | AI stage: %sx%s | Output: %sx%s\n' "$w" "$h" "$fps" "$((w*2))" "$((h*2))" "$outw" "$outh"
work=$(mktemp -d "${TMPDIR:-/tmp}/bitbyte-enhance.XXXXXXXX")
mkdir -p "$work/source" "$work/upscaled"
echo "Temporary files: $work"
success=0
cleanup() {
  if (( success )) && [[ ${KEEP_FRAMES:-0} != 1 ]]; then rm -rf -- "$work";
  else echo "Intermediates retained: $work"; fi
}
trap cleanup EXIT
# -fps_mode passthrough avoids frame duplication during extraction; CFR is expected.
ffmpeg -hide_banner -loglevel error -i "$input" -map 0:v:0 -fps_mode passthrough "$work/source/%08d.png"
source_count=$(find "$work/source" -type f -name '*.png' | wc -l | tr -d ' ')
(( source_count > 0 )) || { echo 'No frames extracted' >&2; exit 1; }
if [[ $expected =~ ^[0-9]+$ ]] && (( expected != source_count )); then
  echo "Warning: reported frame count $expected differs from extracted $source_count" >&2
fi
"$bin" -i "$work/source" -o "$work/upscaled" -n realesr-animevideov3 -s 2 -z 2 -m "$models" -f png
up_count=$(find "$work/upscaled" -type f -name '*.png' | wc -l | tr -d ' ')
(( source_count == up_count )) || { echo "Frame mismatch: $source_count vs $up_count" >&2; exit 1; }
# Check first enhanced frame size before encoding.
read -r aiw aih < <(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$work/upscaled/00000001.png" | tr x ' ')
[[ $aiw == "$((w*2))" && $aih == "$((h*2))" ]] || { echo "Unexpected AI dimensions: ${aiw}x${aih}" >&2; exit 1; }
# Audio is optional; input 1 is the source video. Encode to a temp output for atomic completion.
partial="$work/result.mp4"
ffmpeg -hide_banner -loglevel error -framerate "$fps" -i "$work/upscaled/%08d.png" -i "$input" \
  -map 0:v:0 -map '1:a:0?' -vf "scale=${outw}:${outh}:flags=lanczos,setsar=1" \
  -c:v libx264 -preset "${PRESET:-slow}" -crf "${CRF:-17}" -pix_fmt yuv420p \
  -c:a aac -b:a 320k -ar 48000 -movflags +faststart "$partial"
read -r checkw checkh < <(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$partial" | tr x ' ')
[[ $checkw == "$outw" && $checkh == "$outh" ]] || { echo 'Output dimension verification failed' >&2; exit 1; }
# Prevent overwrite even if output appeared during processing.
if [[ -e $output ]]; then echo "Output appeared during processing: $output" >&2; exit 1; fi
cp -n "$partial" "$output"
[[ -s $output ]] || { echo 'Could not create output' >&2; exit 1; }
success=1
echo "Success: $output"
