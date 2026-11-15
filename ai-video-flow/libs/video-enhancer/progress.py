#!/usr/bin/env python3
"""Run an enhancement stage with one progress line and a retained diagnostic log."""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--total', default='unknown')
    parser.add_argument('--frames-dir', type=Path)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    total = int(args.total) if args.total.isdigit() and int(args.total) > 0 else None
    started = time.monotonic()
    previous = None
    with args.log.open('wb') as output, args.log.open('rb') as reader:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        try:
            while True:
                status = process.poll()
                if args.frames_dir:
                    done = sum(1 for _ in args.frames_dir.glob('*.png'))
                else:
                    reader.seek(max(0, args.log.stat().st_size - 8192))
                    matches = re.findall(rb'(?:^|\n)frame=\s*(\d+)', reader.read())
                    done = int(matches[-1]) if matches else 0
                percent = 100 if status == 0 else min(99, int(done * 100 / total)) if total else None
                value = f'{percent:3d}%' if percent is not None else f'{done} frames'
                line = f'{args.label}: {value} ({time.monotonic() - started:.0f}s)'
                if sys.stdout.isatty():
                    print('\r' + line + '    ', end='', flush=True)
                elif (percent if percent is not None else done) != previous:
                    print(line, flush=True)
                previous = percent if percent is not None else done
                if status is not None:
                    break
                time.sleep(0.5)
        except BaseException:
            process.terminate()
            process.wait()
            raise
        finally:
            if sys.stdout.isatty():
                print(flush=True)
        if status:
            print(f'{args.label} failed. Diagnostic log: {args.log}', file=sys.stderr)
            reader.seek(max(0, args.log.stat().st_size - 4096))
            print(reader.read().decode(errors='replace'), file=sys.stderr)
        return status if status >= 0 else 128 - status


if __name__ == '__main__':
    sys.exit(main())
