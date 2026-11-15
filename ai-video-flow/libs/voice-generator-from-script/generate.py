#!/usr/bin/env python3
"""Offline (after initial model download) Kokoro narration + FFmpeg processing."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

import numpy as np
import soundfile as sf
from kokoro import KPipeline

ROOT = Path(__file__).resolve().parent


def log(message):
    print(f'[{datetime.now():%H:%M:%S}] {message}', flush=True)


def run_ffmpeg(args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main():
    parser = argparse.ArgumentParser(description="Generate cinematic mystery narration")
    parser.add_argument("--script", default=str(ROOT / "scripts" / "narration.json"))
    parser.add_argument("--voice", default=None, help="Override voice, e.g. am_adam")
    parser.add_argument("--speed", type=float, default=None, help="Override speaking speed")
    parser.add_argument("--output", type=Path, default=ROOT / "output", help="Directory for generated audio")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("FFmpeg not found. Install the Conda environment first.")

    log(f'Reading narration script: {args.script}')
    config = json.loads(Path(args.script).read_text(encoding="utf-8"))
    voice = args.voice or config.get("voice", "am_michael")
    speed = args.speed if args.speed is not None else config.get("speed", 0.94)
    if speed <= 0:
        raise SystemExit("Speech speed must be positive")
    cuts = config["cuts"]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    log(f"Loading Kokoro voice: {voice} (first run downloads model files)")
    pipeline = KPipeline(lang_code="a")
    log(f'Model ready; generating {len(cuts)} cuts')
    timeline = np.zeros((int(max(c["start"] + c["duration"] for c in cuts) * 48000),), dtype=np.float32)
    report = []

    for index, cut in enumerate(cuts, 1):
        name, words = cut["id"], cut["text"]
        log(f"Cut {index}/{len(cuts)} — synthesizing {name}: {words}")
        chunks = []
        for chunk_index, (_, _, audio) in enumerate(pipeline(words, voice=voice, speed=speed), 1):
            chunks.append(np.asarray(audio, dtype=np.float32))
            log(f'{name}: synthesized chunk {chunk_index}')
        if not chunks:
            raise RuntimeError(f"Kokoro produced no audio for {name}")
        raw = out / f"{name}_raw.wav"
        processed = out / f"{name}_cinematic.wav"
        log(f'{name}: saving raw audio')
        sf.write(raw, np.concatenate(chunks), 24000)
        filters = ",".join([
            "highpass=f=75",
            "equalizer=f=180:t=q:w=1:g=1.5",
            "equalizer=f=320:t=q:w=1:g=-2",
            "equalizer=f=3000:t=q:w=1:g=1.5",
            "acompressor=threshold=0.08:ratio=2.5:attack=15:release=150",
            "loudnorm=I=-16:TP=-1.5:LRA=9",
        ])
        log(f'{name}: applying cinematic audio filters with FFmpeg')
        run_ffmpeg(["-i", str(raw), "-af", filters, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(processed)])
        audio, sr = sf.read(processed, dtype="float32")
        if sr != 48000:
            raise RuntimeError(f"Unexpected sample rate: {sr}")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        slot_samples = round(cut["duration"] * sr)
        start_samples = round(cut["start"] * sr)
        actual = len(audio) / sr
        if len(audio) > slot_samples:
            print(f"  WARNING: {name} is {actual:.2f}s, exceeds {cut['duration']}s slot; timeline truncates it. Edit text or increase --speed.")
        available = max(0, min(len(audio), slot_samples, len(timeline) - start_samples))
        if available:
            timeline[start_samples:start_samples + available] += audio[:available]
        report.append({"cut": name, "start": cut["start"], "slot_seconds": cut["duration"], "generated_seconds": round(actual, 2), "fits": actual <= cut["duration"]})
        log(f"Cut {index}/{len(cuts)} complete ({index / len(cuts):.0%} of cuts): {processed.name} ({actual:.2f}s)")

    log('All cuts generated; normalizing and saving combined timeline')
    peak = float(np.max(np.abs(timeline)))
    if peak > 0.98:
        timeline *= 0.98 / peak
    timeline_file = out / "full_35s_timeline.wav"
    sf.write(timeline_file, timeline, 48000, subtype="PCM_24")
    log('Saving timing report')
    (out / "timing_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFinished: {timeline_file}")
    print("Check timing_report.json; if a cut is too long, shorten its text or increase speaking speed.")
    print("Note: the combined timeline contains voice only; add knocks, music and branding sounds in DaVinci Resolve.")


if __name__ == "__main__":
    main()
