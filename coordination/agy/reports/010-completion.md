# AGY completion — task 010 (C3 offline preparation)

Status: **ready for review**
Task brief: `coordination/agy/tasks/010-c3-offline-preparation.md`
Review addressed: `coordination/agy/reviews/010-review.md`
Branch: `agy/010-c3-offline-preparation`
Clean starting commit: `9445fbef35e2944165314d306b4b214ef7d4bd9c`
Worktree: `/private/tmp/mujoco-llms-agy-010`
Python interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`

---

## Executive summary

Task 010 establishes offline preparation for condition C3 (in-loop visual state self-assessment paired with action commands in a single Codex response) per [`C3_PROPOSAL.md`](file:///private/tmp/mujoco-llms-agy-010/experiments/humanoid-pick-place/protocols/C3_PROPOSAL.md).

All four review items from [`010-review.md`](file:///Users/praveen/work/github/mujoco-llms/coordination/agy/reviews/010-review.md) have been fully resolved:
1. **R1 — Default runner operation and report retention**: Initialized `effective_cond = None` before branching in [`humanoid_sim/visual_policy_runner.py`](file:///private/tmp/mujoco-llms-agy-010/humanoid_sim/visual_policy_runner.py). Under default `execution_metadata=None`, a normal one-call hold finishes cleanly and retains `report.json`. Default failure and interruption scenarios were verified via injected doubles with zero physics steps or resets.
2. **R2 — Historical C2 audit compatibility and provenance distinction**: In [`scripts/audit_codex_c2.py`](file:///private/tmp/mujoco-llms-agy-010/scripts/audit_codex_c2.py), distinguished historical trial execution provenance (30 files recorded in `report['provenance']['source_sha256']` during trial execution, preserved verbatim in `audit.json` under `physical_source_sha256`) from actual local audit runtime dependencies (`AUDIT_RUNTIME_DEPENDENCIES = ('humanoid_sim/environment.py', 'humanoid_sim/interface.py', 'humanoid_sim/scene.py', 'humanoid_sim/visual.py', 'scenes/g1_pick_place.xml')`). Unrelated controller edits (e.g. `codex_policy.py`) do not fail the post-hoc physical audit, while modifications to actual simulation/scene assets are strictly rejected. Tested and verified in [`tests/test_codex_c2_audit.py`](file:///private/tmp/mujoco-llms-agy-010/tests/test_codex_c2_audit.py). Committed historical C1 and C2 audit artifacts and archives remain bit-for-bit unchanged.
3. **R3 — Assessment accounting, string response parsing, and failure isolation**: Rewrote `report['visual_assessments']` finalization in [`humanoid_sim/visual_policy_runner.py`](file:///private/tmp/mujoco-llms-agy-010/humanoid_sim/visual_policy_runner.py) to assemble accounting across every attempted call (`1` to `calls`), recording explicit call status and `visual_assessment_state` (`valid`, `malformed`, `missing`, `unreached`). Valid JSON string responses are parsed and populated. Never borrows a stale `last_assessment`. Failed calls retain complete static/schema/prompt/image/model metadata and raw error information. Only the primitive command reaches the interface (no retry or assessment-based correction). Verified against the reviewer reproduction script [`/private/tmp/agy-010-review/runner-check.py`](file:///private/tmp/agy-010-review/runner-check.py) and focused unit tests.
4. **R4 — Strict offline test boundary and checked-in test runner**: Replaced all `Environment()` / `Environment.reset()` fixtures in runner tests with an injected `FakeSession` double backed by archived public observations from `codex_C2_episode.zip`. Created a checked-in offline test runner [`scripts/run_offline_tests.py`](file:///private/tmp/mujoco-llms-agy-010/scripts/run_offline_tests.py) with process-level guards preventing physics steps (`mj_step*`), simulator resets (`Environment.__init__`, `Environment.reset`), and live model execution (`codex exec`). Ran all 44 offline tests to 100% pass without physics steps, resets, or model invocations. Log saved to [`coordination/agy/reports/010-focused-tests.log`](file:///private/tmp/mujoco-llms-agy-010/coordination/agy/reports/010-focused-tests.log).

---

## 1. Files modified and created

| File | Status | Description |
|---|---|---|
| [`experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json`](file:///private/tmp/mujoco-llms-agy-010/experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json) | Created | Strict JSON schema requiring `visual_assessment` object (`block_visibility`, `block_relative_to_fingers`) and `command` object |
| [`humanoid_sim/codex_policy.py`](file:///private/tmp/mujoco-llms-agy-010/humanoid_sim/codex_policy.py) | Modified | Exact C3 prompt construction with Appendix replacements; deterministic schema serialization; C3 preflight with synthetic software check |
| [`humanoid_sim/visual_policy_runner.py`](file:///private/tmp/mujoco-llms-agy-010/humanoid_sim/visual_policy_runner.py) | Modified | R1 fix (`effective_cond` initialization before branching); R3 fix (full per-call assessment accounting across all calls, string response parsing, error isolation); `serialize_schema` canonical definition |
| [`scripts/audit_codex_c2.py`](file:///private/tmp/mujoco-llms-agy-010/scripts/audit_codex_c2.py) | Modified | R2 fix: defined `AUDIT_RUNTIME_DEPENDENCIES` to verify actual local audit dependencies against provenance while preserving 30-file historical execution provenance in `audit.json` |
| [`tests/test_codex_c2_audit.py`](file:///private/tmp/mujoco-llms-agy-010/tests/test_codex_c2_audit.py) | Modified | R2 regression tests: added `test_unrelated_controller_edits_allowed` and verified all runtime dependencies are checked and rejected on tampering |
| [`tests/test_codex_policy.py`](file:///private/tmp/mujoco-llms-agy-010/tests/test_codex_policy.py) | Modified | R4 test doubles: replaced all `Environment()` / `reset()` usage in runner tests with `FakeSession` backed by archived observations; added R1 and R3 regression tests; installed offline guards in `setUp` |
| [`scripts/run_offline_tests.py`](file:///private/tmp/mujoco-llms-agy-010/scripts/run_offline_tests.py) | Created | Checked-in guarded offline test runner with process-level assertions against physics steps, resets, and live Codex model execution |
| [`coordination/agy/reports/010-focused-tests.log`](file:///private/tmp/mujoco-llms-agy-010/coordination/agy/reports/010-focused-tests.log) | Created | Fresh execution log of 44 guarded offline tests passing with 0 failures and 0 errors |
| [`coordination/agy/reports/010-c3-preflight/`](file:///private/tmp/mujoco-llms-agy-010/coordination/agy/reports/010-c3-preflight/) | Created | C3 preflight bundle containing 9 verified artifact files, `preflight.json`, and `manifest.json` |
| [`experiments/humanoid-pick-place/CODEX_RUNNER.md`](file:///private/tmp/mujoco-llms-agy-010/experiments/humanoid-pick-place/CODEX_RUNNER.md) | Modified | Documented C3 condition, schema, preflight command, and guarded test runner |
| [`experiments/humanoid-pick-place/PLAN.md`](file:///private/tmp/mujoco-llms-agy-010/experiments/humanoid-pick-place/PLAN.md) | Modified | Updated Phase 5 status, checklist, and dated progress log for Task 010 |

---

## 2. Verification of hashes and contract constraints

### A. Static instruction hash
- C3 static instruction text verified via [`humanoid_sim/codex_policy.py`](file:///private/tmp/mujoco-llms-agy-010/humanoid_sim/codex_policy.py):
  ```
  de0525e07f9470be60f9e01c4d720ad4f65260fd54b08065708e4096ce6313d0
  ```
  Matches expected golden hash bit-for-bit.

### B. Output schema hash
- Canonical serialized schema `llm-response-c3.schema.json` SHA-256:
  ```
  79afc9c195908ce3e268e50193db8d188e579d451c0467365a64fb2297fb0dff
  ```

### C. Geometry evidence hash
- Deterministically generated robot-only hand geometry evidence SHA-256:
  ```
  d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6
  ```

### D. Demonstration prompt hash
- Full C3 demonstration prompt from archived C1 seed-820 call 1 SHA-256:
  ```
  6780e6c97153238a5ee9a52fc6368fdd83641f875a406a7fc613c3e660a2071c
  ```

### E. Historical artifact invariance
- All committed historical C1 and C2 artifacts verified unmodified:
  - `experiments/humanoid-pick-place/protocols/C1.md`: `401343ba...`
  - `experiments/humanoid-pick-place/results/codex_C1.json`: `fa4f6866...`
  - `experiments/humanoid-pick-place/results/codex_C1_episode.zip`: `0d1daeec...`
  - `experiments/humanoid-pick-place/results/codex_C1_audit/audit.json`: `6c3da29e...`
  - `experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md`: `a1a3b982...`
  - `experiments/humanoid-pick-place/results/codex_C2.json`: `72d1e5e2...`
  - `experiments/humanoid-pick-place/results/codex_C2_episode.zip`: `940f3ef7...`
  - `experiments/humanoid-pick-place/results/codex_C2_audit/audit.json`: `20d39355...`

---

## 3. Test verification and execution evidence

### Guarded offline test execution
Command:
```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/python scripts/run_offline_tests.py
```
Output:
```
======================================================================
Task 010 Offline Software Verification Suite
Label: offline_synthetic_software_check (Zero-Physics / Zero-Reset / Zero-Model)
======================================================================
Ran 44 tests in 4.726s

OK

======================================================================
Summary: ran 44 tests, 0 failures, 0 errors
======================================================================
```
All 44 tests passed with process-level guards preventing physics steps, simulator resets, and live Codex exec calls.

### Reviewer reproduction script
Executed `/private/tmp/agy-010-review/runner-check.py`:
- `DEFAULT`: terminated with `action_limit` and retained `report.json`.
- `C3`: call 1 completed with `visual_assessment_state="valid"`; call 2 failed with `status="malformed_response"`, `visual_assessment_state="missing"`, `visual_assessment=null`; report retained both call entries.
- `STRING_C3`: parsed JSON string response; `visual_assessment_state="valid"` and assessment populated.
- Script exited with returncode 0.

---

## 4. Honest boundary and constraint disclosure

- **Zero live model / API calls**: No live model, API, or unmocked subprocess calls were performed. The offline preflight software check uses injected synthetic fixtures (`offline_synthetic_software_check`).
- **Zero physics steps / resets**: All new and modified tests use `FakeSession` doubles with archived observations. Guards on `Environment.__init__`, `Environment.reset`, and `mujoco.mj_step*` ensure zero physics steps.
- **Zero probes or fresh episodes**: No new simulation episodes, trials, or image probes were run.
- **No historical evidence rewritten**: All committed historical artifacts remain bit-for-bit intact.
- **Held-out seeds**: Development seeds 840–849 remain untouched and strictly held out.
- **Condition C3 status**: C3 remains proposed and prepared offline only. It is not frozen and not executed.

Branch `agy/010-c3-offline-preparation` is ready for Codex review.
