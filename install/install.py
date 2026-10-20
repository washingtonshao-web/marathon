#!/usr/bin/env python3
"""Install only the Marathon skill; shared by the native launchers."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
import uuid


def remove_hook(home):
    settings = home / '.claude/settings.json'
    if not settings.exists(): return
    before = settings.read_text(encoding='utf-8-sig')
    data = json.loads(before)
    stop = data.get('hooks', {}).get('Stop', [])
    kept = []
    for entry in stop:
        hooks = entry.get('hooks', [])
        remaining = [h for h in hooks if 'marathon/scripts/stop_hook.py' not in h.get('command', '').replace('\\', '/')]
        if remaining or not hooks: kept.append(dict(entry, hooks=remaining) if hooks else entry)
    if kept == stop: return
    if kept: data['hooks']['Stop'] = kept
    else: data['hooks'].pop('Stop', None)
    temporary = settings.with_name('.marathon-settings-' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if settings.read_text(encoding='utf-8-sig') != before:
            raise SystemExit('settings.json changed during uninstall; rerun uninstall to remove its Marathon hook.')
        temporary.replace(settings)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10 or newer is required: https://www.python.org/downloads/')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--uninstall', action='store_true')
    a = ap.parse_args()
    source = Path(__file__).resolve().parents[1] / 'skill/marathon'
    home = Path(os.environ.get('HOME') or os.environ.get('USERPROFILE') or Path.home()).expanduser().resolve()
    if a.uninstall: remove_hook(home)
    roots = []
    if (home / '.claude').is_dir(): roots.append(home / '.claude')
    codex = Path(os.environ.get('CODEX_HOME') or home / '.codex').expanduser().resolve()
    if os.environ.get('CODEX_HOME') or codex.is_dir(): roots.append(codex)
    if not roots:
        roots = [home / '.claude']
        print('Neither Claude Code nor Codex configuration was found; installing for Claude Code.')
    roots = list(dict.fromkeys(roots))
    for root in roots:
        parent = root / 'skills'
        target = parent / 'marathon'
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise SystemExit('Refusing non-directory or linked target: ' + str(target))
        backup_root = root / 'marathon-backups'
        backups = sorted(backup_root.glob('marathon-*')) if backup_root.exists() else []
        if any(p.is_symlink() or not p.is_dir() for p in backups):
            raise SystemExit('Refusing linked or non-directory backup')
        if a.uninstall:
            if target.exists(): shutil.rmtree(target)
            if backups:
                parent.mkdir(parents=True, exist_ok=True)
                backups[-1].rename(target)
                print('Restored ' + str(target))
            else: print('Removed ' + str(target))
            continue
        if not (source / 'SKILL.md').is_file(): raise SystemExit('Missing skill/marathon/SKILL.md; unzip the whole package first.')
        parent.mkdir(parents=True, exist_ok=True)
        backup_root.mkdir(parents=True, exist_ok=True)
        staging = backup_root / ('.marathon-install-' + uuid.uuid4().hex[:12])
        backup = None
        try:
            shutil.copytree(source, staging, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            if target.exists():
                stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
                backup = backup_root / ('marathon-' + stamp)
                target.rename(backup)
                print('Backed up ' + str(backup))
            staging.rename(target)
        except BaseException:
            if backup and backup.exists() and not target.exists(): backup.rename(target)
            raise
        finally:
            if staging.exists(): shutil.rmtree(staging)
        print('Installed ' + str(target))
    if not a.uninstall: print('In Claude Code or Codex, say: use marathon to build ...')

if __name__ == '__main__':
    main()
