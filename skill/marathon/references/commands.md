# CLI and maintenance

Use `python <installed-skill>/scripts/marathon.py -h` and subcommand -h; never live launches for syntax checks.

status is compact; --full expands, --report includes archived history. Directory-free status lists projects (--days/--json/--sessions/--widget/--markdown). usage defaults to totals; --full/--by-role expand. Worker list: `marathon.py worker list <dir>` or `worker <dir>` without ID. log keeps stdin -, --lead, --at.

## Compatibility aliases (listed once)

| Old | Current |
|---|---|
| overview | status without directory |
| report <dir> | status <dir> --report |
| set-status <dir> S | set <dir> --status S (keep --reason) |
| gate-wait <dir> | wait <dir> --gate |
| workers <dir> | worker <dir> (no ID) |
| handoff-abort <dir> | handoff <dir> --abort |
| logins URLs | preflight --logins URLs |
| models [dir] | config [dir] --models |

Aliases preserve flags/side effects. Score compatibility spellings: --astra-pending/--late (partial-then-merge), --carry-forward/--reuse-round (carry), --missing-reason (final fallback), --adjudication. No --partial/--carry flags exist.

## Checks/budget

Run each scripts/test_*.py and tools/test_package.py. Fake network/models; isolate MARATHON_CLAUDE_HOME, MARATHON_REPOS_ROOT and MARATHON_OVERVIEW_GLOBS in your project. Use your own sync workflow.

Python text-mode characters: SKILL + workers + gate + intake + references/{commands,profiles,adjudication,rotation,codex-workers}.md + chosen mode card ≤25,000 (Claude lead); add references/codex.md ≤29,000 (Codex lead). Count either card; do not relocate required reading. lessons.md ≤3,000; archive not read by default.
