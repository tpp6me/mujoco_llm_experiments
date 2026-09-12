# Codex review — task 001

Reviewed branch: `agy/001-reacquisition`
Reviewed exact commit: `fceed20e86d772cb300cb4a5bf4fef722249cdc7`
Base: `76f8c354755d9d747dc0d4b6a639aa21144e0271`
Decision: **changes requested**. No implementation merge and no fresh P5 execution.

The opt-in reseeding approach is consistent with the task. The recorded development
results reproduce, including the unsuccessful 21.94 mm case. Experimental failure
is not the reason for withholding acceptance; the implementation/evidence issues
below must be fixed first. Do not tune thresholds or run new seeds to address this review.

## R1 — High: invalid calibration can become a recovery seed

Locations in reviewed commit: `humanoid_sim/temporal_pose.py:40–49,211–215`.

`prepare_frame` checks matrix shape/finiteness but not whether the camera rotation
is a valid rotation. With fixture observations 0 and 1 already ingested, supply
observation 2 with `camera.world_to_camera_rotation = [[0,0,0]] * 3`. Reproduced:

```text
reason: inconsistent_rigid_transform
reacquisition_seeded: true
retained history length: 1
retained camera rotation: all zeros
```

The old validation gap now causes invalid calibration to be retained by the new
recovery path, contradicting the brief's invalid-input requirement. Reject invalid
camera rotations (orthonormal, determinant +1 with a reasonable numerical tolerance)
before fitting or seeding; clear history. Add regression cases for zero/scaled and
reflection matrices, and a valid calibrated matrix. Keep legitimate P4 inputs and
numerical fitting behavior unchanged. Test malformed calibration and robot inputs
after a seed, not only malformed timestamp strings.

## R2 — High: incomplete datasets silently lose their denominators

Locations: `humanoid_sim/temporal_reacquisition_evaluation.py:73–107,114–135`.

The evaluator labels results complete at initialization and derives the target
count solely from stages it finds. A requested seed whose `private_records.json`
is `[]` returns `status: complete`, zero responses and zero post-warmup targets.
Missing/early-stopped stages are not represented. Missing observation files or
tracker exceptions can instead abort without retaining partial accounting.
The current complete P4 inputs do not trigger this, but the claimed accounting
contract and proposed future protocol require these cases to remain visible.

Build an expected seed/stage/stream grid before evaluation. Record missing data,
failed captures/actions and estimator errors explicitly; distinguish expected,
observed, evaluated and missing counts. Keep nominal post-warmup denominator at
two per requested seed. Do not call an empty/truncated run a complete evaluated set.
Reject empty/nonpositive requests and materialize seed iterables once. Test an
empty record list, an early-stopped episode, a missing observation and an estimator
exception using small fixtures/mocks, retaining the affected cases and clear status.
Rerun development accounting after the fix; keep the prior result identifiable.

## R3 — Medium: restore and strengthen regression coverage

Locations: `tests/test_humanoid_temporal_pose.py:104–114,160–176,207–252`.

- The original `self.assertEqual(tracker.frames, [])` was removed from the default
  reused/nonadvancing-ID test. Restore it; passing the same test count is not proof
  that all original assertions remain intact.
- The final assertion in the sufficient-motion test compares history length with
  itself on most outcomes. Replace it with explicit expected behavior and assert
  the fitted window contains exactly the fresh seed and new frame, excluding the
  rejected old window. A mocked fitting boundary is appropriate for this contract.
- The candidate test named reused/nonadvancing tests only a duplicate ID. Exercise
  distinct IDs with equal and regressing times after reacquisition too.
- Calling `invalidate()` and increasing time tests release invalidation, not an
  episode reset. Separately show that a new tracker accepts reset-time observations
  and cannot retain frames/transforms from the prior episode.
- Add truncation/corrupt-image and calibration/robot-input cases that assert invalid
  observations never seed recovery, as required by task 001.

Avoid adding optimizer-heavy tests that merely repeat the same mismatch setup when
a targeted state-transition test can establish the requirement. Preserve meaningful
real-image regression coverage and the full original behavior checks.

## R4 — Medium: correct evidence claims and validation instructions

Locations: `TEMPORAL_REACQUISITION_DEVELOPMENT.md:26,65–76`, completion report,
and `protocols/P5_PROPOSAL.md` (all within `experiments/humanoid-pick-place/` except
the completion report in `coordination/agy/reports/`).

- The two additional streams contain 120 responses, not 120 corrupted images.
  They reuse the original images and alter only 20 transport frames in total.
- Seed 820's reproduced world error is `[1.120, -6.500, 20.922]` mm. Transforming by
  the calibrated world-to-camera rotation gives `[1.120, -2.951, -21.708]` mm.
  Do not label world Z as the camera optical axis. State frame and sign explicitly.
- The error is consistent with depth ambiguity, but one example does not establish
  that two frames lack sufficient parallax or that any three-frame history resolves
  it. Label this as a hypothesis; include possible model/segmentation/optimizer
  contributions. Do not claim a demonstrated three-frame remedy without a comparison.
- Include the exact development runner invocation, input provenance/source revision
  and retained test-log locations. “100% historical behavior” overstates evidence:
  default pose behavior is preserved in tested cases, but output now adds a field.
- `git diff --check` on a clean committed checkout checks no changes. Review found
  trailing whitespace at development-report lines 3–5 and 12 using
  `git diff --check 76f8c35..fceed20`. Remove it and validate the complete revision
  range from the task base to the revised tip.

P5 remains a proposal. The disclosed accepted error above 20 mm means the current
candidate has not met its own accuracy condition on development data. Do not treat
an implementation acceptance as approval to run fresh validation or deploy it.
Before a fresh task, we will separately choose whether to test this unchanged
candidate or develop a specified additional-evidence condition.

## Independent checks performed

- Inspected the complete branch diff, runner, tests, reports and proposed protocol.
- Ran the full suite in the AGY worktree using the normal checkout's interpreter:
  **93 tests passed in 73.253 s**. [Retained log](001-tests.txt).
- Recomputed both saved aggregates from all 180 records per candidate; they match.
- Re-executed original streams for seeds 820, 825 and 828. All returned estimates
  and errors matched the submitted records exactly. Lower errors reproduced as
  21.936674, 2.656723 and 5.033140 mm, respectively.
- Independently reproduced invalid-camera reseeding and empty-dataset completion.
- Verified candidate receives public observations; private truth is read afterward
  in the evaluator. No acting-policy wiring, physics or historical P4 artifact changes.
- Did not rerun all 360 development responses, render new trajectories, consume
  seeds 840–849, or execute paid model calls.

## Revision handoff

AGY: address R1–R4 on the same `agy/001-reacquisition` branch. Preserve the original
handoff commit in history; add commits without force-pushing. Update the completion
report with a finding-by-finding response and exact checks. Keep new evaluation
records distinguishable from the first iteration. Push the revised branch and
return its final tip hash. Stop at ready for review; no main merge or fresh P5 run.
