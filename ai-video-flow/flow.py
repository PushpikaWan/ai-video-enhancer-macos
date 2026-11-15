#!/usr/bin/env python3
"""Interactive macOS video workflow; no third-party UI dependencies."""
import json
import math
import re
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIBS = ROOT / 'libs'
VOICE_GENERATOR = LIBS / 'voice-generator-from-script' / 'generate.py'
VIDEO_ENHANCER = LIBS / 'video-enhancer' / 'video-enhance-universal.sh'
STATE = ROOT / '.state' / 'projects.json'


def log(message):
    print(f'[{datetime.now():%H:%M:%S}] {message}', flush=True)


@contextmanager
def activity(label):
    """Keep long external commands visibly active without inventing percentages."""
    started = time.monotonic()
    stopped = threading.Event()
    def heartbeat():
        while not stopped.wait(10):
            log(f'{label}: still running ({time.monotonic() - started:.0f}s elapsed)')
    log(f'{label}: starting')
    worker = threading.Thread(target=heartbeat, daemon=True)
    worker.start()
    try:
        yield
    except BaseException:
        log(f'{label}: failed or interrupted after {time.monotonic() - started:.1f}s')
        raise
    else:
        log(f'{label}: complete ({time.monotonic() - started:.1f}s)')
    finally:
        stopped.set()
        worker.join()


def browse(prompt, folder=False):
    # Pass prompts as argv, never interpolate paths into AppleScript or a shell.
    kind = 'folder' if folder else 'file'
    script = f'''on run argv
try
return POSIX path of (choose {kind} with prompt (item 1 of argv))
on error number -128
return ""
end try
end run'''
    log(f'Opening Finder selection: {prompt}')
    result = subprocess.run(['osascript', '-e', script, prompt], text=True,
                            capture_output=True, check=True)
    value = result.stdout.rstrip('\n')
    log(f'Selected: {value}' if value else 'Selection canceled')
    return Path(value).resolve() if value else None


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def remember(project):
    paths = read_json(STATE) if STATE.exists() else []
    write_json(STATE, [str(project)] + [p for p in paths if p != str(project)])


def valid_name(value):
    return bool(value and value not in ('.', '..') and
                not any(c in value for c in '/\\\0') and
                all(ord(c) >= 32 for c in value))


def new_project():
    name = input('Video name (blank cancels): ').strip()
    if not name:
        return None
    if not valid_name(name):
        raise ValueError('Use a video name without slashes or control characters.')
    parent = browse('Choose where to create your video project', folder=True)
    if parent is None:
        return None
    project = parent / name
    log(f'Creating project folders: {project}')
    project.mkdir()  # Never silently reuse an existing folder.
    for folder in ('frames', 'audio', 'scripts', 'enhanced'):
        (project / folder).mkdir()
    write_json(project / 'project.json', {'name': name, 'created': datetime.now().isoformat()})
    remember(project)
    log('Project created and saved to recent projects')
    return project


def existing_project():
    paths = read_json(STATE) if STATE.exists() else []
    projects = [Path(p) for p in paths if (Path(p) / 'project.json').is_file()]
    for index, path in enumerate(projects, 1):
        print(f'{index}. {path.name} — {path}')
    print('b. Browse for an existing project folder\n0. Back')
    choice = input('Project: ').strip().lower()
    if choice == '0':
        return None
    if choice == 'b':
        project = browse('Choose an ai-video-flow project folder', folder=True)
        if project is None:
            return None
    elif choice.isdigit() and 1 <= int(choice) <= len(projects):
        project = projects[int(choice) - 1]
    else:
        raise ValueError('Choose a listed project or browse.')
    log(f'Loading project: {project}')
    metadata = read_json(project / 'project.json')
    if not isinstance(metadata, dict) or not isinstance(metadata.get('name'), str):
        raise ValueError('Folder does not contain a valid project.json.')
    for folder in ('frames', 'audio', 'scripts', 'enhanced'):
        (project / folder).mkdir(exist_ok=True)
    remember(project)
    log('Project ready')
    return project


def validate_script(config):
    if not isinstance(config, dict):
        raise ValueError('Narration JSON must be an object with a cuts list.')
    if 'voice' in config and (not isinstance(config['voice'], str) or not config['voice'].strip()):
        raise ValueError('voice must be a nonempty Kokoro voice name.')
    def number(value, field, positive=False):
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or (value <= 0 if positive else value < 0)):
            raise ValueError(f'{field} must be a finite {"positive" if positive else "nonnegative"} number.')
    number(config.get('speed', 0.94), 'speed', positive=True)
    cuts = config.get('cuts')
    if not isinstance(cuts, list) or not cuts:
        raise ValueError('cuts must be a nonempty list.')
    names, intervals = set(), []
    for index, cut in enumerate(cuts, 1):
        if not isinstance(cut, dict):
            raise ValueError(f'Cut {index} must be an object.')
        name = cut.get('id')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', name):
            raise ValueError(f'Cut {index}: id must contain letters, numbers, underscores or hyphens.')
        if name in names:
            raise ValueError(f'Duplicate cut id: {name}')
        names.add(name)
        if not isinstance(cut.get('text'), str) or not cut['text'].strip():
            raise ValueError(f'{name}: text must be nonempty.')
        number(cut.get('start'), f'{name}.start')
        number(cut.get('duration'), f'{name}.duration', positive=True)
        end = cut['start'] + cut['duration']
        number(end, f'{name}.end', positive=True)
        intervals.append((cut['start'], end))
    intervals.sort()
    if any(b[0] < a[1] for a, b in zip(intervals, intervals[1:])):
        raise ValueError('Cut time ranges must not overlap.')
    return config


def unique_path(parent, name):
    path = parent / name
    index = 2
    while path.exists():
        path = parent / f'{Path(name).stem}_{index}{Path(name).suffix}'
        index += 1
    return path


def last_frame(project):
    video = browse('Choose a video to extract its last frame')
    if video is None:
        return
    output = project / 'frames' / f'{video.stem}_lastframe.png'
    if output.exists() and input(f'{output.name} exists. Overwrite? [y/N]: ').lower() != 'y':
        return
    with activity('Extracting last frame'):
        subprocess.run(['ffmpeg', '-sseof', '-0.5', '-i', str(video),
                        '-update', '1', '-y', str(output)], check=True)
        log('Checking extracted image')
        if not output.is_file() or not output.stat().st_size:
            raise ValueError('FFmpeg did not produce an image. The video may be too short or contain no video stream.')
    print(f'Created: {output}')


def paste_script(saved):
    print('Paste your JSON object (multiple lines are supported).')
    print('Type END on a separate line to save, or CANCEL to cancel.')
    lines = []
    while True:
        line = input()
        if line.strip() == 'CANCEL':
            log('JSON entry canceled; saved scripts unchanged')
            return False
        if line.strip() == 'END':
            break
        lines.append(line)
    log('Validating pasted JSON and narration fields')
    config = validate_script(json.loads('\n'.join(lines)))
    # Validate before replacing an existing script so invalid edits preserve it.
    log(f'Saving narration script: {saved}')
    write_json(saved, config)
    print(f'Saved valid narration ({len(config["cuts"])} cuts): {saved}')
    return True


def run_audio(project, saved):
    log(f'Validating saved narration: {saved.name}')
    validate_script(read_json(saved))
    output = unique_path(project / 'audio', saved.stem)
    log(f'Audio output folder: {output}')
    with activity('Generating narration audio'):
        subprocess.run([sys.executable, '-u', str(VOICE_GENERATOR),
                        '--script', str(saved), '--output', str(output)], check=True)
    print(f'Audio saved: {output}')


def generate_audio(project):
    scripts_dir = project / 'scripts'
    scripts_dir.mkdir(exist_ok=True)
    while True:
        scripts = sorted(scripts_dir.glob('*.json'))
        print('\nSaved narration scripts:')
        if not scripts:
            print('No saved scripts yet.')
        for index, script in enumerate(scripts, 1):
            print(f'{index}. {script.name}')
        print('n. Paste a new JSON script\n0. Back')
        # Go straight to pasting on the first visit when no script exists.
        choice = input('Choose a script: ').strip().lower() if scripts else 'n'
        if choice == '0':
            return
        try:
            if choice == 'n':
                saved = unique_path(scripts_dir, 'narration.json')
                if not paste_script(saved):
                    return
            elif choice.isdigit() and 1 <= int(choice) <= len(scripts):
                saved = scripts[int(choice) - 1]
            else:
                print('Choose a saved script or n to paste a new one.')
                continue
            while True:
                print(f'\nScript: {saved.name}')
                print('1. Generate audio\n2. View / edit JSON\n0. Back')
                action = input('Choose: ').strip()
                if action == '0':
                    break
                if action == '1':
                    run_audio(project, saved)
                    return
                if action == '2':
                    print(saved.read_text(encoding='utf-8'))
                    if input('Paste replacement JSON to edit? [y/N]: ').strip().lower() == 'y':
                        try:
                            paste_script(saved)
                        except ValueError as error:
                            print(f'Invalid JSON; saved script unchanged: {error}')
                else:
                    print('Choose one of the listed options.')
        except ValueError as error:
            print(f'Invalid narration JSON: {error}')


def enhance(project):
    video = browse('Choose the finished video to enhance')
    if video is None:
        return
    output = unique_path(project / 'enhanced', f'{video.stem}-AI-2x.mp4')
    log(f'Enhancement output: {output}')
    with activity('Enhancing video'):
        subprocess.run(['bash', str(VIDEO_ENHANCER),
                        str(video), str(output)], check=True)
    print(f'Enhanced video: {output}')


def project_menu(project):
    while True:
        print(f'\nProject: {project.name}\n{project}')
        print('1. Get last frame from video\n2. Generate audio from narration JSON\n3. Enhance finished video\n4. Open project in Finder\n0. Back to projects')
        choice = input('Choose: ').strip()
        if choice == '0':
            return
        try:
            if choice == '1':
                last_frame(project)
            elif choice == '2':
                generate_audio(project)
            elif choice == '3':
                enhance(project)
            elif choice == '4':
                with activity('Opening project in Finder'):
                    subprocess.run(['open', str(project)], check=True)
            else:
                print('Choose one of the listed options.')
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print(f'Action failed: {error}')


def main():
    while True:
        print('\nAI Video Flow\n1. Continue an existing video project\n2. Create a new video project\n0. Quit')
        choice = input('Choose: ').strip()
        if choice == '0':
            return
        try:
            if choice not in ('1', '2'):
                print('Choose one of the listed options.')
                continue
            project = existing_project() if choice == '1' else new_project()
            if project:
                project_menu(project)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print(f'Could not open project: {error}')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nGoodbye.')
