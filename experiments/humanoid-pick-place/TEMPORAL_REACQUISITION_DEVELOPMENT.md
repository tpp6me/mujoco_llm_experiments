# Temporal RGB/Hand-Motion Reacquisition Development Report

**Date:** 2026-09-12
**Status:** Development candidate evaluated on seeds 820–829. **Disconnected from control.**
**Historical P4 Results:** [P4 Results](TEMPORAL_POSE_RESULTS.md)
**Proposed Protocol:** [P5 Proposal](protocols/P5_PROPOSAL.md)

---

## 1. Executive Summary

This report evaluates an experimental **reacquisition candidate** (`TemporalReacquisitionPose`) designed to recover carried-block tracking after a rejected temporal window.

In historical P4, model mismatch during transport caused full history invalidation, leaving lowering in warmup and resulting in 14/20 post-warmup targets accepted (failing the 16/20 continuation screen). The reacquisition candidate retains the latest valid current image as a new seed without producing an immediate 3D estimate or inheriting the prior transform, and requires fresh subsequent motion evidence (>=80 mm translation).

On development seeds 820–829:
- **Nominal Post-Warmup Coverage increased from 14/20 (70%) to 17/20 (85%)**, accepting 16/20 (80%) within 20 mm.
- **Recovered Seeds:** Seeds 825 and 828 reacquired accurate poses at Lower (2.66 mm and 5.03 mm error) after Transport rejection.
- **Identified Failure Mode (Seed 820):** In Seed 820, Lower was accepted by the optimizer with **21.94 mm error**. The world error vector is `[+1.120, -6.500, +20.922]` mm. Transforming by the calibrated world-to-camera rotation gives `[+1.120, -2.951, -21.708]` mm in camera coordinates, where the camera optical axis is $+Z_c$. The -21.7 mm error component is along the camera line of sight (depth axis), with the fitted center placed ~21.7 mm closer to the camera than ground truth, despite achieving a low silhouette RMS (0.504 px).
- **Depth Ambiguity as Hypothesis:** Monocular depth ambiguity is a plausible hypothesis consistent with this camera-frame error vector, though a single observed failure does not prove that all two-frame baselines lack sufficient parallax or that a three-frame history would unconditionally resolve it. Other potential contributing factors include cuboid silhouette segmentation errors, unmodeled block orientation mismatch, local optimizer convergence minima, or slight non-rigid finger-contact compliance.
- **Containment Preserved:** Zero positions emitted during release or retract (0/20), zero emitted on black transport frames (0/10), and zero emitted on frozen transport RGB frames (0/10).

---

## 2. Comparative Accounting on Development Seeds 820–829

Evaluated offline across the 10 exact-state G2 capture episodes from P4 (60 original responses, 120 responses across 2 additional disruption streams altering only 20 transport frames in total, for 180 total responses per candidate across 3 streams).

### Runner and Input Provenance
- **Runner Invocation:**
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m humanoid_sim.temporal_reacquisition_evaluation \
    --capture-dir /Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture \
    --output experiments/humanoid-pick-place/results/temporal_reacquisition_development.json
  ```
- **Input Provenance:** Recorded from Phase 4 exact-state G2 capture episodes for seeds 820–829 (`/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture/seed-820` through `seed-829`), preserved from base commit `76f8c354755d9d747dc0d4b6a639aa21144e0271`.
- **Retained Test Logs:** Reviewer independent log retained at `coordination/agy/reviews/001-tests.txt` (93 tests); revised suite passing 102 tests.

### Nominal Original Stream

| Metric | Baseline P4 | Reacquisition Candidate |
|---|---:|---:|
| Total original observations | 60 | 60 |
| Total accepted positions | 14 | 17 |
| **Post-warmup targets (Transport + Lower)** | **20** | **20** |
| Post-warmup targets accepted | 14 (70%) | 17 (85%) |
| Post-warmup targets within 20 mm | 14 (70%) | 16 (80%) |
| Post-warmup targets exceeding 20 mm | 0 | 1 (Seed 820: 21.94 mm) |
| Accepted mean error (all accepted) | 3.645 mm | 4.744 mm |
| Accepted mean error (targets <=20 mm) | 3.645 mm | 3.669 mm |
| Accepted maximum error | 7.420 mm | 21.937 mm |
| Release / retract positions emitted | 0/20 | 0/20 |
| Refusal: `insufficient_motion_history` | 33 | 20 |
| Refusal: `inconsistent_rigid_transform` | 13 | 23 |

### Stage-by-Stage Breakdown (Original Stream, 10 Seeds)

| Stage | Baseline P4 Accepted | Reacquisition Accepted | Notes |
|---|---:|---:|---|
| `lift` | 0/10 | 0/10 | 10 warmup (1 frame) |
| `lift_hold` | 0/10 | 0/10 | 10 warmup (baseline < 80 mm) |
| `transport` | 7/10 | 7/10 | Seeds 820, 825, 828 reject (`inconsistent_rigid_transform`) |
| `lower` | 7/10 | **10/10** | 825 (2.66 mm) & 828 (5.03 mm) recover; 820 has 21.94 mm error |
| `release` | 0/10 | 0/10 | 10 reject (`inconsistent_rigid_transform`), relationship broken |
| `retract` | 0/10 | 0/10 | 10 reject (`inconsistent_rigid_transform`), empty hand moves away |

### Correlated Sensor Disruption Streams

| Stream | Baseline P4 Accepted | Reacquisition Accepted | Altered Transport Emitted | Release/Retract Emitted |
|---|---:|---:|---:|---:|
| `black_transport` (60 responses) | 0/60 | 0/60 | 0/10 | 0/20 |
| `frozen_transport_rgb` (60 responses) | 0/60 | 0/60 | 0/10 | 0/20 |

---

## 3. Detailed Diagnosis: The Seed 820 Failure

In Seed 820, transport rejected with worst-frame RMS 1.160 px (> 0.75 px threshold). Reacquisition seeded the transport frame.
At Lower, the hand translated downward by 115 mm, providing sufficient baseline for a 2-frame fit across `[transport, lower]`.

The optimization converged with:
- Best window RMS: 0.504 px (frame 0: 0.497 px, frame 1: 0.504 px), well below the 0.75 px threshold.
- Hypothesis selection: 8 near-best hypotheses, spread = 11.9 mm (<= 20 mm threshold).
- Error vector in world coordinates: `[+1.120, -6.500, +20.922]` mm.
- Error vector in camera coordinates ($R_{w\to c} \Delta x_w$): `[+1.120, -2.951, -21.708]` mm.
- Error norm: **21.94 mm**.

**Analysis:**
The largest error component (-21.7 mm) aligns closely with the camera optical axis $+Z_c$, placing the reconstructed block slightly too close to the camera.
Monocular depth ambiguity is a hypothesis consistent with this coordinate alignment: a single camera observing a short translation baseline provides weak parallax along the line of sight, allowing small silhouette residual changes to mask significant depth offsets. However, a single observed occurrence does not establish that all two-frame baselines lack sufficient parallax or that any three-frame history unconditionally resolves it without comparison. Other contributing factors may include silhouette boundary segmentation fidelity, local optimizer convergence, or subtle non-rigid finger-pad compliance.

---

## 4. Architectural Safeguards Verified

1. **No Stale or Immediate Output:** On model mismatch, `detected` remains `False`, `reason` is `'inconsistent_rigid_transform'`, and no position is emitted.
2. **Fresh Motion Required:** If subsequent hand translation is < 80 mm, `insufficient_motion_history` is returned.
3. **Invalid Imagery and Calibration Protection:** Missing visible boundaries, blank frames (`frame is None`), invalid/non-orthonormal camera rotation matrices, non-finite/negative focal lengths, invalid hand poses/quaternions, malformed metadata, duplicate IDs, nonadvancing timestamps, and time gaps > 3.0 s invalidate the tracker and purge any seeded frame.
4. **Physical Break Invalidation:** When the hand opens during release, or moves away during retract, the model mismatch check rejects without false positives.
5. **Default Behavior Preserved:** Default `TemporalPose()` preserves historical P4 behavior across all test cases (with output dictionary augmented with explicit diagnostic `'reacquisition_mode': False`).

---

## 5. Next Steps and Recommendations

1. **Do not connect to control**; maintain complete isolation from the acting policy.
2. Propose successor protocol [P5](protocols/P5_PROPOSAL.md) on held-out seeds 840–849.
3. Treat 2-frame depth ambiguity as an open hypothesis requiring explicit testing or comparison (e.g. evaluating 3-frame windows vs. orthogonal motion baselines) before deploying in control.
