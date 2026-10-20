# Intake and questions

Read [profiles](references/profiles.md), chosen mode card and [preflight](preflight.md).

1. Pick repo/slug; `marathon.py init <dir> --type game|site|research --title "..."` starts intake.
2. Log user messages verbatim (--at ISO for older ones). ≤10 minutes on inputs/lessons/tooling; predecessor reuse needs authorization.
3. Run `marathon.py preflight --type <type>`/needed probes. Reuse logins; batch missing access/paid proposals.
4. Send status/config, direct answers, unattended-run explanation and ≤5 unresolved questions through ask. Log with log --lead. If told not to ask, record authorized ordinary defaults and start. Start independent research while waiting.
5. Put resolved choices/assumptions/targets in CHARTER; apply profile/overrides, show config, then `marathon.py set <dir> --status running --reason "intake resolved"`. Research finalizes targets without another approval.

Propose benchmark/scope/budget/output/reuse. Defaults: codex (GPT-6.1-Sol high; Astra optional) or claude (Sonnet), 12 h/balanced, reference-only inputs, output in the user's language; private unless the user asks to publish, no paid tools. Classic unchanged; biology: propose sonnet+astra. ≤5 choices; omit settled ones.

## Ask: intake, phase ends, decision memo

Write a UTF-8 JSON array at <dir>/.tmp/questions.json:

~~~json
[{"id":"mode","text":"Worker mode?","options":["codex","claude"],"default":"codex"}]
~~~

`marathon.py ask <dir> --file <dir>/.tmp/questions.json` accepts ≤5 unique-ID questions, text ≤160 chars, ≤8 options, exact default strings; HTML ≤6,144 bytes. More than 4 options use a select. Show HTML unchanged with show-widget if available, else its text fallback (同意 or 2B). Ordinary defaults are preselected; one Confirm submits all choices.

Login, password, CAPTCHA, payment, public publishing, deletion and more budget/hours require must_decide=true. Their required schema default is never selected/applied. Never store passwords; reuse prior authorization.

Timer: `marathon.py ask <dir> --resolve --at-deadline` polls STATE every 15 s without holding locks while asleep, until answered or expired. Claude: launch with shell `run_in_background=true`; completion wakes the lead. Codex: run foreground only when no useful work remains; otherwise do work, then `marathon.py ask <dir> --status` at the next step and resolve when due. Never end a Codex turn expecting a background wake. On reply run `marathon.py ask <dir> --resolve --answers "<reply>"`. ask_wait defaults to 10 minutes; --wait MIN overrides. A timer is bound to its original set, never a replacement.

At deadline, ordinary defaults apply; unanswered must-decide items become Parked. ask_wait=0 does this immediately. ask records Decisions/clears asking; lead applies choices to CHARTER/config and reconciles replies. Before deadline, partial replies stay WAIT and list unanswered questions; 同意/agree/ok accepts ordinary defaults, with overrides such as 同意 2A. Late replies are recorded for the lead, not applied. Resolve an open set before replacing it. Block only when no independent work remains.
