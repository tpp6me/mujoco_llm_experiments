# AGY completion — task 001

Status: ready for review (revision 3 addressing Codex review R2-A and R2-B)
Task brief: `coordination/agy/tasks/001-reacquisition.md`
Branch: `agy/001-reacquisition`
Starting commit: `76f8c354755d9d747dc0d4b6a639aa21144e0271`
First handoff commit: `fceed20e86d772cb300cb4a5bf4fef722249cdc7`
Revision 2 commit: `266c7c3d57bc6d386cfb47e1874a1314b9d76dc3`

---

## 1. Response to Review Findings R2-A and R2-B (`001-review-r2.md`)

### R2-A (High) — Contain Preparation/Scoring Failures and Prevent History Leakage Across Stream Interruptions
- **Diagnosis:** In `evaluate_stream`, stimulus preparation occurred outside the estimator `try...except` block. Corrupt observation dictionaries (e.g. missing `camera` key in `black_transport`) raised `KeyError` and crashed the evaluator instead of retaining partial accounting. Furthermore, `frozen_transport_rgb` used `previous_image` rather than requiring the declared `lift_hold` stimulus, and interruptions did not explicitly clear tracker history.
- **Remedy:**
  - In `humanoid_sim/temporal_reacquisition_evaluation.py:evaluate_stream`:
    - Wrapped per-case stimulus preparation, observation structure checks, and post-estimation scoring in guarded blocks.
    - Black transport validates camera geometry; missing or invalid dimensions produce a `preparation_error`, retain the grid record, and continue.
    - Frozen transport strictly requires the declared `lift_hold` observation and its `rgb_png_base64`. If missing or invalid, it marks `status: 'stimulus_unavailable'` with a specific message, avoiding fallback to older images or leaving transport unaltered.
    - Tracking history is explicitly invalidated (`tracker.invalidate()`) whenever a stream is interrupted by missing stages, missing/malformed observation files, stimulus preparation failures, or estimator exceptions.
  - In `humanoid_sim/temporal_reacquisition_evaluation.py:evaluate_dataset`:
    - Hardened capture JSON loading against malformed structures (non-list `private_records.json`, non-dict stage records, and non-dict observation files).
  - In `tests/test_temporal_reacquisition_evaluation.py`:
    - Added `test_corrupt_transport_metadata_retains_accounting_and_clears_history` (verifying missing camera metadata raises no uncaught exception, records `preparation_error`, and clears tracker frames).
    - Added `test_malformed_loaded_json_structure_retains_accounting` (verifying dictionary/non-list `private_records.json` and non-dict observation files produce `incomplete` status while retaining expected grid accounting).
    - Added `test_unavailable_frozen_image_source_marks_stimulus_unavailable` (verifying missing or empty `lift_hold` image marks `stimulus_unavailable` and clears tracker history).

### R2-B (High) — Count Emitted Poses Independently of Ground Truth and Mark Incomplete on Missing Truth
- **Diagnosis:** In `compute_aggregate`, `accepted` was computed as `len(errors)`, where `errors` was the list of non-null `error_3d_m` values. When ground truth `private_true_xyz_m` was null, absent, or non-finite, emitted poses (`detected: True`) disappeared from acceptance counts, reporting 0 accepted poses despite valid estimator detections, while labeling the unscored dataset `complete`.
- **Remedy:**
  - In `humanoid_sim/temporal_reacquisition_evaluation.py`:
    - `accepted` and `post_warmup_accepted` now count all emitted detections (`estimate['detected'] is True`) regardless of whether 3D error could be computed.
    - Added evaluator-side helper `is_valid_truth_xyz` that validates ground truth post-hoc (must be 3 finite floats) without leaking any private truth into the estimator.
    - Records classify scoring under `scoring_status` (`scored`, `not_detected`, `unscored_missing_truth`, `unscored_invalid_truth`, `missing_or_invalid_truth`).
    - Aggregates explicitly report `scored_responses`, `unscored_accepted`, and `missing_or_invalid_truth`.
    - If any required ground truth is missing, null, absent, or non-finite (`missing_or_invalid_truth > 0`), the dataset status is marked `incomplete`.
  - In `tests/test_temporal_reacquisition_evaluation.py`:
    - Added `test_null_absent_and_nonfinite_truth_retains_acceptance_and_marks_incomplete` (verifying that null truth, absent truth keys, and NaN truth with a mock tracker emitting accepted poses preserve all 6 accepted detections, report 0 scored responses, mark overall status `incomplete`, and retain the expected grid).

---

## 2. Response to Previous Findings (R1, R3, R4) Preserved

- **R1 (Invalid Calibration):** Camera rotation orthonormality and positive determinant (`det(R) == +1`, `atol=1e-4`) enforced in `prepare_frame`. Invalid calibrations call `self.invalidate()` and clear history.
- **R3 (Regression Coverage):** Restored baseline assertion, verified fresh-window bounds at fitting boundary, exercised duplicate/equal/regressing timestamps, verified episode reset isolation, and tested corrupt/truncated images.
- **R4 (Evidence & Coordinates):** Documented 180 total responses across 3 streams (20 altered transport frames); stated Seed 820 error in world frame `[+1.120, -6.500, +20.922]` mm and camera frame `[+1.120, -2.951, -21.708]` mm along optical axis $+Z_c$; labeled depth ambiguity as a hypothesis; verified zero whitespace warnings across revision range.

---

## 3. Estimator and Policy Boundaries Preserved

- **Estimator Untouched:** No changes to `TemporalPose` or `TemporalReacquisitionPose` fitting, thresholds, or recovery logic in `humanoid_sim/temporal_pose.py`.
- **Disconnected from Control:** `PerceptionSession` and driving policies remain completely untouched.
- **No Validation Leakage:** No fresh episodes on held-out seeds 840–849 executed.
- **No Branch Merge:** Working branch `agy/001-reacquisition` remains separate from `main`.

---

## 4. Validation Evidence

All checks executed from `/private/tmp/mujoco-llms-agy-001` using Python interpreter `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`:

1. **Targeted Unit Tests (27/27 Passed):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest \
     tests/test_temporal_reacquisition_evaluation.py \
     tests/test_humanoid_temporal_pose.py -v
   ```
   **Outcome:** 9 evaluator tests and 18 temporal pose tests ran, all 27 passed.

2. **Full Repository Test Discovery (106/106 Passed in 89.6s):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v
   ```
   **Outcome:** 106 tests ran, 106 passed without regressions.

3. **Development Dataset Evaluation Rerun:**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.temporal_reacquisition_evaluation \
     --capture-dir /Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture \
     --output experiments/humanoid-pick-place/results/temporal_reacquisition_development.json
   ```
   **Outcome:** `Evaluation finished with status: complete.`
   - 60 responses evaluated per stream across 3 streams (180 total).
   - Baseline P4: 14/20 post-warmup targets accepted (all 14 scored and within 20 mm; max error 7.42 mm).
   - Reacquisition candidate: 17/20 post-warmup targets accepted (all 17 scored; 16 within 20 mm, 1 exceeding 20 mm: Seed 820 Lower at 21.94 mm).
   - Disruption streams: 0 accepted on black transport (0/10) and frozen transport RGB (0/10); 0 accepted on release or retract (0/20).
   - Results file updated at `experiments/humanoid-pick-place/results/temporal_reacquisition_development.json`.

4. **Revision Diff Check Against Task Base:**
   ```sh
   git diff --check 76f8c35
   ```
   **Outcome:** Exited with code 0; clean whitespace and formatting.

---

## 5. Git History and Handoff

- Working branch: `agy/001-reacquisition` (worktree at `/private/tmp/mujoco-llms-agy-001`).
- Main checkout `/Users/praveen/work/github/mujoco-llms` remains clean on `main`.
- History preservation: Initial task handoff commit `fceed20e86d772cb300cb4a5bf4fef722249cdc7` and revision 2 commit `266c7c3d57bc6d386cfb47e1874a1314b9d76dc3` preserved.
- Status: **Ready for Codex review**.
