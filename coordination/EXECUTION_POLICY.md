# Current execution direction

Updated 2026-09-15 following the user's instruction to minimise Codex usage,
maximise AGY usage, and reserve Codex for VLA tasks, planning and review.
The earlier restriction on direct OpenAI APIs remains in force.

- AGY performs implementation, debugging, local testing, artifact preparation and
  documentation under bounded Codex task briefs. Codex owns experiment planning,
  acceptance criteria, review, interpretation and integration decisions. Route
  revision work back to AGY rather than routinely fixing its implementation in Codex.
- All VLA decisions use signed-in Codex CLI sessions. AGY may operate a reviewed,
  frozen experiment harness when its task explicitly authorizes that run; it must
  not substitute Gemini decisions or supply private evaluation data to Codex.
- Batch work into complete handoffs with exact commits, diffs, test logs and artifact
  hashes. Codex reviews at milestones and independently verifies material claims;
  avoid repeated full-suite runs or frequent status-only turns without new evidence.
- Do not implement or invoke direct OpenAI API transport, paid API experiments,
  API-key lookup, or account/model endpoints. AGY Task 006 is cancelled before
  implementation; its brief was committed, but no Task 006 AGY process or worktree
  was created.
- Preserve historical exact-state API experiments and offline adapter artifacts as
  historical records; their presence is not authorization to execute API commands.
- The provider-neutral visual runner, guarded action interface and simulator remain
  usable. Carry forward the 20-call/25-second limits, public RGB/proprioception
  boundary and private post-hoc scoring.
- The user confirmed that the controller itself should use the signed-in Codex CLI
  to choose robot actions. Implement and run this through the existing guarded
  visual runner. ChatGPT login is required; no direct API transport or API keys.
  The separate [C1 development protocol](../experiments/humanoid-pick-place/protocols/C1.md)
  declares the model, public input boundary, budgets and trial accounting.
- C2 execution and Task 009 offline diagnosis are accepted. Next implementation
  handoff: [AGY task 010](agy/tasks/010-c3-offline-preparation.md), preparing the
  proposed C3 visual assessment contract. It authorizes offline implementation
  only; any model episode requires a separate Codex review, freeze and run brief.
- Held-out seeds 840–849 remain unused. P5's 5.0 mm mean gate remains unchanged and
  unmet. Do not convert implementation tests into model-performance claims.
