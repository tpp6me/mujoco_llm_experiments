# MuJoCo experiments with Codex

MuJoCo runs locally on the Mac. Codex operates a simulated SO101 arm through
terminal commands, observing state and contacts after each action.

## Experiment plans

- [G1 humanoid pick and basket](experiments/humanoid-pick-place/README.md):
  supported-body contact manipulation, persistent controls, replay, and independent scoring;
  [complete implementation checklist](experiments/humanoid-pick-place/PLAN.md) progresses toward visual LLM control and free-standing balance.
- [SO101 conveyor color sorting](experiments/conveyor-color-sorting/PLAN.md):
  phased plan for evaluating LLM instruction-following, vision, and timed robotic actions.

The [Phase 1 conveyor guide](experiments/conveyor-color-sorting/README.md) covers
transport trials, independent scoring, viewer replay, video export, and validation.
The [Phase 2 pushing results](experiments/conveyor-color-sorting/PHASE2_RESULTS.md)
document the validated conventional controller, its demonstration video, and timing limits.
The [Phase 3 results](experiments/conveyor-color-sorting/PHASE3_RESULTS.md) compare
Codex's explicit sorting actions with the conventional controller using structured state.
The [Phase 4 results](experiments/conveyor-color-sorting/PHASE4_RESULTS.md) show
continuous-time sorting and the measured command-latency and cycle-time limits.
The [Phase 5 results](experiments/conveyor-color-sorting/PHASE5_RESULTS.md) compare
camera-based Codex decisions with conventional vision: correct visual selections,
but 6/16 versus 15/16 physical rejections because of timing failures.
The [Phase 6 development results](experiments/conveyor-color-sorting/PHASE6_RESULTS.md)
cover changed layouts, lighting, camera orientation, counting, and instruction
changes, with runtime-health failures reported separately.

## SO101 red cube pickup

The scene uses the SO101 model from Google DeepMind's MuJoCo Menagerie and a
3 cm, 20 g red cube on a flat table. The arm is fixed to the table. The original
installation-check scene remains available separately.

Watch the saved Codex run (replays recorded physics states, then pauses):

```sh
.venv/bin/mjpython -m so101_sim view --replay
```

Run the repeatable scripted pickup baseline with live physics:

```sh
.venv/bin/mjpython -m so101_sim demo --viewer
```

The arm opens its gripper, approaches, descends, closes, lifts the cube about
6 cm, and holds it for three simulated seconds. After completion, the viewer
pauses on the final state. Close the window to exit. The scripted baseline is
a controller check; it does not call an LLM.

### Commands Codex can execute

Each command loads and saves `runtime/episode.npz`, so the same physics state
persists across terminal calls. Physics advances only during actions. All
coordinates are in metres in the world frame; Z is up.

```sh
.venv/bin/python -m so101_sim reset
.venv/bin/python -m so101_sim observe
.venv/bin/python -m so101_sim gripper open
.venv/bin/python -m so101_sim move 0.22 0 0.075
.venv/bin/python -m so101_sim move 0.22 0 0.020
.venv/bin/python -m so101_sim gripper close
.venv/bin/python -m so101_sim move 0.22 0 0.080 --seconds 3
.venv/bin/python -m so101_sim hold --seconds 3
.venv/bin/mjpython -m so101_sim snapshot
.venv/bin/mjpython -m so101_sim view --replay
```

Run commands sequentially; a saved episode has one writer. `reset` and `demo`
replace the current episode. Use `--state /path/to/episode.npz` before a command
to select another episode. `snapshot` saves `runtime/so101.png` by default.
`runtime/episode.json` contains the action and observation log.

`move` uses numerical inverse kinematics with a downward gripper orientation,
then interpolates position actuator targets. It rejects poses that the solver
cannot reach within joint limits. It does not perform collision-aware path
planning. This initial task uses known cube coordinates and a clear approach;
it is not a general visual grasping policy or a physical robot controller.

The free cube moves through gravity and contact forces. There is no grasp weld
or direct cube-position update during actions. Success requires both jaws in
contact and the cube's lowest point more than 4 cm above the table, maintained
through the hold at approximately 30 Hz observation intervals. The demo also
requires less than 5 mm of drift during that hold.

The upstream robot assets are unmodified. The task uses a 2 ms physics step,
50 solver iterations, and limits gripper torque to 0.35 Nm. The other actuator
limits, masses, and gripper friction come from the upstream model. These are
simulation settings, not calibration against a physical SO101.

Model source and license: [models/so101/SOURCE.md](models/so101/SOURCE.md).

### Record a video

Export the saved episode at its original simulation speed:

```sh
.venv/bin/mjpython -m so101_sim record
```

This writes `runtime/so101_pickup.mp4` (960 x 720, 30 fps, H.264). It renders the
recorded physics trajectory without advancing or changing the saved simulation.
Use `--output /path/to/video.mp4` to choose a destination. FFmpeg must be on PATH;
it is already installed on this Mac.

### Physics checks

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Checks cover grasping, saving and resuming state, sustained lift, release under
gravity, and rejecting an unreachable pose without advancing the simulation.

## Installed environment

- Python 3.13.5, native Apple Silicon, in `.venv`
- MuJoCo 3.12.0 and NumPy 2.5.3
- MuJoCo's built-in interactive viewer

Run commands from this project directory.

## Open the example scene

```sh
.venv/bin/python -m mujoco.viewer --mjcf=scenes/basic.xml
```

The scene contains a red cube above a floor. Press Space to toggle simulation
if paused, and close the window to exit.

## Verify the installation

```sh
.venv/bin/python scripts/check_install.py
.venv/bin/mjpython scripts/check_install.py --render --viewer
```

The first command verifies the cube settles on the floor after two simulated
seconds. The second also checks RGB rendering and opens a viewer for five seconds.
On macOS, passive viewer scripts must use `mjpython` instead of `python`.

## Recreate the environment

With native Python 3.13 installed:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

`requirements.txt` lists direct dependencies; `requirements-lock.txt` records all
installed dependency versions for this Mac setup.

See the [official MuJoCo Python documentation](https://mujoco.readthedocs.io/en/stable/python.html).
