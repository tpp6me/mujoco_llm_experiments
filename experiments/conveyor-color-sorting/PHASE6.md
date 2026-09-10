# Phase 6 — robustness and instruction changes

[Protocol](phase6/PROTOCOL.md) · [Case manifest](phase6/cases.json) · [Progress](PLAN.md)

This phase extends the continuous camera interface with balanced target positions,
wider cube pose variation, dimmed illumination, calibrated camera rotation,
multi-color and counting instructions, and rule changes during motion. The motion
recipe and independent physical destination checks are unchanged.

## Run a case

From the repository root on this Mac:

```sh
.venv/bin/mjpython -m conveyor_sim phase6 launch --actor codex_session --cases layout_01 --root runtime/conveyor/phase6_new
```

Use a fresh root for another run. Evaluated case folders cannot be overwritten.
The command returns a public observation and the input image path. Physics is
already advancing. Launching the Codex branch does not call an LLM automatically;
Codex must inspect the image and explicitly supply its choices through tools.

An observation contains the instruction, rule version, capture timestamp, image,
camera calibration, and belt velocity. It contains no object IDs, colors,
positions, segmentation masks, or bounding boxes. Public status lives in each
episode's `status.json`; do not open `private/` during evaluated decisions.

Obtain another image with:

```sh
.venv/bin/python -m conveyor_sim phase6 observe --episode runtime/conveyor/phase6_new/codex_session/layout_01
```

## Submit visually chosen pixels

Each observation is also saved as `responses/OBSERVATION_ID.json`. Supply that
path and an explicit list of pixel centers and perceived colors:

```text
.venv/bin/python -m conveyor_sim phase6 decide \
  --episode EPISODE_DIRECTORY \
  --observation EPISODE_DIRECTORY/responses/OBSERVATION_ID.json \
  --selections '[{"pixel_xy":[U,V],"perceived_color":"red"}]'
```

Replace the uppercase placeholders using the actual image and saved response.
Multiple selections can be passed in one list, ordered by expected arrival.
`decide` performs arithmetic on those explicit estimates and submits the same
approach, descent, sweep, and retract sequence as Phase 5. It does not detect,
select, or correct a cube. The actual per-cube controls and submission timestamps
are retained in the episode logs.

The camera cases rotate the overhead image by 15 degrees around the vertical
axis. Public calibration gives the rotation; the arithmetic helper applies it
before computing interception time. This is a calibrated in-plane rotation,
not an oblique viewpoint or camera-calibration estimation task.

## Change an instruction while the belt moves

```sh
.venv/bin/mjpython -m conveyor_sim phase6 launch --actor codex_session --cases switch_01 --root runtime/conveyor/phase6_new
```

Read the initial image and submit the initial rule's target. At simulation time
20 seconds, the runtime changes the instruction and increments its version.
Public status exposes the current instruction and version. Obtain a new image
after the change and submit its target with that new observation.

Pending old-rule motions are cancelled, and stale-version commands are rejected.
The switch probes place all cubes upstream, so valid physical approaches begin
after the change. The scorer therefore expects the new color for every cube in
these two episodes. An already-running action would finish under its original
rule, but these probes do not exercise that case. The unchanged robot motion
capability does not imply general online motion replanning.

For `count_01`, “next two” means the first two green cubes in arrival order.
A missed first cube still counts toward the requested two; the third must pass.
For `multi_01`, both red and blue must be rejected and green must pass.

## Conventional comparison

```sh
.venv/bin/mjpython -m conveyor_sim phase6 launch --actor conventional --cases switch_01 --root runtime/conveyor/phase6_new
```

The comparator thresholds RGB pixels inside the calibrated belt area and parses
the same instruction using a fixed, declared grammar. It supports the tested
single-color, two-color, and next-two rules. It monitors rule changes and gets a
fresh image after each change. No LLM or hidden object state selects its actions.
This is a capable baseline for these specific rules, not a general language parser.

## Validate and aggregate

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mjpython -m conveyor_sim phase6 check-camera
.venv/bin/python -m conveyor_sim.phase6_evaluation
```

The graphics check uses development seed 42. The aggregate requires all 48 scored
episodes and verifies their source hashes, public observation schema, complete
cube accounting, and identical initial physical layouts across controllers.
It copies images into `phase6/inputs/` and retains raw reports, command events,
perception audits, and confidence intervals in `results/phase6_comparison.json`.

Private reports are opened only after all evaluated Codex submissions finish.
This workflow convention is not an operating-system security boundary. Saved
trajectories, process logs, and videos remain under the ignored `runtime/` folder.

Record a saved case without re-running physics:

```sh
.venv/bin/mjpython -m conveyor_sim record --episode runtime/conveyor/phase6/codex_session/switch_01/private --output runtime/conveyor/phase6/codex_rule_switch.mp4
```

Replays show the current rule, queue status, score, and the latest captured input
snapshot, clearly labeled as a snapshot rather than a live feed.

## Separate instruction-change check

The original matrix contained runtime-health failures. A separately declared
[supplemental protocol](phase6/confirmatory/PROTOCOL.md) uses new seeds and at most
one Codex/conventional pair at a time. Its launcher refuses to start another pair
while a different case is still running:

```sh
.venv/bin/mjpython -m conveyor_sim phase6-followup launch --actor codex_session --case confirm_switch_01
.venv/bin/mjpython -m conveyor_sim phase6-followup launch --actor conventional --case confirm_switch_01
```

Use the same `phase6 observe` and `phase6 decide` commands with episode paths under
`runtime/conveyor/phase6_confirmatory/`. Wait for both public status files to say
`completed: true` before launching `confirm_switch_02`. Both original and
supplemental evaluated folders reject overwriting. Keep recordings and tests
deferred until every live episode finishes.

Aggregate the separate cohort after all four episodes finish:

```sh
.venv/bin/python -m conveyor_sim.phase6_evaluation --root runtime/conveyor/phase6_confirmatory --cases experiments/conveyor-color-sorting/phase6/confirmatory/cases.json --inputs-relative phase6/confirmatory/inputs --output experiments/conveyor-color-sorting/results/phase6_confirmatory.json
```

These supplemental cases do not replace any original failure and should not be
pooled into a single headline rate without identifying the changed run conditions.

## What remains beyond the development matrix

The original plan proposed a larger formal benchmark: 30 episodes of 20 cubes
per main condition. That requires longer streams, a controller that can receive
repeated model decisions automatically with reliable telemetry, held-out seeds,
balanced positions, frozen model settings, and a separate evaluation session.
It has not been completed by these 24 short cases per controller. Model version,
token usage, model-call count, and cost are unavailable in the current session.
Do not present the development matrix as the larger benchmark or extrapolate
its aggregate success rate to arbitrary tasks or physical hardware.
