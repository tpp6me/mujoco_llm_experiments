# AGY task 009 — Offline C2 failure audit

Status: ready for delegation after Task 008 acceptance; no new experiment authorized.
Owner: AGY implements and packages; Codex reviews geometry, visual interpretation
and any successor VLA condition. Start a dedicated branch/worktree from the main
commit containing Task 008 acceptance. Record that exact commit before edits.

## Objective

Explain the earliest damaging C2 action using retained evidence, then separate
geometric approach failure from subsequent observation/action inconsistency.
C2 recorded no lift or placement: action four displaced the block about 154 mm
horizontally; it reached the floor by the end of action five. Action nine was
rejected by IK. Additional decisions did not establish manipulation progress.
These are observations to audit, not instructions to repair or rerun the policy.

## Checklist

- [x] Verify the committed C2 ZIP SHA-256 and every member against its manifest;
      verify the frozen source/scene identity. Extract to a new audit directory.
      Preserve C1/C2 source archives and all historical outcomes byte-for-byte.
- [x] Build a reproducible offline audit patterned after `scripts/audit_codex_c1.py`.
      Generalize only with explicit protocol/source checks. Do not instantiate an
      environment that resets or steps. Model loading, saved qpos, `mj_forward`
      and scratch-data IK checks are permitted; no `mj_step`, new rollout,
      renderer-generated replacement input, CLI model invocation or API call.
- [x] For C2 action four, retain saved samples spanning the approach, actual
      grasp-site path, object pose, and finger/object geometric contacts. Relate
      the scorer's recorded peak contact at t=3.795 s to the available sampled
      poses. Keep full-rate scorer telemetry distinct from sampled geometry;
      never infer forces or exact peak timing from qpos-only reconstruction.
- [x] Compare actual finger geometry along this path with the nominal C2 bounds.
      Establish whether the prompt's reference frame/bounds were applicable;
      bounds alone do not describe a free grasp cavity or certify a safe path.
      Report measurements, without asserting what the model believed.
- [x] Produce an ordered contact sheet from the original saved public images
      for decisions 3–9, labelled with observation time and following command.
      Include the exact public proprioception/history alongside it. Keep private
      trajectory annotations in a separately labelled evaluator artifact. AGY
      assembles evidence; Codex judges visibility and VLA reasoning implications.
- [x] Reproduce action nine's IK rejection on scratch data without advancing or
      mutating the saved integration state. Record the residual and unchanged state.
- [x] Compare only descriptive C1/C2 facts: first damaging action, displacement,
      lift/placement, penetration and stop reason. Do not treat the reused single
      seed, different action sequences, or extra executed actions as efficacy proof.
- [x] Add focused tests for new audit logic, including source mismatch rejection
      and a check that the audit cannot step/reset physics or invoke a model.
      Report exact commands, source hashes, artifact hashes and limitations.
- [x] Commit/push the task branch, write `coordination/agy/reports/009-completion.md`
      and stop for Codex review. Leave thresholds, prompts, controller and scorer
      unchanged; seeds 840–849 remain unused.

## Codex decision after handoff

Use the audit to select one testable successor intervention (if warranted),
separating geometric task grounding from feedback/reassessment. Specify public
inputs, frozen instructions, budgets, endpoints and accounting before execution.
Do not bundle another instruction change into an unreviewed trial. P5's separate
5.0 mm mean gate remains unchanged and unmet.
