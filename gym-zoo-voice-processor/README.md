# GYM ZOO Voice Processor

Standalone audio-only time-range processor using **FFmpeg + Python 3 standard library**. Does not interact with any video enhancer. Source video is never modified.

## Requirements

- `ffmpeg` and `ffprobe` on PATH
- `python3`

## Usage

```bash
python3 gymzoo-voice.py "/path/to/scene.mp4" segments-example.json
```

Creates `/path/to/scene-gymzoo-voices.wav`, 48 kHz, mono, 24-bit PCM. Optionally specify `--output /path/to/output.wav`.

Edit `segments-example.json` with `start`, `end` and `voice` for each dialogue range. Time formats: seconds (`2.5`), `MM:SS`, or `HH:MM:SS.sss`. Voices: `kongo`, `slothy`, `gira`, `leo`, `croc`, `zee`.

Ranges must not overlap. Unspecified ranges retain the original audio (including music and ambience). The entire first audio stream is converted to mono. If background music is present during dialogue, it will be processed too; **use dialogue-only sources for best results**. If speakers overlap, separate their audio stems first. This is signal processing, not AI voice cloning, source separation, or speaker identity conversion.

The script sorts the ranges by start time, rejects overlaps, retains approximate timing via pitch/tempo compensation, and pads/trims each segment to its original sample count. Some transients near boundaries can sound abrupt: place cuts in pauses where possible. Test sync against the original video in Resolve.

## Presets

The six presets are initial creative starting points, not final approved voice identities. They adjust pitch, EQ and compression. Edit the `PRESETS` dictionary in `gymzoo-voice.py` to refine them. Save a separate version of the script after locking final presets.

## Safety

The script refuses to overwrite an existing output WAV. Input video is read only. No additional downloads or models are required.
