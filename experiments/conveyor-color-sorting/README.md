# Conveyor color-sorting experiment

[Experiment plan and progress checklist](PLAN.md)

**Phase 1 complete:** [30/30 episodes and 180/180 cubes collected](PHASE1_RESULTS.md).

**Phase 2 complete:** [270/270 gate episodes passed; overload limits documented](PHASE2_RESULTS.md).

**Phase 3 complete:** [Codex and the conventional selector both passed 9/9 matched episodes](PHASE3_RESULTS.md).
The [Phase 3 tool guide](PHASE3.md) explains persistent observations and actions.

**Phase 4 complete:** [Continuous-time gate passed at 0.5 cm/s; faster and denser failures retained](PHASE4_RESULTS.md).
The [Phase 4 runtime guide](PHASE4.md) covers the live queue and expiring commands.

**Phase 5 complete:** [Camera comparison measured: Codex rejected 6/16 targets; conventional vision 15/16](PHASE5_RESULTS.md).
The [Phase 5 camera guide](PHASE5.md) covers image observations, pixel estimates, and recordings.

**Phase 6 development matrix executed:** [Robustness and adaptation results](PHASE6_RESULTS.md).
The [Phase 6 guide](PHASE6.md) covers versioned rules and the remaining formal benchmark.
The frozen matrix was also [repeated separately with GPT-5.6 Sol](PHASE6_GPT56_SOL_RESULTS.md).

[Phase 2 pushing guide](PHASE2.md) covers the conventional rejection controller,
its scenarios, recording commands, and validation matrix.

## Phase 1: transport baseline

The SO101 stays parked while six free cubes move along a conveyor and drop into
the collection tray. Colors are balanced across red, blue, and green. A seed
randomizes color order, initial lateral position, longitudinal jitter, and yaw.

This checks the conveyor mechanics and outcome scoring. No LLM or sorting
controller runs in Phase 1. The target color only affects the outcome labels:
red cubes reaching collection are correctly reported as `target_missed`, even
though transporting them there is the intended mechanical baseline behavior.

## Run and inspect

Run these commands from the repository root:

```sh
.venv/bin/python -m conveyor_sim run
.venv/bin/mjpython -m conveyor_sim view
```

`run` advances the physics faster than real time and saves an episode. `view`
replays that recorded motion at simulation speed, then pauses at the final frame.
Close the viewer to exit. This is not yet the continuously running LLM runtime
planned for Phase 4.

Customize a trial:

```sh
.venv/bin/python -m conveyor_sim run --seed 3 --speed 0.01 --target blue
```

Speeds are in metres per second. The default is 0.03 m/s (3 cm/s). Each trial
starts with up to six widely spaced cubes already on the belt; there is no
continuous spawning or recycling yet. The accepted count is 1–6. The default
spacing is 12 cm, with up to 4 mm of longitudinal jitter per cube.

The default output folder is `runtime/conveyor/phase1/`. A new run replaces its
files; use `run --output /path/to/trial` to preserve separate trials.

- `report.json`: configuration, every cube's initial state and outcome, metrics,
  dependency versions, and source hashes.
- `episode.npz`: configuration and the sampled physical trajectory for replay.

## Record and capture

```sh
.venv/bin/mjpython -m conveyor_sim record
.venv/bin/mjpython -m conveyor_sim snapshot --time 8
```

These save `conveyor_transport.mp4` and `conveyor.png` in the default output folder.
The MP4 includes simulation time, belt speed, collection count, and a label making
clear that the arm is parked. FFmpeg is required and already installed on this Mac.
`--episode /path/to/trial` selects another saved run. An `overhead` camera is also
available in the MuJoCo viewer for inspecting the layout.

## Physics and layout

- Belt: 12 cm wide, 90 cm long, top at Z = 0; motion is along world +Y.
- Cubes: 3 cm wide, 20 g each, represented by free joints.
- Transport uses MuJoCo `surfacevel` and friction. Cube positions are initialized
  in the scene; their subsequent positions come from physics integration.
- SO101 servos hold their zero-angle pose throughout each run. Cube–arm contacts
  are monitored at every physics step.
- The collection tray is downstream; the reject tray is beside the belt.
  Its accessibility is validated in the Phase 2 pushing results.
- Physics uses a 2 ms timestep, `implicitfast`, and 50 solver iterations.
- Observations and replay frames are sampled approximately every 34 ms.

## Independent scoring

The scorer accepts cube IDs, colors, positions, bounding extents, velocities,
and contact names. It receives no action commands and does not infer success
from an intended motion.

A tray arrival requires the entire cube's world-axis bounding box to be inside
the tray region (with a 0.5 mm tolerance for compliant contact penetration),
a contact path to the tray (possibly through stacked cubes),
and speed below 5 cm/s for at least 0.3 seconds. If a cube leaves the tray, its
arrival is revoked. Outcomes are finalized at the episode deadline.

| Destination or failure | Target color | Other colors |
|---|---|---|
| Collection tray | `target_missed` | `correct_pass` |
| Reject tray | `correct_reject` | `wrong_reject` |
| On belt, speed at most 2 mm/s for at least 2 seconds at deadline | `stuck` | `stuck` |
| On the world floor, below the apparatus, or outside the scene bounds | `lost` | `lost` |
| No settled outcome by deadline | `unresolved` | `unresolved` |

The deadline is the nominal time for the last cube to reach the belt end, plus
six seconds for falling and settling. Every initial cube is included in the
final accounting. Shortened trials (`run --seconds ...`) return failure if cubes
remain unresolved.

The scorer's world-space regions are defined in `conveyor_sim/scoring.py`:

| Region | X bounds (m) | Y bounds (m) | Z bounds (m) |
|---|---|---|---|
| Collection | 0.11–0.33 | 0.41–0.73 | −0.252–−0.025 |
| Reject | 0.29–0.51 | −0.18–0.18 | −0.152–−0.025 |

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m conveyor_sim validate --seeds 10 --speeds 0.01 0.03 0.05
```

The repeated check covers 30 episodes and 180 cubes. Default output is
`runtime/conveyor/validation.json`; use `--output` to select another file.

Each episode must satisfy all transport criteria:

- Every cube reaches and remains settled in the collection tray.
- Zero cube–arm contact steps.
- No premature departure from the belt before the downstream exit area.
- Maximum deviation of any arm joint from its parked position below 0.01 rad.
- Maximum belt-direction speed error no greater than 2 mm/s after startup,
  measured while cubes contact the central belt section.
- Maximum lateral drift no greater than 5 mm over those same samples.

Automated checks also exercise all scoring outcomes, declared-color changes,
tray containment and dwell, stacked support, revoked arrivals, missing IDs,
stopped-belt behavior, shortened-run accounting, and reproducible initial states.
The existing pickup and release checks remain part of the suite.
