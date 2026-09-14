# AGY task 008 — Operate frozen C2 and package evidence

Status: ready for execution after this brief/freeze are committed.
Branch/worktree: `agy/008-c2-execution`, `/private/tmp/mujoco-llms-agy-008`.
Start from the exact main commit containing this brief and `protocols/C2.md`.
Codex will create the worktree and provide that hash in the launch prompt.

The user explicitly authorized all five stages. Task 007 is accepted; read
`coordination/agy/reviews/007-acceptance.md` and the experiment's `protocols/C2.md`.
AGY owns operation and evidence packaging. All VLA decisions must be made by the
unchanged signed-in Codex CLI adapter, never by Gemini or AGY reasoning.

## 1. Establish the frozen input

- Confirm worktree branch/tip, clean tracked/untracked state, CLI version 0.154.0
  and ChatGPT login using local checks only. No API keys, direct API calls or live
  model probes. Use the existing primary `.venv` interpreter, no dependency changes.
- Before writing tracked files or starting the simulator, create
  `runtime/humanoid/codex-C2/manifest.json` (new directory) with the exact source
  commit, protocol/freeze hashes, static instruction/geometry hashes, seed list
  `[820]`, one requested trial, 20-decision/25-second/120-second limits and CLI info.
  Save hashes of all `humanoid_sim/*.py`, scene XML and C2 specification/freeze.
- Validate the static instruction and geometry digests against the freeze. If any
  precondition fails, retain the failure and stop for Codex review. Do not change
  code, configuration, model, authentication mode or the scientific plan.

## 2. Execute exactly one episode

- Run the literal command from C2.md once from this worktree. Graphics and signed-in
  CLI access are authorized for this command; automatic AGY permissions are allowed.
- Capture stdout/stderr and process exit status separately. Monitor the process,
  not elapsed time alone. No code/docs edits, simulator interventions, additional
  episodes, model probes or automatic retries while the runner is active.
- The harness alone supplies current public input to fresh Codex sessions. Never
  resume a VLA session, inject analysis/truth, edit decisions or replace refusals.
- Preserve every failure. A model failure or guard rejection is a valid result,
  not a request to fix the robot or rerun. No held-out seeds 840–849.

## 3. Package evidence after exit

- Verify source/protocol hashes still match the pre-run manifest. Save all runtime
  files in a committed ZIP under `experiments/humanoid-pick-place/results/`, with a
  per-file SHA-256 manifest. Include failed attempts if any; never omit bad outcomes.
- Write a compact machine-readable C2 summary plus a concise result report. Use
  the private evaluator for physical success/lift/penetration and runner records
  for execution counts/termination. Separate static instruction hashes from full
  per-decision prompt hashes and CLI invocations from unobservable network requests.
- Audit every prompt/PNG against its saved public request via `public_input(...,
  condition='c2')`; validate every completed CLI event log with the pinned parser.
  Missing/incomplete records must be counted and labelled, not called successful.
- Report per-action displacement/orientation from saved qpos for diagnosis, labelled
  as sampled post-hoc geometry; do not claim forces or exact peak timing from qpos.
  Do not modify simulator code to collect new telemetry or rerun missing frames.
- Update PLAN/results index and `coordination/agy/reports/008-completion.md` with exact
  code/launch/handoff commits, commands, outcomes, file hashes and limitations.
  State whether the one planned trial executed and all model/physics counts.
- Commit and push only the task branch. No main merge/push, history rewrite,
  controller fixes, new dependencies, hardware or successor experiment. Stop at
  the complete handoff for Codex's independent review and next-step planning.

A new full software test run is unnecessary for this evidence-only task. Verify
archive hashes, accounting, unchanged source and `git diff --check`. Any proposed
source change instead requires stopping and a separate Codex-reviewed task.
