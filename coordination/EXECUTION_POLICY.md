# Current execution direction

Updated 2026-09-13 following the user's instruction:
"Just use codex. I don't want to use OpenAI APIs for anything."

- Codex performs development directly. Do not launch further AGY tasks unless the
  user explicitly changes this direction.
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
- Held-out seeds 840–849 remain unused. P5's 5.0 mm mean gate remains unchanged and
  unmet. Do not convert implementation tests into model-performance claims.
