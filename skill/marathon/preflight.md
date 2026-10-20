# Preflight

Run `marathon.py preflight --type game|site|research`. It checks Python, Git, optional Node/gh, Codex discovery, optional Playwright/Pillow, browser availability and disk space. Missing optional tools are inventory findings, not permission to install paid services. init accepts any project directory. MARATHON_REPOS_ROOT is an optional overview scan root; without it status scans ~/repos and the current folder's parent (immediate children), plus registered projects.

Claude: claim or set --status running registers the current session and installs the Stop hook when needed; leaving running removes its registration. waiting_on permits stopping for up to 90 minutes, evaluated on Stop; it is not a wake timer. Codex follows references/codex.md.

Probe only capabilities the project needs, bounded to three minutes: a model reply, a generated image, or your deploy command's dry run. A blocked probe is not checked. Never launch a full gate as a probe.

Acquire `marathon.py lock <dir> browser --owner <id>` before browser access; close/release afterward. `preflight --logins <url> ...` opens a configured Chrome profile only with user authorization. The user enters credentials. Reuse authenticated background requests and verify access afterward. Login/password/CAPTCHA decisions are must-decide questions under intake.md; continue other work while parked.
