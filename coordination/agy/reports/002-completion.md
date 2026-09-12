# AGY completion — task 002

Status: ready for review (revision 2 addressing Codex review findings R1–R4)
Task brief: `coordination/agy/tasks/002-reacquisition-evidence.md`
Branch: `agy/002-reacquisition-evidence`
Starting commit: `64bc19a00a03a83a3dc44f75225d6be619a3a754`
First handoff commit: `6f4fb315193a9d79e8e222fe6aace2e908cbb405`

---

## 1. Response to Review Findings R1–R4 (`002-review.md`)

### R1 (High) — Authoritative File Resolution and Observation Consistency Verification
- **Diagnosis:** When loading augmented stage observations, the fallback to `f"{idx:02d}-observation.json"` caused missing files (e.g. absent `07-observation.json` for Lower) to silently load the subsequent stage's file (`08-observation.json`, Release) due to the index shift introduced by inserting `lower_mid`. In addition, loaded observations were not checked for timestamp consistency with record metadata.
- **Remedy:**
  - In `humanoid_sim/temporal_reacquisition_evaluation.py:evaluate_dataset`:
    - Made explicit file references authoritative: when a stage record specifies `image`, only `{prefix}-observation.json` is checked. If absent, `obs_file` remains `None` and does NOT fall back to numerical indices.
    - Legacy numerical index fallback is strictly restricted to records that lack an explicit `image` mapping (e.g. synthetic test fixtures).
  - In `humanoid_sim/temporal_reacquisition_evaluation.py:evaluate_stream`:
    - Added consistency validation comparing `original['time_s']` against `frame_info['time_s']` (tolerance 1 ms) and `original['observation_id']` against `frame_info['perception']['observation_id']`.
    - If a mismatch is detected, tracker history is immediately cleared (`tracker.invalidate()`), status is recorded as `'mismatched_observation'`, scoring status is `'unscored_mismatched_observation'`, and the stream continues to the next stage without scoring.
  - In `tests/test_temporal_reacquisition_evaluation.py`:
    - Added `test_missing_lower_observation_after_midpoint_retains_accounting_and_invalidates`: verifies that omitting `07-observation.json` after midpoint insertion records `missing_observation_file` for Lower rather than loading `08-observation.json`, retains incomplete status, and invalidates tracking.
    - Added `test_mismatched_observation_timestamp_invalidates_and_marks_incomplete`: verifies that an observation with a mismatched timestamp records `mismatched_observation`, clears tracker frames, and retains incomplete accounting.

### R2 (High) — Preserve Task 001 Artifacts and Default Offline Command Path
- **Diagnosis:** The evaluator CLI defined `--compare` with `default=True`, making the ordinary Task 001 evaluation path unreachable, running rendering on default invocation, and overwriting historical Task 001 output `experiments/humanoid-pick-place/results/temporal_reacquisition_development.json`. Furthermore, a redundant candidate alias (`reacquisition_candidate`) was executed in the comparison run, evaluating 4 configurations while reporting 3.
- **Remedy:**
  - Restored `experiments/humanoid-pick-place/results/temporal_reacquisition_development.json` byte-for-byte from base commit `64bc19a00a03a83a3dc44f75225d6be619a3a754`.
  - In `humanoid_sim/temporal_reacquisition_evaluation.py`:
    - Changed `--compare` to `action='store_true', default=False`.
    - Default invocation (without `--compare`) executes only the standard Task 001 evaluation path (`evaluate_dataset`) with the two Task 001 candidates (`baseline_p4` and `reacquisition_candidate`), writes to `--output`, and never invokes rendering or comparison runners.
    - When `--compare` is passed, `evaluate_evidence` evaluates exactly the 3 distinct conditions (`baseline_p4`, `reacquisition_2frame`, `reacquisition_3frame`), writes evidence exclusively to `--output-evidence` (`temporal_reacquisition_evidence_development.json`), and does NOT overwrite `--output`.
    - Removed redundant execution of `reacquisition_candidate` alias during comparison.
  - In `tests/test_temporal_reacquisition_evaluation.py`:
    - Added `test_cli_default_invocation_preserves_task001_path_without_comparison`: mocked CLI invocation verifying that running without `--compare` calls `evaluate_dataset` once, never calls `render_augmented_dataset` or `evaluate_evidence`, and leaves Task 001 artifacts untouched.

### R3 (Medium) — Accurate Replay Description, Dynamic Schedule, Overlap Protection, and Cache Manifest
- **Diagnosis:** Replaying saved states from `episode.npz` loads `qpos` and `time`, but not `qvel` or full integration state. Calling this an "exact physical replay" was inaccurate because public joint velocities in `robot_state` reflected the final loaded state. Additionally, the lowering midpoint schedule was hardcoded to 12.0s rather than derived from stage timestamps, source/destination directory paths were not checked for overlap, and augmented caches lacked hash-based provenance validation.
- **Remedy:**
  - Explicitly labeled replay mode as **qpos-based kinematic replay**.
  - In `humanoid_sim/temporal_reacquisition_evaluation.py:render_augmented_dataset`:
    - Overlap guard: checks `source_capture_dir.resolve()` and `output_capture_dir.resolve()`; raises `ValueError` if paths are identical or subdirectories of each other.
    - Dynamic schedule: derives requested midpoint time dynamically from stage timestamps: $t_{\text{mid}} = (t_{\text{transport}} + t_{\text{lower}}) / 2.0$.
    - Interval validation: verifies selected sample time $t_{\text{mid\_actual}}$ satisfies $t_{\text{transport}} < t_{\text{mid\_actual}} < t_{\text{lower}}$.
    - Kinematic replay marking: explicitly sets `obs['robot_state']['robot']['joint_velocity_rad_s'] = None`, `dynamic_fields_available = False`, and `replay_mode = 'qpos_kinematic_replay'` rather than presenting final-state velocities as midpoint measurements.
    - Record metadata: stores `requested_time_s`, `actual_time_s`, `episode_step_index`, and `replay_mode` in each midpoint record.
    - Cache manifest: writes `output_capture_dir / "augmented_manifest.json"` recording source `private_records.json` and `episode.npz` SHA-256 hashes, camera identity (`fixed`), revision (`task-002-r2`), and schedule rule.
  - In `humanoid_sim/temporal_reacquisition_evaluation.py:is_augmented_cache_valid`:
    - Validates manifest existence, revision, camera identity, and matching SHA-256 hashes for each requested seed before reusing cached renderings; triggers re-rendering if invalid or mismatched.
  - In `tests/test_temporal_reacquisition_evaluation.py`:
    - Added `test_render_schedule_derives_midpoint_within_interval`.
    - Added `test_render_source_output_overlap_rejected`.
    - Added `test_render_cache_mismatch_triggers_regeneration`.

### R4 (Medium) — Metric Disaggregation, Schedule vs Window Effects, Hypotheses, and Thresholds
- **Diagnosis:** The previously reported 5.07 mm mean on the augmented stream aggregated all 24 accepted responses, including 7 midpoint estimates, obscuring the mean over the 17 accepted original targets (5.8715 mm). The latter exceeds the proposed P5 planning gate ($\le 5.0$ mm). In addition, all 210 augmented responses match identically between 2-frame and 3-frame candidates, meaning the augmented stream shows an observation-schedule improvement rather than an incremental benefit of the minimum-window rule. Depth ambiguity was stated as fact rather than hypothesis, and report thresholds misstated the code constants.
- **Remedy:**
  - In `humanoid_sim/temporal_reacquisition_evaluation.py:compute_aggregate`:
    - Added explicit `post_warmup_mean_error_m` and `post_warmup_max_error_m` fields to JSON aggregates, separately reporting metrics over nominal post-warmup targets (`transport` and `lower`) alongside all-accepted metrics (`accepted_mean_error_m`, `accepted_max_error_m`).
  - Metric Reporting and Disaggregation:
    - Augmented stream, accepted original targets (17/20): mean **5.8715 mm**, max **14.8479 mm**.
    - Augmented stream, all accepted responses (24/70): mean **5.0659 mm**, max **14.8479 mm**.
    - Explicitly documented that the 5.8715 mm mean over accepted original targets exceeds the P5 planning proposal target ($\le 5.0$ mm). Thresholds and gates are preserved without modification.
  - Separation of Effects:
    - Clarified that both 2-frame and 3-frame candidates produce identical results across all 210 augmented responses because both fit over the 3-frame window once available.
    - The augmented stream demonstrates the benefit of the **observation schedule** (mitigating the Seed 820 error).
    - The original stream demonstrates the **stricter refusal behavior** of the 3-frame rule (refusing at Lower on Seeds 820, 825, 828 when only 2 frames exist after reacquisition seed).
    - The minimum-frame rule does not provide incremental accuracy on the augmented stream itself.
  - Midpoint Refusal Scoping:
    - Clarified that midpoint refusal applies specifically to the 3 recovering seeds (820, 825, 828) due to hand translation 65–72 mm $< 80$ mm.
    - The other 7 tracked seeds had accumulated motion $\ge 80$ mm and emitted valid midpoint estimates (mean error 3.12 mm).
  - Optical-Axis Depth Ambiguity:
    - Maintained strictly as an explanatory **hypothesis**, not a proven fact.
  - Corrected Code Thresholds:
    - Corrected numerical fit thresholds to code constants: RMS threshold `MAX_RMS_PX = 0.75` px, center spread threshold `MAX_SPREAD_M = 0.02` m (20 mm), baseline motion threshold `MIN_BASELINE_M = 0.08` m (80 mm).
  - Estimator Calls and Denominators:
    - Evaluated exactly 3 candidates (`baseline_p4`, `reacquisition_2frame`, `reacquisition_3frame`).
    - Original stream: 3 candidates $\times$ 3 variants $\times$ 60 responses = 540 calls.
    - Augmented stream: 3 candidates $\times$ 3 variants $\times$ 70 responses = 630 calls.
    - Combined total: 1,170 estimator calls.

---

## 2. Validation Evidence

All checks executed from `/private/tmp/mujoco-llms-agy-002` using Python interpreter `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`:

1. **Evaluator Accounting and Regression Unit Tests (16/16 Passed in 35.2s):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_temporal_reacquisition_evaluation.py -v
   ```
   **Outcome:** 16/16 passed. Retained log: `.system_generated/tasks/task-994.log`.

2. **Temporal Pose Unit Tests (21/21 Passed in 59.8s):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_humanoid_temporal_pose.py -v
   ```
   **Outcome:** 21/21 passed. Retained log: `.system_generated/tasks/task-760.log`.

3. **Full Repository Test Discovery (116/116 Passed in 136.9s):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v
   ```
   **Outcome:** 116/116 passed across all test modules without regressions. Retained log: `.system_generated/tasks/task-998.log`.

4. **Comparative Evidence Evaluation Rerun (`--compare`):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.temporal_reacquisition_evaluation --compare
   ```
   **Outcome:** Complete. Retained log: `.system_generated/tasks/task-954.log`.
   Evidence output: `experiments/humanoid-pick-place/results/temporal_reacquisition_evidence_development.json`.
   Historical Task 001 artifact `experiments/humanoid-pick-place/results/temporal_reacquisition_development.json` remains restored byte-for-byte from `64bc19a`.

5. **Git Working Diff and Whitespace Check:**
   ```sh
   git diff --check 64bc19a00a03a83a3dc44f75225d6be619a3a754..HEAD
   ```
   **Outcome:** Exited code 0 (clean formatting, no trailing whitespace).

---

## 3. Experiment Evidence Summary

### Provenance and Scope
- Evaluated on development seeds **820–829**. Status: **development evidence** (not fresh validation).
- Source P4 captures under `runtime/humanoid/temporal-P4/capture/` remain strictly read-only.
- Trackers receive public RGB, calibration, and robot state only. Object truth is used post-hoc by the evaluator after estimation returns.

### Aggregate Performance Table Across Development Seeds 820–829

| Stream | Candidate | Accepted / Total | Post-Warmup Targets Accepted / Denom | Mean Error (Accepted Original Targets) | Mean Error (All Accepted Responses) | Max Error | Release/Retract Accepted |
|---|---|---|---|---|---|---|---|
| **Original** (6-stage) | `baseline_p4` | 14 / 60 | 14 / 20 | 3.6448 mm | 3.6448 mm | 7.4200 mm | 0 |
| **Original** (6-stage) | `reacquisition_2frame` | 17 / 60 | 17 / 20 | 4.7443 mm | 4.7443 mm | **21.9367 mm** (Seed 820) | 0 |
| **Original** (6-stage) | `reacquisition_3frame` | 14 / 60 | 14 / 20 | 3.6448 mm | 3.6448 mm | 7.4200 mm | 0 |
| **Augmented** (7-stage) | `baseline_p4` | 21 / 70 | 14 / 20 | 5.6723 mm | 4.8180 mm | 9.4442 mm | 0 |
| **Augmented** (7-stage) | `reacquisition_2frame` | 24 / 70 | 17 / 20 | **5.8715 mm** | 5.0659 mm | **14.8479 mm** | 0 |
| **Augmented** (7-stage) | `reacquisition_3frame` | 24 / 70 | 17 / 20 | **5.8715 mm** | 5.0659 mm | **14.8479 mm** | 0 |

### Per-Seed Slipped Recovery Detail at Lower ($t=13.0$s)

| Seed | Original 2-Frame Error | Original 3-Frame Status | Augmented 3-Frame Error | Gate (<= 20 mm) |
|---|---|---|---|---|
| **820** | **21.94 mm** | Refused (`insufficient_motion_history`) | **14.85 mm** | **Pass** |
| **825** | 2.66 mm | Refused (`insufficient_motion_history`) | 4.00 mm | **Pass** |
| **828** | 5.03 mm | Refused (`insufficient_motion_history`) | 1.56 mm | **Pass** |

### Disruption Streams
- `black_transport`: 0/60 and 0/70 accepted across all candidates and streams.
- `frozen_transport_rgb`: 0/60 and 0/70 accepted across all candidates and streams.
- Physical release and retract: 0 accepted across all candidates and streams.

---

## 4. Limitations and Next Checkpoint

1. **Limitations:**
   - On the augmented stream, the mean error across accepted original targets is **5.8715 mm**, which exceeds the earlier P5 planning target of $\le 5.0$ mm.
   - The 3-frame candidate requires an intermediate view to emit before the lower endpoint; under an endpoint-only schedule, it strictly refuses at lower.
   - Saved-state replay is kinematic only; public joint velocities were unavailable for the intermediate view.
   - The candidate remains disconnected from control.

2. **Recommendation for Protocol P5:**
   - Incorporate a deterministic lowering midpoint ($t_{\text{mid}} = (t_{\text{transport}} + t_{\text{lower}}) / 2.0$) into the P5 trajectory capture schedule.
   - Use `TemporalThreeFrameReacquisitionPose` as the candidate estimator for P5 validation to enforce the 3-view requirement.
   - Revisit the target mean error gate in the P5 proposal to account for the empirical 5.87 mm development baseline.
   - Protocol P5 remains proposed in `experiments/humanoid-pick-place/protocols/P5_PROPOSAL.md`. Seeds 840–849 remain untouched pending review.
