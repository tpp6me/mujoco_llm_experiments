# AGY task 002 — Additional evidence before accepting a reacquired pose

Status: **ready**. Branch: `agy/002-reacquisition-evidence`.
Start from the main revision containing this brief and the accepted task-001 tip
`7ffc056018cc03cd5d886ef3e86b23b1d7fbc8ab`. Record the exact starting hash.
Read `coordination/agy/WORKFLOW.md` and the task-001 acceptance review first.

## Objective

Test the specific hypothesis that a third fresh RGB/hand observation within the
reacquired window reduces the known false acceptance without merely eliminating
useful coverage. Task 001's two-frame candidate recovered two accurate lower poses
but accepted seed 820 at 21.94 mm error. An added frame is evidence to test, not a
guarantee of independent parallax or a rigid grasp.

Keep task 001 and default P4 behavior unchanged. Implement a separate opt-in
experimental condition and compare it against the accepted two-frame candidate.
No fresh validation or acting-controller integration is authorized by this task.

## Workspace and inputs

Create a dedicated worktree without switching branches in the primary checkout:

```sh
git worktree add -b agy/002-reacquisition-evidence /private/tmp/mujoco-llms-agy-002 main
```

If it already exists, inspect and resume only if it belongs to this task; never
reset/delete an existing worktree. Reuse the primary checkout's `.venv/bin/python`
from the task worktree if dependencies are not installed there.

Read the temporal/reacquisition implementation, tests, development report, P4
protocol/results and P5 proposal. Existing seeds 740–742 and 820–829 are development
inputs. Runtime captures and trajectories live under the primary checkout's
`runtime/humanoid/` and must be treated as read-only.

## Bounded implementation and experiment

1. Add an opt-in recovery condition requiring at least three distinct, fresh
   observations since a valid recovery seed before emitting a center. Preserve
   the existing 80 mm motion threshold and numerical fit/ambiguity thresholds.
   No previous rejected transform or old 3D center may be inherited.
2. Inspect the saved P4 trajectories for additional observations during lowering,
   before release. Use a deterministic schedule based on action timestamps only
   (for example the lowering midpoint plus its existing endpoint). Never select
   views using private object pose, error or scoring feedback.
3. Prefer rendering saved states. If artifacts are insufficient, a repeat capture
   of the existing development seeds with unchanged G2 physics/controller is allowed;
   explicitly label it development, record source/input provenance and capture
   state-preservation checks. No new seed, new recovery motion, scene or scorer change.
   If reliable recapture cannot be done, report the limitation without fabricated data.
4. Feed the same observations to both two-frame and three-frame conditions. Retain
   the original endpoint-only baseline separately so the effect of extra observations
   is not confused with the effect of the minimum-window rule.
5. Evaluate all selected original targets, including 820, 825 and 828. Include
   visibility loss, frozen-image inconsistency and physical release/retract checks.
   Use the corrected fixed-grid evaluator accounting: missing cases, emitted but
   unscored estimates, refusals and exceptions must remain visible.
6. Add focused tests proving the new condition cannot emit after only two views,
   cannot recycle pre-rejection observations, and preserves invalidation/release
   behavior. Keep all prior tests intact.

## Acceptance and reporting

Report original and augmented observation counts, motion baselines, observation
schedule, estimator calls, acceptance coverage, all-case <=20 mm counts,
accepted-only errors and false acceptances. Additional observations consume
communication/compute time even if the existing simulated motion is unchanged;
state this explicitly. Do not claim a 25-second real-time controller qualification.

Evidence that the hypothesis fails is an acceptable task outcome. Do not adjust
thresholds, omit seed 820, or count repeated/static images as independent viewpoints
to obtain a pass. Candidate inputs remain public RGB/calibration/robot state only;
private truth is used by the evaluator after estimation.

Provide a concrete recommendation for the next protocol based on these development
results. P5 remains proposed, not frozen or executed. Seeds 840–849 remain untouched.
Do not change a proposal into a fresh run without the next review checkpoint.

Run focused tests, the full test suite, and `git diff --check <starting-hash>..HEAD`
plus the working diff check before committing. Record exact commands and retained
logs. No paid APIs, hardware, dependency changes without a concrete justification,
or main-branch merge/push.

## Handoff

Write `coordination/agy/reports/002-completion.md` using the template. Keep reports
and result files distinct from historical task-001/P4 evidence. Commit and push
only `agy/002-reacquisition-evidence`, then return its exact tip hash and completion
report. Stop at ready for review.
