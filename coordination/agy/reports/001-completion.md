# AGY completion — task 001

Status: ready for review (revision 2 addressing Codex review R1–R4)
Task brief: `coordination/agy/tasks/001-reacquisition.md`
Branch: `agy/001-reacquisition`
Starting commit: `76f8c354755d9d747dc0d4b6a639aa21144e0271`
First handoff commit: `fceed20e86d772cb300cb4a5bf4fef722249cdc7`

---

## 1. Response to Codex Review Findings (R1–R4)

### R1 (High) — Reject Invalid Calibration and Prevent Invalid Seeding
- **Diagnosis:** `prepare_frame` validated matrix shape and finiteness, but did not check orthonormality or positive unit determinant. In invalid calibrations (such as zero, scaled, or reflection matrices), `prepare_frame` passed the geometry to downstream fitters. On fit mismatch, the recovery path seeded the invalid frame into `tracker.frames`.
- **Remedy:**
  - In `humanoid_sim/temporal_pose.py:prepare_frame`: Added explicit checks verifying `np.allclose(cam_rot.T @ cam_rot, np.eye(3), atol=1e-4)` and `np.isclose(np.linalg.det(cam_rot), 1.0, atol=1e-4)`. Any non-orthonormal, scaled, reflection, or non-finite matrix raises `ValueError`.
  - In `TemporalPose.observe`: Any exception raised in `prepare_frame` triggers `self.invalidate()`, clearing all history and preventing invalid calibration from ever seeding reacquisition.
  - In `tests/test_humanoid_temporal_pose.py`: Added `test_invalid_camera_rotation_rejected_and_never_seeds` (exercising all-zeros, scaled, reflection, and valid calibration matrices) and `test_malformed_robot_and_calibration_inputs_after_seed_clears_history` (exercising NaN hand positions, zero quaternions, negative focal lengths, infinite camera origins, and zero rotation matrices arriving after a valid seed).

### R2 (High) — Complete Evaluator Grid and Denominator Accounting
- **Diagnosis:** The initial evaluation runner derived target counts dynamically from whatever records it encountered in `private_records.json`. An empty records list or truncated episode would silently undercount expected responses or post-warmup targets, returning `status: complete`. In addition, missing observation files or tracker exceptions could abort without retaining partial accounting.
- **Remedy:**
  - In `humanoid_sim/temporal_reacquisition_evaluation.py`: Pre-builds an expected grid across `(seed, stage, variant)`.
  - Seed validation: Materializes seed iterables once and enforces non-empty, positive integers.
  - Denominator accounting: Nominal post-warmup target count is fixed at 2 per requested seed (20 for 10 seeds). Distinguishes `expected_responses` (60 per stream, 180 total), `evaluated_responses`, and `missing_responses`.
  - Fault tolerance: Explicitly handles and records `missing_stage`, `missing_observation_file`, and `estimator_error` without crashing, preserving seed, stage, and variant details. If any stage is missing or errored, overall status is marked `incomplete`.
  - In `tests/test_temporal_reacquisition_evaluation.py`: Added 5 focused unit tests covering: empty records list, early-stopped episodes, missing observation files, estimator exceptions, and invalid seed requests.
  - Re-executed development evaluation across seeds 820–829; all 180 records per candidate evaluated with 0 missing responses and `status: complete`.

### R3 (Medium) — Restore and Strengthen Regression Coverage
- **Diagnosis:** Review identified: (1) omission of `self.assertEqual(tracker.frames, [])` in `test_reused_or_nonadvancing_frames_clear_history`; (2) self-comparison assertion in `test_reacquisition_sufficient_motion_fits_fresh_window`; (3) candidate nonadvancing test covered only duplicate IDs; (4) lack of episode reset isolation test with a fresh tracker instance; (5) lack of corrupt/truncated image tests.
- **Remedy:**
  - Restored `self.assertEqual(tracker.frames, [])` in `test_reused_or_nonadvancing_frames_clear_history`.
  - Patched `fit_window` in `test_reacquisition_sufficient_motion_fits_fresh_window` to assert the fitted window contains exactly 2 frames `[seed, new_frame]` with matching timestamps, excluding the rejected old window frames.
  - Updated `test_reacquisition_reused_or_nonadvancing_clears_seeded_history` to test duplicate IDs, equal timestamps, and regressing timestamps after reacquisition seeding.
  - Added `test_reacquisition_episode_reset_isolation` verifying that creating a new tracker instance for a new episode accepts reset-time observations (`time_s = 0.5`) without leaking prior episode frames or transforms.
  - Added `test_truncated_or_corrupt_image_never_seeds` (verifying corrupted base64, invalid PNG bytes, and empty black frames never seed recovery).
  - Total test suite expanded from 84 baseline tests to 93 in first handoff, and now to 102 tests in this revision (all 102 passing).

### R4 (Medium) — Correct Evidence Claims, Coordinates, and Formatting
- **Response count correction:** Clarified that the two disruption streams contain 120 responses (60 each) across 2 streams altering only 20 transport frames in total, for 180 total responses across 3 streams.
- **Seed 820 coordinate clarification:**
  - World error vector: `[+1.120, -6.500, +20.922]` mm (norm = 21.937 mm).
  - Camera-frame error vector ($R_{w\to c} \Delta x_w$): `[+1.120, -2.951, -21.708]` mm.
  - The -21.7 mm component aligns along the camera optical axis $+Z_c$, placing the fitted center closer to the camera than ground truth.
- **Depth ambiguity as hypothesis:** Labeled depth ambiguity as a hypothesis consistent with this camera-frame error vector, acknowledging other possible contributing factors (silhouette boundary segmentation fidelity, local optimizer convergence, subtle non-rigid finger compliance), without claiming a 3-frame history unconditionally resolves it.
- **Runner provenance and test logs:** Documented exact runner commands, input provenance (`/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture/`), reviewer 93-test log (`coordination/agy/reviews/001-tests.txt`), and revised 102-test log.
- **Whitespace check:** Fixed trailing whitespace on lines 3–5 and 12 of `TEMPORAL_REACQUISITION_DEVELOPMENT.md`. Verified `git diff --check 76f8c35` passes with zero errors across the entire revision range.

---

## 2. Changes Summary by File

1. **`humanoid_sim/temporal_pose.py`**:
   - `prepare_frame`: Enforces camera rotation matrix orthonormality and positive determinant (`det(R) == +1`, `atol=1e-4`), raising `ValueError` on invalid calibration.
   - `TemporalPose.observe`: Calls `self.invalidate()` upon any exception in `prepare_frame`.
   - Preserves `TemporalReacquisitionPose` opt-in subclass; default `TemporalPose()` retains baseline behavior.
   - Preserves complete disconnection from control.

2. **`humanoid_sim/temporal_reacquisition_evaluation.py`**:
   - Constructs expected `(seed, stage, variant)` grid upfront.
   - Validates seed input (rejects empty/negative/non-integer seeds).
   - Distinguishes expected, evaluated, and missing responses.
   - Post-warmup targets fixed at $2 \times N_{\text{seeds}}$ (20 for 10 seeds).
   - Retains accounting on missing stages, missing files, or estimator exceptions, setting run status to `incomplete`.
   - Re-executed development evaluation across seeds 820–829; output saved to `experiments/humanoid-pick-place/results/temporal_reacquisition_development.json`.

3. **`tests/test_temporal_reacquisition_evaluation.py`** (new):
   - 5 unit tests validating evaluator denominator accounting and error retention:
     - `test_empty_records_list_retains_accounting_and_marks_incomplete`
     - `test_early_stopped_episode_retains_accounting`
     - `test_missing_observation_file_retains_accounting`
     - `test_estimator_exception_retains_accounting_and_details`
     - `test_invalid_seed_requests_rejected`

4. **`tests/test_humanoid_temporal_pose.py`**:
   - Restored original `self.assertEqual(tracker.frames, [])` assertion.
   - Fixed `test_reacquisition_sufficient_motion_fits_fresh_window` with explicit window verification.
   - Added `test_reacquisition_episode_reset_isolation`.
   - Added `test_invalid_camera_rotation_rejected_and_never_seeds`.
   - Added `test_malformed_robot_and_calibration_inputs_after_seed_clears_history`.
   - Added `test_truncated_or_corrupt_image_never_seeds`.
   - Extended `test_reacquisition_reused_or_nonadvancing_clears_seeded_history` for duplicate IDs, equal timestamps, and regressing timestamps.

5. **`experiments/humanoid-pick-place/TEMPORAL_REACQUISITION_DEVELOPMENT.md`**:
   - Updated response counts (180 total responses across 3 streams, 20 altered transport frames).
   - Documented Seed 820 error in both world frame `[+1.120, -6.500, +20.922]` mm and camera frame `[+1.120, -2.951, -21.708]` mm.
   - Labeled depth ambiguity as a hypothesis.
   - Documented exact runner invocation, input provenance, and test log references.
   - Removed all trailing whitespace.

6. **`experiments/humanoid-pick-place/protocols/P5_PROPOSAL.md`**:
   - Updated Seed 820 error coordinates and camera optical axis signs.
   - Labeled depth ambiguity as a hypothesis.
   - Preserved proposed status; no fresh validation executed.

---

## 3. Validation Evidence

All checks executed from `/private/tmp/mujoco-llms-agy-001` using Python interpreter `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`:

1. **Targeted Reacquisition & Evaluator Unit Tests**:
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest \
     tests/test_temporal_reacquisition_evaluation.py \
     tests/test_humanoid_temporal_pose.py -v
   ```
   **Outcome:** 23 tests ran, 23 passed in 48.844s.

2. **Full Repository Test Discovery**:
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v
   ```
   **Outcome:** 102 tests ran, 102 passed in 90.166s. All 84 baseline tests, 9 task-001 tests, and 9 review-fix tests passed without regression.

3. **Development Dataset Evaluation**:
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.temporal_reacquisition_evaluation \
     --capture-dir /Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture \
     --output experiments/humanoid-pick-place/results/temporal_reacquisition_development.json
   ```
   **Outcome:** `Evaluation finished with status: complete.`
   - Evaluated 60 responses per stream (180 total across 3 streams) with 0 missing responses.
   - Post-warmup targets: 20 per stream.
   - Baseline P4: 14/20 post-warmup accepted (all 14 within 20 mm; max error 7.42 mm).
   - Reacquisition candidate: 17/20 post-warmup accepted, 16/20 within 20 mm (max error 21.94 mm on Seed 820 Lower).
   - Disruption streams: 0 accepted on black transport (0/10) and frozen transport RGB (0/10); 0 accepted on release or retract (0/20).

4. **Revision Diff Check Against Task Base**:
   ```sh
   git diff --check 76f8c35
   ```
   **Outcome:** Exited with code 0; zero whitespace or formatting warnings across all modified and new files.

5. **Checks Categorization**:
   - *Executed*: Unit test suite (102 tests), offline development evaluation runner across seeds 820–829 on 3 streams.
   - *Proposed*: Protocol P5 on held-out seeds 840–849.
   - *Excluded*: Fresh validation execution (no seeds 840–849 consumed), merging to `main`, and active control integration.

---

## 4. Git History and Handoff

- Working branch: `agy/001-reacquisition` (worktree at `/private/tmp/mujoco-llms-agy-001`).
- Clean separation: Main working copy `/Users/praveen/work/github/mujoco-llms` remains untouched on `main`.
- History preservation: Initial task handoff commit `fceed20e86d772cb300cb4a5bf4fef722249cdc7` preserved; changes committed as a clean subsequent commit.
- Status: **Ready for Codex review**.
