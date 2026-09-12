# G1 supported-body pick and basket

This milestone implements conventional contact-based manipulation in MuJoCo.
The pelvis is fixed and the arm starts above the block. The [live LLM pilot](LLM_RESULTS.md)
now compares individual exact-state actions through the shared interface.
Use the [complete implementation checklist](PLAN.md) as the living reference
for progress, phase gates, next actions, and the historical scoring protocol.

[Historical V4 results](V4_RESULTS.md): 98/100 task successes, 96/100 strict passes;
the 95/100 mechanical qualification gate is met. The V4 implementation passed 42 tests; the current suite passes 75 tests.

The [versioned policy interface](INTERFACE.md) adds orientation, robot-state
observations and a sampled collision guard. Its [G2 qualification](GUARDED_RESULTS.md) passed with **100/100 placements,
97/100 strict passes and no guard rejections**. See the [results index](RESULTS_INDEX.md)
for all configurations; V4 refers to the archived conventional controller.

## Replay the qualified guarded controller

After running the G2 matrix below, replay its first episode:

```sh
.venv/bin/mjpython -m humanoid_sim --episode runtime/humanoid/guarded-g2-100/seed-0600 view
```

The verified video is `runtime/humanoid/guarded-g2-100/seed-0600/pick_place.mp4`.
Use the corresponding path if you chose a different matrix directory.

## Run the historical V4 baseline

From the repository root, using the existing virtual environment:

```sh
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/v4-demo demo
.venv/bin/mjpython -m humanoid_sim --episode runtime/humanoid/v4-demo view
.venv/bin/mjpython -m humanoid_sim --episode runtime/humanoid/v4-demo record
.venv/bin/mjpython -m humanoid_sim --episode runtime/humanoid/v4-demo snapshot
```

The commands above use `runtime/humanoid/v4-demo`. The CLI default remains
`runtime/humanoid/demo`, which may contain the earlier V3 demonstration. A completed trial is never
overwritten or modified by action commands. Choose a new directory for another run:

```sh
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/seed-42 demo --seed 42 --randomize
.venv/bin/mjpython -m humanoid_sim --episode runtime/humanoid/seed-42 view
```

`view` replays recorded physics states at simulation speed, then pauses. Close the
window to exit. `record` exports an annotated H.264 MP4; FFmpeg is required.
Rendering uses separate MuJoCo data and does not advance the saved physics.
On macOS, graphics commands require `mjpython` and access to the graphics session.

## Persistent primitive commands

```sh
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/manual-01 reset
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/manual-01 observe
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/manual-01 move .255 -.18 .975
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/manual-01 move .255 -.18 .775
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/manual-01 hand 1
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/manual-01 move .255 -.18 .975
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/manual-01 hold --seconds 2
```

Coordinates are world-frame metres, with Z up. `move` targets the right grasp site
with a fixed downward orientation. `hand` is a coordinated three-finger closure
between 0 and 1; it is not an automatic grasp policy. Run commands sequentially;
each episode has one writer. Physics pauses between calls in this milestone.

The observation currently exposes simulator truth for baseline development. It
must not be used unchanged in the future visual-only LLM evaluation.

IK rejects unreachable requests before advancing physics and uses a fixed seed
posture for consistent arm configurations. The controller interpolates joint
targets and retains collision physics. It does **not** perform general
collision-aware path planning; only the tested recipe and narrow workspace are
validated. The initial overhead posture is a reset assumption.

## Validation and artifacts

```sh
.venv/bin/python -m unittest discover -s tests -p test_humanoid.py -v
.venv/bin/python -m humanoid_sim validate --output runtime/humanoid/new-validation --seeds 100 --first-seed 400
```

Validation requires a new output directory and saves each trial immediately,
including failures. Each episode includes:

- `episode.npz`: integration state, frame times, and recorded joint/object poses.
- `events.json`: actions, exact-state observations, and cumulative per-action scores.
- `metadata.json`: scene hash, reset parameters, and resumable scorer state.
- `report.json`: physical outcome, contact quality, initial/final observations,
  controller failure, dependency versions, and source hashes (baseline trials).

Peak object-contact telemetry records time, contacting body/geom, normal force,
and penetration. These scores and diagnostics are private evaluation data for
future visual policies. Older episodes without peak telemetry load with it unknown.

The validation root also includes `summary.json`. A smaller run is diagnostic
and does not pass the 100-trial mechanical gate, even if every episode succeeds.
Saved episodes refuse to replay against a different generated scene.

## Assets and scene

The upstream model is in `models/g1/`; provenance, checksums, license, and all
simulation overrides are in [SOURCE.md](../../models/g1/SOURCE.md).
`scenes/g1_pick_place.xml` is generated by:

```sh
.venv/bin/python -m humanoid_sim.scene
```

Regenerate only when intentionally changing the task. The G1 meshes and source
XML remain untouched. The generated scene includes a head camera for the next
phase; no camera-observation policy has been evaluated in this milestone.

## Guarded shared-interface evaluation

```sh
.venv/bin/python -m humanoid_sim.guarded_evaluation --output runtime/humanoid/guarded-g2-100 --protocol g2 --count 100 --first-seed 600
```

The conventional policy uses only the versioned interface. The evaluator freezes
source/schema/protocol hashes, records each action attempt, and terminates on a
rejection without retry. See [protocol G2](protocols/G2.md) for the reserved seeds
and unchanged physical scoring limits. Use a new directory for each run.

## Live exact-state LLM pilot

The [runner guide](LLM_RUNNER.md) describes credentials, budget, action boundaries
and logs. [L2 results](LLM_RESULTS.md): GPT-5.6 Sol placed 0/3 objects and achieved
one sustained lift; the matched conventional policy placed all three. This small
pilot does not measure vision or establish a general comparison.

```sh
.venv/bin/python -m humanoid_sim.llm_runner --output runtime/humanoid/new-llm-pilot --seeds 700 701 702 --budget-usd 4.5
```

Use a fresh directory and account for prior API spend. These are now development
seeds. Freeze a new protocol before changing prompts, models or conditions.

## RGB observations

The [visual boundary](VISUAL.md) exports calibrated RGB with robot state and
single-use observation IDs. It excludes object truth and scoring data. Fixed-camera
reset captures are validated; the head view needs better coverage. No visual LLM
policy has been evaluated, and the simple pixel-centroid helper is not a qualified
pose estimator. See the [grasp audit](GRASP_AUDIT.md) for the exact-state failures.

The [P1 initial block estimator](POSE_RESULTS.md) uses RGB and declared geometry
priors: all 20 fresh reset images were within 5 mm XY error. Carried-object pose
and full visual control remain pending.

The [perception wrapper](PERCEPTION.md) expires that initial support prior before
interaction and reports pixel visibility separately from unavailable 3D pose.
[P2](PERCEPTION_RESULTS.md) audits its behavior across manipulation endpoints
driven by the exact-state baseline; it is not a visual controller evaluation.
