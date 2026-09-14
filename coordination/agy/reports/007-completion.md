# AGY completion — task 007 (revision 2)

Status: **ready for review**
Task brief: `coordination/agy/tasks/007-c2-implementation.md`
Branch: `agy/007-c2-implementation`
Starting commit: `87bce15dda8a99b8c8d9ff0bf3c657653a998eba`
Base review tip: `8938222791d542640ebb0f094891e99a8751eb79`
Code commit (clean tree): `acbf28449049dde6f059b28bfaa8a4c4ab019def`
Worktree: `/private/tmp/mujoco-llms-agy-007`
Python interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`

---

## Executive summary of revision

This revision directly addresses changes requested in `coordination/agy/reviews/007-review.md` (R1–R4). All implementation, test, and evidence defects identified by Codex have been corrected:

1. **R1 (Geometry serialization & provenance)**: Hashing and serialization use identical sorted keys (`sort_keys=True`) and newline termination, achieving exact digest agreement (`d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6`). Static run evidence (`geometry_evidence.json`) is persisted immediately upon folder creation before decision execution and survives interruption. Static instruction hash is distinguished from per-decision prompt hashes. Complete provenance (protocol path, protocol hash, source commit, git status, dirty flag) is tracked and bound to outputs.
2. **R2 (Condition & settings validation)**: Condition aliases (`condition` and `condition_id`) are strictly compared; missing condition identity is inferred from protocol if valid or rejected; mismatched callable conditions, models (`!= gpt-5.6-sol`), timeouts (`!= 120.0`), and altered-model probes are rejected before capture, folder creation, or callable invocation.
3. **R3 (Default C1 check & offline independence)**: Preserved C1's original graphics-free default CLI install/login check in `main()`. Rewrote `run_preflight()` to load committed public input from `experiments/humanoid-pick-place/results/codex_C1_episode.zip:seed-820/call_001.json`, eliminating runtime `RGBRenderer` and physics/IK dependencies while preserving exact C1 call 1 image bytes. Handled absent login gracefully so offline checks and unit tests run without account credentials or graphics.
4. **R4 (Evidence accuracy & committed bundle)**: Corrected all physical geometry facts (7 collision geoms, extents `[-0.074, 0.058] x [-0.042, 0.042] x [-0.077, 0.085]` m, prompt placement preceding observation JSON), test counts (33 related tests: 3 audit + 30 runner; 20 policy tests; 226 full discovery tests), and limited zero-step claims strictly to static checks. Generated and committed a compact preflight evidence bundle in `coordination/agy/reports/007-c2-preflight/` with `manifest.json` at clean code commit `acbf28449049dde6f059b28bfaa8a4c4ab019def`.

---

## Detailed changes addressing review findings

### R1 — Execution provenance matches retained evidence

- **Uniform Serialization**:
  - `humanoid_sim/visual_policy_runner.py:write_json` now defaults to `sort_keys=True`.
  - `humanoid_sim/codex_policy.py:serialize_geometry_evidence` uses `json.dumps(geom, indent=2, sort_keys=True) + '\n'`.
  - SHA-256 digest computed in memory matches written file byte-for-byte: `d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6`.
- **Pre-Decision Static File Persistence**:
  - In `run_visual_episode`, static run artifacts passed via `execution_metadata['static_files']` (including `geometry_evidence.json`) are written immediately after `folder.mkdir(parents=True, exist_ok=False)` and before any turn execution or observation capture.
  - Interrupted episodes retain their static evidence and write `report.json` in the `finally` block with matching provenance.
  - Added unit test `test_geometry_evidence_written_and_retained_on_interruption` injecting a `KeyboardInterrupt` stub; proves `geometry_evidence.json` exists on disk with matching hash and matching provenance in `report.json`.
- **Static vs Per-Decision Prompt Provenance**:
  - Added `static_instruction(condition)` helper returning the complete static text preceding dynamic observation JSON (`VISUAL_PROMPT + DECISION_INSTRUCTION` for C1; `+ C2_INSTRUCTION` for C2).
  - Preflight and episode provenance explicitly record:
    - `static_instruction_sha256`: `6d90729760f5458d69dfc6d90e9f433eacd7721f2552e8c24060a840e27237db` (C2) / `c1b058ec0e447b9ca404bf702167cb4be067c30d9575971489e24fa2eb4a13f6` (C1)
    - `demonstration_prompt_sha256` / `prompt_sha256`: full prompt hash including dynamic observation JSON
- **Source and Protocol Provenance**:
  - `git_source_info()` records commit hash, `is_dirty` boolean, and `git_status` string (`clean` or `dirty`).
  - Provenance includes `protocol_path` (`experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md`), `protocol_sha256` (`a1a3b982fd455c9c2e220787be74c9bbad4c1c0dd6f4e32894aac9a896ced7c0`), `source_commit`, `git_status`, and `is_dirty`.

### R2 — Condition and settings validation

- **Condition Alias Validation**:
  - If both `condition` and `condition_id` are provided in `execution_metadata`, `run_visual_episode` raises `ValueError` if they disagree (`cond != cond_id`).
  - If omitted, condition is inferred from `protocol_id` if recognised (`humanoid-codex-c1-development` -> `c1`, `humanoid-codex-c2-development` -> `c2`).
  - Any unknown condition label is rejected before capture.
- **Model Callable & Settings Validation**:
  - If model callable defines `condition`, it must match effective condition.
  - For C1 and C2 conditions, model callable's `model` is validated against declared metadata (default `gpt-5.6-sol`), and callable's `timeout` is validated against declared timeout (`120.0` s).
  - In `codex_policy.py:main()`, `--probe` enforces `model == MODEL` (`gpt-5.6-sol`) and maximum 20 calls for both C1 and C2, preventing relabelling of altered models.
- **Reproduction Cases**:
  - All 3 review metadata cases from `007-reproduce.py` are rejected before capture:
    1. `condition=c2`, `condition_id=c1`: rejected with `Conflicting condition (c2) and condition_id (c1)`.
    2. `protocol_id=humanoid-codex-c1-development`, callable `condition=c2`: rejected with `Mismatched model callable condition (c2) and execution metadata condition (c1)`.
    3. Matching C2 labels with callable `model=other-model`: rejected with `Mismatched model callable model (other-model) and expected model (gpt-5.6-sol)`.
  - Added unit test `test_condition_and_settings_mismatches_rejected` verifying all three cases plus timeout mismatch and CLI probe path model validation.

### R3 — Default C1 check & offline independence

- **Default C1 Local Check Preserved**:
  - `python -m humanoid_sim.codex_policy --condition c1 --output <dir>` runs `check_install()`, writes `preflight.json`, and exits.
  - Zero MuJoCo calls, zero scene loading, zero graphics rendering.
  - Tested in `test_default_c1_local_check_preserves_graphics_free_behavior`.
- **Archived Public Input for Preflight**:
  - `run_preflight()` loads observation PNG and observation state from committed archive `experiments/humanoid-pick-place/results/codex_C1_episode.zip:seed-820/call_001.json`.
  - Eliminates runtime `RGBRenderer` and MuJoCo IK solving from preflight while guaranteeing exact C1 call 1 image bytes (`c59315cbd6cc656d0f86ba918ede532855377a7eff1c9da0e4a8252034c3ce65`).
- **Offline Independence**:
  - If Codex CLI or login is unavailable, offline preflight records `'cli_status': 'unverified (offline environment)'` without raising `RuntimeError`.
  - Offline preflight and policy unit tests run independently of real login, real credentials, and graphics displays.
  - Zero model invocations (`model_invocations: 0`) and zero physics steps (`physics_steps: 0`).

### R4 — Geometry facts, test counts, and committed preflight evidence bundle

- **Accurate Geometry Facts**:
  - Hand collision geoms: exactly **7** (`right_palm_collision`, `right_hand_thumb_0_collision`, `right_hand_thumb_1_collision`, `right_hand_thumb_2_collision`, `right_hand_middle_0_collision`, `right_hand_middle_1_collision`, `right_hand_index_0_collision`).
  - Nominal world-axis offset extents:
    - X: `[-0.07355, 0.05720]` m
    - Y: `[-0.04160, 0.04140]` m
    - Z: `[-0.07696, 0.08475]` m
  - Rounded bounds declared in C2 proposal:
    - X: `[-0.074, +0.058]` m
    - Y: `[-0.042, +0.042]` m
    - Z: `[-0.077, +0.085]` m
  - C2 paragraph precedes observation JSON, not a JSON schema.
- **Accurate Test Counts**:
  - Codex policy unit test suite (`tests/test_codex_policy.py`): **20 tests** (expanded from 18 to include R1 interruption and R3 C1 local check tests; all pass in 1.782s).
  - Related suites: **33 tests** (`tests/test_codex_c1_audit.py` [3 tests] + `tests/test_humanoid_visual_policy_runner.py` [30 tests] = 33 tests; all pass in 8.639s).
  - Full repository discovery: **226 tests** (all pass in 177.447s, 0 failures, 0 errors).
- **Committed Preflight Evidence Bundle**:
  - Location: `coordination/agy/reports/007-c2-preflight/`
  - Generated at clean code commit `acbf28449049dde6f059b28bfaa8a4c4ab019def`.
  - Contains `manifest.json` with SHA-256 hashes, file sizes, generator command, and exact source commit.

---

## Committed preflight evidence manifest

Bundle path: `coordination/agy/reports/007-c2-preflight/`
Generator command:
```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.codex_policy --condition c2 --output coordination/agy/reports/007-c2-preflight
```

| File | Size (bytes) | SHA-256 Digest | Description |
|---|---|---|---|
| `manifest.json` | 1,749 | — | Bundle manifest with source provenance and metadata |
| `geometry_evidence.json` | 2,203 | `d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6` | Nominal robot-only hand geometry offsets and bounds |
| `observation.png` | 98,944 | `c59315cbd6cc656d0f86ba918ede532855377a7eff1c9da0e4a8252034c3ce65` | Archived C1 seed-820 call 1 observation PNG |
| `preflight.json` | 2,054 | `53d01d5dd6c70f00981670f2b595dda97b301e6d9321f542c216ce1ab8d5284e` | Clean execution metadata and configuration verification |
| `prompt.txt` | 8,330 | `3afbd2e2a27444ac514fc5a35540ca9ddfa8b1482abea719b04a174241e018e4` | Complete prompt: static instructions, C2 geometry, public obs |
| `public_payload.json` | 143,799 | `b5a82c5ac0eecfb1e1a7dc51ccf470c0845335a2ef775ffc568d7c8bf0242ab4` | Public observation payload excluding private simulator state |

Verification metrics in `preflight.json`:
- `source_commit`: `acbf28449049dde6f059b28bfaa8a4c4ab019def`
- `git_status`: `clean`
- `is_dirty`: `false`
- `model_invocations`: `0`
- `physics_steps`: `0`
- `isolation_verified`: `true`

---

## Validation summary

All checks executed with `/Users/praveen/work/github/mujoco-llms/.venv/bin/python` from `/private/tmp/mujoco-llms-agy-007`.

### 1. Codex Policy Unit Suite (`tests/test_codex_policy.py`)
```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_codex_policy.py -v
```
Outcome: **20/20 tests passed** in 1.782s.

### 2. Related Regression Suites (`test_codex_c1_audit.py`, `test_humanoid_visual_policy_runner.py`)
```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_codex_c1_audit.py tests/test_humanoid_visual_policy_runner.py -v
```
Outcome: **33/33 tests passed** in 8.639s (3 audit tests + 30 runner tests).

### 3. Review Reproduction Script (`007-reproduce.py`)
```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/python /Users/praveen/work/github/mujoco-llms/coordination/agy/reviews/007-reproduce.py
```
Output snippet:
```json
{
  "all_three_c1_prompts_match_archives": true,
  "c2_text_matches_proposal": true,
  "geometry_digest": {
    "recorded_by_execute": "d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6",
    "actual_written_file": "d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6",
    "matches": true
  },
  "actual_geometry": {
    "source": "robot model, closure=0 joint targets, downward IK at nominal site [.24,-.18,.94]; no episode state",
    "world_offset_min_m": [-0.07355185900082623, -0.04160017704683794, -0.0769602209585496],
    "world_offset_max_m": [0.05720106964327992, 0.04139976336228118, 0.08474807814493945],
    "geom_count": 7
  },
  "metadata_cases": [
    {"metadata": {"condition": "c2", "condition_id": "c1", ...}, "callable_reached": false, "rejected_before_capture": true, "error": "Conflicting condition (c2) and condition_id (c1)"},
    {"metadata": {"protocol_id": "humanoid-codex-c1-development"}, "callable_reached": false, "rejected_before_capture": true, "error": "Mismatched model callable condition (c2) and execution metadata condition (c1)"},
    {"metadata": {"condition": "c2", "condition_id": "c2", ..., "model_requested": "gpt-5.6-sol"}, "callable_reached": false, "rejected_before_capture": true, "error": "Mismatched model callable model (other-model) and expected model (gpt-5.6-sol)"}
  ],
  "mocked_preflight": {
    "status": "complete",
    "source_commit": "acbf28449049dde6f059b28bfaa8a4c4ab019def",
    "model_invocations": 0,
    "physics_steps": 0
  }
}
Policy tests with injected auth/renderer: 20 success: True
```

### 4. Full Repository Test Discovery
```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v > coordination/agy/reports/007-full-discovery.log 2>&1
```
Outcome: **226/226 tests passed** in 177.447s (0 failures, 0 errors).
Retained log: `coordination/agy/reports/007-full-discovery.log`.

### 5. Git Diff Whitespace Check
```sh
git diff --check
```
Outcome: Clean (exit code 0).

### 6. C1 Immutability Check
```sh
git diff 87bce15dda8a99b8c8d9ff0bf3c657653a998eba --exit-code -- experiments/humanoid-pick-place/protocols/C1.md experiments/humanoid-pick-place/results/codex_C1*
```
Outcome: Clean (exit code 0). All C1 protocol documents and archived results are 100% byte-identical to starting commit `87bce15dda8a99b8c8d9ff0bf3c657653a998eba`.

---

## Limitations and next checkpoint

- **Status of C2**: C2 is fully implemented and qualified offline, but is **NOT marked frozen** and **has NOT been executed**.
- **Execution Authority**: Execution requires separate Codex review, protocol freeze, and explicit execution brief.
- **Proposed Frozen Run Command**:
  ```sh
  .venv/bin/mjpython -m humanoid_sim.codex_policy --execute --condition c2 --output runtime/humanoid/codex-C2/seed-820
  ```
  Requires macOS graphics access and signed-in Codex CLI ChatGPT authentication. Not executed during Task 007.
- **Review Handoff**: Codex reviews revised tip on branch `agy/007-c2-implementation`.
