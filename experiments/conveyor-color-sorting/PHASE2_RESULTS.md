# Phase 2 results — SO101 physical pushing

Date: 2026-09-09. **Phase 2 gate passed.** The existing SO101 gripper physically
pushes designated cubes into the reject tray, then retracts clear of the belt.
The controller receives exact target IDs and positions. No LLM decisions are
evaluated in this phase.

## Validation

The full [machine-readable report](results/phase2_push_validation.json) retains
all 290 episodes, including 20 overload probes. The 270 gate episodes rejected
330/330 targets and passed 80/80 non-targets. There were no unintended arm–cube,
arm–fixture, or cube–cube contacts in the belt area.

| Condition | Successful episodes | Targets rejected | Non-targets passed |
|---|---:|---:|---:|
| Stationary isolated target | 100/100 | 100/100 | — |
| Moving isolated target, 1 cm/s | 100/100 | 100/100 | — |
| Target between neighbors, 12 cm spacing, 0.5 cm/s | 10/10 | 10/10 | 20/20 |
| Same, 1 cm/s | 10/10 | 10/10 | 20/20 |
| Same, 2 cm/s | 10/10 | 10/10 | 20/20 |
| Same, 3 cm/s | 10/10 | 10/10 | 20/20 |
| Three consecutive targets, 1 cm/s, 8 cm spacing | 10/10 | 30/30 | — |
| Same, 10 cm spacing | 10/10 | 30/30 | — |
| Same, 12 cm spacing | 10/10 | 30/30 | — |

Each isolated condition exceeds the planned gate of 95 successful rejections in
100 trials. Evaluation seeds were 1000–1099 for isolated trials, 2000–2009 for
neighbor trials, 3000–3009 for consecutive targets, and 4000–4009 for overload
probes. Target colors cycle through red, blue, and green. The scene randomizes
lateral position by ±6 mm, longitudinal position, and yaw by ±0.15 rad. These
results apply to this scene and parameter distribution, without physical-robot
calibration or perception uncertainty.

All 20 automated tests passed, covering existing pickup and conveyor behavior,
physical pushing, neighboring cubes, repeated targets, overload accounting, and
IK failure before live state changes. Saved source hashes for every evaluation
episode were verified against the implementation at Phase 2 completion.

## Motion, reach, and spacing

The belt remains centered at X = 0.22 m. The tool descends at X = 0.18 m and
sweeps to X = 0.30 m at Z = 0.020 m. Across the passing trials, descent Y targets
ranged from approximately −0.007 to 0.020 m, and sweep endpoints from −0.007 to
0.080 m. The tool retracts diagonally to (0.22, 0.005, 0.075) m to stay within
the SO101's reach. This establishes a tested trajectory through the working
area; it is not a map of every reachable or collision-free pose.

Measured arm motion per rejection takes **6.52–6.57 simulation seconds**, excluding
waiting for the next target. The largest measured tool endpoint error in the
gate trials was **0.332 mm**, below the 5 mm threshold. Endpoint error does not
measure tracking error along every point of the trajectory.

For three consecutive targets at 1 cm/s, **8 cm is the smallest tested passing
nominal center-to-center spacing**. Ten and twelve centimetres also passed.
Spacing has up to 4 mm of initial longitudinal jitter per cube. Eight centimetres
provides an 8-second nominal arrival interval, above the measured motion cycle.
The exact minimum spacing has not been established; 7 cm was not tested.

## Overload failures

| Condition | Successful episodes | Targets rejected | Targets missed |
|---|---:|---:|---:|
| Three targets, 6 cm spacing at 1 cm/s | 1/10 | 19/30 | 11/30 |
| Three targets, 12 cm spacing at 2 cm/s | 0/10 | 10/30 | 20/30 |

Both conditions have a nominal 6-second arrival interval, shorter than the arm's
motion cycle. The controller reported that a target had passed its interception
entry point. All missed cubes reached the collection tray and were counted as
`target_missed`; no cube was omitted from scoring. These failures are retained
in the report and excluded from the declared supported conditions.

The neighboring-cube checks at faster speeds test one selected target with two
non-target neighbors. They do not establish consecutive rejection capacity at
those speeds. Use 1 cm/s and 12 cm nominal spacing as a conservative starting
configuration for Phase 3; 8 cm is available as a tighter tested condition.

## Demonstration and reproduction

The [recorded demonstration](../../runtime/conveyor/phase2/pushing.mp4) shows one
red target between green and blue cubes at 2 cm/s, seed 3. The red cube settles
in the reject tray; both other cubes settle in the collection tray. The MP4 is
43.67 seconds, 960 × 720, 30 fps, H.264. Playback through the MuJoCo viewer,
video metadata, full FFmpeg decoding, and frames around the rejection were checked.
The overlay explicitly labels the conventional controller and supplied state.

Runtime artifacts are ignored by Git and can be recreated from the repository:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m conveyor_sim validate-push --output experiments/conveyor-color-sorting/results/phase2_push_validation.json
.venv/bin/python -m conveyor_sim push --scenario neighbors --speed 0.02 --seed 3
.venv/bin/mjpython -m conveyor_sim record --episode runtime/conveyor/phase2 --output runtime/conveyor/phase2/pushing.mp4
```

See the [pushing guide](PHASE2.md) for controller details and other scenarios,
and the [progress checklist](PLAN.md) for subsequent phases. Phase 3 has not started.
