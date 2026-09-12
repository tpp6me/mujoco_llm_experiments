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
- **Identified Failure Mode (Seed 820):** In Seed 820, Lower was accepted by the optimizer with **21.94 mm error** (20.9 mm error along the camera line of sight Z-axis), despite achieving a low silhouette RMS (0.504 px). With only a 2-frame baseline (`[transport, lower]`), monocular perspective ambiguity permits low-residual fits with significant depth error.
- **Containment Preserved:** Zero positions emitted during release or retract (0/20), zero emitted on black transport frames (0/10), and zero emitted on frozen transport RGB frames (0/10).

---

## 2. Comparative Accounting on Development Seeds 820–829

Evaluated offline across the 10 exact-state G2 capture episodes from P4 (60 original observations, 120 corrupted observations across 3 streams).

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
| `black_transport` (60 obs) | 0/60 | 0/60 | 0/10 | 0/20 |
| `frozen_transport_rgb` (60 obs) | 0/60 | 0/60 | 0/10 | 0/20 |

---

## 3. Detailed Diagnosis: The Seed 820 Failure

In Seed 820, transport rejected with worst-frame RMS 1.160 px (> 0.75 px threshold). Reacquisition seeded the transport frame.
At Lower, the hand translated downward by 115 mm, providing sufficient baseline for a 2-frame fit across `[transport, lower]`.

The optimization converged with:
- Best window RMS: 0.504 px (frame 0: 0.497 px, frame 1: 0.504 px), well below the 0.75 px threshold.
- Hypothesis selection: 8 near-best hypotheses, spread = 11.9 mm (<= 20 mm threshold).
- Error vector: `[+1.1 mm, -6.5 mm, +20.9 mm]` in world coordinates.
- Error norm: **21.94 mm**.

**Root cause:** A 2-frame window viewed from a single camera provides insufficient perspective parallax to disambiguate depth along the optical axis for a 5 × 7 × 12 cm block. In 3-frame windows, three distinct camera-relative viewpoints constrain depth significantly better.

---

## 4. Architectural Safeguards Verified

1. **No Stale or Immediate Output:** On model mismatch, `detected` remains `False`, `reason` is `'inconsistent_rigid_transform'`, and no position is emitted.
2. **Fresh Motion Required:** If subsequent hand translation is < 80 mm, `insufficient_motion_history` is returned.
3. **Invalid Imagery Protection:** Missing visible boundaries or black frames (`frame is None`), malformed metadata, duplicate IDs, nonadvancing timestamps, and time gaps > 3.0 s invalidate the tracker and purge any seeded frame.
4. **Physical Break Invalidation:** When the hand opens during release, or moves away during retract, the model mismatch check rejects without false positives.

---

## 5. Next Steps and Recommendations

1. **Do not connect to control**; maintain complete isolation from the acting policy.
2. Propose successor protocol [P5](protocols/P5_PROPOSAL.md) on held-out seeds 840–849.
3. Consider requiring either a 3-frame history or explicit orthogonal motion before qualifying reacquired estimates, to resolve 2-frame monocular depth ambiguity.
