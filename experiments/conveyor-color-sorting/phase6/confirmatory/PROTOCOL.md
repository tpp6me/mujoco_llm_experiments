# Supplemental instruction-change check

Frozen after the original 48-run matrix and before these four new runs.
The original matrix has seven runtime-health failures, including all four
instruction-change episodes. Rendering overlapped the final live trials.
No original case is discarded, replaced, or retried.

Use new seeds 24003 and 24004 with the same two instruction-change conditions.
Run at most one Codex/conventional pair concurrently; wait for both to finish
before starting the other pair. Do not record videos, run tests, or launch
unrelated simulations while these trials are active. All other source code,
instructions, camera calibration, motion recipe, scoring, and lag threshold
remain frozen and identical to the original Phase 6 implementation.

For each Codex run, inspect the initial image and submit its target. At the
20-second rule change, obtain a fresh image and submit the new target. Preserve
expired commands and failures. Do not read this cohort's private reports until
all Codex submissions in this cohort have finished. Conventional decisions use
the same declared image detector and rule parser as before.

Report these four episodes separately from the original matrix. Verify matching
initial states, complete accounting, frozen source hashes, public observations,
and maximum lag ≤0.25 seconds. Report old-command cancellation, new-rule selection,
transition delay, and physical outcomes. No additional attempts if a run fails.
This is a small diagnostic check of instruction changes under reduced machine
load, not a replacement formal benchmark or an independent blinded evaluation.
