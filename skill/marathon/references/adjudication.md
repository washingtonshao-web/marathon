# Adjudication

[gate.md](../gate.md) owns partial-then-merge, carry and final fallback. For this fourth case, reviewers/confirmers use the same frozen artifact/evidence; Astra full, configured Claude full/focused per [gate-prompt](gate-prompt.md).

On ADJUDICATE reproduce/check evidence, write audits/round-N/ADJUDICATION.md, rescore with --adjudication <file>. Each because needs ≥10 characters citing evidence:

~~~text
KEY stability = 8 because tests/save.test.ts passed the reproduced reload case.
CRITICAL = 0 because tests/save.test.ts disproves the reported loss.
MAJOR = 1 because screenshot 4 shows one remaining clipped label.
CONFIRMED BY audits/round-N/confirmation.md
TOTAL ACCEPTED because tests/acceptance.txt supports the conservative merged total.
~~~

Cover disputed keys/critical presence. TOTAL ACCEPTED handles total-only splits without changing merged values. Reducing max critical requires a separate fresh confirming review, never the lead/original disputed reviewer. It reads both reports, ruling and evidence and includes:

~~~text
REVIEWER: <fresh identity>
CONFIRM: dismiss
~~~
