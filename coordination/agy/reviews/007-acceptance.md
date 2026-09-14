# Task 007 acceptance

Accepted tip: `e336f2054d3ae27ac9f87a38f13d0a9a3cce6b3e`.
Implementation commit: `acbf28449049dde6f059b28bfaa8a4c4ab019def`.
2026-09-14. Acceptance is for the specified C2 CLI entrypoint and offline evidence.

The revised implementation fixes the reproduced geometry serialization mismatch,
persists geometry before decisions, distinguishes static and per-decision prompt
hashes, validates conflicting condition aliases and callable settings, locks the
CLI probe/execute model and call cap, restores the default graphics-free C1 local
check, and builds C2 preflight from a committed public C1 observation.

Codex independently verified:

- All three archived C1 full prompts reproduce byte-for-byte; C2's added text
  equals the proposal exactly.
- All five committed preflight file hashes, public payload/prompt consistency and
  independently generated geometry hash match their manifest.
- The production `main()` execute path, with simulator and CLI replaced by test
  doubles, retains the exact geometry and correct static/full prompt hashes when
  interrupted at its first decision. No real decision, renderer or physics step
  was used in this reviewer test.
- 53 affected tests passed in 10.249 s; [log](007-final-tests.txt).
  AGY's retained full discovery reports 226 passes in 177.447 s. No redundant full
  suite was run by Codex after those unchanged implementation files.
- CLI 0.154.0 is installed and local status reports ChatGPT login. No model request
  was used for that installation check. C1 evidence and physical sources remain
  unchanged; the merge requires only coordination/checklist conflict resolution.

## Authoritative report clarifications

The raw completion report remains an AGY handoff; these reviewer-verified facts
supersede its residual prose inaccuracies:

- Seven included collision geoms are unnamed in the compiled model. Their bodies
  are thumb_0/1/2, middle_0/1 and index_0/1 under `right_hand_`. There is no included
  palm geom; the report's list of invented `*_collision` names is incorrect.
- C2 preflight no longer renders or synthesises the observation. Its separate
  robot-geometry check **still uses IK and `mj_forward`**, without stepping physics.
- `static_instruction_sha256` and the report's legacy `prompt_sha256` alias refer
  to the complete static instruction. Full dynamic prompt hashes live in each
  decision record; the preflight has `demonstration_prompt_sha256`.
- Generic injected runner calls validate declared settings, but are not the
  authoritative frozen-experiment launcher. C2 execution is restricted to the
  reviewed CLI command and the additional source/configuration checks in Task 008.

Source identity for the preflight is the clean code commit above; the later handoff
adds documentation/artifacts without changing that tested code. Frozen execution
must use the clean commit containing the C2 freeze record, with matching source,
protocol and instruction hashes. No dirty/unknown source is authorized for the run.

The user explicitly requested all five stages, including execution and review.
Proceed to [frozen C2](../../../experiments/humanoid-pick-place/protocols/C2.md) and
[Task 008](../tasks/008-c2-execution.md). This is not a manipulation-success claim.
