# Proposed Successor Protocol P5 — Temporal Reacquisition Validation

**STATUS: PROPOSED ONLY — NOT FROZEN, NOT EXECUTED.**
*This protocol is submitted for Codex review under AGY task 001. No fresh episodes or validation runs under this protocol have been executed or generated.*

---

## 1. Objective and Scope

Evaluate whether the experimental temporal reacquisition candidate (`TemporalReacquisitionPose`) reliably re-establishes carried-block pose tracking following model mismatch across held-out trajectories without introducing uncontained drift, false positives, or stale predictions.

Tracking remains an experimental candidate and **strictly disconnected from control**. The acting `PerceptionSession` continues to use the verified P2 prior lifetime guard.

---

## 2. Proposed Evaluation Denominator and Held-Out Seeds

- **Proposed Seeds**: 840–849 (10 episodes). Verified unused in repository history.
- **Driving Policy**: Conventional exact-state G2 controller (identical to P4), release height Z = 0.88 m, hand closure = 0.4.
- **Observations per Episode**: Six action endpoints per completed episode:
  1. `lift` (warmup)
  2. `lift_hold` (warmup)
  3. `transport` (nominal post-warmup target)
  4. `lower` (nominal post-warmup target)
  5. `release` (ground-truth relationship termination)
  6. `retract` (ground-truth empty-hand motion)
- **Total Nominal Observations**: 60 across 10 episodes, yielding:
  - 40 carried observations (lift, lift_hold, transport, lower).
  - 20 nominal post-warmup targets (transport, lower).
  - 20 empty-hand / relationship-loss endpoints (release, retract).
- **Correlated Sensor Disruption Streams**:
  - `black_transport`: 60 observations (transport image replaced with blank/black frame).
  - `frozen_transport_rgb`: 60 observations (transport image replaced with lift_hold RGB while preserving current robot pose/timestamp/ID).
- **Total Evaluated Responses**: 180 responses across 3 streams. Every refusal, error, or missing case remains in the denominator.

---

## 3. Development Evidence and Model Definition

Development evaluation on seeds 820–829 under task 001 established:
1. Reacquisition enabled tracking to recover at Lower on seeds 825 (2.66 mm error) and 828 (5.03 mm error) after transport rejection.
2. In Seed 820, Lower was accepted with 21.94 mm error (+20.9 mm in Z), revealing that a 2-frame window (`[transport, lower]`) is susceptible to monocular line-of-sight depth ambiguity despite passing the 0.75 px RMS threshold.
3. Across all 10 seeds, zero false positives were emitted during release or retract (0/20 accepted), and zero false positives were emitted during sensor disruption (0/20 on altered transport frames).

### Fixed Model Parameters
- **Window Size**: Up to 3 frames (`WINDOW_SIZE = 3`).
- **Motion Threshold**: Minimum 80 mm hand translation (`MIN_BASELINE_M = 0.08`).
- **Timing Constraint**: Maximum 3.0 s gap between observations (`MAX_GAP_S = 3.0`).
- **Reacquisition Semantics**: On model mismatch (`inconsistent_rigid_transform`), retain only the current valid frame as a seed (`self.frames = [frame]`).
- **Input Hardening**: Invalid metadata, duplicate IDs, nonadvancing timestamps, camera/robot calibration errors, and visibility loss (`frame is None`) immediately invalidate the tracker and clear all history (`self.frames.clear()`).
- **Release Invalidation**: Explicit `invalidate()` on announced release or reset.

---

## 4. Action and Time Budget Accounting

If reacquisition requires an active recovery motion to resolve 2-frame depth ambiguity (e.g. collecting a third observation after a small orthogonal translation):
- Each additional observation step consumes 1 communication round.
- Active recovery motion must be bounded (e.g. 1.0–2.0 simulated seconds) and counted directly against the task's 25-second deadline.
- In this passive evaluation protocol, no extra recovery motions are injected; tracking is evaluated strictly on the natural motion of the G2 trajectory.

---

## 5. Continuation Gates (Screening Criteria)

To qualify for consideration in an active visual control loop, the fresh validation on seeds 840–849 must satisfy:
1. **Nominal Post-Warmup Coverage**: >=16/20 post-warmup targets accepted (transport and lower across 10 episodes).
2. **Maximum Accepted Error**: No accepted original center error exceeding 20.0 mm (addressing the Seed 820 depth ambiguity).
3. **Accuracy**: Mean error of accepted targets <= 5.0 mm.
4. **Safety & Containment**:
   - Zero accepted positions on `release` or `retract` (0/20).
   - Zero accepted positions on corrupted `transport` images (0/10 black, 0/10 frozen RGB).
5. **No State Leakage**: All private ground-truth poses and drift metrics computed post-hoc after candidate returns.

---

## 6. Execution Authorization

**DO NOT RUN.** This protocol must be reviewed, locked with frozen source/scene hashes, and authorized by Codex before any execution on seeds 840–849.
