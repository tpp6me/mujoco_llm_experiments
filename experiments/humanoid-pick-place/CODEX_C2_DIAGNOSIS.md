# C2 failure diagnosis

2026-09-15. Post-hoc offline analysis of the saved C2 episode, with **zero physics steps,
fresh resets or model invocations**. Original C1 and C2 actions, outcomes, guard thresholds,
and evidence archives are preserved byte-for-byte. [Reproducible audit](../../scripts/audit_codex_c2.py),
[full numeric evidence](results/codex_C2_audit/audit.json),
[contact sheet](results/codex_C2_audit/contact_sheet.png),
[public proprioception/history](results/codex_C2_audit/public_proprioception_history.json),
[private trajectory annotations](results/codex_C2_audit/private_trajectory_annotations.json),
[original result](CODEX_C2_RESULTS.md).

The failure sequence began during Action 4 when the descending open hand collided with the
upright block, toppling and displacing it 154.269 mm in XY toward the table edge. In Action 5,
the destabilized block slid off the table edge to the floor (804.145 mm total displacement).
Subsequent actions (6–8) continued open-loop manipulation at the original table region while the
block lay on the floor. Finally, Action 9 commanded an unreachable position at the table edge
and was rejected by interface inverse kinematics (residual 0.0542 m) without physics advance.

---

## Saved observations and visual progression

Public observation images for Decisions 3–9 are assembled into an ordered contact sheet
from the original saved PNGs using ordinary Pillow composition (no image generation or new rendering):

![C2 Decisions 3 to 9 Contact Sheet](results/codex_C2_audit/contact_sheet.png)

Alongside this contact sheet:
- Public proprioception (`robot_state`) and public history are recorded in
  [`results/codex_C2_audit/public_proprioception_history.json`](results/codex_C2_audit/public_proprioception_history.json).
- Ground-truth object states, contact pairs, and displacement data are kept in the separately
  labelled evaluator artifact [`results/codex_C2_audit/private_trajectory_annotations.json`](results/codex_C2_audit/private_trajectory_annotations.json).

AGY measures and assembles the evidence; Codex owns VLA interpretation and successor-condition decisions.

---

## Action 4 approach kinematics and contact measurements

Action 4 (`call_004`, t=3.20–4.00 s) executed a `move` to `[0.251, -0.173, 0.80]`, 0.8 s.

| Metric | Measured value | Attribution / Source |
|---|---|---|
| Initial block centre (t=3.200 s) | `[0.249256, -0.175484, 0.759999]` m | Sampled qpos geometry (sample 100) |
| Commanded grasp site | `[0.251, -0.173, 0.800]` m | Public action command |
| Final block centre (t=4.000 s) | `[0.096101, -0.193997, 0.742923]` m | Sampled qpos geometry (sample 125) |
| Block displacement in Action 4 | `[-153.155, -18.513, -17.076]` mm | Sampled qpos geometry |
| Block XY displacement in Action 4 | **154.269 mm** | Sampled qpos geometry |
| Block 3D displacement in Action 4 | 155.212 mm | Sampled qpos geometry |
| Block rotation angle in Action 4 | 166.578° | Sampled qpos geometry |
| Final block upright axis \|Z\| | 0.000223 (toppled) | Sampled qpos geometry |
| First sampled hand/block contact | t=3.761 s, 0.274 mm penetration | Sampled qpos geometry (sample 117, `right_hand_middle_0_link`) |
| Max sampled hand/block penetration | t=3.794 s, 5.185 mm penetration | Sampled qpos geometry (sample 118, `right_hand_middle_0_link`) |
| Scorer peak object penetration | **5.185 mm** (`0.005184672 m`) | Authoritative 1 kHz private scorer telemetry (t=3.795 s) |
| Scorer normal force at peak penetration | **25.51 N** (`25.506541 N`) | Authoritative 1 kHz private scorer telemetry (t=3.795 s) |
| Final block centre after Action 5 (t=5.000 s) | `[-0.022621, -0.355780, 0.024999]` m | Sampled qpos geometry (floor height) |
| Total block displacement to floor | **804.145 mm** | Sampled qpos geometry |

### Distinction: full-rate scorer telemetry vs sampled qpos geometry

- **Full-rate scorer telemetry**: The simulation evaluator runs at every 1 ms physics step
  (1000 Hz). It recorded peak penetration of 5.185 mm and **25.51 N normal force at peak penetration**
  at t=3.795 s against `right_hand_middle_0_link` (geom 98). The 25.51 N value is specifically the normal
  force measured at peak penetration, not a separately maximized normal force.
- **Sampled qpos geometry**: The saved trajectory records robot and object configuration at approximately
  30 Hz (dt ≈ 0.033 s). Nearest sample 118 (t=3.794 s) shows 5.185 mm geometric overlap with
  `right_hand_middle_0_link`. Qpos trajectory analysis is post-hoc geometric reconstruction only; it cannot
  reconstruct continuous contact forces, normal impulses, or exact microsecond collision dynamics.

---

## Finger geometry vs nominal C2 bounds

The C2 prompt supplied nominal collision bounds for the open hand in downward orientation:
- **Prompt nominal bounds (relative to site)**:
  - X: `[-0.074, +0.058]` m
  - Y: `[-0.042, +0.042]` m
  - Z: `[-0.077, +0.085]` m

Actual collision geometry along the Action 4 path was evaluated from collision mesh vertices and box corners:
- Pre-approach actual bounds (t=3.200 s): X `[-0.0725, +0.0572]`, Y `[-0.0417, +0.0414]`, Z `[-0.0778, +0.0847]` m
- Contact actual bounds (t=3.794 s): X `[-0.0729, +0.0572]`, Y `[-0.0415, +0.0416]`, Z `[-0.0774, +0.0847]` m
- Independent robot calibration (`nominal_open_hand_geometry`): downward IK at `[0.24, -0.18, 0.94]`, closure 0:
  X `[-0.0736, +0.0572]`, Y `[-0.0416, +0.0414]`, Z `[-0.0770, +0.0847]` m

### Applicability finding

The prompt's reference frame and numeric bounds **were applicable**: the hand was fully open (closure 0) and
in the downward orientation, so the actual collision volume closely matched the prompt bounds.
However:
1. **Bounds describe solid occupied geometry**, not an open grasp cavity or collision-free path.
2. The upright block top is at `z = 0.760 + 0.060 = 0.820 m`.
3. The commanded grasp site was `z = 0.800 m` (20 mm below the top of the block).
4. Because fingers extend to `z_site - 0.077 m = 0.723 m`, descending the site to 0.800 m swept the solid
   fingers directly through the top 97 mm of the upright block.
Bounds alone do not certify a safe path; planning descent below the top of the object necessarily caused collision.
This is a geometric measurement of the commanded path; it does not assert what the model internally believed.

---

## Action 9 IK reachability rejection

Action 9 commanded `move` to `[0.15, -0.48, 0.90]`, 1.2 s, orientation `[0.5, -0.5, 0.5, 0.5]`.

- **Production rejection**: Rejected before execution by interface inverse kinematics:
  `Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m`.
- **Scratch-data reproduction**: Loading the preserved final integration state at t=7.70 s and calling
  `Environment.solve` on scratch data reproduced the exact error string:
  `Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m`.
- **Integration state preservation**: `before == after` integration state check passes bit-for-bit
  (`final_integration_state_unchanged: True`). No physics steps or state mutations occurred.

---

## Descriptive comparison: C1 vs C2

| Dimension | C1 (Seed 820) | C2 (Seed 820) |
|---|---|---|
| Protocol ID | `humanoid-codex-c1-development` | `humanoid-codex-c2-development` |
| First damaging action | Action 2 (`move [0.250, -0.184, 0.820]`) | Action 4 (`move [0.251, -0.173, 0.800]`) |
| Block XY displacement in damaging action | 84.640 mm | 154.269 mm |
| Block final state | Toppled on table | Toppled on table (Act 4), on floor (Act 5) |
| Total block displacement | 84.640 mm | 804.145 mm (to floor) |
| Sustained lift | 0/1 (max bottom 0.7010 m, +1.0 mm) | 0/1 (max bottom 0.7095 m, +9.5 mm) |
| Physical placement | 0/1 | 0/1 |
| Strict pass | 0/1 | 0/1 |
| Peak object penetration | 6.291 mm (at t=2.093 s) | 5.185 mm (at t=3.795 s) |
| Normal force at peak penetration | 0.0 N | 25.51 N |
| Terminating stop reason | Action 3 collision guard rejection (table overlap) | Action 9 IK reachability rejection (residual 0.0542 m) |
| Completed actions | 2 | 8 |
| Simulated duration | 2.50 s | 7.70 s |

**Efficacy disclaimer**: C1 and C2 share a single development seed (820). Differences in action sequence,
completed action count, or penetration are descriptive development observations. They do not constitute
statistical or causal evidence of controller efficacy or task improvement.

---

## Verification and test coverage

- [x] Verified committed C2 archive SHA-256 (`940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8`)
      and all 73 members against manifest.
- [x] Verified frozen provenance source file hashes and scene hash match current repository.
- [x] Reproducible offline audit executed with zero physics steps, resets, or model calls.
- [x] Action 9 IK rejection reproduced on scratch data with zero state mutation.
- [x] Ordered contact sheet generated with Pillow from original public images for Decisions 3–9.
- [x] Public proprioception/history and private trajectory annotations cleanly separated into distinct artifacts.
- [x] 5 focused C2 audit tests and 3 C1 audit tests pass cleanly:
      [`results/codex_C2_audit/tests.txt`](results/codex_C2_audit/tests.txt).
- [x] Arithmetic self-reviewed against JSON evidence.
