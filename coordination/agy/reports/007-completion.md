# AGY completion — task 007

Status: **ready for review**
Task brief: `coordination/agy/tasks/007-c2-implementation.md`
Branch: `agy/007-c2-implementation`
Starting commit: `87bce15dda8a99b8c8d9ff0bf3c657653a998eba`
Worktree: `/private/tmp/mujoco-llms-agy-007`
Python interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`

---

## Changes and rationale

Task 007 implements explicit condition selection (`c1` default vs `c2`), prompt composition, static robot-only geometry enclosure verification, strict provenance tracking, and an offline-only preflight mode in `humanoid_sim/codex_policy.py` and `humanoid_sim/visual_policy_runner.py`.

### 1. Condition Selection and Prompt Preservation (`humanoid_sim/codex_policy.py`)
- **Default Condition**: `DEFAULT_CONDITION = 'c1'`, with `CONDITIONS = ('c1', 'c2')`.
- **C1 Prompt Preservation**: When `condition='c1'`, `public_input(payload, condition='c1')` reproduces the exact byte sequence of the original C1 prompt. Verified byte-for-byte in unit tests.
- **C2 Paragraph Inclusion**: When `condition='c2'`, `public_input(payload, condition='c2')` appends the exact nominal robot geometry paragraph from `experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md` immediately before the JSON schema:
  ```text
  The right hand nominal open bounding box spans [-0.05, 0.05] m in X, [-0.07, 0.07] m in Y, and [-0.17, 0.01] m in Z relative to right_grasp site. Reassess object position from visual observation before moving. Keep commanded grasp approaches clear of table surface and bounding box margins.
  ```
- **CLI Options**: Added `--condition {c1,c2}` to `main()`. Default is `'c1'`. Added `--executable` (default `'codex'`) to permit testing against alternative mock binaries without modifying system state.

### 2. Static Robot-Only Geometry Enclosure (`humanoid_sim/codex_policy.py`)
- **Independent Nominal Bounds**: Calculated strictly from robot MJCF geometry (`models/g1/assets/`) at nominal open-hand pose (`hand_targets(0)`):
  - Hand collision geoms: 14 geoms (`right_palm_collision`, `right_hand_thumb_0_collision` through `thumb_2`, `middle_0` through `middle_1`, `index_0` through `index_1`).
  - Nominal bounding box:
    - X: `[-0.0463, 0.0487]` m $\subset [-0.05, 0.05]$ m
    - Y: `[-0.0631, 0.0645]` m $\subset [-0.07, 0.07]$ m
    - Z: `[-0.1601, 0.0033]` m $\subset [-0.17, 0.01]$ m
- **Rounded Enclosure Verification**: `verify_nominal_bounds_enclosure()` programmatically verifies that all 14 hand collision geoms remain strictly inside the rounded box bounds defined in the C2 proposal.
- **Evidence Generation**: `generate_geometry_evidence()` exports a structured evidence dictionary (`geometry_evidence.json`) containing link names, geom names, local bounding boxes, and nominal enclosure confirmation.
- **Isolation from Object Truth**: The geometry contract is purely kinematic and robot-centric. Tests prove that altering object ground truth, table height, or scene objects in the simulation has zero effect on the computed geometry evidence.
- **Distinguishing Solid Robot Volume**: Unit tests prove that the nominal bounding box bounds solid robot collision geometry rather than an empty grasp cavity or free path: placing an object at the hand geom positions triggers collision contacts.

### 3. Provenance and Configuration Validation (`humanoid_sim/visual_policy_runner.py` & `codex_policy.py`)
- **Run Provenance**: Top-level `report.json` and `preflight.json` record:
  - `condition`: `'c1'` or `'c2'`
  - `condition_id`: matching condition string
  - `protocol_id`: `'humanoid-codex-c1-development'` for C1, `'humanoid-codex-c2-development'` for C2
  - `protocol_path`: path to protocol markdown file
  - `protocol_sha256`: SHA-256 hash of protocol file
  - `prompt_sha256` / `demonstration_prompt_sha256`: SHA-256 hash of exact prompt text
  - `geometry_evidence_sha256`: SHA-256 hash of geometry evidence JSON
  - `source_commit`: current git HEAD commit hash (`87bce15dda8a99b8c8d9ff0bf3c657653a998eba`)
- **Strict Validation**: In `run_visual_episode`, mismatched `condition` and `protocol_id` (e.g. `c1` with `humanoid-codex-c2-development` or vice versa) or mismatches between model callable condition and runner metadata are rejected with `ValueError` before simulator execution or turn invocation.

### 4. Offline Preflight Mode (`humanoid_sim/codex_policy.py:run_preflight`)
- Invoked when neither `--execute` nor `--probe` is specified.
- Uses static kinematics (`mujoco.mj_forward`, zero `mj_step` calls).
- Sets initial development pose (arm solve to `[.24, -.18, .94]`, open hand targets, seed 820 object placement).
- Renders initial camera observation (`RGBRenderer(camera='fixed')`).
- Builds public payload via `build_public_payload` using `PolicyInterface(env, 'robot_state').observe()`.
- Verifies input isolation: deliberately injects private oracle fields (`ground_truth_object_pos`, `private_oracle_score`) and confirms they are stripped.
- Verifies environment variable isolation: ensures no API keys (`OPENAI_API_KEY`, etc.) are exposed.
- Writes 5 artifacts to the new output directory:
  1. `observation.png`
  2. `public_payload.json`
  3. `prompt.txt`
  4. `geometry_evidence.json`
  5. `preflight.json`
- Confirms:
  - `model_invocations: 0`
  - `physics_steps: 0`
  - `isolation_verified: true`

### 5. Documentation Updates
- `experiments/humanoid-pick-place/CODEX_RUNNER.md`: Documented `--condition {c1,c2}`, C2 geometry evidence, C2 preflight, and proposed C2 frozen run command.
- `experiments/humanoid-pick-place/PLAN.md`: Updated Task 007 status and added next step for Codex review and protocol freeze.
- `coordination/agy/WORKFLOW.md`: Updated Task 007 status in the task register to "Ready for review".
- `coordination/agy/tasks/007-c2-implementation.md`: Updated status to "ready for review" and marked all acceptance criteria checkboxes complete.

---

## Validation

All checks were executed using the primary project virtual environment:
`/Users/praveen/work/github/mujoco-llms/.venv/bin/python` from `/private/tmp/mujoco-llms-agy-007`.

### 1. Codex Policy Unit Suite (`tests/test_codex_policy.py`)
- Command:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_codex_policy.py -v
  ```
- Outcome: **18/18 tests passed** in 1.866s.
- Tested:
  - `test_api_environment_not_forwarded`: confirms subprocess environment excludes API keys.
  - `test_budget_and_call_cap`: confirms call caps and budgets.
  - `test_c1_artifacts_and_frozen_protocol_unchanged`: confirms all C1 artifact and protocol hashes match git starting commit.
  - `test_c1_prompt_preservation_and_c2_paragraph_inclusion`: verifies byte-identical C1 prompt and exact C2 proposal text insertion.
  - `test_c1_rejects_changed_condition_before_login_or_execution`: rejects condition changes when running C1 protocol.
  - `test_condition_and_settings_mismatches_rejected`: verifies rejection of condition/protocol mismatches.
  - `test_corrupt_image_and_identity_mismatch_never_launch`: checks image integrity guards.
  - `test_fresh_public_only_sessions_and_tool_configuration`: checks clean session setup.
  - `test_geometry_altered_object_truth_cannot_affect_contract`: proves altered object positions cannot change robot geometry bounds.
  - `test_geometry_distinguishes_occupied_bounds_from_grasp_cavity_and_safe_path`: proves hand bounds enclose solid links and detects contacts.
  - `test_geometry_nominal_bounds_and_enclosure_verification`: validates nominal open hand bounds and enclosure.
  - `test_guarded_runner_records_condition_and_preserves_mock_identity`: validates provenance keys in guarded runner.
  - `test_offline_preflight_zero_model_invocations_and_artifacts`: validates preflight artifact creation, zero model calls, and zero physics steps.
  - `test_only_exact_disabled_host_notice_before_turn_is_allowed`: validates CLI event notice parsing.
  - `test_private_field_exclusion_and_payload_isolation`: validates allowlist stripping of private fields.
  - `test_requires_reviewed_cli_and_chatgpt_login`: validates CLI version and login method checks.
  - `test_timeout_nonzero_missing_and_invalid_output_retain_failure`: validates turn failure retention.
  - `test_tool_events_failed_turns_and_output_disagreement_stop`: validates rejection of tool events.

### 2. Related Regression Suites (`tests/test_codex_c1_audit.py`, `tests/test_humanoid_visual_policy_runner.py`)
- Command:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_codex_c1_audit.py tests/test_humanoid_visual_policy_runner.py -v
  ```
- Outcome: **36/36 tests passed** in 8.625s (3 audit tests + 33 visual policy runner tests).

### 3. Full Repository Test Discovery
- Command:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v > coordination/agy/reports/007-full-discovery.log 2>&1
  ```
- Outcome: **224/224 tests passed** in 175.289s (0 failures, 0 errors).
- Retained log: `coordination/agy/reports/007-full-discovery.log`.

### 4. Git Diff & Whitespace Check
- Command:
  ```sh
  git diff --check
  ```
- Outcome: Exit code 0 (clean, no trailing whitespace or conflicts).

### 5. C1 Immutability Check
- Command:
  ```sh
  git diff 87bce15dda8a99b8c8d9ff0bf3c657653a998eba -- experiments/humanoid-pick-place/protocols/C1.md experiments/humanoid-pick-place/results/codex_C1*
  ```
- Outcome: Exit code 0, 0 lines diff. All C1 artifacts and protocol files are 100% byte-identical to starting commit.

---

## Experiment evidence and boundary audit

- **Zero Model Invocations and Zero Physics Steps**:
  No model calls were made during Task 007. No Codex decisions were invoked; no Gemini VLA decisions were invoked; no OpenAI API requests or network calls were made. The simulation was never stepped (`physics_steps: 0`).
- **No Fresh Performance Episodes**:
  No fresh episode (C1, C2, or otherwise) was executed. Held-out validation seeds 840–849 remain untouched and strictly guarded.
- **C2 Preflight Run**:
  Executed offline preflight command:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.codex_policy --condition c2 --output runtime/humanoid/c2-preflight
  ```
  Generated artifacts and verified SHA-256 hashes:
  - `geometry_evidence.json`: `d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6`
  - `observation.png`: `3eaa19796fdce7c65da1a6b78bb88a6bdf923b541f235bbf61d7592fa6e74545`
  - `preflight.json`: `970ec694815a4bc4f8587ba721d9d8bd421d867f6d85d57113ae36a9b6de04e2`
  - `prompt.txt`: `439eb8ffb8d75436a032ccf9894e2b084487b365dcd27b39f1522caf8df9ae4b`
  - `public_payload.json`: `d27b2cd4c7f4f26c0892f9570f610533b256453c73487ddc2c0f61148c6cd770`

  In `preflight.json`, `demonstration_prompt_sha256` (`439eb8ffb8d75436a032ccf9894e2b084487b365dcd27b39f1522caf8df9ae4b`) matches `prompt.txt`, and `geometry_evidence_sha256` (`d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6`) matches `geometry_evidence.json`.

---

## Limitations and next checkpoint

- **Status of C2**: C2 is implemented and qualified offline, but is **NOT marked frozen** and **has NOT been executed**.
- **Execution Authority**: Execution requires separate review by Codex, formal protocol freeze, and an explicit execution authorization brief.
- **Proposed Frozen Run Command**:
  ```sh
  .venv/bin/mjpython -m humanoid_sim.codex_policy --execute --condition c2 --output runtime/humanoid/codex-C2/seed-820
  ```
  Note: This command requires macOS graphics access and signed-in Codex CLI ChatGPT authentication. It was **NOT** executed during Task 007.

- **Next Checkpoint**:
  Codex reviews Task 007 implementation, tests, and preflight evidence on branch `agy/007-c2-implementation`. If accepted, Codex freezes C2 and issues a separate execution task.
