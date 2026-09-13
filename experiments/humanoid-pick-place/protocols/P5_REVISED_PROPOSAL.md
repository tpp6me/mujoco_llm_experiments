# Revised Proposed Protocol P5 — Temporal Reacquisition Validation (Passive Screen)

**STATUS: PROPOSED ONLY — NOT FROZEN, NOT EXECUTED.**

*This revised protocol is submitted for Codex review under AGY Task 003. It supersedes the planning outline in [P5_PROPOSAL.md](P5_PROPOSAL.md) (preserved as historical planning evidence). No fresh episodes, rendering, simulator resets, or validation runs on held-out seeds 840–849 have been executed.*

---

## 1. Objective and Scientific Scope

Evaluate whether the primary candidate estimator (`TemporalThreeFrameReacquisitionPose`) on an augmented observation schedule reliably re-establishes carried-block pose tracking following model mismatch across held-out trajectories without introducing uncontained drift, false positives, or stale predictions.

Tracking remains an experimental perception candidate and **strictly disconnected from control**. The acting low-level environment continues to use the verified P2 prior lifetime guard and exact-state G2 controller.

### Primary Condition and Prespecified Comparators
- **Primary Condition:** `TemporalThreeFrameReacquisitionPose` evaluated on the **augmented schedule** (including lowering midpoint).
- **Prespecified Comparators:**
  1. `TemporalReacquisitionPose` (2-frame minimum window) on both schedules.
  2. `TemporalPose` (baseline P4 with reacquisition disabled) on both schedules.
- **Schedule Comparison:** Evaluating both original (endpoint-only) and augmented streams isolates the observation-schedule effect from the candidate estimator's minimum-window logic.
- **No Winner Selection:** All conditions, schedules, and metrics are prespecified. Hypotheses cannot be re-selected or winners chosen post hoc after inspecting validation outcomes. A failed screen is an informative, valid scientific outcome.

---

## 2. Held-Out Seeds and Trajectory Generation Contract

- **Proposed Validation Seeds:** 840–849 (10 episodes). Verified unused across repository history. **Must not be captured, rendered, reset, or inspected before separate protocol freeze and explicit authorization.**
- **Driving Policy:** Conventional exact-state G2 controller (identical to P4), release height $Z = 0.88$ m, hand closure = 0.4, nominal duration 25 simulated seconds.
- **Camera Configuration:** Fixed scene camera at $960 \times 720$ resolution RGB:
  - Name: `fixed`
  - Lookat: `[0.24, -0.24, 0.8]` m
  - Distance: `1.35` m
  - Azimuth: `90.0` deg
  - Elevation: `-65.0` deg
- **Observation Boundary:** Public observations contain only RGB image, camera calibration matrices/intrinsics, and proprioceptive robot state (hand Cartesian pose, orientation quaternion, timestamps). Object ground-truth poses, scene truth, private simulation contacts, and scorer records are excluded and strictly evaluated post hoc.

---

## 3. Observation Schedules and Midpoint Kinematics

### Evaluated Schedules
1. **Original Schedule (6 action endpoints per episode):**
   - `lift` (warmup, low hand motion)
   - `lift_hold` (warmup, low hand motion)
   - `transport` (nominal post-warmup target 1)
   - `lower` (nominal post-warmup target 2)
   - `release` (ground-truth relationship termination)
   - `retract` (ground-truth empty-hand motion)
2. **Augmented Schedule (7 stages per episode):**
   - Incorporates one deterministic lowering midpoint observation (`lower_mid`) inserted between `transport` and `lower`.

### Dynamic Midpoint Schedule Derivation
The lowering midpoint timestamp is derived dynamically using the production helper `derive_midpoint_schedule`:
$$t_{\text{mid\_target}} = \frac{t_{\text{transport}} + t_{\text{lower}}}{2.0}$$
The episode time array is searched for the nearest recorded discrete simulation sample $t_{\text{mid\_actual}}$, strictly requiring:
$$t_{\text{transport}} < t_{\text{mid\_actual}} < t_{\text{lower}}$$
The requested target time and actual sample time are distinguished and recorded explicitly in observation and manifest metadata.

### Kinematic Replay Semantics
Midpoint frames generated from saved trajectories reuse `qpos`-based kinematic replay (as in Task 002):
- Object and robot `qpos` and time are loaded into MuJoCo physics.
- Dynamic fields are explicitly marked unavailable: `joint_velocity_rad_s = None`, `dynamic_fields_available = False`, `replay_mode = 'qpos_kinematic_replay'`.
- Kinematic replay is not claimed as full dynamic simulation state.

---

## 4. Disruption Streams and Response Accounting

Each schedule is evaluated across three variants per episode:
1. `original`: Unaltered nominal RGB and sensor stream.
2. `black_transport`: Transport image replaced with a solid black frame ($960 \times 720$ RGB); all other stages nominal.
3. `frozen_transport_rgb`: Transport image replaced with the preceding `lift_hold` RGB frame while retaining current robot pose, timestamp, and observation ID; all other stages nominal.

### Release and Corruption Rules
- Corrupted frames must trigger estimator rejection (`inconsistent_rigid_transform` or boundary refusal) and clear tracker history.
- An announced `release` or `retract` must immediately invalidate tracking history (`tracker.invalidate()`).

### Grid Denominator and Expected Response Counts
- **Original Schedule (6 stages $\times$ 3 variants $\times$ 10 episodes):**
  - 180 responses per candidate.
  - 540 responses across 3 candidates.
- **Augmented Schedule (7 stages $\times$ 3 variants $\times$ 10 episodes):**
  - 210 responses per candidate.
  - 630 responses across 3 candidates.
- **Total Expected Responses:** 1,170 responses across 3 candidates and 2 schedules.
- **Nominal Post-Warmup Target Denominator:**
  - Strictly **20 original targets** across 10 episodes (`transport` and `lower`).
  - **Extra midpoint responses never enlarge the original-target denominator.** Midpoint metrics are accounted and reported separately.
- **Independence Note:** Responses within each episode share physical trajectory history, and disruption streams reuse nominal frames; they are correlated within-episode observations, not 1,170 independent trials.

---

## 5. Continuation Gates (Screening Criteria)

To qualify for consideration in a future active visual control loop, the primary candidate (`TemporalThreeFrameReacquisitionPose`) on the augmented schedule must satisfy all of the following gates:

1. **Nominal Post-Warmup Target Coverage:**
   $$\ge 16 / 20 \text{ targets accepted (transport and lower across 10 episodes, } \ge 80\%)$$
2. **Nominal Post-Warmup Target Accuracy:**
   $$\text{Mean 3D center error over accepted original targets } \le 5.0 \text{ mm}$$
   *(Preserved unchanged from initial planning. On development seeds 820–829, this mean is 5.8715 mm and fails this gate.)*
3. **Maximum Accepted Nominal Error:**
   $$\text{No accepted center error } > 20.0 \text{ mm across any accepted nominal stage}$$
   *(Includes transport, lower, and lower_mid. Midpoint errors are reported separately and included in this maximum error check.)*
4. **Relationship Loss Safety:**
   $$\text{Zero accepted poses on release or retract endpoints } (0 / 20 \text{ accepted})$$
5. **Sensor Disruption Robustness:**
   $$\text{Zero accepted poses on corrupted transport frames } (0 / 10 \text{ black}, 0 / 10 \text{ frozen RGB})$$
   *(All-stream containment across all stages is also reported descriptively.)*

### Incompleteness and Scorer Integrity
- Any missing stages, missing observations, malformed records, missing ground truth, estimator exceptions, preparation errors, or unscored acceptances cause the evaluation status to be **incomplete**.
- **Incomplete is never a pass.**
- Refusal reasons (`insufficient_motion_history`, `inconsistent_rigid_transform`, etc.) must remain visible in reporting.

---

## 6. Budget, Compute, and Real-Time Qualification Limits

- Optimization cost (Levenberg-Marquardt fitting over multi-view cuboids) and communication of intermediate midpoint observations are accounted as computational and communication overhead.
- This passive perception screen does not qualify real-time execution, control closed-loop stability, or 25-second acting-controller deadlines.
- This screen evaluates perception accuracy on fixed trajectories; it does not constitute a general manipulation success rate.

---

## 7. Provenance, Manifest, and Future Freeze Step

Before executing this protocol on seeds 840–849 in a subsequent reviewed task:
1. **Source and Scene Integrity:** Git commit SHA, scene XML SHA-256 (`get_scene_sha256()`), dependency environment, and protocol file SHA-256 must be computed and recorded in a preflight report.
2. **Provenance Binding:** Public input hashes (`source_observations_sha256`) and augmented cache manifests (`augmented_manifest.json`) must be validated.
3. **Future Execution Sketch (Non-Executable Python API Sketch):**
   Fresh trajectory capture and observation generation would be invoked via the `audit` API in a future reviewed task (DO NOT RUN IN TASK 003):
   ```python
   # Python API sketch for future fresh capture (separate reviewed task):
   from pathlib import Path
   from humanoid_sim.perception_evaluation import audit

   audit(
       output=Path('runtime/humanoid/temporal-P5/capture'),
       seeds=range(840, 850),
       protocol=Path('experiments/humanoid-pick-place/protocols/P5_REVISED_PROPOSAL.md'),
       protocol_id='P5_capture',
   )
   ```
4. **Currently Supported Development Commands (Task 003):**
   - Preflight inspection:
     ```sh
     python -m humanoid_sim.p5_evaluation --preflight
     ```
   - Artifact rescore on existing evidence:
     ```sh
     python -m humanoid_sim.p5_evaluation --rescore experiments/humanoid-pick-place/results/temporal_reacquisition_evidence_development.json
     ```
   - Development dry run on existing captures (seeds 820–829):
     ```sh
     python -m humanoid_sim.p5_evaluation --dry-run --seeds 820 821 822 823 824 825 826 827 828 829
     ```
5. **Current Status:** **PROPOSED ONLY. DO NOT EXECUTE ON SEEDS 840–849.**
