# Best practices from earlier marathons

Read at kickoff. Keep reusable rules here and project-specific observations in the project; keep this file concise.

- Resume from STATE/CHARTER and the R/Q ledger; keep working, park user-only blockers, ask at decisions, answer directly, keep the link visible. User silent >1 day: status paused.
- Fix benchmark, targets and scope before comparable gates; trust computed scores, not PASS labels. Keep the cross-model final gate, one grader model, a fix wave after round 1. Report added targets apart from the total. Min-merged gates: aim waves at the key under the floor. Reviewers >10 points apart twice: ask the user.
- Judge outcomes, not paperwork: rendered repro per defect; tests use real menus, check amounts, fail on refusals, cover natural phrasing and the first ten minutes. Every bot command needs a UI path. Eval sets: held-out split before the first prompt change.
- Sweep defect classes; rerun affected scenarios after rule changes. Money: reconcile subledgers with the general ledger after a month-end copy.
- Release: prove freshness, bundle identity, bot completion and budgets; build and score each SHA from a clean tree; verify production logged out; never hand over a repair command; recover real source before rebuilding a live tool.
- Workers: bounded, on the worker subscription; lead thin. Reports and evidence in .tmp/reports/ (scratch is deleted), credentials in a fixed folder. Measure usage, look at silent workers every 30 min, steer codex_worker only after it exits, rotate at quiet points.
- Keep the desktop quiet: one browser/perf job at a time, unthrottled, GPU vendor asserted, reruns recorded; rule out Remote Desktop (~30 fps cap) first; settle timed-out jobs. Distant users: measure TCP connect per host before shaving bytes. Check user decisions before changing setup.
- Games: art direction before assets (painted textures plateau; plan illustrated terrain early). Inspect at play distance on rendered frames: pops, brightness, framing, anatomy. Test onboarding with cutscenes, boot-frame time, shader compiles. Ship render-pipeline changes apart from art; reward depth. Sourced start state before balance, persona playtest each fix wave, content frozen before final balance. A path near 0% after two tuning passes is structural: redesign.
- Sites: proven basemaps, frozen coverage samples, random primary-source audits, mobile check after visual changes.
- Research: reconstruct the user's original questions; define each rate, the scope rule and "critical" in the reviewer prompt before gate 1. Deliver numbers, labelled estimates, probabilities and a decision; field terms, glossary, source counts, parameter ledger (recompute dependents).
- Plateau: attack the reviewer's largest gap or stop with options; polish is not evidence. Size a raised pass mark from the planned gain (gates swing ±0.5).
