# AGY task 007 — C2 implementation and offline qualification

Status: **ready for review**. Branch: `agy/007-c2-implementation`.
Use a dedicated worktree `/private/tmp/mujoco-llms-agy-007`, based on the main
commit containing this brief. Record the exact starting and final commits.

Read `coordination/EXECUTION_POLICY.md`, `coordination/agy/WORKFLOW.md`,
`experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md`, `CODEX_C1_DIAGNOSIS.md`,
`CODEX_RUNNER.md`, `humanoid_sim/codex_policy.py` and its existing tests.
Task 006 remains cancelled; none of its direct-API requirements apply here.

## Objective and implementation

- [x] Implement explicit C1/C2 selection with C1 remaining the default. Preserve
  C1 prompt bytes, model settings, limits and historical artifacts. Use the exact
  additional C2 text in the proposal; do not tune or invent alternative instructions.
- [x] Keep geometry in the prompt a static, robot-only contract. Reproduce the
  nominal bounds from the robot description and verify their rounded enclosure.
  Do not load the private C1 audit, object state or outcomes in the policy path.
- [x] Record condition ID, complete prompt hash, geometry evidence hash and source
  revision in run provenance. Reject mismatched labels/settings before invocation.
- [x] Prepare a local-only preflight that demonstrates C2 configuration, public
  payload construction, isolation, budgets and a new output path. It must not
  invoke a Codex decision. Keep the action/event auditing and error retention intact.
- [x] Update the guide and checklist to describe final behavior accurately. Prepare
  a concrete freeze/run command for Codex review; do not mark C2 frozen or executed.

## Permissions and boundaries

AGY may read the repo, edit its worktree, run offline tests, create diagnostic
artifacts, and commit/push its own task branch. Use the primary checkout's existing
`.venv/bin/python`; identify reused paths explicitly. Read-only committed C1
archives are available; do not depend on an untracked runtime dataset.

No main merge/push, history rewrite, dependency changes, hardware, direct API calls,
API-key access or invocation of Codex decisions. Do not launch fresh performance
episodes, including C2. Existing simulator unit tests and static geometry checks
are allowed. Preserve scene, physics, camera, guard thresholds, scoring and held-out
seeds 840–849. Gemini/AGY must never act as the VLA or repair a model response.

## Acceptance evidence

- [x] Tests prove exact C1 prompt preservation and exact C2 paragraph inclusion.
- [x] Tests prove private-field exclusion and reject condition/settings mismatches
  and accidental model invocation in offline preflight. Preserve existing failure,
  timeout, tool-use, budget and observation-freshness behavior.
- [x] Geometry checks distinguish occupied bounds from a grasp cavity or safe path;
  altered object truth cannot affect the static public geometry contract.
- [x] Run affected tests during development, then one full discovery after final
  changes. If failures require fixes, rerun the affected checks and accurately
  state which revision each retained log covers. Run `git diff --check`.
- [x] Verify C1 artifacts and frozen protocol are unchanged from the starting commit.
- [x] Submit `coordination/agy/reports/007-completion.md` with exact commits, changed
  files, commands, test counts/log paths, preflight artifact hashes, limitations and
  proposed frozen-run command. Clearly state zero model invocations and no C2 run.

Stop at the complete review handoff. Codex owns review, protocol freeze and the
decision to issue a separate execution task. Revise this same branch for findings;
do not independently change the scientific plan or start successor experiments.
