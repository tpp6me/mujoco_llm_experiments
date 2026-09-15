# AGY completion — task 009 (revision 1)

Status: **ready for review**
Task brief: `coordination/agy/tasks/009-c2-failure-audit.md`
Branch: `agy/009-c2-failure-audit`
Starting commit: `d125d74be4324dad9b938adcd4ef4ded84a2d636`
Worktree: `/private/tmp/mujoco-llms-agy-009`
Python interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`

---

## Executive summary of revision 1

Following Codex independent review of Task 009, this revision addresses all four review findings
(R1–R4) across the audit implementation, artifacts, tests, and documentation with zero physics steps,
resets, model calls, or modifications to historical C1/C2 evidence archives:

1. **R1 — Public proprioception and contact sheet (high)**:
   - Fixed public proprioception extraction: archived observations store public robot telemetry in
     `request['observation']['robot_state']`, not `obs.get('robot')`.
   - All 7 decisions (3–9) now export complete, non-null `public_robot_state` with 43 joint positions,
     43 joint velocities, hand XYZ, quaternion, and contact links.
   - Structured `public_proprioception_history.json` with strict separation between
     `input_preceding_decision` and `subsequent_command_and_execution`.
   - Added explicit validation in `audit()` that rejects missing or malformed `robot_state`.
   - Removed the contact sheet's interpretive summary card; retained original 960x720 RGB images with
     factual time and command labels, plus a neutral reference metadata index panel.
2. **R2 — Penetration and sample derivation (medium)**:
   - Nearest sample to scorer peak (t=3.795 s) is dynamically derived as sample 118 (t=3.794 s) with
     `nearest_sample_penetration_m = 0.005184672 m` (5.185 mm), correcting earlier attribution to first contact.
   - First contact (sample 117, t=3.761 s, 0.000274 m) and max penetration sample (sample 118, 0.005185 m)
     are derived dynamically from trajectory arrays rather than hard-coded.
   - Derived IK residual from the reproduced error string with four-decimal precision (`0.0542 m`).
3. **R3 — Geometry and comparison overclaims (high)**:
   - Removed necessity/universal claims ("necessarily caused collision", "97 mm finger sweep through block")
     and solid-fill interpretations of bounding boxes.
   - Physical collision is established by the actual empirical contact pairs and recorded trajectory:
     contact begins at sample 117 between `right_hand_middle_0_link` (geom 98) and `object` (geom 105)
     at 0.274 mm penetration, reaching 5.185 mm penetration at sample 118.
   - Retained per-sample hand bounds across all 26 samples of Action 4; measured lower Z extends to -0.0778 m
     pre-approach (0.8 mm beyond prompt nominal -0.077 m); recorded joint deflections under contact
     (middle finger joint reaches 0.112 rad). Explained applicability as approximate with measured limits.
   - Derived C1 vs C2 comparison dynamically from retained evidence archives (`codex_C1_episode.zip`,
     `codex_C1_audit/audit.json`, `codex_C2_episode.zip`), retaining all source hashes.
   - Consistently labelled both intervals and dimensions (XY vs 3D):
     - C1 Action 2 (t=1.000–2.500 s): 84.640 mm XY, 91.591 mm 3D.
     - C2 Action 4 (t=3.200–4.000 s): 154.269 mm XY, 155.212 mm 3D.
     - C2 Action 4 start to Action 5 end (t=3.200–5.000 s): 326.227 mm XY, 804.145 mm 3D (floor height z=0.025 m).
   - Removed unevidenced assertions regarding open-loop intent or transfer/recovery.
4. **R4 — Integrity checks and failure tests (medium)**:
   - Pinned accepted C2 archive digest (`940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8`),
     verified complete and unique member accounting, and verified all 73 member byte hashes before trusting manifest.
   - Fixed source/scene failure tests to leave episode bytes intact and perturb only the specific source lookup,
     directly asserting the specific failure message and absence of output directory.
   - Covered `subprocess.Popen` in the no-model guard in addition to `subprocess.run`, `mj_step`, and `Environment.reset`.
   - Added focused regressions for R1, R2, and archive integrity: 11 tests pass in 1.882 s (8 C2 + 3 C1).

---

## 1. Changes and files updated

| File | Change | Purpose |
|---|---|---|
| `scripts/audit_codex_c2.py` | Updated | Pinned archive check, validated `robot_state`, derived nearest/max samples, dynamic C1 comparison, factual contact sheet |
| `tests/test_codex_c2_audit.py` | Updated | 8 focused tests: Popen/run/reset/step guard, R1 proprioception regression, R2 penetration derivation regression, source/scene/archive mismatch |
| `experiments/humanoid-pick-place/results/codex_C2_audit/` | Regenerated | Complete regeneration from authoritative archive (audit.json, contact_sheet.png, public_proprioception_history.json, private_trajectory_annotations.json, tests.txt) |
| `experiments/humanoid-pick-place/CODEX_C2_DIAGNOSIS.md` | Updated | Revised geometry prose, removed overclaims, added per-sample bounds departure, consistent C1/C2 comparison |
| `experiments/humanoid-pick-place/RESULTS_INDEX.md` | Updated | Updated test count (11 total) and audit references |
| `experiments/humanoid-pick-place/PLAN.md` | Updated | Updated Task 009 checklist and dated log with 11 passing tests and verified public proprioception |
| `coordination/agy/reports/009-completion.md` | Updated | This completion report |

---

## 2. Validation and exact commands

1. **Verify C2 archive integrity and complete member hashes**:
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -c "
   import zipfile, hashlib, json
   archive = 'experiments/humanoid-pick-place/results/codex_C2_episode.zip'
   assert hashlib.sha256(open(archive, 'rb').read()).hexdigest() == '940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8'
   with zipfile.ZipFile(archive) as z:
       manifest = json.loads(z.read('sha256.json'))
       assert len(z.namelist()) == 74 and len(manifest) == 73
       for name, expected in manifest.items():
           assert hashlib.sha256(z.read(name)).hexdigest() == expected
   print('Archive and 73 members verified.')
   "
   ```
   *Outcome: passed (0 mismatches).*

2. **Run C2 audit script and regenerate artifacts**:
   ```sh
   PYTHONPATH=. /Users/praveen/work/github/mujoco-llms/.venv/bin/python scripts/audit_codex_c2.py \
       --episode runtime/humanoid/codex-C2/seed-820 \
       --output experiments/humanoid-pick-place/results/codex_C2_audit
   ```
   *Outcome: generated audit.json (58.5 KB), contact_sheet.png (267.8 KB), public_proprioception_history.json (63.4 KB), private_trajectory_annotations.json (24.0 KB).*

3. **Run focused test suite**:
   ```sh
   PYTHONPATH=. /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest -v \
       tests/test_codex_c2_audit.py tests/test_codex_c1_audit.py \
       > experiments/humanoid-pick-place/results/codex_C2_audit/tests.txt 2>&1
   ```
   *Outcome: Ran 11 tests in 1.882 s, OK.*

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
| C2 episode archive SHA-256 | `940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8` | Pinned C2 archive file digest |
| Scene SHA-256 | `6d86617e402db06acc80226736bc7202ccae5dd8efc98fb348b714935333e725` | `metadata.json` & `scenes/g1_pick_place.xml` |
| C1 archive SHA-256 | `19f3313d521ecbdd5b9181dee2717e9219d5eea1784ed346d6e1553745b9caee` | `codex_C1_episode.zip` file digest |
| C1 audit SHA-256 | `6c3da29eb53d291d30d8e7b24195c174e95debaa76f73d0e1bd3a5d729cdf601` | `codex_C1_audit/audit.json` file digest |
| Action 4 start object xyz (t=3.200 s) | `[0.249256, -0.175484, 0.759999]` m | `episode.npz` sample 100 |
| Action 4 end object xyz (t=4.000 s) | `[0.096101, -0.193997, 0.742923]` m | `episode.npz` sample 125 |
| Action 4 object XY displacement | 154.269491 mm (`0.154269 m`) | `norm(disp[:2])` between samples 100 and 125 |
| Action 4 object 3D displacement | 155.211626 mm (`0.155212 m`) | `norm(disp)` between samples 100 and 125 |
| Action 4 rotation angle | 166.578° | Matrix trace relative to initial orientation |
| Action 4 final upright axis \|Z\| | 0.000223 | `abs(data.xmat[object_id][2, 2])` at sample 125 |
| First sampled hand contact | sample 117 (t=3.761 s, 0.274 mm pen.) | `right_hand_middle_0_link` (geom 98) |
| Sample nearest to scorer peak | sample 118 (t=3.794 s, 5.185 mm pen.) | `right_hand_middle_0_link` (geom 98) |
| Max sampled penetration | sample 118 (t=3.794 s, 5.185 mm pen.) | Derived dynamically across trajectory |
| Scorer peak penetration | 5.184672 mm (`0.005184671623014815 m`) | `evaluator_report.json` at t=3.795 s |
| Scorer normal force at peak penetration | 25.506541 N (`25.51 N`) | `evaluator_report.json` at t=3.795 s |
| Action 5 end object xyz (floor) | `[-0.022621, -0.355780, 0.024999]` m | `episode.npz` sample 155 (t=5.000 s) |
| Act 4 start to Act 5 end XY displacement | 326.226623 mm (`0.326227 m`) | `norm(floor_xy - initial_xy)` |
| Act 4 start to Act 5 end 3D displacement | 804.144769 mm (`0.804145 m`) | `norm(floor_pos - initial_pos)` |
| Action 9 error | `Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m` | `call_009.json` & scratch reproduction |
| Action 9 derived residual | 0.0542 m (four-decimal precision) | Parsed from reproduced error string |
| Action 9 final state unchanged | `True` | `np.array_equal(before, after)` on integration state |
| Max object bottom Z | 0.70946653 m (+9.47 mm above table 0.70 m) | `evaluator_report.json` |

---

## 4. Descriptive C1 vs C2 facts comparison

All metrics are derived directly from retained evidence archives (`codex_C1_episode.zip`, `codex_C2_episode.zip`):

| Metric | C1 (Seed 820) | C2 (Seed 820) |
|---|---|---|
| Protocol ID | `humanoid-codex-c1-development` | `humanoid-codex-c2-development` |
| First damaging action | Action 2 (`move [0.250, -0.184, 0.820]`) | Action 4 (`move [0.251, -0.173, 0.800]`) |
| First damaging action interval | t = 1.000–2.500 s (1.5 s) | t = 3.200–4.000 s (0.8 s) |
| First damaging action XY displacement | **84.640 mm** | **154.269 mm** |
| First damaging action 3D displacement | **91.591 mm** | **155.212 mm** |
| Subsequent displacement interval | None (Action 3 rejected) | Action 4 start to Action 5 end (t=3.200–5.000 s) |
| Subsequent XY displacement | — | **326.227 mm** |
| Subsequent 3D displacement | — | **804.145 mm** (floor height z=0.025 m) |
| Block final posture | Toppled on table | Toppled on table (Act 4), on floor (Act 5) |
| Sustained lift | 0/1 (max bottom 0.7010 m, +1.0 mm) | 0/1 (max bottom 0.7095 m, +9.5 mm) |
| Physical placement | 0/1 | 0/1 |
| Quality pass (penetration ≤ 2 mm) | Failed (6.291 mm peak) | Failed (5.185 mm peak) |
| Scorer normal force at peak penetration | 0.0 N | 25.51 N |
| Terminating stop reason | Collision preflight guard rejection (table overlap) | Interface IK reachability rejection (residual 0.0542 m) |
| Completed actions | 2 | 8 |
| Total simulated duration | 2.50 s | 7.70 s |

---

## 5. Limitations and Codex handoff

1. **Kinematic vs Dynamic Information**: Trajectory samples represent qpos at ~30 Hz, not full
   continuous dynamics. Contact force (25.51 N at peak penetration) and peak timing (t=3.795 s)
   derive from 1 kHz evaluator telemetry, not geometric reconstruction.
2. **Internal Model State**: Action coordinates reflect output requests; they do not reveal
   the model's latent belief, visual localization estimate, or reasoning strategy.
3. **Collision Bounds vs Physical Path**: Nominal prompt bounds describe approximate occupied volume,
   not an open grasp cavity or certified clearance path. Physical contact is demonstrated by the
   empirical contact pairs and path, not box overlap alone.
4. **Single Seed**: All results derive from development seed 820; held-out seeds 840–849 remain untouched.
   P5's 5.0 mm mean gate remains unchanged and unmet.

AGY has assembled and verified all numeric and visual evidence. Codex owns VLA interpretation
and successor-condition decisions. Handoff is complete; stopping for Codex review.
