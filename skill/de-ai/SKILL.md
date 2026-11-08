---
name: de-ai
description: "去AI味: on demand, find and rewrite machine-sounding prose (Chinese or English) in a page, site, report, slides, subtitles or narration script so it reads like a colleague wrote it, with before/after numbers. Use only when asked by name or intent: 去AI味, 去 AI 味, AI 味太重, 太像 AI 写的, 说人话, 改成人话, 读起来像机器, humanize, humanizer, de-AI, deslop, ai_tells. Not needed for routine writing; Marathon gates run its script without loading this skill."
---

# 去 AI 味 (de-ai)

The test: **would I say this sentence out loud to a colleague?** Everything below serves it. `scripts/ai_tells.py` measures; `patterns.md` lists the patterns with fixes.

## Mode
- **Check** (检查 / 看看 / 打个分 / 先不要动): measure and report; change no files.
- **Rewrite** (去AI味 / 改 / 做, or text pasted in chat): measure, rewrite, re-measure. Text pasted in chat comes back rewritten in the reply.

## Steps
1. **Measure.** `python <this skill>/scripts/ai_tells.py <page.html | folder | file.md> --examples 5` (narration or subtitles: add `--spoken`; built sites: run it on the output folder). Keep only the summary and the flagged lines; never read whole files just to count.
2. **Read the matching sections of `patterns.md` only** (A: tallies, meta lines, notes, openers, repeats; B: sentence tells; C: wrong shape for the occasion; D: narration). Skip sections with no hits.
3. **Fix in this order**: first screen of each page → section A (deliverable level) → C if the shape is wrong (say so; a talk written as a consulting report needs restructuring, not polishing) → B sentence by sentence → D for anything spoken.
4. **Rules while rewriting**
   - Facts, numbers, names, links and citations stay exactly as they are; change words, not content. Sources move to one place (drawer, footnote, method page); they are not deleted.
   - Say the point: lead with the view, one caveat where it matters, no wrap-up sentence.
   - Don't write to the script: removing a flagged word while keeping the dull sentence is not a fix. The script is a hint; the read-aloud test decides.
   - Keep the author's register (spoken first-person plural for a talk, plain and precise for a report, labels only for a tool).
   - Edit source files (content/*.md, templates, data) rather than built output, then rebuild.
5. **Check.** Re-run the script; read the first screen and two random paragraphs as if aloud; pick five random sentences and cut any that tell a colleague nothing new.
6. **Report** in a few lines: per-1,000-character tells, notes and first-screen openers before → after, the suggested `voice` cap before → after, 3 before/after example sentences, and anything left because changing it would change meaning.

## Limits
- Advisory thresholds come from one calibrated case (a colleague-facing talk: its owner gave 60–65 where model reviewers gave 87–89); a clean count with a dull voice still fails.
- Scope is wording and shape. Look, layout, voice choice and sound mixing are out of scope.
