# AI Video Flow

Run from this repository on macOS:

```bash
bash ai-video-flow/run.sh
```

One-time environment setup:

```bash
bash ai-video-flow/setup.sh
```

Setup clones `wwh-voice` when available to preserve its installed voice packages,
then adds FFmpeg (including ffprobe) and the Python espeakng-loader speech library. On a fresh machine it creates
`ai-workflow` from `environment.yml`. Existing `base` and `wwh-voice` environments
are left unchanged. Python 3.11 is used for the voice dependencies; base's Python
and conda management packages are not needed by this workflow.

At every launch, the script automatically activates `ai-workflow` without a
selection prompt. Its Python and packages are used by all workflow actions.
FFmpeg is checked on PATH after activation, so Homebrew installations also work.
If setup is interrupted after cloning, rerun setup to finish dependencies.

Choose **Create a new video project**, enter a video name, and use the macOS folder
picker to choose its parent folder. Existing folders are never silently reused.
Choose **Continue an existing video project** to see saved names and full paths,
or browse for a project created by this tool. The most recently opened project
appears first. Paths persist in `ai-video-flow/.state/projects.json` between runs;
this local registry is ignored by Git. A moved project can be found with Browse.

Each project contains:

```text
My Video/
  project.json
  frames/       # <video-name>_lastframe.png
  scripts/      # validated narration JSON snapshots
  audio/        # separate output folder for each generation
  enhanced/     # enhanced finished videos
```

The project menu provides:

1. **Get last frame**: choose a video in a native macOS file picker. Runs
   `ffmpeg -sseof -0.5 -i <video> -update 1 -y <video-name>_lastframe.png`.
   It decodes the final half-second, retaining the last decoded frame. Existing
   images require overwrite confirmation. Very short clips may not yield a frame.
2. **Generate audio**: paste a narration JSON object, then type `END` on its own
   line to validate and save it in the project's `scripts/` folder. Type `CANCEL`
   on its own line to cancel. Saved scripts are listed on later visits; select
   one to generate audio or choose **View / edit JSON** to display it and paste
   a replacement. Invalid edits leave the saved script intact. Validates before
   invoking the Kokoro generator in `libs/voice-generator-from-script/generate.py`.
   Each run gets a new output folder, preserving previous runs. Requires the voice generator's
   dependencies in `ai-workflow` (see `environment.yml`).
   The first model load may require internet. A structurally valid voice name must
   also be supported by the installed Kokoro model.
3. **Enhance finished video**: choose your produced video; invokes the existing
   `libs/video-enhancer/video-enhance-universal.sh` with output inside `enhanced/`. This requires
   ffprobe and the existing Real-ESRGAN executable and models. Existing enhancer
   environment settings such as `TARGET_HEIGHT` still apply.
4. **Open project in Finder**.
5. **Generate subtitles**: choose audio/video in Finder. Uses the separate
   `ai-caption-generator` conda environment and saves UTF-8 SRT files in the
   project's `subtitles/` folder. Saved defaults are used without extra questions.
6. **Edit subtitle defaults**: paste only the settings you want to change, ending
   with `END`. Defaults include punctuation removal, 4 words, 22 characters,
   1 line, English, and automatic sentence/pause splitting. Overrides persist per project.

Install the caption environment once:

```bash
conda env create -f ai-video-flow/libs/ai-caption-generator/environment.yml
```

See [the standalone caption generator](libs/ai-caption-generator/README.md) for
CLI options, model caching, and installation details.

Canceling a file/folder picker returns to the menu. Source files are read only.
Audio failures can leave partial output for inspection; reruns use a new folder.

Actions print timestamped stage, completion, and failure messages. Long frame,
and audio commands also print elapsed-time updates every 10 seconds.
Audio generation reports model loading, synthesized chunks, completed cuts, and
timeline/report saving. Enhancement shows one updating percentage line per stage
with elapsed time, hiding raw FFmpeg and Real-ESRGAN output. AI percentages track
output frames rather than individual tile percentages. If the input frame count
is unknown, extraction shows a frame count instead. Diagnostic logs are retained
with temporary frames on failure. Cut percentages measure completed cuts,
rather than estimated run time.

Narration JSON uses the existing generator's format:

```json
{
  "title": "My Video",
  "voice": "am_michael",
  "speed": 0.94,
  "cuts": [
    {"id": "cut01", "start": 0, "duration": 4, "text": "Your narration here."},
    {"id": "cut02", "start": 4, "duration": 6, "text": "The next scene."}
  ]
}
```

`voice` and `speed` are optional (defaults `am_michael` and `0.94`). Cuts must
have unique safe IDs, nonempty text, finite nonnegative start times, positive
durations, and no overlaps. Times are seconds. This accepts narration scripts,
not the separate Gym Zoo audio transformation segment format.

Audio includes individual raw/cinematic WAVs, `timing_report.json`, and the existing
generator's `full_35s_timeline.wav` (the filename is fixed; actual duration follows
the cuts). Narration longer than its slot is truncated in the combined timeline;
review the timing report. This workflow does not produce the scenes themselves.

Run workflow checks without downloading models:

```bash
python3 -m unittest discover -s ai-video-flow -p 'test_*.py'
```
