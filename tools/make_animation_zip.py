#!/usr/bin/env python3
"""Create the animation-making download (dist/animation-making.zip) from the media-pipeline repo.

    python tools/make_animation_zip.py [--repo PATH]   # default: ../media-pipeline next to this repo

Takes only files tracked at HEAD (git archive), so nothing local, generated or secret is packed, and adds one-click
launchers plus a Chinese read-me at the top of the unzipped folder.
"""
import argparse
import hashlib
import io
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = 'animation-making/'
STAMP = (2026, 1, 1, 0, 0, 0)

INSTALL_CMD = r'''@echo off
setlocal
cd /d "%~dp0"
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then double-click install.cmd again.
  pause
  exit /b 1
)
echo Installing the tools: Python packages, ffmpeg, fonts, map data. About 400 MB, several minutes.
%PY% -m mp.setup
%PY% -m mp.setup --skill
echo.
%PY% -m mp.doctor
echo.
echo Finished. Keep this folder where it is: the installed skill points to it.
echo Restart Claude Code or Codex, then say: make an animation about ...
pause
'''.replace('\n', '\r\n')

INSTALL_SH = '''#!/bin/sh
cd "$(dirname "$0")" || exit 1
py=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
        py=$candidate
        break
    fi
done
if [ -z "$py" ]; then
    echo 'Python 3.10 or newer is required: https://www.python.org/downloads/' >&2
    exit 1
fi
echo 'Installing the tools: Python packages, ffmpeg, fonts, map data. About 400 MB, several minutes.'
"$py" -m mp.setup
"$py" -m mp.setup --skill
echo
"$py" -m mp.doctor
echo
echo 'Finished. Keep this folder where it is: the installed skill points to it.'
echo 'Restart Claude Code or Codex, then say: make an animation about ...'
'''

README = '''动画制作（animation-making）安装说明

用一个话题做出 2-5 分钟、带中文解说的 AI 插画纪录短片。适用于 Claude Code 和 OpenAI Codex。
详细介绍：https://marathon.falconshire.com/zh/animation/

一、安装
1. 先把这个文件夹放到一个固定位置（例如“文档”），装好后不要再移动：skill 会指向这里。
2. Windows：双击 install.cmd。macOS / Linux：在这个文件夹里运行 sh install.sh。
   它会安装 Python 包、ffmpeg、字体和历史地图数据（约 400 MB），并把 skill 装进 Claude Code 和 Codex。
3. 最后一屏是体检结果：READY 就可以开始；NOT READY 会逐项写明还缺什么、怎么补。
4. 重启 Claude Code 或 Codex，说：“用动画制作做一部关于 xx 的短片”。

需要 Python 3.10 或更新版本（Windows 安装时勾选 Add python.exe to PATH）。

二、可选账号（缺了也能做，只是降一档）
- 画画：至少需要一个出图渠道。有 ChatGPT 订阅的话，安装 Codex 并登录（codex login），就能免费出图。
- 配音和音效：火山引擎豆包语音密钥，一部 3 分钟的片子约 4 元。没有密钥时自动改用免费的微软 Edge 语音。
- 会动的镜头：Google AI Pro/Ultra 订阅加 flow-video 插件。没有的话改用本地视差或推拉镜头。
- 视差和语音回听质检：python -m mp.setup --depth --asr（约 8 GB，有 NVIDIA 显卡更快）。
每一步怎么开通，见 skill/animation-making/references/first-run.md；也可以直接让 AI 带你一步步做。

三、自检
python tests/e2e_sample.py --engine edge 会做一部 3 个镜头的样片，显示 ALL PASS 就说明装好了。
'''


def add(archive, name, data, mode=0o100644):
    info = zipfile.ZipInfo(TOP + name, STAMP)
    info.create_system = 3
    info.external_attr = mode << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default=str(ROOT.parent / 'media-pipeline'))
    repo = Path(ap.parse_args().repo)
    if not (repo / 'mp' / 'setup.py').is_file():
        raise SystemExit(f'not a media-pipeline checkout: {repo}')
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    tar = subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar', 'HEAD'], capture_output=True, check=True).stdout
    output = ROOT / 'dist' / 'animation-making.zip'
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive, \
                tarfile.open(fileobj=io.BytesIO(tar)) as members:
            for member in sorted((m for m in members.getmembers() if m.isfile()), key=lambda m: m.name):
                mode = 0o100755 if member.name.endswith('.sh') else 0o100644
                add(archive, member.name, members.extractfile(member).read(), mode)
            add(archive, 'install.cmd', INSTALL_CMD.encode('ascii'))
            add(archive, 'install.sh', INSTALL_SH.encode('ascii'), 0o100755)
            add(archive, '安装说明.txt', '﻿'.encode('utf-8') + README.replace('\n', '\r\n').encode('utf-8'))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(str(output))
    print('media-pipeline:', head)
    print('bytes:', output.stat().st_size)
    print('sha256:', hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
