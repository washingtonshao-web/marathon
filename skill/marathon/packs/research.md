# Pack: research and strategy (with or without code), usually delivered as a site

Craft:
- the literature sweep uses bounded researchers (parallel researchers, notes on disk, source counts);
- marathon owns targets, gate, output and follow-ups; for biology the lead proposes gate=sonnet+astra;
- output: a readable HTML long-read with sourced charts and a glossary; use your preferred design and chart tools.

## What the user keeps asking for
- **Numbers and a decision.** Estimate when data is thin (and label it). Give probabilities, scores, ranges and a recommendation. A method without a result is not an answer.
- **Literature before your own work.** Read what the field does before modelling, simulating or downloading. Use industry-standard terms and never invent labels (no "T0", "PMRD" or "no-op" unless the field uses them). A glossary defines every term a colleague might not know.
- **Answer the question asked.** Every research question in the authorized brief is a Q-n row in CHARTER; answers start directly. Ordinary follow-up questions remain chat-only under followups.md. The gate checks every Q-n.
- **Colleague-readable.** Conclusions first; method, assumptions and references at the end. When the reader must act, give an SOP: steps, inputs and decision thresholds.
- **Own your view.** Disagree with the user when the evidence says so, with the numbers. Don't flip-flop to agree.

## Code and data verification (when the brief asks for working code)
- Add the `verified_on_data` rubric key (15, rebalanced) and hard targets with measured numbers (e.g. sensitivity and precision against a truth set at stated depths).
- **Data**: download the public datasets needed for verification into the project (gitignored: BAM, CRAM, FASTQ and VCF are excluded by `init`). Record each source, version and checksum. Don't download more than the verification needs.
- **Benchmark honesty**: choose and freeze the truth set and the test samples in phase 1. Tune on separate samples, never on the test set, and report the held-out result.
- **Compute**: Use native Linux/macOS tools or WSL on Windows. Respect your resource limits. Estimate run time before long jobs, and run them as resumable scripts with a STATUS file.
- **Code** ships with a README, pinned versions, one command per stage, and a small test that runs in minutes.

## Parameter ledger
The user's own parameters (purity, enrichment, input mass, depth, prices) go into CHARTER with their date. Changing one means recomputing everything that depends on it (`followups.md`).

## Fact-checking
- Every headline number has ≥2 independent sources, or is marked as an estimate with its derivation.
- Regulatory status, approvals, prices and company facts are checked fresh, because they change.
- The gate samples 10 claims against their sources.

## Independence
When the user runs the same brief with another model or session, don't read its output unless asked. When asked to compare, tabulate where and why the results differ.

## Targets to put in CHARTER (typical)
- Every Q answered (n/n).
- Every headline number sourced or derived.
- The glossary covers every term used.
- A recommendation with probabilities.
- ≥N primary sources read.
- With code: the measured performance on the held-out truth set.

## Human-only checklist
Would a colleague in the field accept the terms and numbers? Do the recommendations fit the company's real constraints, which the user knows?
