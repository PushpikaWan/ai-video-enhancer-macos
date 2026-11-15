# Wait, What Happened? — Offline AI Voice Generator

Free local narration for **The Message From Tomorrow**, using Kokoro TTS and FFmpeg. Built for Apple Silicon Macs and Conda/Miniforge. The first run requires internet to download model weights; subsequent runs can work offline if the models are cached.

## Prerequisite

Install **Miniforge (Apple Silicon)** if Conda is not installed: https://github.com/conda-forge/miniforge . Open a new Terminal after installing. Check with `conda --version`.

## Quick start

```bash
cd ~/Downloads/wait-what-happened-voice
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

Alternatively but recommended, use:

```bash
conda env create -f environment.yml
conda activate wwh-voice
python generate.py
```

If the environment already exists, run `conda env update -n wwh-voice -f environment.yml --prune` instead of `./setup.sh`.

## Outputs

The `output/` folder will contain `cut01_cinematic.wav` through `cut06_cinematic.wav`, raw WAV versions, `full_35s_timeline.wav`, and `timing_report.json`. Import these WAV files into DaVinci Resolve. The full timeline aligns each cut to 0, 4, 9, 15, 21, and 28 seconds, padding short narration with silence. If narration exceeds its allocated duration, the combined timeline **truncates** that cut and prints a warning; individual cinematic WAV files remain complete. Review the timing report before using the combined file.

## Change voice or text

Edit `scripts/narration.json` to change text, speed, voice or cut timing. Try `am_michael` or `am_adam`. Or run:

```bash
./run.sh --voice am_adam --speed 1.05
```

No background music, door knocks, or other sound effects are generated. Add those in DaVinci Resolve. Keep the same voice for all cuts to preserve consistency.

## Troubleshooting

- If `conda` is missing, install Miniforge and restart Terminal.
- If voice model download fails, reconnect to the internet and retry.
- If speech is too long, shorten text or increase speed slightly.
- If macOS has trouble loading `espeak-ng`, ensure the Conda environment is active and try `conda install -c conda-forge espeak-ng`.
- If `kokoro` installation fails because of package changes, inspect the error and update dependencies in `environment.yml`.

## Licensing

Kokoro is an open-source model; check its current model/voice licenses and the terms of any downloaded assets before commercial publishing. No paid API is used by this project.
