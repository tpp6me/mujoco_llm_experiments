# AGY task 001 — Temporal tracking reacquisition

Status: **accepted for development-only integration**; see [review](../reviews/001-acceptance.md). Branch: `agy/001-reacquisition`.
Functional starting revision: `3a3dd24`. Start from the main revision containing
this brief; record its full hash. Later workflow-only commits are expected.
If functional code has changed since `3a3dd24`, inspect and report that difference
before assuming the P4 behavior still applies.

## Objective

Implement and evaluate an experimental reacquisition path after a rejected temporal
window. Test whether the latest valid current image can seed a new relationship,
with subsequent fresh motion evidence, without reusing an old 3D center or assuming
a rigid grasp. Return code, development evidence and a proposed fresh protocol for
Codex review. A documented unsuccessful approach is acceptable; do not force a pass.

## Start and read

From the normal checkout, ensure the branch/worktree names are unused, then create:

```sh
git worktree add -b agy/001-reacquisition /private/tmp/mujoco-llms-agy-001 main
```

If that worktree already belongs to this task, inspect and resume it. Do not delete,
reset or overwrite an existing worktree. Perform all edits/tests in the task worktree.
Do not switch branches in the normal checkout.

Read:

- `coordination/agy/WORKFLOW.md`
- `experiments/humanoid-pick-place/PLAN.md`
- `experiments/humanoid-pick-place/TEMPORAL_POSE.md`
- `experiments/humanoid-pick-place/TEMPORAL_POSE_RESULTS.md`
- `experiments/humanoid-pick-place/protocols/P4.md`
- `humanoid_sim/temporal_pose.py` and `temporal_pose_evaluation.py`
- `tests/test_humanoid_temporal_pose.py`

P4 reached 14/20 nominal post-warmup targets, below its 16/20 coverage screen.
Accepted mean/max errors were 3.645/7.420 mm. Seeds 820, 825 and 828 rejected at
transport; clearing their entire histories left lowering in warmup. A fresh valid
image may be useful as a new seed even when the preceding relationship was invalid.
That hypothesis needs evidence, not an automatic claim of recovered tracking.

## Authorized implementation

- Prefer a separate opt-in candidate or explicit recovery mode. Preserve default
  P4 behavior and keep the acting `PerceptionSession` unchanged.
- On model mismatch, investigate retaining only the current valid image as a new
  seed. It must not produce an immediate 3D estimate or inherit the prior transform.
- Distinguish valid current imagery from loss, truncation, malformed metadata,
  stale/reused IDs and invalid robot/calibration inputs. Invalid imagery must not
  become a recovery seed.
- Require subsequent fresh time/motion evidence. Known release/reset must invalidate
  the relationship. Preserve the distinction between model consistency and grasp proof.
- Add focused tests and a reproducible development runner/report. Reuse existing
  geometry and image extraction where appropriate; explain changes to shared code.
- Draft a successor protocol, explicitly marked **proposed, not frozen or executed**.
  Include action/time costs if recovery requires additional observations or motion.

## Development inputs and boundaries

Existing datasets 740–742 and 820–829 may now be used as development data for this
new candidate. P4 is still historical frozen evidence for its original method;
new tuning against its images is not fresh validation. Use tracked fixtures first.
Existing local captures, if available, are read-only at:

`/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture/`

The existing interpreter may be reused at:

`/Users/praveen/work/github/mujoco-llms/.venv/bin/python`

Run it from the task worktree so imports select that worktree's code. Record paths
and commands. If runtime data is missing, complete fixture-based work and report
what prevents the broader development check; do not invent results.

Do not generate or inspect new randomized seeds for validation. Propose seeds
840–849 for the successor protocol, subject to Codex checking they are unused.
Do not run that fresh validation in this task. The review checkpoint prevents
validation-set leakage while the implementation/protocol is still changing.

No new model/API calls, hardware actions, scene/physics/scorer changes, threshold
relaxation or control integration. Do not edit historical protocols, result JSON,
source archives or prior test logs. New reports go in new files.

## Acceptance criteria

1. Default temporal behavior remains covered; the existing 84-test baseline is
   preserved, or any deviation is explicitly justified for review.
2. Recovery emits no stale/immediate position from a newly seeded window.
3. Tests exercise a valid new seed, sufficient/insufficient motion, visibility loss,
   invalid metadata, reused/nonadvancing observations, release and episode reset.
4. Development accounting includes every selected case, refusal, error and reset.
   Compare old/new candidates on the same inputs, with accepted-only and all-case
   statistics separated. Do not use private truth in either candidate.
5. Any improvement is labeled development-only. Keep the candidate disconnected
   from control regardless of development results.
6. A concrete successor protocol is reviewable before any fresh run.

Run targeted tests and the complete suite:

```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v
git diff --check
```

## Required handoff

Create `coordination/agy/reports/001-completion.md` using the template. Record the
starting hash, implementation commit, exact commands, test counts, development
inputs, results, artifacts, deviations and remaining limitations. Commit the report
with the task work, push only `agy/001-reacquisition`, and return the final tip hash
in your completion message. The final hash belongs in that message rather than
inside the commit that it identifies.

Stop at **ready for review**. Do not merge main or execute the proposed fresh run.
