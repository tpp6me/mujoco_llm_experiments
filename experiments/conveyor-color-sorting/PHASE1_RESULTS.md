# Phase 1 results — conveyor transport

Completed: 2026-09-09.

**Gate passed: 30/30 episodes and 180/180 cubes transported into the collection
tray without robot intervention.** Phase 2 has not started.

## Validation matrix

| Belt speed | Seeds | Episodes | Cubes collected |
|---|---|---|---|
| 1 cm/s | 0–9 | 10/10 passed | 60/60 |
| 3 cm/s | 0–9 | 10/10 passed | 60/60 |
| 5 cm/s | 0–9 | 10/10 passed | 60/60 |
| Total | | 30/30 passed | 180/180 |

Each episode used six 3 cm, 20 g cubes with balanced colors and randomized color
order, initial position jitter, and yaw. The SO101 held its initial zero-angle
pose throughout. Cube motion was produced by belt friction and physics.

## Measured limits

| Check | Required limit | Worst observed result |
|---|---|---|
| Cube–arm contact steps | 0 | 0 |
| Premature belt departures | 0 | 0 |
| Arm joint deviation from parked pose | < 0.01 rad | 0.000827 rad |
| Belt-direction speed error after startup | ≤ 0.002 m/s | 1.18 × 10⁻⁹ m/s |
| Lateral drift on central belt section | ≤ 0.005 m | 0.000580 m (0.58 mm) |
| Cubes remaining unresolved at deadline | 0 | 0 |

The very small belt-speed error reflects this idealized constant-speed, high-friction
simulation. It is not a claim about a physical conveyor's accuracy.

## Independent scoring

With red declared as the target, the final sorting labels were:

- 120 `correct_pass` (blue and green cubes in collection).
- 60 `target_missed` (red cubes in collection).
- Zero wrong rejections, lost cubes, stuck cubes, or unresolved cubes.

These expected target misses distinguish sorting performance from the Phase 1
transport objective. No LLM or sorting controller was evaluated.

The scorer checks containment, speed, dwell, and tray contact support, including
support through stacked cubes. Every cube is accounted for. A cube leaving a
tray loses its previously detected arrival.

## Boundary correction during development

The first matrix classified 178/180 cubes as collected. The two unclassified
cubes were physically inside the collection tray, resting against its front
wall, with approximately 0.10 mm and 0.04 mm of compliant contact penetration.

Added a 0.5 mm region-containment tolerance and a regression check confirming
that larger violations still fail. No cube states or transport physics were
changed to resolve these outcomes. Reran all 30 episodes with the corrected scorer.
This is development validation, not a held-out LLM benchmark.

- [Initial boundary-check report](results/phase1_initial_boundary_check.json)
- [Final full report](results/phase1_transport.json)

Each report contains seed/configuration data, per-cube outcomes, metrics, dependency
versions, and source SHA-256 hashes. All 30 final reports were checked against the
scene, SO101 model XML, environment, and scorer source hashes at Phase 1 completion.

## Automated and visual checks

All **15 tests** passed, covering conveyor transport; stopped-belt behavior;
physical landings in the reject tray; all outcome labels; color changes; support
chains; region bounds and dwell; revoked arrivals; missing IDs; shortened runs;
reproducible initial states; and the existing SO101 pickup/release checks.

The native macOS replay viewer opened and closed successfully in a bounded check.
The default six-cube run was exported as a 32.93-second, 960 × 720, 30 fps H.264 MP4.
Full video decoding passed. Rendered frames and the final `Collected 6/6` overlay
were inspected.

Generated local artifacts (ignored by Git):

- `runtime/conveyor/phase1/report.json`
- `runtime/conveyor/phase1/episode.npz`
- `runtime/conveyor/phase1/conveyor.png`
- `runtime/conveyor/phase1/conveyor_transport.mp4`

## Reproduce

From the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m conveyor_sim validate --seeds 10 --speeds 0.01 0.03 0.05
.venv/bin/python -m conveyor_sim run
.venv/bin/mjpython -m conveyor_sim view
.venv/bin/mjpython -m conveyor_sim record
```

See the [usage guide](README.md) for configuration, scoring definitions, and output
locations. The next gate is Phase 2: reliable physical pushing into the reject tray.
