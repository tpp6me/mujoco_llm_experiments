# AGY completion — task 001

Status: ready for review
Task brief: `coordination/agy/tasks/001-reacquisition.md`
Branch: `agy/001-reacquisition`
Starting commit: `76f8c354755d9d747dc0d4b6a639aa21144e0271`

## Changes and rationale

1. **`humanoid_sim/temporal_pose.py`**:
   - Extended `TemporalPose.__init__` with optional `reacquisition=False` parameter, preserving 100% of historical P4 behavior by default.
   - Defined `TemporalReacquisitionPose` subclass as an explicit opt-in candidate for reacquisition tracking.
   - On model mismatch (`inconsistent_rigid_transform`), if reacquisition is enabled, retains the current valid image as a new single-frame seed (`self.frames = [frame]`).
   - The new seed emits **no immediate 3D center** and inherits **no prior transform parameters**.
   - Requires subsequent fresh motion evidence (minimum 80 mm hand translation across multiple frames) before attempting a fit.
   - Preserved rigorous input guards: malformed metadata, duplicate IDs, nonadvancing timestamps, camera/robot calibration errors, and visibility loss (`frame is None`) immediately invalidate the tracker and clear all history (`self.frames.clear()`), preventing corrupted imagery from seeding reacquisition.
   - Maintained disconnection from control; `PerceptionSession` and driving policies remain completely untouched.

2. **`humanoid_sim/temporal_reacquisition_evaluation.py`**:
   - Created reproducible offline evaluation runner comparing baseline P4 (`reacquisition=False`) and the reacquisition candidate side-by-side on captured development datasets.
   - Reuses existing geometry and observation extraction; evaluates all stages (`lift`, `lift_hold`, `transport`, `lower`, `release`, `retract`) across nominal, black transport, and frozen transport RGB streams.

3. **`tests/test_humanoid_temporal_pose.py`**:
   - Added 9 focused unit tests (increasing suite from 84 to 93 tests) exercising: default P4 preservation, valid reacquisition seeding, withholding immediate positions, insufficient motion refusals (<80 mm), multi-frame fitting on sufficient motion (>=80 mm), visibility loss clearing, invalid metadata clearing, duplicate ID / timestamp regression clearing, time gap clearing, and explicit invalidation / reset.

4. **`experiments/humanoid-pick-place/protocols/P5_PROPOSAL.md`**:
   - Drafted proposed successor protocol P5 explicitly marked **proposed, not frozen or executed**.
   - Proposed held-out seeds 840–849 (verified unused in repository history).
   - Specified action and time budget accounting for potential active recovery motions.

5. **`experiments/humanoid-pick-place/TEMPORAL_REACQUISITION_DEVELOPMENT.md`**:
   - Documented complete comparative development accounting on seeds 820–829, detailing the recovery on seeds 825 and 828 and diagnosing the Seed 820 depth ambiguity failure.

6. **`experiments/humanoid-pick-place/PLAN.md`**:
   - Updated living checklist next actions and added a dated progress log entry.

Deviations from the brief: None.

## Validation

All checks executed from `/private/tmp/mujoco-llms-agy-001` using `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`:

1. **Targeted Temporal Tests**:
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_humanoid_temporal_pose.py -v
   ```
   Outcome: 14 tests ran, 14 passed (Ran in 38.97s).

2. **Complete Test Suite Baseline & Regression Check**:
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v
   ```
   Outcome: 93 tests ran, 93 passed (Ran in 86.88s). Preserved all 84 baseline tests without regression.

3. **Git Diff Check**:
   ```sh
   git diff --check
   ```
   Outcome: Passed with zero whitespace or formatting errors.

4. **Checks Distinguished**:
   - *Executed*: Unit test suite (93 tests), offline development evaluation across seeds 820–829 on 3 streams (180 responses per candidate).
   - *Proposed*: Protocol P5 on held-out seeds 840–849.
   - *Blocked / Excluded*: Fresh validation execution (preventing validation-set leakage prior to Codex review); control integration (candidate remains offline).

## Experiment evidence

- **Dataset Provenance**: Historical P4 capture trajectories for seeds 820–829 at `/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture/`. All findings are strictly **development-only**.
- **Observation Isolation**: Neither candidate accessed private object ground truth, private rotations, or scorer states. Ground-truth 3D errors and hand-relative center drift were evaluated strictly post-hoc after candidate returns.
- **Results on Nominal Original Stream (60 observations, 10 seeds)**:
  - Post-warmup targets (transport & lower): 20 targets.
  - Baseline P4: 14/20 accepted (70%), all 14 <= 20 mm. Mean error: 3.645 mm, max error: 7.420 mm.
  - Reacquisition candidate: 17/20 accepted (85%), 16/20 <= 20 mm (80%).
  - Accepted-only metrics (reacquisition): Mean error 4.744 mm, max error 21.937 mm.
  - Accepted <= 20 mm metrics (reacquisition): Mean error 3.669 mm, max error 7.420 mm.
  - Exceeded 20 mm: 1 target (Seed 820 Lower: 21.94 mm).
  - Warmup: 20/20 refused (`insufficient_motion_history`).
  - Relationship-loss endpoints (release & retract): 0/20 accepted (20/20 refused with `inconsistent_rigid_transform`).
- **Correlated Sensor Disruption Streams**:
  - `black_transport` (60 observations): 0 accepted. 40 `insufficient_motion_history`, 10 `insufficient_visible_boundary`, 10 `inconsistent_rigid_transform`.
  - `frozen_transport_rgb` (60 observations): 0 accepted. 30 `insufficient_motion_history`, 30 `inconsistent_rigid_transform`.
- **Artifacts**:
  - Development summary and records: `experiments/humanoid-pick-place/results/temporal_reacquisition_development.json`.
  - Analysis report: `experiments/humanoid-pick-place/TEMPORAL_REACQUISITION_DEVELOPMENT.md`.
  - Proposed protocol: `experiments/humanoid-pick-place/protocols/P5_PROPOSAL.md`.

## Limitations and next checkpoint

1. **Monocular 2-Frame Depth Ambiguity**:
   - In Seed 820, Lower was accepted with 21.94 mm error despite a 0.504 px silhouette RMS. 20.9 mm of the error was along the camera viewing axis (Z), demonstrating that a 2-frame window (`[transport, lower]`) lacks the parallax needed to fully constrain depth for a 5 × 7 × 12 cm block from a single camera.
2. **Control Disconnection**:
   - The candidate remains strictly offline and must not be connected to the acting controller.
3. **Next Checkpoint**:
   - Codex review of branch diff, evidence, and proposed protocol `P5_PROPOSAL.md`.
   - Consideration of requiring either a 3-frame history or explicit active motion before qualifying reacquired poses.
