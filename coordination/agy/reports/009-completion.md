# AGY completion — task 009

Status: **ready for review**
Task brief: `coordination/agy/tasks/009-c2-failure-audit.md`
Branch: `agy/009-c2-failure-audit`
Starting commit: `d125d74be4324dad9b938adcd4ef4ded84a2d636`
Worktree: `/private/tmp/mujoco-llms-agy-009`
Python interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`

---

## Executive summary

Task 009 executes a reproducible, post-hoc offline failure audit of the committed C2 episode
(`experiments/humanoid-pick-place/results/codex_C2_episode.zip`), patterned directly after
`scripts/audit_codex_c1.py`. **Zero physics steps, simulator resets, or model invocations**
occurred during this task. All historical C1/C2 archives, protocols, and outcomes remain
byte-for-byte unchanged.

Key findings of the audit:
1. **Archive and Scene Provenance**: Verified committed C2 ZIP SHA-256
   (`940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8`) and all 73 members
   against `sha256.json`. All 30 tracked execution sources and scene hash
   (`6d86617e402db06acc80226736bc7202ccae5dd8efc98fb348b714935333e725`) match the freeze.
2. **Action 4 Approach Kinematics**: Between t=3.200 s (sample 100) and t=4.000 s (sample 125),
   Action 4 commanded `move [0.251, -0.173, 0.80]`, 0.8 s. Hand contact displaced the red block
   **154.269 mm in XY** (155.212 mm 3D), rotating it 166.58° into a toppled posture on the table
   edge (`upright_axis_z_abs = 0.000223`). By the end of Action 5 (t=5.000 s), the destabilized
   block slid off the table onto the floor (804.145 mm total displacement to floor height z=0.025 m).
3. **Contact Telemetry Distinction**:
   - **Full-rate 1 kHz scorer telemetry**: Private scorer recorded peak penetration of **5.185 mm**
     (`0.005184672 m`) and **25.51 N normal force at peak penetration** (`25.506541 N`) at
     **t=3.795 s** (`3.794999999999693 s`) against `right_hand_middle_0_link` (geom 98).
     The 25.51 N value is normal force *at peak penetration*, not a separately maximized normal force.
   - **Sampled 30 Hz qpos geometry**: First sampled contact occurred at t=3.761 s (0.274 mm penetration,
     middle link); nearest sample 118 at t=3.794 s matches the 5.185 mm penetration. Qpos reconstruction
     represents sampled kinematic geometry only and cannot infer continuous contact forces or exact peak timing.
4. **Finger Geometry vs Prompt Nominal Bounds**:
   - Nominal prompt bounds (X `[-0.074, +0.058]`, Y `[-0.042, +0.042]`, Z `[-0.077, +0.085]` m)
     accurately bounded actual open-hand collision volume in downward orientation (actual X `[-0.0729, +0.0572]`,
     Y `[-0.0415, +0.0416]`, Z `[-0.0774, +0.0847]` m at contact).
   - However, bounds enclose solid occupied geometry rather than an open grasp cavity. With upright
     block top at z=0.820 m, commanding grasp site z=0.800 m placed the reference 20 mm inside the block,
     sweeping open fingers extending down to z ~ 0.723 m directly into the block.
5. **Visual Progression & Public/Private Separation**:
   - Assembled an ordered contact sheet (`contact_sheet.png`, 273 KB) from original saved public images
     for Decisions 3–9 using ordinary Pillow composition.
   - Packaged exact public proprioception and public history in `public_proprioception_history.json`.
   - Segregated private evaluator ground truth (object poses, distances, contacts) in `private_trajectory_annotations.json`.
6. **Action 9 IK Reachability Reproduction**:
   - Loaded saved final integration state at t=7.70 s and called `Environment.solve` on scratch data.
   - Exact production error reproduced: `Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m`.
   - Verified `before == after` integration state bit-for-bit (`final_integration_state_unchanged: True`).
7. **Descriptive Comparison**: Compared descriptive facts between C1 and C2 (first damaging action,
   displacement, penetration, lift/placement, stop reason). Recorded explicit disclaimer that differences
   on the single shared development seed (820) are descriptive observations, not proof of controller efficacy.
8. **Focused Test Suite**: 8 tests run in 0.991 s (5 new focused C2 audit tests + 3 C1 audit tests),
   all passing cleanly with physics stepping and model invocations patched out.

---

## 1. Changes and files created

| File | Type | Purpose |
|---|---|---|
| `scripts/audit_codex_c2.py` | New script | Reproducible offline audit patterned after `scripts/audit_codex_c1.py` |
| `tests/test_codex_c2_audit.py` | New tests | 5 focused unit tests: physics/model disable, modified evidence rejection, source/scene mismatch, output overlap/exists |
| `experiments/humanoid-pick-place/results/codex_C2_audit/audit.json` | New artifact | Master numeric audit evidence |
| `experiments/humanoid-pick-place/results/codex_C2_audit/contact_sheet.png` | New artifact | Ordered Pillow contact sheet for decisions 3–9 |
| `experiments/humanoid-pick-place/results/codex_C2_audit/public_proprioception_history.json` | New artifact | Exact public robot state and history for decisions 3–9 |
| `experiments/humanoid-pick-place/results/codex_C2_audit/private_trajectory_annotations.json` | New artifact | Segregated evaluator ground truth for decisions 3–9 & Action 4 |
| `experiments/humanoid-pick-place/results/codex_C2_audit/tests.txt` | New artifact | Log of 8 passing audit unit tests |
| `experiments/humanoid-pick-place/CODEX_C2_DIAGNOSIS.md` | New document | C2 failure diagnosis patterned after `CODEX_C1_DIAGNOSIS.md` |
| `experiments/humanoid-pick-place/RESULTS_INDEX.md` | Modified | Added C2 failure audit entry |
| `experiments/humanoid-pick-place/PLAN.md` | Modified | Updated Task 009 checkbox and dated progress table |
| `coordination/agy/tasks/009-c2-failure-audit.md` | Modified | Marked all 9 checklist items complete |
| `coordination/agy/reports/009-completion.md` | New report | This completion report |

---

## 2. Validation and exact commands

### Commands executed

1. **Verify C2 archive integrity and manifest**:
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -c "
   import zipfile, hashlib, json
   archive = 'experiments/humanoid-pick-place/results/codex_C2_episode.zip'
   with open(archive, 'rb') as f:
       assert hashlib.sha256(f.read()).hexdigest() == '940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8'
   with zipfile.ZipFile(archive) as z:
       manifest = json.loads(z.read('sha256.json'))
       assert len(z.namelist()) == 74 and len(manifest) == 73
       for name, expected in manifest.items():
           assert hashlib.sha256(z.read(name)).hexdigest() == expected
   print('Archive and 73 members verified.')
   "
   ```
   *Outcome: passed (0 mismatches).*

2. **Run C2 audit script**:
   ```sh
   PYTHONPATH=. /Users/praveen/work/github/mujoco-llms/.venv/bin/python scripts/audit_codex_c2.py \
       --episode runtime/humanoid/codex-C2/seed-820 \
       --output experiments/humanoid-pick-place/results/codex_C2_audit
   ```
   *Outcome: generated audit.json, contact_sheet.png, public_proprioception_history.json, private_trajectory_annotations.json.*

3. **Run focused test suite**:
   ```sh
   PYTHONPATH=. /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest -v \
       tests/test_codex_c2_audit.py tests/test_codex_c1_audit.py \
       > experiments/humanoid-pick-place/results/codex_C2_audit/tests.txt 2>&1
   ```
   *Outcome: Ran 8 tests in 0.991 s, OK.*

4. **Whitespace check against starting commit**:
   ```sh
   git diff --check d125d74be4324dad9b938adcd4ef4ded84a2d636..HEAD
   ```
   *Outcome: clean (zero whitespace or formatting errors).*

---

## 3. Numeric evidence and self-review

All arithmetic and metrics in this report were verified against raw JSON and trajectory arrays:

| Quantity | Self-reviewed value | Raw evidence source |
|---|---|---|
| C2 episode archive SHA-256 | `940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8` | `codex_C2_episode.zip` file digest |
| Scene SHA-256 | `6d86617e402db06acc80226736bc7202ccae5dd8efc98fb348b714935333e725` | `metadata.json` & `scenes/g1_pick_place.xml` |
| Audit script SHA-256 | `0db57ffd308dedd6742aff83555b8782b274e70a8e36f8390ee50ea9940c174e` | `scripts/audit_codex_c2.py` file digest |
| Action 4 start object xyz | `[0.249256, -0.175484, 0.759999]` m | `episode.npz` sample 100 (t=3.200 s) |
| Action 4 end object xyz | `[0.096101, -0.193997, 0.742923]` m | `episode.npz` sample 125 (t=4.000 s) |
| Action 4 object XY displacement | 154.269491 mm (`0.154269491 m`) | `norm(disp[:2])` between samples 100 and 125 |
| Action 4 object total displacement | 155.211626 mm (`0.155211626 m`) | `norm(disp)` between samples 100 and 125 |
| Action 4 rotation angle | 166.578° | Matrix trace relative to initial orientation |
| Action 4 final upright axis \|Z\| | 0.000223 | `abs(data.xmat[object_id][2, 2])` at sample 125 |
| Scorer peak penetration | 5.184672 mm (`0.005184671623014815 m`) | `evaluator_report.json` at t=3.795 s |
| Scorer normal force at peak penetration | 25.506541 N (`25.51 N`) | `evaluator_report.json` at t=3.795 s |
| Action 5 end object xyz (floor) | `[-0.022621, -0.355780, 0.024999]` m | `episode.npz` sample 155 (t=5.000 s) |
| Total displacement to floor | 804.144769 mm (`0.804145 m`) | `norm(floor_pos - initial_pos)` |
| Action 9 error | `Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m` | `call_009.json` & scratch reproduction |
| Action 9 final state unchanged | `True` | `np.array_equal(before, after)` on integration state |
| Max object bottom Z | 0.70946653 m (+9.47 mm above table 0.70 m) | `evaluator_report.json` |

---

## 4. Descriptive C1 vs C2 facts comparison

| Fact | C1 (Seed 820) | C2 (Seed 820) |
|---|---|---|
| Protocol | `humanoid-codex-c1-development` | `humanoid-codex-c2-development` |
| Earliest damaging action | Action 2 (`move [0.250, -0.184, 0.820]`) | Action 4 (`move [0.251, -0.173, 0.800]`) |
| Damaging action displacement | 84.640 mm XY | 154.269 mm XY (804.145 mm to floor by Act 5) |
| Block toppling | Toppled on table | Toppled on table, then floor |
| Sustained lift | 0/1 (max bottom 0.7010 m, +1.0 mm) | 0/1 (max bottom 0.7095 m, +9.5 mm) |
| Physical placement | 0/1 | 0/1 |
| Quality pass (penetration ≤ 2 mm) | Failed (6.291 mm peak) | Failed (5.185 mm peak) |
| Scorer normal force at peak penetration | 0.0 N | 25.51 N |
| Terminating stop reason | Collision preflight guard rejection (table overlap) | Interface IK reachability rejection (residual 0.0542 m) |
| Completed actions | 2 | 8 |
| Total simulated time | 2.50 s | 7.70 s |

---

## 5. Limitations and Codex handoff

1. **Kinematic vs Dynamic Information**: Trajectory samples represent qpos at ~30 Hz, not full
   continuous dynamics. Contact force (25.51 N at peak penetration) and peak timing (t=3.795 s)
   derive from 1 kHz evaluator telemetry, not geometric reconstruction.
2. **Internal Model State**: Action coordinates reflect output requests; they do not reveal
   the model's latent belief, visual localization estimate, or reasoning process.
3. **Collision Bounds vs Grasp Cavity**: The nominal bounds accurately describe occupied volume
   for the downward open hand, but bounds alone cannot certify a free cavity or safe trajectory.
4. **Single Seed**: All results derive from development seed 820; held-out seeds 840–849 remain untouched.
   P5's 5.0 mm mean gate remains unchanged and unmet.

AGY has assembled and verified all numeric and visual evidence. Codex owns VLA interpretation
and successor-condition decisions. Handoff is complete; stopping for Codex review.
