# AGY task 012 — Offline C3 grasp and guard audit

Status: ready for delegation after Task011 acceptance; not launched.
Owner: AGY implements/packages diagnostics; Codex interprets images, plans and reviews.
Use a dedicated agy/012-c3-grasp-audit worktree from the main commit containing this brief.

Read C3.md, CODEX_C3_RESULTS.md and Task011 acceptance. Audit the preserved C3 episode
only; no new model calls, API calls, reset, physics stepping, live rendering, source
controller changes or episode retries. All C1/C2/C3 archives and blind labels remain
immutable. Do not invent or revise image labels; those remain Codex's responsibility.

- [ ] Verify the pinned C3 archive hash and all members against the pre-run manifest
      and 92-file freeze. Extract into a new temporary directory. No mutable runtime
      capture is authoritative over the archive.
- [ ] Build a post-hoc diagnostic for action4's first close, action13/14's later close
      and lift, action17's final close, and the rejected action18. Use saved qpos with
      exact timestamps and public proprioception; label sampled geometry separately
      from the preserved scorer's 1 kHz telemetry. Never infer forces from qpos.
- [ ] Compare commanded versus achieved hand/site pose and finger joint configuration.
      Inspect finger/block contacts and relative geometry with mj_forward on scratch
      states. Distinguish occupied geometry from free grasp space and apparent 2D
      alignment from actual enclosure. Report ambiguity and missing information.
- [ ] Reproduce action18's production guard rejection on scratch data without mutating
      the saved integration state. Identify rejecting bodies, sample and penetration
      criterion; do not weaken the guard or execute the rejected command.
- [ ] Explain what observable evidence supports misalignment, closure-induced block
      displacement or unverified grasp. Propose diagnostic options only; Codex chooses
      any future intervention. Do not infer private model beliefs or provide a new recipe.
- [ ] Add focused tests under explicit Environment construction/reset and mj_step*
      guards; forbid live process/model launches. Use archived fixtures and doubles.
      No broad discovery that advances physics. Retain script/input/artifact hashes
      after final edits, commands, logs, all missing cases and interpretation limits.
- [ ] Write a concise report, machine-readable diagnostics and 012-completion.md;
      update PLAN, commit/push only the task branch, return exact tip and stop for
      Codex review. No main merge/push, new dependency, held-out seed or successor run.

The task is evidence preparation. Existing 2 mm strict scoring and P5's unmet 5.0 mm
mean gate stay fixed. This brief does not authorize a live C4 experiment.
