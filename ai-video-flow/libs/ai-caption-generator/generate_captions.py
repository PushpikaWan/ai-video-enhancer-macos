#!/usr/bin/env python3
"""Local Apple Silicon transcription and word-timed SRT captions."""
import argparse
import hashlib
import json
import math
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULTS = dict(max_chars=22, max_words=4, max_lines=1, max_duration=2.5,
                min_duration=0.5, pause=0.5, uppercase=False,
                remove_punctuation=False, language='en', offset=0,
                model='mlx-community/whisper-large-v3-turbo')


def log(message):
    print(f'[{datetime.now():%H:%M:%S}] {message}', flush=True)


def language(value):
    value = value.strip().lower()
    return {'english': 'en', 'sinhala': 'si', 'sinhalese': 'si',
            'auto': None}.get(value, value)


def validate_settings(settings):
    unknown = settings.keys() - DEFAULTS.keys()
    if unknown:
        raise ValueError(f'Unknown caption settings: {", ".join(sorted(unknown))}')
    config = {**DEFAULTS, **settings}
    for key in ('max_chars', 'max_words', 'max_lines'):
        if type(config[key]) is not int or config[key] < 1:
            raise ValueError(f'{key} must be a positive integer')
    for key in ('max_duration', 'min_duration', 'pause', 'offset'):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{key} must be a finite number')
        if key != 'offset' and (value < 0 or (key == 'max_duration' and value == 0)):
            raise ValueError(f'{key} must be {"positive" if key == "max_duration" else "nonnegative"}')
    for key in ('uppercase', 'remove_punctuation'):
        if type(config[key]) is not bool:
            raise ValueError(f'{key} must be true or false')
    for key in ('language', 'model'):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f'{key} must be a nonempty string')
    config['language'] = language(config['language']) or 'auto'
    return config


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     suffix='.tmp', delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False, indent=2,
                      default=lambda v: v.item())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    temp.replace(path)


def cache_identity(source, model, requested_language):
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    metadata = dict(version=1, source_sha256=digest.hexdigest(), model=model,
                    language=language(requested_language))
    key = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    return key, metadata


def transcribe(source, config):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('Transcription requires native ARM64 Python on an Apple Silicon Mac.')
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg is missing. Install it or add your existing FFmpeg to PATH.')
    log('Initializing MLX Whisper runtime (the first import can take a little longer)')
    try:
        import mlx.core as mx
        import mlx_whisper
        from mlx_whisper.tokenizer import LANGUAGES
    except ImportError as error:
        raise RuntimeError('Activate ai-caption-generator and install environment.yml dependencies.') from error
    if not mx.metal.is_available():
        raise RuntimeError('MLX Metal GPU is unavailable. Run natively on Apple Silicon, outside Rosetta.')
    requested_language = language(config['language'])
    if requested_language is not None and requested_language not in LANGUAGES:
        raise ValueError('Unsupported language. Use en/English, si/Sinhala, auto, or a Whisper language code.')
    mx.set_default_device(mx.gpu)
    log('MLX Metal GPU ready')
    with tempfile.TemporaryDirectory(prefix='ai-captions-') as folder:
        audio = Path(folder) / 'audio.wav'
        log('Extracting mono 16 kHz audio with FFmpeg (source stays unchanged)')
        result = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                                 '-i', str(source), '-map', '0:a:0', '-vn', '-ac', '1',
                                 '-ar', '16000', '-c:a', 'pcm_s16le', str(audio)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f'Audio extraction failed: {result.stderr.strip()}')
        log(f'Loading {config["model"]}; first use downloads and caches model weights')
        log('Transcribing on the Metal GPU with word timestamps; progress follows after model loading')
        return mlx_whisper.transcribe(str(audio), path_or_hf_repo=config['model'],
                                      language=requested_language, task='transcribe',
                                      word_timestamps=True, verbose=False)


def get_transcription(source, config, force=False, cache_dir=None):
    log('Checking input fingerprint and transcription cache')
    key, metadata = cache_identity(source, config['model'], config['language'])
    path = (cache_dir or ROOT / 'cache') / f'{key}.json'
    if path.exists() and not force:
        try:
            cached = json.loads(path.read_text(encoding='utf-8'))
            if cached['identity'] == metadata and isinstance(cached['transcription']['segments'], list):
                log(f'Reusing cached transcription: {path.name}')
                return cached['transcription']
        except (ValueError, KeyError, TypeError):
            log('Cache is invalid; transcribing again')
    result = transcribe(source, config)
    atomic_json(path, dict(identity=metadata, source=str(source), transcription=result))
    log(f'Saved raw transcription and word timestamps: {path}')
    return result


def timed_words(result):
    words = []
    cursor = 0.0
    for segment in result.get('segments', []):
        if segment.get('text', '').strip() and not segment.get('words'):
            raise ValueError('Transcription lacks word timestamps. Rerun with --force-transcribe.')
        for word in segment.get('words', []):
            text = word['word'].strip()
            start, end = float(word['start']), float(word['end'])
            if not math.isfinite(start) or not math.isfinite(end) or end < start:
                raise ValueError('Transcription contains invalid word timestamps.')
            if not text:
                continue
            # Correct timestamp overlaps without moving subsequent speech earlier.
            start = max(0.0, cursor, start)
            end = max(start, end)
            if end <= start:
                # Punctuation tokens often have zero duration; attach them to speech.
                if words and all(unicodedata.category(c).startswith('P') for c in text):
                    words[-1]['text'] += text
                    continue
                end = start + 0.001
            words.append(dict(text=text, start=start, end=end))
            cursor = end
    return words


def display_text(text, config):
    if config['remove_punctuation']:
        text = ''.join(c for c in text if not unicodedata.category(c).startswith('P'))
    return text.upper() if config['uppercase'] else text


def wrap_caption(text, max_lines):
    if max_lines == 1:
        return text
    width = max(max(map(len, text.split())), math.ceil(len(text) / max_lines))
    while True:
        lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
        if len(lines) <= max_lines:
            return '\n'.join(lines)
        width += 1


def group_captions(words, config):
    groups, current = [], []
    sentence_end = re.compile(r'[.!?…।෴][\"\u201d\u2019\u0027)]*$')
    for word in words:
        text = display_text(word['text'], config)
        if not text.strip():
            continue
        item = {**word, 'display': text}
        candidate = current + [item]
        if current and (
                sum(len(w['display'].split()) for w in candidate) > config['max_words'] or
                len(' '.join(w['display'] for w in candidate)) > config['max_chars'] or
                word['end'] - current[0]['start'] > config['max_duration'] or
                word['start'] - current[-1]['end'] > config['pause']):
            groups.append(current)
            current = []
        current.append(item)
        if sentence_end.search(word['text']):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    captions = []
    previous_end = 0
    for index, group in enumerate(groups):
        start, end = group[0]['start'], group[-1]['end']
        next_start = groups[index + 1][0]['start'] if index + 1 < len(groups) else math.inf
        # Minimum duration is a preference; never extend into the next caption.
        end = max(end, min(start + config['min_duration'], next_start,
                           start + config['max_duration']))
        start_ms = round(start * 1000 + config['offset'])
        end_ms = round(end * 1000 + config['offset'])
        if end_ms <= 0:
            continue
        start_ms = max(0, previous_end, start_ms)
        end_ms = max(start_ms + 1, end_ms)
        captions.append(dict(start=start_ms, end=end_ms, text=wrap_caption(
            ' '.join(w['display'] for w in group), config['max_lines'])))
        previous_end = end_ms
    return captions


def timestamp(milliseconds):
    hours, remainder = divmod(max(0, int(milliseconds)), 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{millis:03}'


def srt_text(captions):
    return ''.join(f'{i}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["text"]}\n\n'
                   for i, c in enumerate(captions, 1))


def arguments():
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument('--config', type=Path)
    known, _ = pre.parse_known_args()
    defaults = DEFAULTS
    if known.config:
        data = json.loads(known.config.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Caption config must be a JSON object')
        defaults = validate_settings(data)
    parser = argparse.ArgumentParser(description=__doc__, parents=[pre])
    parser.add_argument('input', type=Path)
    for name in ('max_chars', 'max_words', 'max_lines'):
        parser.add_argument('--' + name.replace('_', '-'), type=int, default=defaults[name])
    for name in ('max_duration', 'min_duration', 'pause', 'offset'):
        parser.add_argument('--' + name.replace('_', '-'), type=float, default=defaults[name])
    for name in ('uppercase', 'remove_punctuation'):
        parser.add_argument('--' + name.replace('_', '-'), action=argparse.BooleanOptionalAction,
                            default=defaults[name])
    for name in ('language', 'model'):
        parser.add_argument('--' + name, default=defaults[name])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--force-transcribe', action='store_true')
    return parser.parse_args()


def main():
    args = arguments()
    config = validate_settings({key: getattr(args, key) for key in DEFAULTS})
    source = args.input.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {'.wav', '.mp3', '.m4a', '.mp4', '.mov'}:
        raise ValueError('Choose an existing WAV, MP3, M4A, MP4, or MOV file')
    output = args.output.expanduser().resolve() if args.output else source.with_suffix('.srt')
    if (output.suffix.lower() != '.srt' or output == source or
            (output.exists() and output.samefile(source))):
        raise ValueError('Output must be a separate .srt file')
    result = get_transcription(source, config, args.force_transcribe)
    log('Grouping word timestamps into captions')
    captions = group_captions(timed_words(result), config)
    if not captions:
        raise ValueError('No speech captions found; no SRT was written')
    output.parent.mkdir(parents=True, exist_ok=True)
    # A custom output symlink must never overwrite the input (resolve above).
    output.write_text(srt_text(captions), encoding='utf-8')
    log(f'Complete: {len(captions)} captions saved to {output}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCaption generation canceled.', file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print(f'Caption generation failed: {error}', file=sys.stderr)
        sys.exit(1)
