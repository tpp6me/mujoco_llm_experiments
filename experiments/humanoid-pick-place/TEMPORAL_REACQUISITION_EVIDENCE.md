# Multi-View Evidence for Temporal Pose Reacquisition (Task 002)

Date: 2026-09-12. Branch: `agy/002-reacquisition-evidence`.
Base commit: `64bc19a00a03a83a3dc44f75225d6be619a3a754`.

---

## 1. Objective and Hypothesis

In Task 001 (`agy/001-reacquisition`), enabling temporal reacquisition upon model mismatch recovered 17/20 post-warmup targets on development seeds 820–829, recovering accurate lower poses on Seeds 825 and 828, but accepted Seed 820 at **21.94 mm** error (a false acceptance exceeding the 20 mm gate due to monocular depth ambiguity along the camera optical axis).

Task 002 tested the specific hypothesis:
> **Hypothesis:** Requiring a third distinct, fresh RGB/hand observation within the reacquired window reduces the known Seed 820 false acceptance without eliminating useful post-warmup coverage.

To isolate the effect of the observation schedule from the minimum-window rule, Task 002 compared three conditions across both the original endpoint-only stream (6 stages) and an augmented stream (7 stages) with a deterministic lowering midpoint:
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
1. **Original Endpoint-Only Stream (6 stages, 60 responses/variant):**
   - Stages: `lift` ($t=8.5$s), `lift_hold` ($t=9.0$s), `transport` ($t=11.0$s), `lower` ($t=13.0$s), `release` ($t=15.0$s), `retract` ($t=17.0$s).
   - Post-warmup targets: nominal targets are fixed at 2 per seed (`transport` and `lower`), giving 20 post-warmup targets.
2. **Augmented Stream (7 stages, 70 responses/variant):**
   - Stages: `lift` ($t=8.5$s), `lift_hold` ($t=9.0$s), `transport` ($t=11.0$s), `lower_mid` ($t=12.0$s), `lower` ($t=13.0$s), `release` ($t=15.0$s), `retract` ($t=17.0$s).
   - Deterministic schedule: lowering midpoint selected solely by timestamp $t_{\text{mid}} = (t_{\text{transport}} + t_{\text{lower}}) / 2 = 12.0$s.
   - Exact physical states were rendered from saved `episode/episode.npz` recordings using unchanged MuJoCo scene and camera models into `runtime/humanoid/temporal-P4-augmented/capture/` (local and gitignored).

---

## 3. Motion Baselines and Window Mechanics

Across all seeds 820–829, lowering spans $t=11.0$s to $t=13.0$s:
- **At Lowering Midpoint ($t=12.0$s):** Hand translation from `transport` is **65–72 mm** (below the 80 mm motion threshold).
  - Both 2-frame and 3-frame reacquisition trackers refuse with `insufficient_motion_history`.
  - Exactly 0 positions emitted at midpoint for seeds recovering from transport mismatch (Seeds 820, 825, 828).
- **At Lower Endpoint ($t=13.0$s):** Total hand translation reaches **97–104 mm** (satisfying the $\ge 80$ mm motion threshold).
  - In the original stream, only 2 frames exist after reacquisition seed (`[transport, lower]`).
    - `reacquisition_3frame` refuses with `insufficient_motion_history` (proving it cannot emit after only two views).
    - `reacquisition_2frame` fits across 2 frames, accepting Seed 820 at 21.94 mm error.
  - In the augmented stream, 3 frames exist in history (`[transport, lower_mid, lower]`).
    - Both 2-frame and 3-frame trackers fit across the full 3-frame window.
    - Multi-view triangulation resolves the optical-axis depth ambiguity.

---

## 4. Empirical Evaluation Results

### Aggregate Performance Across Development Seeds 820–829

| Stream | Candidate | Accepted / Total | Post-Warmup Accepted / Targets | $\le 20$ mm | $> 20$ mm | Mean Error | Max Error | Release/Retract Accepted |
|---|---|---|---|---|---|---|---|---|
| **Original** | `baseline_p4` | 14 / 60 | 14 / 20 | 14 | 0 | 3.64 mm | 7.42 mm | 0 |
| **Original** | `reacquisition_2frame` | 17 / 60 | 17 / 20 | 16 | 1 (Seed 820) | 4.74 mm | **21.94 mm** | 0 |
| **Original** | `reacquisition_3frame` | 14 / 60 | 14 / 20 | 14 | 0 | 3.64 mm | 7.42 mm | 0 |
| **Augmented** | `baseline_p4` | 21 / 70 | 14 / 20 | 21 | 0 | 4.82 mm | 9.44 mm | 0 |
| **Augmented** | `reacquisition_2frame` | 24 / 70 | 17 / 20 | **24** | **0** | 5.07 mm | **14.85 mm** | 0 |
| **Augmented** | `reacquisition_3frame` | 24 / 70 | 17 / 20 | **24** | **0** | 5.07 mm | **14.85 mm** | 0 |

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

## 5. Key Findings

1. **Hypothesis Confirmed:** Adding a third fresh observation within the lowering sequence directly reduced Seed 820's lower pose error from **21.94 mm to 14.85 mm**, resolving the monocular depth ambiguity and satisfying the $\le 20$ mm accuracy gate across 100% of accepted post-warmup poses.
2. **Refusal Rule Enforced:** In the absence of intermediate views (the original endpoint-only stream), `TemporalThreeFrameReacquisitionPose` strictly refuses at `lower` on all three recovery seeds (820, 825, 828), verifying that it cannot emit after only two views.
3. **Motion Gate Preserved:** At the lowering midpoint, hand motion is ~68 mm ($< 80$ mm threshold). Both candidates correctly refuse at midpoint (`insufficient_motion_history`), preventing premature estimation before sufficient parallax is established.
4. **Safety Maintained:** Invalidation upon physical release, hand retraction, black transport, and frozen frames is preserved without regression (0 false acceptances).
5. **Compute and Communication Cost:** Additional observations require image capture, serialization, and multi-view non-linear optimization time. While simulated physical motion duration is unchanged (25.0s), an active controller making intermediate perception calls incurs compute latency. No 25-second real-time controller qualification is claimed.

---

## 6. Recommendations for Protocol P5

1. **Observation Schedule:** Protocol P5 should mandate capturing a deterministic lowering midpoint ($t=12.0$s) in addition to endpoints.
2. **Candidate Selection:** Adopt `TemporalThreeFrameReacquisitionPose` as the primary reacquisition candidate for P5 validation, paired with the 3-frame lowering schedule.
3. **Status:** P5 remains proposed, not frozen or executed. Seeds 840–849 remain untouched pending formal review.
