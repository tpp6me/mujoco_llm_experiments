# AGY task 003 — Prepare the passive P5 protocol and runner

Status: **ready**. Branch: `agy/003-p5-preparation`.
Start from the main revision containing this brief and the accepted Task 002 tip
`a351053f6c933d82380a611121989c008a26eafa`. Record the exact starting hash.
Read `coordination/agy/WORKFLOW.md`, `reviews/002-acceptance.md`, the existing P5
proposal and Task 002 evidence before implementation.

## Objective and boundaries

Make the next passive perception experiment reproducible and reviewable before
using held-out seeds. Task 002 showed 17/20 original targets accepted within 20 mm,
but the accepted-target mean is 5.8715 mm and fails the proposed 5.0 mm gate.
Both reacquisition candidates give identical augmented-stream results. Acceptance
of Task 002 is acceptance of implementation and development evidence, not model
qualification. A failed future experiment is a valid outcome.

This task prepares a protocol and runner only. **Do not execute, capture, render,
reset the simulator with, or inspect outcomes for seeds 840–849.** Do not freeze
or claim fresh validation. Do not change estimator thresholds, recovery semantics,
G2 actions/physics, cameras, control policies, dependencies or historical evidence.
No paid model APIs or robot hardware. Perception remains disconnected from control.

Create a dedicated worktree without switching the primary checkout:

```sh
git worktree add -b agy/003-p5-preparation /private/tmp/mujoco-llms-agy-003 main
```

If it already exists, inspect and resume only if it belongs to this task. Reuse
the primary checkout's `.venv/bin/python` and read-only development runtime inputs;
record their absolute locations. Never delete another task's cache/worktree.

## Implementation

1. Write a revised proposal as `experiments/humanoid-pick-place/protocols/P5_REVISED_PROPOSAL.md`.
   Keep the earlier P5 proposal as historical planning evidence and link both.
   Label the revision **proposed, not frozen, not executed**. Specify:
   - Proposed fresh seeds 840–849, unchanged exact-state G2 driver, fixed 960x720 RGB.
   - Primary condition: `TemporalThreeFrameReacquisitionPose` on the augmented
     schedule. Two-frame and baseline P4 are prespecified comparators; endpoint-only
     streams isolate the schedule effect. No selection of a winner after scoring.
   - Original six evaluated stages and augmented seven-stage schedule; derive the
     lowering midpoint from Transport/Lower timestamps with the production helper.
     Reuse qpos-based kinematic replay as in Task 002, with unavailable dynamic
     fields explicit. Distinguish requested midpoint from actual saved sample time.
   - Three variants per schedule (nominal, black Transport, frozen Lift-Hold RGB
     at Transport), unchanged image substitution and release invalidation rules.
   - Twenty original post-warmup targets per nominal condition. Original schedule:
     180 responses per candidate; augmented: 210. Three candidates: 1,170 expected
     responses total, including 540 original and 630 augmented. Extra midpoint
     responses never enlarge the original-target denominator.
   - Gates remain >=16/20 accepted original targets, <=5.0 mm mean error over
     accepted original targets, no accepted nominal center >20 mm, zero release/
     retract emissions and zero corrupted Transport emissions. Report midpoint
     errors separately and include every accepted nominal stage in the maximum
     error check. Report all-stream containment descriptively as well.
   - Missing stages, missing truth, preparation/scoring/estimator errors and
     unscored acceptances make evidence incomplete; incomplete is never a pass.
     Refusal counts remain visible. State independent episodes versus correlated
     within-episode observations. This small screen is not a general success rate.
   - Record code/scene/dependency/protocol hashes, seed list, capture provenance,
     public-input hashes and augmented manifest; identify the future freeze step.
     Added observations and optimization cost count as compute/communication;
     no real-time or 25-second acting-controller qualification is claimed.
2. Add a small separate P5 preparation/evaluation wrapper, reusing the accepted
   fixed-grid evaluator and augmentation helpers. Avoid duplicating trackers or
   rewriting the existing Task 001/002 paths. It should produce:
   - a preflight report with exact candidate/schedule/seed/grid configuration,
     input availability, hashes and explicit development/preparation status;
   - a structured gate report from evaluation results, with numerator/denominator,
     scored versus unscored counts, pass/fail/incomplete (or not applicable for
     subset dry runs), and a concise reason for each gate;
   - retained evidence and manifest in a new task-specific output directory.
   Normal/preflight execution must not capture episodes or touch held-out inputs.
   Restrict executable development mode to the existing 820–829 captures in this
   task; reserve future fresh execution for the next reviewed task. It is sufficient
   to document the future capture command instead of enabling fresh execution now.
3. Run a development dry run on existing saved inputs. Prefer the validated Task
   002 augmented cache read-only; preserve cache validation and use a new directory
   if generation is necessary. A full ten-seed report must show the existing mean
   criterion fails, without changing the gate. A smaller optimizer smoke run is
   acceptable if the full gate report is also independently exercised on retained
   ten-seed Task 002 evidence and clearly labeled an artifact rescore.
4. Add focused tests of actual production paths: known 5.8715 mm failure at the
   unchanged gate, successful synthetic metrics, missing/invalid truth and missing
   targets never passing, all-refused results, midpoint denominator separation,
   and preflight/development modes never invoking fresh capture or held-out seeds.
   Preserve existing tests and historical artifacts.

## Deliverables and review checkpoint

- Revised proposed protocol and runner usage instructions with exact commands.
- Development preflight/gate reports with input provenance and limitations; do
  not mislabel a rescore or subset smoke run as fresh ten-episode validation.
- `coordination/agy/reports/003-completion.md`: source revision, files changed,
  commands/logs, all gate outcomes, and recommendation whether to proceed with a
  separately frozen P5 screen or do further development. Do not relax the 5.0 mm
  criterion to accommodate the known result.
- Update the living plan and results index, retaining the distinction between
  prepared implementation and completed fresh validation.
- Run focused tests, full discovery, and `git diff --check <starting-hash>..HEAD`
  plus the working diff check. Commit and push only `agy/003-p5-preparation`,
  return the exact tip and stop ready for review. No main merge or P5 execution.
