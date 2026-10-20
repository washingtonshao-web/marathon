"""Offline packaging and native installer integration tests; never use the real home."""
import ast
import hashlib
import json
import zipfile
import importlib.util
from unittest.mock import patch
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / '.tmp'
SCRATCH.mkdir(exist_ok=True)

class PackageTests(unittest.TestCase):
    def test_python310_syntax(self):
        for p in (ROOT / 'skill').rglob('*.py'):
            ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p), feature_version=(3, 10))

    def test_installers(self):
        launchers = []
        if os.name == 'nt':
            launchers += [('powershell', ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'install/install.ps1')], '-Uninstall')]
        bash = shutil.which('bash') or shutil.which('sh')
        if bash:
            script = (ROOT / 'install/install.sh').as_posix()
            if os.name == 'nt': script = '/' + script[0].lower() + script[2:]
            launchers += [('shell', [bash, script], '--uninstall')]
        self.assertTrue(launchers, 'No native installer runner')
        for name, command, uninstall in launchers:
            for scenario in ('neither', 'both', 'codex-custom'):
                with self.subTest(launcher=name, scenario=scenario), tempfile.TemporaryDirectory(dir=SCRATCH) as td:
                    home = Path(td) / 'home with spaces'; home.mkdir()
                    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONDONTWRITEBYTECODE='1')
                    env.pop('CODEX_HOME', None)
                    env.pop('PYTHONUTF8', None)
                    targets = [home / '.claude/skills/marathon']
                    if scenario == 'both':
                        (home / '.claude').mkdir(); (home / '.codex').mkdir()
                        targets.append(home / '.codex/skills/marathon')
                    if scenario == 'codex-custom':
                        env['CODEX_HOME'] = str(home / 'custom codex')
                        targets = [home / 'custom codex/skills/marathon']
                    def run(*flags):
                        result = subprocess.run([*command, *flags], env=env, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
                        self.assertEqual(0, result.returncode, (result.stdout + result.stderr).decode('utf-8', 'replace'))
                        return result.stdout.decode('utf-8', 'replace')
                    self.assertIn('use marathon to build', run())
                    for target in targets:
                        self.assertTrue((target / 'SKILL.md').is_file())
                        (target / 'user-marker').write_text('old skill', encoding='utf-8')
                        (target.parent / 'other-skill').mkdir()
                    run()
                    for target in targets:
                        self.assertFalse((target / 'user-marker').exists())
                        self.assertEqual(1, len(list((target.parent.parent / 'marathon-backups').glob('marathon-*'))))
                        self.assertEqual(['marathon', 'other-skill'], sorted(p.name for p in target.parent.iterdir()))
                    settings = home / '.claude/settings.json'
                    settings.parent.mkdir(parents=True, exist_ok=True)
                    other = {'type': 'command', 'command': 'echo keep'}
                    settings.write_text(json.dumps({'custom': 7, 'hooks': {'Other': [], 'Stop': [{'matcher': 'keep', 'hooks': [other, {'command': 'python "~/.claude/skills/marathon/scripts/stop_hook.py"'}]}, {'hooks': [{'command': '"C:/Python/python.exe" "C:/home/.claude/skills/marathon/scripts/stop_hook.py"'}]}]}}), encoding='utf-8')
                    run(uninstall)
                    data = json.loads(settings.read_text(encoding='utf-8'))
                    self.assertEqual({'custom': 7, 'hooks': {'Other': [], 'Stop': [{'matcher': 'keep', 'hooks': [other]}]}}, data)
                    before_settings = settings.read_bytes()
                    for target in targets:
                        self.assertEqual('old skill', (target / 'user-marker').read_text(encoding='utf-8'))
                        self.assertTrue((target.parent / 'other-skill').is_dir())
                    run(uninstall)
                    self.assertEqual(before_settings, settings.read_bytes())
                    for target in targets:
                        self.assertFalse(target.exists())
                        self.assertTrue((target.parent / 'other-skill').is_dir())
                    print('PASS', name, scenario, 'install/reinstall/restore/remove')

    def test_documented_commands(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td); project = root / 'repos/project'
            env = dict(os.environ, MARATHON_CLAUDE_HOME=str(root / 'home'), MARATHON_REPOS_ROOT=str(root / 'repos'), MARATHON_OVERVIEW_GLOBS=str(root / 'repos/*/STATE.md'), PYTHONIOENCODING='utf-8')
            env.pop('CLAUDE_CODE_SESSION_ID', None)
            env.pop('MARATHON_API_KEY', None); env.pop('MARATHON_API_BASE_URL', None)
            cli = [sys.executable, str(ROOT / 'skill/marathon/scripts/marathon.py')]
            for args in (['init', str(project), '--type', 'site', '--title', 'public'], ['status', str(project)], ['status', str(project), '--full'], ['status', str(project), '--report', '--no-live'], ['status'], ['config', str(project)], ['config', str(project), '--models'], ['set', str(project), 'workers=astra'], ['set', str(project), 'profile=claude'], ['set', str(project), 'gate=sonnet+astra'], ['set', str(project), '--status', 'paused', '--reason', 'package test'], ['usage', str(project)], ['worker', 'list', str(project)], ['ask', str(project), '--status']):
                result = subprocess.run(cli + args, env=env, capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
                self.assertEqual(0, result.returncode, (args, result.stdout, result.stderr))

    def test_public_defaults(self):
        module_path = ROOT / 'skill/marathon/scripts/marathon.py'
        spec = importlib.util.spec_from_file_location('public_marathon', module_path)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td); current = root / 'elsewhere/current'; current.mkdir(parents=True)
            env = dict(os.environ, MARATHON_CLAUDE_HOME=str(root / 'claude'))
            for key in ('MARATHON_REPOS_ROOT', 'MARATHON_OVERVIEW_GLOBS', 'CLAUDE_CODE_SESSION_ID'):
                env.pop(key, None)
            with patch.dict(os.environ, env, clear=True), patch('pathlib.Path.home', return_value=root), patch('pathlib.Path.cwd', return_value=current):
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                expected = [str(root / 'repos/*/STATE.md'), str(current.parent / '*/STATE.md')]
                self.assertEqual(expected, module.project_globs())
                self.assertIn('Run config · Codex workers', '\n'.join(module.run_config({'profile': 'codex'})))
                self.assertEqual(['Classic', 'All Claude', 'Codex workers'], [p['name'] for p in module.PROFILES.values()])
            with patch.dict(os.environ, dict(env, MARATHON_REPOS_ROOT=str(root / 'collection')), clear=True):
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                self.assertEqual([str(root / 'collection/*/STATE.md')], module.project_globs())
            result = subprocess.run([sys.executable, str(module_path), 'status', '-h'], env=env, capture_output=True, check=True)
            help_text = result.stdout.decode('utf-8')
            for term in ('immediate child folders', 'MARATHON_REPOS_ROOT', '~/repos', "current folder's parent", 'registered projects', 'MARATHON_OVERVIEW_GLOBS'):
                self.assertIn(term, ' '.join(help_text.split()))
            for name in ('mode-codex.md', 'mode-claude.md'):
                text = (ROOT / 'skill/marathon' / name).read_text(encoding='utf-8')
                self.assertLessEqual(len(text), 1600)
                self.assertIn('balanced 4, efficient 4, fast 10', text)
            self.assertFalse((ROOT / 'skill/marathon/references' / ('tripo-' + 'studio.md')).exists())
            cli = [sys.executable, str(module_path)]
            project = root / 'outside-collection'
            for args in (['init', str(project), '--type', 'research', '--title', 'test'], ['handoff', str(project), '--why', 'test rotation']):
                subprocess.run(cli + args, env=env, capture_output=True, check=True)
            self.assertIn('- Resume prompt: Resume marathon', (project / 'STATE.md').read_text(encoding='utf-8'))
            self.assertEqual(('codex', 'gpt-6.1-sol', 'high'), module.resolve_model('6.1 ' + 'Sonnet'))
            self.assertEqual('claude', module.SPOKEN_PROFILES['全 ' + 'cloud'])

    def test_installed_hook(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            home = Path(td) / 'home with spaces'; home.mkdir()
            (home / '.claude').mkdir()
            env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(home / '.codex'), MARATHON_CLAUDE_HOME=str(home / '.claude'))
            env.pop('CLAUDE_CODE_SESSION_ID', None)
            subprocess.run([sys.executable, str(ROOT / 'install/install.py')], env=env, check=True, capture_output=True)
            script = home / '.codex/skills/marathon/scripts' / 'marathon.py'
            subprocess.run([sys.executable, str(script), 'install-hook'], env=env, check=True, capture_output=True)
            data = json.loads((home / '.claude/settings.json').read_text(encoding='utf-8'))
            command = data['hooks']['Stop'][0]['hooks'][0]['command']
            self.assertTrue(command.startswith('"' + Path(sys.executable).resolve().as_posix() + '" "'))
            self.assertIn('home with spaces', command)
            result = subprocess.run(command, shell=True, input=b'{}', capture_output=True, env=dict(env, PATH=''), timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_newest_backup(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            home = Path(td)
            backups = home / '.claude/marathon-backups'
            for stamp in ('20260101', '20260201'):
                backup = backups / ('marathon-' + stamp); backup.mkdir(parents=True)
                (backup / 'marker').write_text(stamp, encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'install/install.py'), '--uninstall'], env=dict(os.environ, HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(home / '.codex')), capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual('20260201', (home / '.claude/skills/marathon/marker').read_text())
            self.assertTrue((backups / 'marathon-20260101').is_dir())

    def test_missing_python(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            env = dict(os.environ, HOME=td, USERPROFILE=td)
            env.pop('CODEX_HOME', None)
            commands = []
            if os.name == 'nt':
                commands.append(([str(Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'install/install.ps1')], str(Path(td))))
            bash = shutil.which('bash') or shutil.which('sh')
            if bash:
                script = (ROOT / 'install/install.sh').as_posix()
                if os.name == 'nt': script = '/' + script[0].lower() + script[2:]
                # Git Bash's own bin has dirname/sh, and no Python interpreter.
                if os.name == 'nt': commands.append(([bash, script], str(Path(bash).parent)))
            for command, path in commands:
                result = subprocess.run(command, env=dict(env, PATH=path), capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn(b'https://www.python.org/downloads/', result.stdout + result.stderr)
            self.assertFalse((Path(td) / '.claude').exists())

    def test_zip_reproducible(self):
        command = [sys.executable, str(ROOT / 'tools/make_zip.py')]
        subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)
        path = ROOT / 'dist/marathon-skill.zip'
        first = path.read_bytes()
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            self.assertTrue(all(n.startswith('marathon/') for n in names))
            for name in ('install.cmd', 'install.sh', 'install/install.py', 'skill/marathon/SKILL.md'):
                self.assertIn('marathon/' + name, names)
            self.assertIn(b'install\\install.cmd', archive.read('marathon/install.cmd'))
            self.assertIn(b'/install/install.sh', archive.read('marathon/install.sh'))
        subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(hashlib.sha256(first).digest(), hashlib.sha256(path.read_bytes()).digest())

if __name__ == '__main__': unittest.main(verbosity=2)
