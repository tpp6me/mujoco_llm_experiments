# Phase 2 — physical pushing baseline

This phase uses a conventional controller with supplied target IDs and exact
positions. It tests the SO101's ability to reject a cube by pushing it into the
side tray. There are no LLM decisions or camera-based perception in these runs.

**Complete:** [validation results and measured operating limits](PHASE2_RESULTS.md).

## Run

From the repository root:

```sh
# One stationary target.
.venv/bin/python -m conveyor_sim push --scenario isolated --speed 0

# One moving target between two non-target cubes.
.venv/bin/python -m conveyor_sim push --scenario neighbors --speed 0.02 --seed 3

# Three consecutive targets on a slow belt.
.venv/bin/python -m conveyor_sim push --scenario stream --speed 0.01 --spacing 0.08
```

Each run replaces `runtime/conveyor/phase2/`. Use `--output /path/to/trial` to
preserve a run separately. `--target red|blue|green` sets the designated target's
color; the neighboring-cube scenario gives the other two cubes the other colors.
The scenario supplies the correct target IDs to the controller. This establishes
a mechanical baseline before testing LLM target selection in Phase 3.

## View and record

```sh
.venv/bin/mjpython -m conveyor_sim view --episode runtime/conveyor/phase2
.venv/bin/mjpython -m conveyor_sim record --episode runtime/conveyor/phase2 --output runtime/conveyor/phase2/pushing.mp4
.venv/bin/mjpython -m conveyor_sim snapshot --episode runtime/conveyor/phase2 --time 10 --output runtime/conveyor/phase2/pushing.png
```

The viewer and MP4 replay saved physics states at simulation speed. The overlay
identifies the conventional controller, target color, belt speed, rejected count,
and passed count. Physics advances continuously through all motions and simulated
waiting periods, but runs faster than wall-clock time during headless evaluation.
Continuous wall-clock execution during LLM calls remains Phase 4 work.

## Motion and interception

The existing SO101 model and actuator limits are used without adding a pusher
attachment. The closed gripper contacts the cube; it is not welded or attached to it.

1. Approach above the near side of the belt at X = 0.18 m, Z = 0.065 m (2 seconds).
2. For a moving cube, wait until its center reaches Y = −0.015 m.
3. Descend to Z = 0.020 m, leading the cube by the expected belt movement during
   descent (1 second).
4. Sweep to X = 0.30 m while following the belt's Y motion (2 seconds).
5. Retract diagonally to X = 0.22 m, Z = 0.075 m (approximately 1.5 seconds).

The diagonal retraction accommodates the SO101's joint limits at extended reach.
Cartesian moves use waypoints no more than 5 mm apart. The controller preflights
inverse kinematics for a complete motion before changing the live state, then
interpolates actuator targets at the 2 ms physics timestep. The initial approach
uses joint interpolation at clearance height. This is a validated trajectory for
this scene, not a general collision-aware motion planner.

The nominal cube centerline is X = 0.22 m, randomized by ±6 mm. Y position is
randomized and cube yaw varies by ±0.15 rad. Targets move toward world +Y; the
arm pushes toward world +X into the existing reject tray.

The interception controller explicitly reports a missed window when a target is
more than 0.5 seconds past the entry time after approach. It then lets every cube
reach an outcome so failures remain visible in the scorer's results.

## Success and clearance

A trial passes only if:

- Every designated target finishes in the reject tray.
- Every non-target finishes in the collection tray.
- Every target has recorded physical contact with the arm.
- No arm contact with a non-target cube or conveyor fixture occurred.
- No cube–cube contact occurred in the belt area; pile contacts inside trays are allowed.
- Every motion endpoint tracks within 5 mm of its requested tool position.
- The controller completes without an interception or IK error.

The existing independent scorer supplies destinations, including containment,
contact support, dwell, and revocation if a cube leaves a tray. All physical
contacts used for clearance checks are monitored at every physics step.

`report.json` contains target IDs, action timing, measured endpoint errors,
contacts, cube outcomes, configuration, versions, and source hashes. `episode.npz`
stores the configuration and sampled trajectory for replay. Cube states are only
initialized by the scene builder; subsequent motion comes from dynamics.

## Gate validation

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m conveyor_sim validate-push
```

The default validation writes `runtime/conveyor/push_validation.json`. Use
`--output` to select another path. The matrix contains:

| Group | Trials | Purpose |
|---|---|---|
| Stationary isolated target | 100 | At least 95% successful rejections |
| Isolated target at 1 cm/s | 100 | At least 95% successful rejections |
| Target between neighbors, 12 cm spacing | 10 each at 0.5, 1, 2, 3 cm/s | All trials pass without unintended contacts |
| Three consecutive targets at 1 cm/s | 10 each at 8, 10, 12 cm spacing | All trials pass with complete retraction/recovery |
| Overload: 6 cm spacing at 1 cm/s | 10 | Report timing failures; excluded from supported conditions |
| Overload: 12 cm spacing at 2 cm/s | 10 | Report timing failures; excluded from supported conditions |

The matrix uses separate seed ranges from the initial development examples and
cycles target colors. It retains the full reports for passing and failing runs.
Overload groups are explicitly separate from gate cases; their failures must not
be presented as successful sorting. Fewer than 100 isolated trials per condition
cannot satisfy the gate, even when a shortened validation run has no failures.

The eventual LLM comparison should use this same motion capability and declare
which additional choices the LLM makes. Phase 2 performance alone is not evidence
of LLM efficacy.
