#!/usr/bin/env python3
"""Create a deterministic public installer archive."""
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    output = ROOT / 'dist/marathon-skill.zip'
    output.parent.mkdir(exist_ok=True)
    files = []
    for name in ('skill', 'install', 'README.md', 'README.zh-CN.md', 'LICENSE'):
        path = ROOT / name
        if not path.exists(): raise SystemExit('Missing package input: ' + name)
        files += list(path.rglob('*')) if path.is_dir() else [path]
    temporary = output.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(files):
                if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc': continue
                info = zipfile.ZipInfo('marathon/' + path.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (0o100755 if path.suffix == '.sh' else 0o100644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
            # One-click launchers at the top of the unzipped folder: double-click install.cmd, or run sh install.sh
            launchers = {'install.cmd': (b'@echo off\r\ncall "%~dp0install\\install.cmd" %*\r\n', 0o100644),
                         'install.sh': (b'#!/bin/sh\nexec sh "$(dirname "$0")/install/install.sh" "$@"\n', 0o100755)}
            for name, (data, mode) in launchers.items():
                info = zipfile.ZipInfo('marathon/' + name, (2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = mode << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(str(output))
    print('bytes:', output.stat().st_size)
    print('sha256:', hashlib.sha256(output.read_bytes()).hexdigest())

if __name__ == '__main__': main()
