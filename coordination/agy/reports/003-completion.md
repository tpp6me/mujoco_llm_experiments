# AGY completion — task 003

Status: ready for review
Task brief: `coordination/agy/tasks/003-p5-preparation.md`
Branch: `agy/003-p5-preparation`
Starting commit: `55479a189af716316d133a9ca543f09934889726`

---

## 1. Changes and Rationale

This task prepares the passive P5 protocol, runner, and screening infrastructure without executing or touching held-out seeds 840–849.

### Modified and Created Files
1. `experiments/humanoid-pick-place/protocols/P5_REVISED_PROPOSAL.md` (New):
   - Comprehensive revised protocol labeled **PROPOSED ONLY — NOT FROZEN, NOT EXECUTED**.
   - Specifies proposed fresh seeds 840–849, unchanged exact-state G2 driver, fixed $960 \times 720$ RGB scene camera (`lookat [0.24, -0.24, 0.8]`, distance 1.35, azimuth 90, elevation -65).
   - Primary condition: `TemporalThreeFrameReacquisitionPose` on the 7-stage augmented schedule (with lowering midpoint). Prespecified comparators: `TemporalReacquisitionPose` (2-frame) and `TemporalPose` (baseline P4) on both original and augmented schedules.
   - Prespecified evaluation principle: no post-hoc winner selection.
   - Dynamic midpoint derivation using production helper `derive_midpoint_schedule` ($t_{\text{mid}} = (t_{\text{transport}} + t_{\text{lower}}) / 2.0$, strictly bounded by $t_{\text{transport}} < t_{\text{mid\_actual}} < t_{\text{lower}}$).
   - `qpos`-based kinematic replay semantics with dynamic velocity fields marked unavailable (`joint_velocity_rad_s = None`, `dynamic_fields_available = False`, `replay_mode = 'qpos_kinematic_replay'`).
   - Three disruption variants per schedule (`original`, `black_transport`, `frozen_transport_rgb`).
   - Fixed grid denominator: 180 responses/candidate for original (540 total), 210 responses/candidate for augmented (630 total); 1,170 total expected responses across 3 candidates.
   - Fixed 20-target nominal post-warmup denominator (`transport` and `lower` across 10 episodes). Extra midpoint responses never enlarge or dilute the original-target denominator.
   - Continuation gates strictly preserved: $\ge 16/20$ coverage, $\le 5.0$ mm mean error over accepted original targets, no accepted nominal center $> 20.0$ mm (including midpoint), zero release/retract emissions (0/20), zero corrupted transport emissions (0/20).
   - Incomplete evidence rule: missing stages, missing truth, errors, and unscored acceptances make evidence incomplete; incomplete is never a pass.
   - Budget and compute limits: multi-view optimization and communication overhead accounted against task budget; no real-time or 25-second acting-controller qualification claimed.
2. `experiments/humanoid-pick-place/protocols/P5_PROPOSAL.md` (Modified):
   - Added header note linking to `P5_REVISED_PROPOSAL.md` while retaining historical planning text intact.
3. `humanoid_sim/p5_evaluation.py` (New):
   - Production evaluation and preflight wrapper.
   - Reuses accepted fixed-grid evaluator, candidate estimators, and cache validation helpers from Task 002 without duplicating tracker logic.
   - Enforces strict held-out seed protection: executing with seeds 840–849 raises `ValueError` immediately.
   - Forbids fresh capture in Task 003 (`--fresh-capture` raises `RuntimeError` documenting the future execution command).
   - Generates structured preflight report (`build_preflight_report`) recording code/scene/protocol hashes and input availability.
   - Evaluates the 5 continuation gates (`compute_gate_report`), disaggregating midpoint metrics and reporting reasons for each gate.
   - Supports `--preflight`, `--rescore <path>`, and `--dry-run` modes.
4. `tests/test_p5_evaluation.py` (New):
   - 13 comprehensive unit tests covering:
     - Immediate rejection of held-out seeds 840–849 and out-of-range seeds.
     - Known 5.8715 mm post-warmup mean failure at unchanged 5.0 mm gate.
     - Successful synthetic metrics passing all 5 gates.
     - Missing truth and unscored acceptances resulting in `INCOMPLETE` (never pass).
     - All-refused results failing coverage and accuracy safely without exceptions.
     - Midpoint denominator separation: midpoint metrics never dilute or enlarge the 20-target denominator.
     - Subset dry runs correctly marked `not_applicable` rather than passing/failing.
     - Rejection of corrupted transport and release/retract emissions.
     - Preflight report generation and schema checks.
     - CLI `--fresh-capture` rejection.
5. `experiments/humanoid-pick-place/results/p5_preparation/` (New):
   - `preflight_report.json`: complete preflight metadata and hashes.
   - `gate_report_rescore.json`: structured gate evaluation rescoring accepted Task 002 evidence.
   - `p5_development_evidence.json`: evidence artifact from 10-seed development dry run.
   - `gate_report_development.json`: structured gate evaluation from 10-seed development dry run.
   - `manifest.json`: provenance manifest linking artifacts and execution status.
6. `experiments/humanoid-pick-place/PLAN.md` and `RESULTS_INDEX.md` (Modified):
   - Checked off Task 003 execution in living plan next actions.
   - Added dated progress log row and results index entry documenting P5 preparation, runner, and unchanged 5.0 mm gate failure.
7. Retained Test Logs:
   - `coordination/agy/reports/003-targeted-tests.log`: 31 tests passed.
   - `coordination/agy/reports/003-full-discovery.log`: 131 tests passed across repository.

---

## 2. Validation and Execution Evidence

All commands executed in worktree `/private/tmp/mujoco-llms-agy-003` using interpreter `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`.

### Chronology and Batch Timeout Accounting
In the initial execution batch, preflight checks, artifact rescoring, and a seed-820 smoke run were completed. The full 10-seed development dry run was launched as a background process (`task-94`). Because the full optimizer on 10 seeds (1,170 calls) took approximately 25 minutes, the interactive session reached its 30-minute turn timeout while the background process continued. The background process finished successfully with exit code 0 at `2026-09-13T01:46:12Z`, producing complete artifacts (`p5_development_evidence.json` and `gate_report_development.json`).
Upon resumption, an inspection of `tests/test_p5_evaluation.py` revealed a `TypeError` in `test_all_refused_results` caused by formatting `pw_mean_mm` when `None`. This was fixed in `humanoid_sim/p5_evaluation.py`, and the saved evidence was rescored without repeating the full optimization.

### Exact Verification Commands and Results

1. **Preflight Check:**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.p5_evaluation --preflight
   ```
   - **Outcome:** Exited code 0.
   - Verified scene SHA-256 (`6d86617e402db06acc80226736bc7202ccae5dd8efc98fb348b714935333e725`), protocol hashes, code hashes, and input availability (augmented cache valid: `True`).
   - Artifact: `experiments/humanoid-pick-place/results/p5_preparation/preflight_report.json`.

2. **Artifact Rescore on Accepted Task 002 Evidence:**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.p5_evaluation \
       --rescore experiments/humanoid-pick-place/results/temporal_reacquisition_evidence_development.json \
       --report-name gate_report_rescore.json
   ```
   - **Outcome:** Exited code 0.
   - Artifact: `experiments/humanoid-pick-place/results/p5_preparation/gate_report_rescore.json`.

3. **Development Dry Run on Development Seeds 820–829:**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.p5_evaluation \
       --dry-run --seeds 820 821 822 823 824 825 826 827 828 829
   ```
   - **Outcome:** Exited code 0. Completed in background task at `2026-09-13T01:46:12Z`.
   - Reused read-only validated augmented cache from `/private/tmp/mujoco-llms-agy-002/runtime/humanoid/temporal-P4-augmented/capture`.
   - Artifacts: `experiments/humanoid-pick-place/results/p5_preparation/p5_development_evidence.json`, `gate_report_development.json`, `manifest.json`.

4. **Targeted Test Suite (31 Tests):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_p5_evaluation.py tests/test_temporal_reacquisition_evaluation.py -v > coordination/agy/reports/003-targeted-tests.log 2>&1
   ```
   - **Outcome:** **31/31 passed in 35.259s**.
   - Retained log: `coordination/agy/reports/003-targeted-tests.log`.

5. **Full Repository Discovery (131 Tests):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v > coordination/agy/reports/003-full-discovery.log 2>&1
   ```
   - **Outcome:** **131/131 passed in 136.498s** across all repository test suites without regressions.
   - Retained log: `coordination/agy/reports/003-full-discovery.log`.

6. **Git Formatting and Working Diff Check:**
   ```sh
   git diff --check 55479a189af716316d133a9ca543f09934889726..HEAD
   ```
   - Verified clean formatting, no trailing whitespace, and clean working tree.

---

## 3. Experiment Evidence and Gate Outcomes

### Evaluation Summary: Primary Condition (`TemporalThreeFrameReacquisitionPose` on Augmented Stream)
- Evaluated seeds: **820–829** (10 development episodes; held-out seeds 840–849 remain untouched).
- Source captures: `/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture` (read-only).
- Augmented cache: `/private/tmp/mujoco-llms-agy-002/runtime/humanoid/temporal-P4-augmented/capture` (read-only).
- Truth isolation: Object ground truth was accessed post-hoc by the evaluator after tracking estimation returned.

### Gate Report Across Development Seeds 820–829

| Gate | Description | Threshold | Numerator / Value | Denominator | Scored / Unscored | Status | Reason |
|---|---|---|---|---|---|---|---|
| **Gate 1** | Nominal post-warmup coverage | $\ge 16/20$ | 17 | 20 | 17 / 0 | **PASS** | Accepted 17/20 post-warmup targets ($\ge 16$ required) |
| **Gate 2** | Nominal post-warmup accuracy | $\le 5.0$ mm mean error | **5.8715 mm** | 17 | 17 / 0 | **FAIL** | Mean error 5.8715 mm exceeds 5.0 mm threshold (gate strictly preserved) |
| **Gate 3** | Maximum nominal error | $\le 20.0$ mm max error | 14.8479 mm | 24 | 24 / 0 | **PASS** | Maximum error 14.8479 mm $\le 20.0$ mm (midpoint max error: 5.1140 mm) |
| **Gate 4** | Relationship loss safety | 0 accepted on release/retract | 0 | 20 | 0 / 0 | **PASS** | 0/20 positions emitted on release or retract endpoints |
| **Gate 5** | Sensor disruption robustness | 0 accepted on corrupted transport | 0 | 20 | 0 / 0 | **PASS** | 0/20 positions emitted on corrupted transport frames |
| **Overall** | Continuation Screen | All 5 gates pass | 4 pass, 1 fail | — | Complete | **FAIL** | Failed accuracy gate (5.8715 mm > 5.0 mm) |

### Disaggregated Midpoint Metrics
- Accepted midpoint responses: **7 / 10**.
- Mean midpoint error: **3.1093 mm**.
- Maximum midpoint error: **5.1140 mm**.
- **Denominator Separation:** Midpoint responses do not enter the nominal post-warmup denominator ($N=20$) and do not dilute the original-target mean (which remains 5.8715 mm). All-accepted mean across all 24 nominal responses is 5.0659 mm.

### Disruption and Refusal Breakdown
- `black_transport`: 0 accepted across all 70 responses.
- `frozen_transport_rgb`: 0 accepted across all 70 responses.
- Refusals in nominal stream: 33 `insufficient_motion_history` (warmup and recovering stages), 13 `inconsistent_rigid_transform`.

---

## 4. Limitations and Recommendation

### Limitations
1. **Known Accuracy Gate Failure:** The accepted original-target mean on development trajectories is **5.8715 mm**, which exceeds the $\le 5.0$ mm gate. The gate was strictly preserved without relaxation.
2. **Development Data Only:** All evidence is from development trajectories (seeds 820–829). No held-out seeds (840–849) were executed, captured, or rendered.
3. **Kinematic Replay:** Midpoint observations rely on saved `qpos` kinematics; full dynamic integration velocities are marked unavailable.
4. **Control Disconnection:** Tracking remains strictly passive and disconnected from robot control.

### Recommendation for Next Checkpoint
- Proceed with Codex review of this preparation task (`003-p5-preparation`).
- Because development evidence shows an accepted-target mean of 5.8715 mm against a 5.0 mm gate, Codex should decide whether to:
  1. **Freeze and execute Protocol P5 on seeds 840–849 as an exploratory screen**, recognizing that a failed gate on held-out seeds is an informative, valid scientific outcome; or
  2. **Pause before consuming held-out seeds** to explore further estimator improvements (e.g. additional motion windows or feature improvements) if a $\le 5.0$ mm gate is a strict prerequisite.
