#!/usr/bin/env python3
"""Standalone FFmpeg-based time-range voice processor. Python standard library only."""
import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

# Pitch modification with duration compensation; asetrate changes pitch and duration,
# atempo restores approximate original duration. No AI speaker conversion.

PRESETS = {
    # KONGO — Massive, deep, heavy, powerful
    "kongo": {
        "pitch": 0.73,
        "hp": 50,
        "eq": [
            (100, 5),
            (280, -3),
            (900, -2),
            (2600, 3),
            (4800, -2)
        ],
        "comp": (0.12, 4.0, 10, 140)
    },

    # SLOTHY — Relaxed, dry, slightly nasal, sarcastic
    "slothy": {
        "pitch": 1.10,
        "hp": 110,
        "eq": [
            (160, -4),
            (450, -2),
            (950, 4),
            (2300, 2),
            (5500, -3)
        ],
        "comp": (0.22, 1.6, 30, 200)
    },

    # GIRA — High, thin, awkward, nervous
    "gira": {
        "pitch": 1.36,
        "hp": 150,
        "eq": [
            (180, -6),
            (550, -3),
            (1200, 4),
            (3300, 5),
            (6500, 1)
        ],
        "comp": (0.18, 2.0, 8, 95)
    },

    # LEO — Rich, confident, theatrical authority
    "leo": {
        "pitch": 0.90,
        "hp": 65,
        "eq": [
            (135, 4),
            (380, -2),
            (1100, 2),
            (2800, 4),
            (6000, 1)
        ],
        "comp": (0.14, 3.0, 15, 150)
    },

    # CROC — Sharp, street-smart, gritty hustler
    "croc": {
        "pitch": 0.96,
        "hp": 95,
        "eq": [
            (170, -2),
            (550, 2),
            (1100, 4),
            (2800, 5),
            (5000, 2)
        ],
        "comp": (0.15, 3.2, 7, 90)
    },

    # ZEE — Feminine, youthful, energetic influencer
    "zee": {
        "pitch": 1.42,
        "hp": 165,
        "eq": [
            (160, -7),
            (300, -5),
            (650, -3),
            (1200, 2),
            (2500, 4),
            (3800, 5),
            (6500, 3)
        ],
        "comp": (0.20, 2.0, 8, 100)
    }
}

RATE = 48000

def run(cmd):
    subprocess.run(cmd, check=True)

def parse_time(value):
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        n = float(value)
    elif isinstance(value, str):
        parts = value.split(':')
        if len(parts) > 3:
            raise ValueError(f'Invalid timestamp: {value}')
        try:
            n = 0.0
            for p in parts:
                n = n * 60 + float(p)
        except ValueError:
            raise ValueError(f'Invalid timestamp: {value}') from None
    else:
        raise ValueError(f'Invalid timestamp: {value}')
    if not math.isfinite(n) or n < 0:
        raise ValueError(f'Invalid timestamp: {value}')
    return n

def filters_for(name):
    if name == 'original':
        return 'anull'

    preset = PRESETS[name]

    pitch = float(preset["pitch"])
    highpass = float(preset["hp"])
    eqs = preset["eq"]
    comp = preset["comp"]

    chain = [
        f'asetrate={RATE}*{pitch}',
        f'aresample={RATE}',
        f'atempo={1/pitch:.9f}',
        f'highpass=f={highpass}'
    ]

    for freq, gain in eqs:
        chain.append(
            f'equalizer=f={freq}:t=q:w=1:g={gain}'
        )

    threshold, ratio, attack, release = comp

    chain.append(
        f'acompressor=threshold={threshold}:ratio={ratio}:attack={attack}:release={release}'
    )

    return ','.join(chain)


def main():
    parser = argparse.ArgumentParser(description='Extract and transform selected dialogue time ranges; outputs WAV audio only.')
    parser.add_argument('input', type=Path, help='Video/audio source file')
    parser.add_argument('segments', type=Path, help='JSON list of {start,end,voice} ranges')
    parser.add_argument('--output', type=Path, help='Output WAV (default: <source>-gymzoo-voices.wav)')
    args = parser.parse_args()
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        parser.error('ffmpeg and ffprobe must be installed and on PATH')
    if not args.input.is_file() or not args.segments.is_file():
        parser.error('Input and JSON segment file must exist')
    out = args.output or args.input.with_name(args.input.stem + '-gymzoo-voices.wav')
    out = out.resolve()
    if out.exists():
        parser.error(f'Output exists; refusing to overwrite: {out}')
    if out.suffix.lower() != '.wav':
        parser.error('Output must have a .wav extension')
    try:
        probe = subprocess.check_output(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=duration:format=duration','-of','json',str(args.input)],text=True)
        metadata = json.loads(probe)
        if not metadata.get('streams'):
            parser.error('Source contains no audio stream')
        duration_text = metadata['streams'][0].get('duration') or metadata.get('format',{}).get('duration')
        if not duration_text:
            parser.error('Could not determine source audio duration')
        duration = float(duration_text)
        raw = json.loads(args.segments.read_text(encoding='utf-8'))
        if not isinstance(raw, list) or not raw:
            parser.error('Segments JSON must be a nonempty list')
        segments = []
        for i, item in enumerate(raw,1):
            if not isinstance(item, dict):
                raise ValueError(f'Segment {i} must be an object')
            start, end, voice = parse_time(item['start']), parse_time(item['end']), item['voice'].lower()
            if voice not in PRESETS:
                raise ValueError(f'Segment {i}: unknown voice {voice!r}; choose {", ".join(PRESETS)}')
            if end <= start or end > duration + 0.03:
                raise ValueError(f'Segment {i}: invalid interval {start} to {end}, source duration {duration:.3f}')
            segments.append((start, min(end,duration), voice))
        segments.sort(key=lambda x: x[0])
        if any(b[0] < a[1] - 0.00001 for a,b in zip(segments,segments[1:])):
            raise ValueError('Overlapping ranges are not supported; split speakers into nonoverlapping ranges')
        # Fill unspecified gaps with original audio; use sample-index boundaries for precise concatenation.
        spans = []
        cursor = 0
        for start,end,voice in segments:
            a,b = round(start*RATE),round(end*RATE)
            if a > cursor:
                spans.append((cursor,a,'original'))
            spans.append((a,b,voice))
            cursor=b
        last=round(duration*RATE)
        if cursor < last:
            spans.append((cursor,last,'original'))
        # Single FFmpeg invocation: trim, process, pad/trim back to exact length, concat.
        graphs=[]
        for i,(a,b,voice) in enumerate(spans):
            count=b-a
            fx=filters_for(voice)
            graphs.append(f'[0:a:0]aresample={RATE},aformat=channel_layouts=mono,atrim=start_sample={a}:end_sample={b},asetpts=PTS-STARTPTS,{fx},apad,atrim=end_sample={count},asetpts=PTS-STARTPTS[s{i}]')
        joins=''.join(f'[s{i}]' for i in range(len(spans)))
        graphs.append(f'{joins}concat=n={len(spans)}:v=0:a=1[out]')
        out.parent.mkdir(parents=True, exist_ok=True)
        run(['ffmpeg','-hide_banner','-nostdin','-v','warning','-i',str(args.input),'-filter_complex',';'.join(graphs),'-map','[out]','-c:a','pcm_s24le','-ar',str(RATE),'-ac','1','-y',str(out)])
        print(f'Created: {out}')
        print(f'Processed {len(segments)} voice ranges; other audio left unprocessed. No video output created.')
    except (ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as e:
        if out.exists():
            out.unlink()
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
