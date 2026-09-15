# AGY completion — task 010 (C3 offline preparation, revision 2)

Status: **ready for review**
Task brief: `coordination/agy/tasks/010-c3-offline-preparation.md`
Reviews addressed: `coordination/agy/reviews/010-review.md` and Codex review R2 (tip `109c6c3cd00f9b99b1212c1df63adaf157600c3c`)
Branch: `agy/010-c3-offline-preparation`
Clean starting commit: `9445fbef35e2944165314d306b4b214ef7d4bd9c`
Worktree: `/private/tmp/mujoco-llms-agy-010`
Python interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`

---

## Executive summary of revision 2

This revision addresses all findings from Codex handoff review R2 across the runner implementation, preflight evidence binding, audit dependencies, test suite, and reporting:

1. **R1-A — Inferred C3 without metadata safely invokes policy and retains report**:
   - In `humanoid_sim/visual_policy_runner.py` (lines 944–952, 1338), safely branch when reading requested model: default `req_model = 'gpt-5.6-sol'`, read from `execution_metadata` only when `execution_metadata is not None`, and fall back to `getattr(model_callable, 'model', None)`.
   - Added unit test `test_inferred_c3_without_metadata_invokes_policy_and_retains_report` in `tests/test_codex_policy.py` verifying that under `execution_metadata=None` with a callable declaring `condition='c3'` and `model='gpt-5.6-sol'`:
     - Normal execution invokes the policy (fake model counter == 1, completed_actions == 1), retains `report.json`, and records `visual_assessments` with `status='completed'`, `visual_assessment_state='valid'`, and `model_requested='gpt-5.6-sol'`.
     - Interrupted execution retains `report.json` with `termination_reason='interrupted'`, `status='interrupted'`, and `visual_assessment_state='unreached'`.
     - Malformed response execution retains `report.json` with `termination_reason='malformed_response'`, `status='malformed_response'`, and `visual_assessment_state='missing'`.

2. **R4-A — Honest boundary disclosure and link normalization**:
   - Dedicated Section 5 discloses the initial batch test execution (`Environment.__init__`, `Environment.reset`, and synthetic physics-backed tests) prior to Codex stopping the run at 02:48:33 UTC (logged in `/private/tmp/agy-010-execution/output.jsonl`).
   - Replaced all runner fixtures with zero-physics `FakeSession` doubles backed by archived public observations.
   - Updated `experiments/humanoid-pick-place/PLAN.md` lines 90 and 400 to replace blanket zero-reset claims with precise wording reflecting the initial run and subsequent guarded double verification.
   - Replaced all `file:///private/tmp/...` URLs in documentation with repo-relative paths.
   - Explicitly distinguished local subprocess calls (`git`, `codex --version`, `codex login status`) from VLA model decision calls (which strictly had zero invocations).

3. **R5 — Preflight bundle bound to exact implementation bytes**:
   - Recorded SHA-256 digests for all 8 modified implementation and test files (`humanoid_sim/codex_policy.py`, `humanoid_sim/visual_policy_runner.py`, `scripts/audit_codex_c2.py`, `scripts/run_offline_tests.py`, `tests/test_codex_policy.py`, `tests/test_codex_c1_audit.py`, `tests/test_codex_c2_audit.py`, `experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json`) in `manifest.json` and `preflight.json`.
   - Preflight record explicitly distinguishes clean base commit (`9445fbef35e2944165314d306b4b214ef7d4bd9c`) from dirty working changes.
   - Regenerated fresh preflight bundle in `coordination/agy/reports/010-c3-preflight/` including `manifest.json` and all 9 artifact files.

4. **Audit provenance clarification**:
   - Added `humanoid_sim/__init__.py` and `humanoid_sim/scoring.py` to `AUDIT_RUNTIME_DEPENDENCIES` in `scripts/audit_codex_c2.py`, expanding the runtime dependency set to 7 assets.
   - Documented the inherited mesh asset limitation: checking `scenes/g1_pick_place.xml` verifies the top-level scene XML against `metadata['scene_sha256']`; mesh XMLs/assets inherit provenance from `model_commit` recorded in metadata rather than per-mesh historical digests.
   - Clarified that `audit.json` copies all 30 historical trial provenance files into `physical_source_sha256` while the local audit runtime check verifies the 7 runtime dependencies.

5. **Test suite expansion**:
   - The guarded offline test suite in `scripts/run_offline_tests.py` now runs 45 tests (up from 44) in 4.934 s with 0 failures and 0 errors.

---

## 1. Files modified and created

| File | Status | Description |
|---|---|---|
| `experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json` | Created | Strict JSON schema requiring `visual_assessment` object (`block_visibility`, `block_relative_to_fingers`) and `command` object |
| `humanoid_sim/codex_policy.py` | Modified | C3 prompt construction with Appendix replacements; deterministic schema serialization; preflight bundle generator binding implementation source digests to `preflight.json` and `manifest.json` |
| `humanoid_sim/visual_policy_runner.py` | Modified | R1 fix (`effective_cond` initialization before branching); R1-A fix (safe metadata reading when `execution_metadata=None`); R3 fix (full per-call assessment accounting, string response parsing, error isolation); `serialize_schema` canonical definition |
| `scripts/audit_codex_c2.py` | Modified | R2 fix: defined `AUDIT_RUNTIME_DEPENDENCIES` (including `__init__.py` and `scoring.py`) to verify actual local audit dependencies against provenance while preserving 30-file historical execution provenance in `audit.json`; documented mesh asset limitation |
| `tests/test_codex_c2_audit.py` | Modified | R2 regression tests: added `test_unrelated_controller_edits_allowed` and verified runtime dependencies are checked and rejected on tampering |
| `tests/test_codex_policy.py` | Modified | R4 test doubles: replaced all `Environment()` / `reset()` usage in runner tests with `FakeSession` backed by archived observations; added R1, R1-A, and R3 regression tests; asserted `manifest.json` and implementation hashes in preflight |
| `scripts/run_offline_tests.py` | Created | Checked-in guarded offline test runner with process-level assertions against physics steps, resets, and live Codex model execution |
| `coordination/agy/reports/010-focused-tests.log` | Created | Fresh execution log of 45 guarded offline tests passing with 0 failures and 0 errors |
| `coordination/agy/reports/010-c3-preflight/` | Created | Fresh C3 preflight bundle containing 10 verified files: 9 artifact files, `preflight.json`, and `manifest.json` |
| `experiments/humanoid-pick-place/CODEX_RUNNER.md` | Modified | Documented C3 condition, schema, preflight command, and guarded test runner |
| `experiments/humanoid-pick-place/PLAN.md` | Modified | Updated Phase 5 status, checklist, and dated progress log with accurate disclosure |

---

## 2. Verification of hashes and contract constraints

### A. Static instruction hash
- C3 static instruction text verified via `humanoid_sim/codex_policy.py`:
  ```
  de0525e07f9470be60f9e01c4d720ad4f65260fd54b08065708e4096ce6313d0
  ```
  Matches expected golden hash bit-for-bit.

### B. Output schema hash
- Canonical serialized schema `experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json` SHA-256:
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

### E. Implementation source hashes (R5 binding)
Recorded in `coordination/agy/reports/010-c3-preflight/manifest.json` and `preflight.json`:
- `experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json`: `969434023fd1d874402b83bd4c689ee83351b1b678ead129c60ef5088a3f510b`
- `humanoid_sim/codex_policy.py`: `70719232ea2c343624e877e80fe57638ae7b4589b6c657580c7eb9e5743ac1ee`
- `humanoid_sim/visual_policy_runner.py`: `295de19872e35a001146d3de79ef6b989e852d70942645ab8d108678e77d2884`
- `scripts/audit_codex_c2.py`: `c4d773af346f180591362c794b18bd2f4b33c60878beca4461763475e92ceca0`
- `scripts/run_offline_tests.py`: `f7d56ab0a86112ef02c4ab4b41b47d9e358999b387a9393cdd50ce6977cc28a2`
- `tests/test_codex_c1_audit.py`: `bb4accc648b68eff453ea5a1949b0fd1b54a571693fe2e62d77cf3ad9c92df2f`
- `tests/test_codex_c2_audit.py`: `5e2cd19dade03ce48ea4a37c8996c7793a884e010bac9843d4a71b6e7a4804fc`
- `tests/test_codex_policy.py`: `67a357e34877883c03a5f19332d6c65ed7d8fff7d4aa0e5625d8c1029d363684`

### F. Historical artifact invariance
All committed historical C1 and C2 artifacts verified unmodified:
- `experiments/humanoid-pick-place/protocols/C1.md`: `401343ba76317d5f1eb8f01cabff7dcc9f79d6dddbb5325b0252204e1e9e07a4`
- `experiments/humanoid-pick-place/results/codex_C1.json`: `fa4f6866f8da951950d2bb78a1bc3bf89759d5870b21a812bc85c54c330dfbc0`
- `experiments/humanoid-pick-place/results/codex_C1_episode.zip`: `0d1daeec465355a297e68e0d4ea9bfa450d03258525b6a3788da986ff9455e7a`
- `experiments/humanoid-pick-place/results/codex_C1_audit/audit.json`: `6c3da29eeb134ff8c47f7d1b32d2039943676235b2e95a9477eb372a9df2c293`
- `experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md`: `a1a3b982fd455c9c2e220787be74c9bbad4c1c0dd6f4e32894aac9a896ced7c0`
- `experiments/humanoid-pick-place/results/codex_C2.json`: `72d1e5e2e4ffc2ea0f13c66289b0d625530f6d62886f45ef130f40d43a60a7ad`
- `experiments/humanoid-pick-place/results/codex_C2_episode.zip`: `940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8`
- `experiments/humanoid-pick-place/results/codex_C2_audit/audit.json`: `20d393557e4e1325d74feff0e689bf1db77bf7316fc1cb2a5e4d29f8f41ddf3c`

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
Ran 45 tests in 4.934s

OK

======================================================================
Summary: ran 45 tests, 0 failures, 0 errors
======================================================================
```
All 45 tests passed under active process-level guards. The test run log was saved to `coordination/agy/reports/010-focused-tests.log`.

### Golden C1/C2 preservation
Independent verification confirmed bit-for-bit preservation of all 12 archived C1/C2 prompts and images across calls.

---

## 4. Preflight bundle verification

The preflight bundle was regenerated at `coordination/agy/reports/010-c3-preflight/` via:
```sh
python -m humanoid_sim.codex_policy --condition c3 --output coordination/agy/reports/010-c3-preflight
```
The bundle contains 10 files:
1. `geometry_evidence.json` (SHA-256 `d05eaa29...`, 2,203 bytes)
2. `observation.png` (SHA-256 `c59315cb...`, 98,944 bytes)
3. `preflight.json` (SHA-256 `6a75270e...`, 3,356 bytes)
4. `prompt.txt` (SHA-256 `6780e6c9...`, 9,232 bytes)
5. `public_payload.json` (SHA-256 `b5a82c5a...`, 143,799 bytes)
6. `schema.json` (SHA-256 `79afc9c1...`, 3,590 bytes)
7. `synthetic_decision.json` (SHA-256 `d82f9771...`, 200 bytes)
8. `synthetic_events.jsonl` (SHA-256 `fb9ed217...`, 438 bytes)
9. `synthetic_record.json` (SHA-256 `bbdacee1...`, 3,113 bytes)
10. `manifest.json` (SHA-256 of bundle entries, size bytes, and implementation file digests)

---

## 5. Honest boundary and constraint disclosure (R4-A)

### Disclosure of initial batch test execution and stoppage
During the initial implementation batch of Task 010, the test suite (`tests/test_codex_policy.py`) instantiated `Environment()` fixtures and executed simulator resets and synthetic physics steps as part of runner verification tests. Codex detected this boundary violation and stopped the run at 02:48:33 UTC before any commit or handoff. The full record of this initial run is preserved in `/private/tmp/agy-010-execution/output.jsonl`.

Following the stoppage, all runner test fixtures were comprehensively replaced with zero-physics `FakeSession` test doubles backed by archived public observations from `codex_C2_episode.zip`. Process-level guards were installed in `scripts/run_offline_tests.py` and `tests/test_codex_policy.py` (`setUp`) patching `mujoco.mj_step*`, `Environment.__init__`, `Environment.reset`, and `subprocess.Popen` to raise `AssertionError` if physics, resets, or live Codex model commands are attempted. All subsequent test runs and preflight generations operated strictly within this zero-physics boundary.

### Distinction between subprocess checks and VLA model decisions
- **VLA model decisions**: Zero live model or API invocations were performed. Condition C3 has never been executed with a live model. The preflight check uses an offline synthetic fixture (`offline_synthetic_software_check`) with a mock process runner.
- **Local subprocess calls**: Local, non-model CLI checks did execute during test and preflight runs:
  - `git` commands: `git rev-parse HEAD`, `git status --porcelain` (to capture repository commit and dirty status for provenance).
  - Codex CLI checks: `codex --version` (verified version `0.154.0`) and `codex login status` (verified login method `chatgpt`).
  These local CLI metadata queries do not invoke LLM inference or send prompt payloads.

### Inherited mesh asset limitation
In `scripts/audit_codex_c2.py`, verification of `scenes/g1_pick_place.xml` checks the top-level scene XML file against `metadata['scene_sha256']`. Individual mesh XMLs and STL/OBJ assets referenced by the scene inherit their provenance from `model_commit` recorded in the audit metadata rather than through per-mesh SHA-256 digests. Full per-mesh asset pinning remains deferred from Task 010; the mesh assets were not modified.

### Held-out seeds and historical evidence
- Seeds 840–849 remain strictly held out and untouched.
- All historical evidence files in `experiments/humanoid-pick-place/results/` remain byte-for-byte unmodified.
- Condition C3 is prepared offline only; it is not frozen and not authorized for live execution.

Branch `agy/010-c3-offline-preparation` is ready for final Codex review.
