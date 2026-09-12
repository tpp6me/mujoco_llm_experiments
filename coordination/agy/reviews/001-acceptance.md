# Codex acceptance — task 001

Reviewed exact commit: `7ffc056018cc03cd5d886ef3e86b23b1d7fbc8ab`
Branch: `agy/001-reacquisition`
Decision: **accepted for development-only integration**.
The integration commit includes this acceptance record and retains the complete
AGY revision history. Earlier review records remain historical evidence.

## Findings closed

- R1: non-rotation camera matrices are rejected before fitting or recovery seeding;
  malformed image, robot and calibration inputs clear history.
- R2: the evaluator retains its expected seed/stage/stream grid through missing
  data and preparation/estimator errors. Emitted detections are counted separately
  from scored detections. Missing/invalid truth makes the evaluation incomplete
  while retaining the unscored output. Frozen transport requires its declared
  lift-hold source, and stream interruptions invalidate tracking history.
- R3: baseline assertions were restored and recovery-window contents, invalidation,
  release and episode reset received focused regression coverage.
- R4: response counts, world/camera coordinates, uncertainty language and validation
  instructions were corrected; the complete revision diff passes whitespace checks.

This accepts the bounded implementation and its development evidence. It does not
assert the model meets its accuracy gate or approve fresh P5 execution/control use.
The known seed-820 false acceptance remains an open scientific issue.

## Independent verification

- Reran the complete repository suite in the AGY worktree: **106 tests passed in
  89.989 s**. [Retained test log](001-r3-tests.txt).
- Reproduced the previously fatal corrupt-transport case: it now returns a
  preparation-error entry with all six expected stage slots retained.
- Reproduced the six-accepted-poses/no-truth case: all six detections remain counted,
  zero are scored, all six are unscored, the nominal denominator remains two, and
  overall status is incomplete.
- Recomputed both saved aggregates from their 180 records each. All 360 saved
  estimates and numeric errors match revision 2; fitting/recovery code is unchanged
  in the final evaluator-only revision.
- Confirmed `git diff --check 76f8c35..7ffc056` passes and the acting interface,
  driving policies, physics and historical P4 artifacts are unchanged.
- The first review independently reran the three decisive recovery sequences;
  this review checked their retained values rather than repeating the complete
  expensive development run.
- No new trajectories or paid model calls were run by the reviewer. Fresh P5
  seeds 840–849 remain excluded from authorized AGY work.

## Scientific result retained

On the existing P4 development trajectories, reacquisition emits positions on
17/20 nominal post-warmup targets, with 16/20 within 20 mm. The remaining accepted
error is 21.94 mm on seed 820 Lower. No positions were emitted on altered transport
or release/retract cases in the retained development evaluation. These findings
are development-only, not a formal held-out comparison or task success rate.

## Next task

[Task 002](../tasks/002-reacquisition-evidence.md) tests an explicit three-fresh-view
condition and additional observations on existing development trajectories. It must
compare the observation schedule and window rule separately and retain failures.
An extra frame is a hypothesis to test, not proof of adequate parallax or a rigid
grasp. The proposed P5 protocol remains unexecuted pending that review.
