# AGY completion — task 002

Status: ready for review
Task brief: `coordination/agy/tasks/002-reacquisition-evidence.md`
Branch: `agy/002-reacquisition-evidence`
Starting commit: `64bc19a00a03a83a3dc44f75225d6be619a3a754`

---

## Changes and rationale

1. **Opt-In Three-Frame Recovery Candidate (`humanoid_sim/temporal_pose.py`):**
   - Implemented `TemporalThreeFrameReacquisitionPose(TemporalPose)` (`min_reacquisition_frames=3`), leaving Task 001's `TemporalReacquisitionPose(min_reacquisition_frames=2)` and default P4 `TemporalPose(reacquisition=False)` behavior completely unchanged.
   - When a rigid transform inconsistency occurs, reacquisition is seeded with the current valid observation (`self.frames = [frame]`, `self.recovering = True`).
   - While recovering, the tracker requires at least `min_reacquisition_frames` distinct fresh observations since the recovery seed (and $\ge 80$ mm hand motion baseline) before calling `fit_window` or emitting a center.
   - Preserves all numerical fit, ambiguity, and baseline thresholds (80 mm baseline, 2 px RMS, 1.5 cm center spread).
   - No rejected transform or previous 3D center is inherited; pre-rejection observations are never recycled.
   - `self.recovering` resets to `False` upon a successful detection (`detected: True`) or invalidation (`invalidate()`).

2. **Deterministic Lowering Midpoint Observation (`humanoid_sim/temporal_reacquisition_evaluation.py`):**
   - Added `render_augmented_dataset` to synthesize intermediate lowering observations from saved P4 trajectories.
   - Schedule is strictly deterministic based on action timestamps only: $t_{\text{mid}} = (t_{\text{transport}} + t_{\text{lower}}) / 2 = 12.0$s (lowering action spans $t=11.0$s to $t=13.0$s across all development episodes). Never selects views using private object pose, error, or score feedback.
   - Renders exact physical states from `episode/episode.npz` using unchanged MuJoCo physics, scene models, and camera parameters into an isolated workspace directory (`runtime/humanoid/temporal-P4-augmented/capture/`), keeping the source capture directory under `runtime/humanoid/temporal-P4/capture/` strictly read-only.
   - Mapped stage observations robustly via record image filename prefixes (e.g. `06b-observation.json`, `07-observation.json`) with numerical index fallbacks.

3. **Comparative Evaluation and Fixed-Grid Accounting (`humanoid_sim/temporal_reacquisition_evaluation.py`):**
   - Added `evaluate_evidence` to execute paired evaluation across original endpoint-only streams (6 stages, 60 responses/variant) and augmented streams (7 stages, 70 responses/variant) for three configurations: `baseline_p4`, `reacquisition_2frame`, and `reacquisition_3frame`.
   - Fixed nominal post-warmup targets at 2 per seed (`transport` and `lower`), giving 20 post-warmup targets across all 10 seeds, ensuring the denominator is not distorted by intermediate observations.
   - Retained full grid accounting: missing responses, malformed records, preparation errors, estimator exceptions, unscored acceptances, and invalid truth remain distinct and visible.

4. **Focused Unit Tests (`tests/test_humanoid_temporal_pose.py`, `tests/test_temporal_reacquisition_evaluation.py`):**
   - `test_three_frame_reacquisition_refuses_after_only_two_views`: proves the 3-frame candidate cannot emit after only two views (even with $\ge 80$ mm baseline motion), while the 2-frame candidate does emit on the exact same input.
   - `test_three_frame_reacquisition_fits_on_third_fresh_view`: verifies that on the third fresh view with $\ge 80$ mm motion, the 3-frame candidate fits across all 3 frames `[seed, view-2, view-3]` without recycling pre-rejection observations, and resets `recovering = False`.
   - `test_three_frame_reacquisition_invalidation_and_gap`: verifies invalidation and time gaps ($> 3.0$s) clear history and reset `recovering = False`.
   - `test_three_frame_reacquisition_evaluation_accounting_original_vs_augmented`: verifies evaluator accounting for 3-frame candidate across 6-stage and 7-stage streams, confirming post-warmup targets remain fixed at 2 per seed.

5. **Disconnections and Boundaries:**
   - The reacquisition candidates remain completely disconnected from control (`PerceptionSession` and driving policies untouched).
   - No fresh validation executed: seeds 840–849 remain untouched.

---

## Validation

All checks executed in worktree `/private/tmp/mujoco-llms-agy-002` using Python interpreter `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`:

1. **Targeted Temporal Pose Unit Tests (21/21 Passed):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_humanoid_temporal_pose.py -v
   ```
   **Outcome:** 21/21 tests passed (59.75s). Retained log: `.system_generated/tasks/task-760.log`.

2. **Evaluator Accounting Unit Tests (10/10 Passed):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_temporal_reacquisition_evaluation.py -v
   ```
   **Outcome:** 10/10 tests passed (55.29s). Retained log: `.system_generated/tasks/task-828.log`.

3. **Full Repository Test Discovery (110/110 Passed):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v
   ```
   **Outcome:** 110/110 tests passed across all test modules (186.23s). Retained log: `.system_generated/tasks/task-832.log`.

4. **Comparative Evidence Evaluation on Development Seeds 820–829:**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.temporal_reacquisition_evaluation \
     --capture-dir /Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture \
     --augmented-dir runtime/humanoid/temporal-P4-augmented/capture \
     --output experiments/humanoid-pick-place/results/temporal_reacquisition_development.json \
     --output-evidence experiments/humanoid-pick-place/results/temporal_reacquisition_evidence_development.json \
     --start-seed 820 --count 10 --compare
   ```
   **Outcome:** Status `complete`. Retained log: `.system_generated/tasks/task-838.log`.
   Generated evidence artifacts:
   - `experiments/humanoid-pick-place/results/temporal_reacquisition_evidence_development.json`
   - `experiments/humanoid-pick-place/results/temporal_reacquisition_development.json`
   - `experiments/humanoid-pick-place/TEMPORAL_REACQUISITION_EVIDENCE.md`

5. **Git Diff and Whitespace Check:**
   ```sh
   git diff --check 64bc19a00a03a83a3dc44f75225d6be619a3a754..HEAD
   ```
   **Outcome:** Exited with code 0 (clean formatting, no trailing whitespace).

---

## Experiment evidence

### Provenance and Scope
- **Dataset:** Development seeds **820–829** only. Status: **development evidence** (not fresh validation).
- **Source Read-Only Check:** Read-only P4 data at `/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture/` was strictly read; augmented states rendered to `runtime/humanoid/temporal-P4-augmented/capture/`.
- **Private Truth Isolation:** Trackers received public RGB, camera calibration, and robot state only. Ground truth object poses and drift metrics were computed post-hoc by the evaluator after estimation returned.

### Aggregate Performance Across Development Seeds 820–829

| Stream | Candidate | Accepted / Total | Post-Warmup Accepted / Targets | $\le 20$ mm | $> 20$ mm | Mean Error | Max Error | Release/Retract Accepted |
|---|---|---|---|---|---|---|---|---|
| **Original** (6-stage) | `baseline_p4` | 14 / 60 | 14 / 20 | 14 | 0 | 3.64 mm | 7.42 mm | 0 |
| **Original** (6-stage) | `reacquisition_2frame` | 17 / 60 | 17 / 20 | 16 | 1 (Seed 820) | 4.74 mm | **21.94 mm** | 0 |
| **Original** (6-stage) | `reacquisition_3frame` | 14 / 60 | 14 / 20 | 14 | 0 | 3.64 mm | 7.42 mm | 0 |
| **Augmented** (7-stage) | `baseline_p4` | 21 / 70 | 14 / 20 | 21 | 0 | 4.82 mm | 9.44 mm | 0 |
| **Augmented** (7-stage) | `reacquisition_2frame` | 24 / 70 | 17 / 20 | **24** | **0** | 5.07 mm | **14.85 mm** | 0 |
| **Augmented** (7-stage) | `reacquisition_3frame` | 24 / 70 | 17 / 20 | **24** | **0** | 5.07 mm | **14.85 mm** | 0 |

### Per-Seed Slipped Recovery Breakdown at Lower ($t=13.0$s)

| Seed | Original 2-Frame Error | Original 3-Frame Status | Augmented 3-Frame Error | Gate ($\le 20$ mm) |
|---|---|---|---|---|
| **820** | **21.94 mm** | Refused (`insufficient_motion_history`) | **14.85 mm** | **Pass** |
| **825** | 2.66 mm | Refused (`insufficient_motion_history`) | 4.00 mm | **Pass** |
| **828** | 5.03 mm | Refused (`insufficient_motion_history`) | 1.56 mm | **Pass** |

### Motion Baseline and Refusal Mechanics
- **Midpoint ($t=12.0$s):** Hand translation from transport is 65–72 mm ($< 80$ mm threshold). Both 2-frame and 3-frame candidates refuse on recovering seeds with `insufficient_motion_history` (0 positions emitted at midpoint for Seeds 820, 825, 828).
- **Lower endpoint ($t=13.0$s):** Total hand translation reaches 97–104 mm ($\ge 80$ mm).
  - In original stream, only 2 frames exist (`[transport, lower]`). `TemporalThreeFrameReacquisitionPose` refuses on Seeds 820, 825, 828 (`insufficient_motion_history`), demonstrating it cannot emit after only 2 views.
  - In augmented stream, 3 frames exist (`[transport, lower_mid, lower]`). Triangulation over 3 distinct views resolves the optical-axis depth ambiguity, reducing Seed 820 error from 21.94 mm down to 14.85 mm.

### Disruption Stream Robustness
- `black_transport`: 0/60 and 0/70 accepted across all candidates and streams.
- `frozen_transport_rgb`: 0/60 and 0/70 accepted across all candidates and streams.
- Physical release and retract: 0 accepted across all candidates and streams.

### Latency and Communication Cost
- Additional observations require RGB capture, serialization, and non-linear optimization time. While simulated physical trajectory duration is unchanged (25.0s), an acting controller making intermediate perception calls incurs compute latency. No 25-second real-time controller qualification is claimed.

---

## Limitations and next checkpoint

1. **Limitations:**
   - The 3-frame reacquisition candidate requires an intermediate observation during lowering to achieve reacquisition before the lower endpoint. Under an endpoint-only schedule, it refuses at lower.
   - While Seed 820 error dropped to 14.85 mm, it is closer to the 20 mm threshold than nominal tracking seeds (mean error ~5 mm).
   - The tracker remains disconnected from control.

2. **Recommendation for Protocol P5:**
   - Incorporate a deterministic lowering midpoint ($t=12.0$s) into the trajectory capture schedule.
   - Use `TemporalThreeFrameReacquisitionPose` as the candidate estimator for P5 validation, ensuring both 17/20 coverage and 100% $\le 20$ mm accuracy on development trajectories.
   - Protocol P5 remains proposed in `experiments/humanoid-pick-place/protocols/P5_PROPOSAL.md`. Seeds 840–849 remain untouched pending review.
