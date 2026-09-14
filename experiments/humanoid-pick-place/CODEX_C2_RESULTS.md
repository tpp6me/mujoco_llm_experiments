# C2: Codex visual controller development result

The signed-in Codex CLI chose structured actions from camera images, public robot
state, nominal hand geometry bounds, and visual reassessment guidance under condition C2.
The single seed-820 simulator episode achieved **0/1 placements and 0/1 sustained lifts**.
Eight actions executed successfully; the ninth was rejected by the collision guard
due to kinematic unreachability (`Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m`).
Normal budget exhaustion (20 decisions, 25.0 s simulated deadline) was not reached; the
episode halted on guard rejection at t=7.70 s.

The user authorized ChatGPT-login Codex decisions without direct API integration or API keys.
No API keys or AGY reasoning were used to choose robot actions. All nine CLI invocations
are retained. The CLI may make internal network requests; nine is an invocation count, not
an API request count.

## Declared condition and outcome

[C2 protocol](protocols/C2.md) and implementation were frozen before the episode at commit
`a675e5223a7966926744624561d2e4542883d17a`. CLI version 0.154.0 used ChatGPT login,
requested `gpt-5.6-sol` with low reasoning, fixed 960 x 720 RGB, public calibration and
proprioception, serialized nominal robot hand collision bounds, and the guarded
move/hand/hold interface. The backend model snapshot is not independently identified by
the CLI event stream. The budget was 20 invocations and simulated t=25 s, with 120 s timeout
per decision and no wrapper retry.

| Measure | Result |
|---|---:|
| Planned / completed episodes | 1 / 1 |
| Placement / sustained lift / strict pass | 0 / 0 / 0 |
| CLI decisions / executed actions / rejected actions | 9 / 8 / 1 |
| Tool calls observed in decision event logs | 0 |
| Final simulation time, including reset | 7.70 s (deadline pass: t ≤ 25.0 s) |
| Total wall decision latency | 224.89 s |
| Mean / minimum / maximum CLI decision latency | 24.99 / 12.08 / 36.59 s |
| Peak object penetration | 5.185 mm; exceeds 2.0 mm quality limit |
| Peak recorded contact normal force | 25.51 N against `right_hand_middle_0_link` at t=3.795 s |

The process exited after saving the episode. Exit code zero or `placement_success_claimed=false`
must not be used as a task-success indicator. Private scorer `success` and `lifted` are both
false. The deadline pass is met (7.70 s ≤ 25.0 s), but physical placement, contact-quality,
and rejection criteria failed.

## Action trace and interpretation

All positions are world metres and use downward quaternion `[0.5, -0.5, 0.5, 0.5]`.

| Decision | Time range | Requested primitive | Execution | Outcome / Post-hoc geometry |
|---|---|---|---|---|
| 1 | t=0.50–1.00 s | `hand` closure 0.0, 0.5 s | Completed | Fingers opened; hand site at `[0.2385, -0.1803, 0.9332]`; block untouched at `[0.2493, -0.1755, 0.7600]` |
| 2 | t=1.00–2.00 s | `move` to `[0.251, -0.149, 0.91]`, 1.0 s | Completed | Hand site reached `[0.2478, -0.1494, 0.9061]`; block untouched |
| 3 | t=2.00–3.20 s | `move` to `[0.251, -0.149, 0.84]`, 1.2 s | Completed | Hand site reached `[0.2470, -0.1492, 0.8363]`; block untouched |
| 4 | t=3.20–4.00 s | `move` to `[0.251, -0.173, 0.80]`, 0.8 s | Completed | Hand site reached `[0.2467, -0.1727, 0.7966]`. Middle finger contacted block at t=3.795 s (5.185 mm penetration, 25.51 N normal force). Block displaced 155.21 mm (154.27 mm XY) to `[0.0961, -0.1940, 0.7429]`, tilted to quaternion `[-0.1601, -0.2457, -0.6630, 0.6888]` |
| 5 | t=4.00–5.00 s | `hand` closure 1.0, 1.0 s | Completed | Hand closed. Destabilized block slid off table edge to floor at `[-0.0226, -0.3558, 0.0250]` (745.44 mm displacement) |
| 6 | t=5.00–6.20 s | `move` to `[0.251, -0.173, 0.95]`, 1.2 s | Completed | Hand lifted to `[0.2484, -0.1735, 0.9460]`. Empty grasp; block remained on floor |
| 7 | t=6.20–6.70 s | `hand` closure 0.0, 0.5 s | Completed | Hand opened; block remained on floor |
| 8 | t=6.70–7.70 s | `move` to `[0.251, -0.173, 0.80]`, 1.0 s | Completed | Hand lowered to `[0.2466, -0.1728, 0.7962]`; block remained on floor |
| 9 | t=7.70 s | `move` to `[0.15, -0.48, 0.90]`, 1.2 s | Rejected | Arm IK residual 0.0542 m exceeded reachability threshold; guard rejected action; episode halted |

Sampled post-hoc geometry indicates that during Decision 4, the hand translated in -Y
and descended toward Z=0.80 m while grasping was open. The solid middle finger
(`right_hand_middle_0_link`, geom 98) collided with the red block at t=3.795 s. Peak penetration
reached 5.185 mm with 25.51 N normal force recorded by the private contact sensor. This collision
knocked the block over and drove it 154.27 mm laterally toward the table edge. During Decision 5,
the closing fingers missed the displaced block, which fell from the table to the floor.

Following the loss of the block, the policy executed a lift (Decision 6), release (Decision 7),
and downward re-approach (Decision 8), before attempting a wide transfer motion to `[0.15, -0.48, 0.90]`
(Decision 9). That target was kinematically unreachable for the fixed-pelvis G1 arm with the declared
downward orientation quaternion, resulting in guard rejection.

Private qpos trajectory analysis is post-hoc only; it reconstructs sampled kinematic geometry
and cannot reconstruct continuous peak contact forces or exact microsecond dynamics.

## Boundary and validation evidence

Every saved episode prompt and observation PNG reproduced byte-for-byte from its allowlisted public
`call_NNN.json` request via `public_input(..., condition='c2')`. All nine CLI event logs passed the
pinned audit (`validate_events`), containing exactly one turn start, one agent completion matching
`decision.json`, and zero tool use. Source hashes at completion match the pre-run manifest exactly.
Each decision used a fresh temporary directory with disabled tools, shell, apps, plugins, memory,
and host skill discovery.

- Complete static instruction SHA-256: `6d90729760f5458d69dfc6d90e9f433eacd7721f2552e8c24060a840e27237db`.
- Serialized geometry evidence SHA-256: `d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6`.
- Pre-run manifest SHA-256: `72f2da6d97318fc8ee2c3ca11d02db62195683f24c9b98894340c5633b69f306`.
- Episode archive SHA-256: `940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8`.
- Token totals across 9 decisions: 103,092 input tokens (5,888 cached), 5,164 output tokens (4,700 reasoning tokens).

## Retained artifacts

- Machine-readable result: [codex_C2.json](results/codex_C2.json)
- Complete episode archive: [codex_C2_episode.zip](results/codex_C2_episode.zip) (74 files including `sha256.json` manifest)
- Pre-run manifest: `runtime/humanoid/codex-C2/manifest.json`
- Frozen protocol: [protocols/C2.md](protocols/C2.md) and [protocols/C2_PROPOSAL.md](protocols/C2_PROPOSAL.md)

C2 is a descriptive development trial on development seed 820, not a statistical claim or a
qualified visual controller. P5 remains separate and unqualified under its unchanged 5.0 mm gate.
Held-out seeds 840–849 remain untouched.
