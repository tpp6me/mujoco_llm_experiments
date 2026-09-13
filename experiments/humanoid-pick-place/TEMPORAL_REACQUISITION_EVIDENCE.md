# Multi-View Evidence for Temporal Pose Reacquisition (Task 002)

Date: 2026-09-12. Branch: `agy/002-reacquisition-evidence`.
Base commit: `64bc19a00a03a83a3dc44f75225d6be619a3a754`.

---

## 1. Objective and Hypotheses

In Task 001 (`agy/001-reacquisition`), enabling temporal reacquisition upon model mismatch recovered 17/20 post-warmup targets on development seeds 820–829, recovering accurate lower poses on Seeds 825 and 828, but accepted Seed 820 at **21.94 mm** error (a false acceptance exceeding the 20 mm gate, hypothesized to stem from monocular optical-axis depth ambiguity).

Task 002 tested the specific hypothesis:
> **Hypothesis:** Requiring a third distinct, fresh RGB/hand observation within the reacquired window reduces the known Seed 820 false acceptance without eliminating useful post-warmup coverage.

To isolate the effect of the observation schedule from the minimum-window rule, Task 002 compared three conditions across both the original endpoint-only stream (6 stages) and an augmented stream (7 stages) with an intermediate lowering observation:
1. `baseline_p4`: `TemporalPose(reacquisition=False)` — baseline P4 tracker (no recovery after mismatch).
2. `reacquisition_2frame`: `TemporalReacquisitionPose(min_reacquisition_frames=2)` — Task 001 accepted 2-frame recovery candidate.
3. `reacquisition_3frame`: `TemporalThreeFrameReacquisitionPose()` — Task 002 opt-in 3-frame candidate requiring $\ge 3$ distinct, fresh observations since recovery seed before emitting a center.

---

## 2. Dataset and Observation Schedule

### Development Provenance
- Evaluated exclusively on existing development seeds **820–829**.
- Source runtime captures live under `runtime/humanoid/temporal-P4/capture/` and were treated as strictly read-only.
- Seeds 840–849 (proposed P5 validation seeds) remain completely untouched.
- All ground-truth poses and private drift measurements are computed post-hoc by the evaluator and are never visible to the tracker.

### Observation Schedules
1. **Original Endpoint-Only Stream (6 stages, 60 responses/variant per candidate):**
   - Stages: `lift` ($t=8.5$s), `lift_hold` ($t=9.0$s), `transport` ($t=11.0$s), `lower` ($t=13.0$s), `release` ($t=15.0$s), `retract` ($t=17.0$s).
   - Post-warmup targets: fixed at 2 per seed (`transport` and `lower`), giving 20 post-warmup targets across 10 seeds.
2. **Augmented Stream (7 stages, 70 responses/variant per candidate):**
   - Stages: `lift` ($t=8.5$s), `lift_hold` ($t=9.0$s), `transport` ($t=11.0$s), `lower_mid`, `lower` ($t=13.0$s), `release` ($t=15.0$s), `retract` ($t=17.0$s).
   - Lowering midpoint schedule is derived dynamically from declared stage endpoints: $t_{\text{mid}} = (t_{\text{transport}} + t_{\text{lower}}) / 2.0$. For all development seeds, nominal target is $12.0$s; selected actual samples range from $11.980$s to $11.995$s and are verified to lie strictly within $(t_{\text{transport}}, t_{\text{lower}})$.
   - Replay mode: **qpos-based kinematic replay** from saved `episode/episode.npz` files into `runtime/humanoid/temporal-P4-augmented/capture/`. Saved history records `qpos` and `time`, not full integration velocity states (`qvel`). Dynamic velocity fields (`joint_velocity_rad_s`) are explicitly marked unavailable rather than presenting final-state velocities as midpoint measurements.
   - Cache validation: An `augmented_manifest.json` tracks source trajectory file hashes (`private_records.json`, `episode.npz`), generation revision, schedule rule, and camera identity. Overlapping source/output directory paths are rejected before copying/writing.

---

## 3. Motion Baselines and Window Mechanics

Across all seeds 820–829, lowering spans $t=11.0$s to $t=13.0$s:
- **At Lowering Midpoint ($t \approx 12.0$s):**
  - For the 3 seeds recovering from transport mismatch (Seeds 820, 825, 828), hand translation from `transport` is **65–72 mm** (below the 80 mm motion threshold). Both 2-frame and 3-frame reacquisition trackers refuse with `insufficient_motion_history`. Exactly 0 positions emitted at midpoint for recovering seeds.
  - For the 7 nominal tracked seeds (821, 822, 823, 824, 826, 827, 829), accumulated hand motion exceeds 80 mm, and valid midpoint estimates are emitted (mean error 3.12 mm).
- **At Lower Endpoint ($t=13.0$s):** Total hand translation reaches **97–104 mm** (satisfying the $\ge 80$ mm motion threshold).
  - In the original stream, only 2 frames exist after reacquisition seed (`[transport, lower]`).
    - `reacquisition_3frame` refuses with `insufficient_motion_history` (proving it strictly cannot emit after only two views).
    - `reacquisition_2frame` fits across 2 frames, accepting Seed 820 at 21.94 mm error.
  - In the augmented stream, 3 frames exist in history (`[transport, lower_mid, lower]`).
    - Both 2-frame and 3-frame trackers fit across the full 3-frame window.

---

## 4. Empirical Evaluation Results

### Aggregate Performance Across Development Seeds 820–829

| Stream | Candidate | Accepted / Total | Post-Warmup Targets Accepted / Denom | Mean Error (Accepted Original Targets) | Mean Error (All Accepted Responses) | Max Error | Release/Retract Accepted |
|---|---|---|---|---|---|---|---|
| **Original** (6-stage) | `baseline_p4` | 14 / 60 | 14 / 20 | 3.6448 mm | 3.6448 mm | 7.4200 mm | 0 |
| **Original** (6-stage) | `reacquisition_2frame` | 17 / 60 | 17 / 20 | 4.7443 mm | 4.7443 mm | **21.9367 mm** (Seed 820) | 0 |
| **Original** (6-stage) | `reacquisition_3frame` | 14 / 60 | 14 / 20 | 3.6448 mm | 3.6448 mm | 7.4200 mm | 0 |
| **Augmented** (7-stage) | `baseline_p4` | 21 / 70 | 14 / 20 | 5.6723 mm | 4.8180 mm | 9.4442 mm | 0 |
| **Augmented** (7-stage) | `reacquisition_2frame` | 24 / 70 | 17 / 20 | **5.8715 mm** | 5.0659 mm | **14.8479 mm** | 0 |
| **Augmented** (7-stage) | `reacquisition_3frame` | 24 / 70 | 17 / 20 | **5.8715 mm** | 5.0659 mm | **14.8479 mm** | 0 |

### Per-Seed Detail for Slipped Episodes at Lower ($t=13.0$s)

| Seed | Original 2-Frame Error | Original 3-Frame Status | Augmented 3-Frame Error | Gate ($\le 20$ mm) |
|---|---|---|---|---|
| **820** | **21.94 mm** | Refused (`insufficient_motion_history`) | **14.85 mm** | **Pass** |
| **825** | 2.66 mm | Refused (`insufficient_motion_history`) | 4.00 mm | **Pass** |
| **828** | 5.03 mm | Refused (`insufficient_motion_history`) | 1.56 mm | **Pass** |

### Disruption Stream Robustness (All Candidates, Both Streams)

| Variant Stream | Total Responses | Emitted Positions | Scored Positions | Release/Retract Emitted | Status |
|---|---|---|---|---|---|
| `black_transport` | 60 (orig) / 70 (aug) | **0** | 0 | 0 | Refused cleanly |
| `frozen_transport_rgb` | 60 (orig) / 70 (aug) | **0** | 0 | 0 | Refused cleanly |

---

## 5. Separation of Effects and Discussion

1. **Schedule Improvement vs Minimum-Window Rule:**
   - On the augmented stream, all 210 responses match identically between `reacquisition_2frame` and `reacquisition_3frame` in detection status, refusal reasons, and 3D errors. Both fit over the available 3-frame history.
   - The augmented stream demonstrates an **observation-schedule improvement** for Seed 820: adding an intermediate view during lowering reduces Seed 820 error from 21.94 mm to 14.85 mm, satisfying the $\le 20$ mm gate.
   - The original stream demonstrates the **stricter refusal behavior** of the 3-frame rule: in the absence of an intermediate view, `reacquisition_3frame` refuses at Lower on all three recovering seeds (820, 825, 828), proving it cannot emit after only two views.
   - The minimum-frame rule provides refusal protection against insufficient views, but does not provide incremental accuracy beyond what a 2-frame candidate achieves when given the same 3-frame history.
2. **Mean Error Limitation Relative to P5 Proposal:**
   - The mean error over the 17 accepted *original post-warmup targets* on the augmented stream is **5.8715 mm**.
   - While all 17 targets are well within the $\le 20$ mm gate (max 14.85 mm), the 5.87 mm mean exceeds the planning target of $\le 5.0$ mm specified in the earlier P5 proposal.
   - This limitation is reported explicitly; thresholds and gates are not altered.
3. **Depth Ambiguity Mechanism:**
   - The hypothesis that Seed 820's 2-frame error was driven by optical-axis depth ambiguity remains a hypothesis consistent with the observation that multi-view triangulations with wider angular baseline reduce the error, not a mathematically proven fact.
4. **Latency and Compute Cost:**
   - Adding an observation at the lowering midpoint requires camera rendering, transmission, and non-linear multi-view optimization.
   - Although the simulated physical motion is unchanged (25.0s duration), calling perception mid-action consumes computation and communication budget. No 25-second real-time controller qualification is claimed.

---

## 6. Recommendations for Protocol P5

1. **Incorporate Lowering Midpoint:** Protocol P5 should include a deterministic lowering observation ($t_{\text{mid}} = (t_{\text{transport}} + t_{\text{lower}}) / 2.0$) in the trajectory schedule.
2. **Primary Candidate:** Use `TemporalThreeFrameReacquisitionPose` as the primary reacquisition candidate for P5, ensuring it enforces the 3-view requirement and cannot emit on truncated histories.
3. **Preserve Target Mean Gate:** On development data, the post-warmup mean error on accepted original targets is 5.87 mm ($> 5.0$ mm), which fails the planning target of $\le 5.0$ mm. Preserve the existing 5.0 mm proposal gate as an unmet development criterion; do not raise or relax it to accommodate development results.
4. **Status:** Protocol P5 remains proposed in `experiments/humanoid-pick-place/protocols/P5_PROPOSAL.md`. Seeds 840–849 remain untouched pending review.
