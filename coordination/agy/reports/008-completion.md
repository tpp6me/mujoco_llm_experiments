# AGY completion — task 008

Status: **ready for review**  
Task brief: `coordination/agy/tasks/008-c2-execution.md`  
Branch: `agy/008-c2-execution`  
Starting commit (clean source freeze): `a675e5223a7966926744624561d2e4542883d17a`  
Worktree: `/private/tmp/mujoco-llms-agy-008`  
Python interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/mjpython` (and `.venv/bin/python`)  

---

## 1. Frozen input and execution verification

Before starting the episode or creating tracked files:
- Verified clean git working tree at frozen starting commit `a675e5223a7966926744624561d2e4542883d17a`.
- Verified local CLI installation and ChatGPT login using local checks only (`codex-cli 0.154.0`, logged in via ChatGPT, executable `/Users/praveen/versions/node/v20.18.1/bin/codex`). No API keys, direct API calls, or live model probes.
- Verified frozen protocol SHA-256:
  - `experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md`: `a1a3b982fd455c9c2e220787be74c9bbad4c1c0dd6f4e32894aac9a896ced7c0`
  - `experiments/humanoid-pick-place/protocols/C2.md`: `388ed874df4271784c3255954b1efbbe34173748891b24b4ef1caae142ad7757`
- Verified static instruction digest: `6d90729760f5458d69dfc6d90e9f433eacd7721f2552e8c24060a840e27237db`.
- Verified serialized geometry digest: `d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6`.
- Generated and saved pre-run manifest to `runtime/humanoid/codex-C2/manifest.json` (SHA-256 `72f2da6d97318fc8ee2c3ca11d02db62195683f24c9b98894340c5633b69f306`).
- Executed the literal authorized command once:
  ```sh
  /Users/praveen/work/github/mujoco-llms/.venv/bin/mjpython -m humanoid_sim.codex_policy --execute --condition c2 --output runtime/humanoid/codex-C2/seed-820
  ```
- Captured stdout, stderr, and exit status. The runner ran to completion and saved all episode artifacts in `runtime/humanoid/codex-C2/seed-820/`.

---

## 2. Experiment outcomes

| Metric | Planned | Measured | Result / Status |
|---|---:|---:|---|
| Episodes | 1 | 1 | Complete (seed 820) |
| Physical placement | 1 | 0 | 0/1 placements (`success=false`) |
| Sustained lift | 1 | 0 | 0/1 sustained lifts (`lifted=false`) |
| Strict pass | 1 | 0 | 0/1 strict passes |
| Max object bottom Z | — | 0.7095 m | No lift above table (0.70 m) |
| Peak object penetration | ≤ 2.0 mm | 5.185 mm | Quality limit failed (at t=3.795 s against `right_hand_middle_0_link`) |
| Peak contact normal force | — | 25.51 N | Recorded during Decision 4 descent collision |
| Simulated duration | ≤ 25.0 s | 7.70 s | Deadline passed (t ≤ 25.0 s) |
| CLI invocations | ≤ 20 | 9 | 9 invocations (ephemeral sessions) |
| Completed actions | — | 8 | 8 actions executed |
| Rejected actions | — | 1 | Guard rejection on Decision 9 (`Unreachable hand pose`) |
| Budget exhaustion vs failure | — | Rejection | Stopped on guard rejection, not budget exhaustion |
| Tool calls in event logs | 0 | 0 | Clean event audit; zero tool items |
| Decision latency (wall) | ≤ 120 s | 24.99 s mean | Total 224.89 s; min 12.08 s; max 36.59 s |
| Token usage (total) | — | 103,092 in / 5,164 out | 5,888 cached input; 4,700 reasoning output |

Neither process exit 0 nor `placement_success_claimed=false` is treated as a task success. Physical placement, sustained lift, contact quality, and rejection criteria all failed.

---

## 3. Action trace and sampled post-hoc kinematics

All coordinates are world metres; downward orientation quaternion `[0.5, -0.5, 0.5, 0.5]`.

1. **Decision 1** (t=0.50–1.00 s): `hand` closure 0.0, 0.5 s. Completed. Fingers opened; hand site at `[0.2385, -0.1803, 0.9332]`; block untouched at `[0.2493, -0.1755, 0.7600]`.
2. **Decision 2** (t=1.00–2.00 s): `move` to `[0.251, -0.149, 0.91]`, 1.0 s. Completed. Hand site reached `[0.2478, -0.1494, 0.9061]`; block untouched.
3. **Decision 3** (t=2.00–3.20 s): `move` to `[0.251, -0.149, 0.84]`, 1.2 s. Completed. Hand site reached `[0.2470, -0.1492, 0.8363]`; block untouched.
4. **Decision 4** (t=3.20–4.00 s): `move` to `[0.251, -0.173, 0.80]`, 0.8 s. Completed.
   - Hand site translated toward `[0.2467, -0.1727, 0.7966]`.
   - At t=3.795 s, middle finger (`right_hand_middle_0_link`, geom 98) collided with the red block.
   - Peak penetration reached 5.185 mm with 25.51 N normal force.
   - Collision knocked block 155.21 mm total (154.27 mm in XY) toward table edge, ending at `[0.0961, -0.1940, 0.7429]`, tilted to `[-0.1601, -0.2457, -0.6630, 0.6888]`.
5. **Decision 5** (t=4.00–5.00 s): `hand` closure 1.0, 1.0 s. Completed. Hand closed; destabilized block slid off table edge to floor at `[-0.0226, -0.3558, 0.0250]` (745.44 mm displacement).
6. **Decision 6** (t=5.00–6.20 s): `move` to `[0.251, -0.173, 0.95]`, 1.2 s. Completed. Hand lifted to `[0.2484, -0.1735, 0.9460]`. Empty grasp; block remained on floor.
7. **Decision 7** (t=6.20–6.70 s): `hand` closure 0.0, 0.5 s. Completed. Fingers opened at Z=0.9460.
8. **Decision 8** (t=6.70–7.70 s): `move` to `[0.251, -0.173, 0.80]`, 1.0 s. Completed. Hand descended to `[0.2466, -0.1728, 0.7962]`.
9. **Decision 9** (t=7.70 s): `move` to `[0.15, -0.48, 0.90]`, 1.2 s. Rejected. Commanded target was kinematically unreachable for the fixed-pelvis G1 arm with downward quaternion (`Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m`). Guard rejected action; episode halted.

*Note on kinematics*: Qpos trajectory analysis is post-hoc only and represents sampled kinematic geometry; it cannot reconstruct continuous peak contact forces or exact microsecond dynamics.

---

## 4. Boundary audit and packaging

- **Audit**:
  - Validated all 9 public request payloads against saved prompts and observation PNGs using `public_input(call_data['request'], condition='c2')`: 100% byte-for-byte exact reproduction.
  - Validated all 9 CLI event logs using `validate_events`: zero tool items, exactly one turn start and completion, final message matching `decision.json`.
  - Verified all tracked source file hashes match pre-run manifest.
- **Evidence archive**:
  - Saved all 73 runtime files from `runtime/humanoid/codex-C2/` into committed ZIP `experiments/humanoid-pick-place/results/codex_C2_episode.zip` with per-file SHA-256 manifest `sha256.json` (74 files total).
  - Archive SHA-256: `940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8`.
- **Machine-readable result**:
  - Written to `experiments/humanoid-pick-place/results/codex_C2.json` (SHA-256 `72d1e5e2e4805988fecd4439aebc6d37b0ea8f8d8077766b57069fdd00308cc1`).
- **Reports and documentation**:
  - `experiments/humanoid-pick-place/CODEX_C2_RESULTS.md`
  - `experiments/humanoid-pick-place/RESULTS_INDEX.md`
  - `experiments/humanoid-pick-place/PLAN.md`

---

## 5. Verification and limitations

- `git diff --check`: passed cleanly.
- Historical C1 artifacts and code/protocols: unchanged.
- No controller code changes, dependency changes, or live API keys.
- C2 is a descriptive development result on development seed 820; it is not a statistical C1/C2 comparison or a qualified visual controller.
- P5 reacquisition remains separate and unqualified under its unchanged 5.0 mm gate.
- Held-out seeds 840–849 remain untouched.
