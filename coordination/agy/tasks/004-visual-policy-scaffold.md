# AGY task 004 — Offline RGB-to-action policy runner

Status: **ready**. Branch: `agy/004-visual-policy-scaffold`.
Start from the main integration containing this brief and Task 003 acceptance.
Record the exact starting hash. Use a new dedicated worktree:
`/private/tmp/mujoco-llms-agy-004`.

Read `coordination/agy/WORKFLOW.md`, `coordination/agy/reviews/003-acceptance.md`,
`experiments/humanoid-pick-place/PLAN.md`, `VISUAL.md`, `LLM_RUNNER.md`, and the
existing `visual.py`, `interface.py`, `llm_runner.py` and related tests.

## Objective

Advance the original experiment toward an LLM choosing manipulation actions from
RGB and proprioception. Build and test a provider-neutral, offline visual policy
loop using an injected callable/stub. This is runner implementation, not a live
model experiment and not evidence that an LLM can perform the task.

P5 preparation is complete, but its development mean remains 5.8715 mm against
an unchanged 5.0 mm gate. Do not treat the carried-pose estimator as qualified.
The visual runner must not depend on temporal poses, private object coordinates,
or oracle feedback. Fresh passive P5 remains a separate review decision.

## Authorized scope and boundaries

- Work only on `agy/004-visual-policy-scaffold` in its dedicated worktree.
- Reuse existing dependencies, the primary `.venv/bin/python`, interface action
  schema, RGB/proprioception boundary and guarded primitives.
- No network/model API calls, credentials, new providers/SDKs, model pricing or
  token-billing implementation. No default HTTP transport. The injected callable
  is explicitly a test stub; implement the live provider adapter in a later task.
- No hardware, held-out seeds 840–849, fresh evaluation, physics/controller/camera
  changes, dependency changes, estimator changes, main merge/push or history rewrite.
- Treat all previous captures, reports and task worktrees as read-only. Use complete
  mock boundaries and saved public development observations for tests. If a real
  simulator smoke check adds necessary coverage, use only already-developed seed
  820, label it a stub smoke check and retain output separately; it is optional.

## Implementation

1. Add a separate `humanoid_sim/visual_policy_runner.py` or equivalently small
   module. Reuse `VisualSession` through a narrow adapter and accept an injected
   model callable, clock and log destination. Keep the existing exact-state L2
   runner, provider client and its historical evidence unchanged.
2. Define an explicit public request contract for the callable:
   - instruction and action schema;
   - current RGB image, calibration, timestamp/observation identity;
   - allowed robot/proprioceptive fields and remaining action/time budget;
   - bounded history of public actions and outcomes only.
   Construct this payload from an allowlist. Never serialize the environment,
   simulator state, task truth, object pose, private scorer, source-file paths or
   diagnostic objects. Do not simply pass through an arbitrary observation or
   history dictionary. Do not reuse L2's exact-state prompt unchanged; it says
   there are no images and may imply an exact-state condition.
3. For each iteration capture one fresh observation, call the injected model with
   only that public payload, parse and validate one structured primitive, and
   execute through `VisualSession.execute(observation_id, request)` so freshness
   and the existing collision guard remain authoritative. Never bypass the public
   interface to move the robot. Do not reuse an observation after an action.
4. Preserve the existing pilot limits: at most 20 attempted actions/calls and a
   25-second simulated episode deadline including reset. Distinguish model wall
   latency from simulated time (paused inference). Stop on a refused/malformed
   response, exception, rejected action, stale observation or exhausted budget;
   no silent retries, replacement actions or oracle fallback. Do not advertise
   real-time control. Use injectable clocks rather than sleeping in tests.
5. Retain reviewable run logs in a new output directory: public requests, raw stub
   responses, validated commands, action results, timing, termination reason,
   image identity/hash and source/instruction/schema provenance. Any private task
   score, if recorded by a smoke harness after the loop, stays in separate evaluator
   output and never returns through the model's history or request. Count refusals,
   errors and interrupted attempts honestly. Never infer placement success merely
   from a completed move or a stub's success claim.
6. Provide an explicit offline CLI/demo, if useful, that requires/selects a named
   stub and never accidentally invokes a real model. The stub may issue a small
   scripted sequence for plumbing tests, clearly labeled as such. Do not present
   it as a conventional comparator, LLM policy or model success result.

## Meaningful verification

Tests must call production code through injected boundaries and cover:
- RGB and declared robot state reach the callable, while deliberately planted
  private fields in observations, action responses and history do not.
- Valid command uses the exact captured ID and guarded execute path; successive
  actions require fresh capture. Stale/reused IDs are rejected without movement.
- Invalid JSON/command, model refusal/exception and interface rejection terminate
  explicitly without fallback or extra action.
- Call/action limit and simulated deadline, including boundary rounding, prevent
  excess execution; wall latency is separately logged.
- No network call or credential access occurs in the default/offline modes.
- A completed action does not become a fabricated successful-placement result.

Keep tests fast; do not run the 25-minute P5 optimizer. Run focused tests and full
repository discovery once final code is ready. Broaden/repeat only if changes or
failures require it. Retain exact commands and stable log paths.

## Deliverables

- Offline visual policy runner, tests and a small retained demo/request example.
- `experiments/humanoid-pick-place/VISUAL_POLICY_RUNNER.md`: public contract, run
  instructions, stub limitations, and precise work left for a live adapter and
  frozen pilot. Distinguish implementation, simulation smoke checks and model evidence.
- Plan/results-index update and `coordination/agy/reports/004-completion.md` with
  source revision, changes, tests, logs and boundary audit.
- `git diff --check <starting-hash>..HEAD` and working diff check; commit and push
  only the task branch. Return exact local/remote tip hashes and stop ready for
  Codex review. No live calls, P5 execution or main integration.
