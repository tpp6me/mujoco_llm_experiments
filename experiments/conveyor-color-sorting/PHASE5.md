# Phase 5 — camera observations with continuous physics

[Results](PHASE5_RESULTS.md) · [Frozen protocol](phase5/PROTOCOL.md) ·
[Progress checklist](PLAN.md)

Codex sees an overhead image, its capture time, the instruction, camera
calibration, and belt velocity. It selects pixels visually and submits an
explicit motion sequence. MuJoCo keeps advancing during rendering, reasoning,
queue waiting, and motion. No local LLM or API key is needed for the interactive
Codex branch; launching a trial does not automatically call a model.

## Start a fresh trial

Run from the repository root on this Mac. Choose a new output root to preserve
the evaluated episodes; existing case directories are rejected.

```sh
.venv/bin/mjpython -m conveyor_sim camera launch --actor codex_session --cases mixed_0.005_green --root runtime/conveyor/phase5_new
```

The launcher returns the first observation and an image path. Inspect that image
immediately: the belt is already moving. The runtime finishes automatically at
the case deadline. The twelve available case IDs are in [cases.json](phase5/cases.json).

During a trial, public commands are:

```sh
.venv/bin/python -m conveyor_sim camera observe --episode runtime/conveyor/phase5_new/codex_session/mixed_0.005_green
.venv/bin/python -m conveyor_sim camera status --episode runtime/conveyor/phase5_new/codex_session/mixed_0.005_green
```

`observe` returns a newly captured image. Evaluated trials used one initial
image each. `status` returns time and command status without object state.
Do not inspect `private/` or run the conventional detector during Codex decisions.

## Submit an explicit action

Use `camera submit --episode PATH --command 'JSON'`. The JSON requires these
fields; fill in values from the actual observation rather than replaying old times:

| Field | Meaning |
|---|---|
| `object_id` | A neutral label chosen by Codex, such as `object_A` |
| `observation_id` | ID of the image used for the decision |
| `pixel_xy` | Estimated cube center `[u, v]` in that image |
| `perceived_color` | `red`, `blue`, or `green`, as seen by Codex |
| `start_at_s` | Absolute simulation time to begin approach |
| `expires_at_s` | Latest permitted start; evaluated trials used start + 0.05 s |
| `primitives` | Explicit `move_to`, `sweep`, and `retract` sequence |

For this calibrated scene, metres per pixel are 0.0007708974633054824:

```text
x = 0.22 + (u - 480) * metres_per_pixel
y = -0.18 - (v - 360) * metres_per_pixel
start_at_s = image_time_s + (-0.015 - y) / belt_speed - 2
```

The evaluated recipe approaches `[0.18, 0.005, 0.065]` in two seconds with
`joint: true`, descends in one second to `[0.18, belt_speed - 0.01, 0.020]`,
sweeps in two seconds to `[0.30, 3 * belt_speed - 0.01, 0.020]`, then retracts.
Each motion uses `tool`, `xyz`, and `seconds`; retraction uses only
`{"tool": "retract"}`. Coordinates are metres and belt speed is m/s.
This is the known motion recipe used for the comparison, not general path planning.

Pixel conversion is geometric. Neither the neutral label nor the claimed color
resolves an actual cube or corrects the trajectory. The private scorer later
matches the estimate with ground truth and checks real contacts and destinations.
Static image rulers provide pixel coordinates without object labels or boxes.

## Conventional image baseline

```sh
.venv/bin/mjpython -m conveyor_sim camera launch --actor conventional --cases mixed_0.005_green --root runtime/conveyor/phase5_new
```

This branch automatically thresholds image colors and finds pixel regions inside
the fixed belt area. It uses the same calibration and motion queue. It does not
call an LLM or obtain object positions from the simulator.

## Evidence and replays

Each episode retains public `images/`, `requests/`, `responses/`, and `status.json`.
The `private/` folder holds configuration, render inputs, the independently
scored report, and `episode.npz`. This separation is a workflow convention, not
an OS access-control boundary. Inspect private evidence after all evaluated
Codex submissions have finished.

```sh
.venv/bin/python -m conveyor_sim.phase5_evaluation
.venv/bin/mjpython -m conveyor_sim record --episode runtime/conveyor/phase5/codex_session/mixed_0.005_green/private --output runtime/conveyor/phase5/codex_camera_success.mp4
.venv/bin/mjpython -m conveyor_sim record --episode runtime/conveyor/phase5/codex_session/mixed_0.02_red/private --output runtime/conveyor/phase5/codex_camera_expired.mp4
```

Aggregation requires all 24 completed reports and verifies source hashes, cube
accounting, matching Phase 4 layouts, and the public observation schema. It copies
the input images into [phase5/inputs](phase5/inputs) and includes their hashes in
the [aggregate report](results/phase5_comparison.json). Runtime trajectories and
videos stay in the ignored local `runtime/` directory. Recordings replay saved
physics; their inset is the original decision snapshot, not a live camera feed.

The automated suite runs with `.venv/bin/python -m unittest discover -s tests -v`.
The separate graphics check is `.venv/bin/mjpython scripts/check_camera.py`;
it uses development seed 42, outside the evaluated matrix.
