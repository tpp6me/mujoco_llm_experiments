# Phase 4 — continuous-time Codex control

MuJoCo runs in a separate local process at approximately one simulation second
per wall-clock second. The belt keeps moving while Codex reads observations,
thinks, invokes tools, and submits commands. A file queue connects the runtime
to Codex; no API key, network service, or local LLM is required.

See the [results](PHASE4_RESULTS.md), [frozen protocol](phase4/PROTOCOL.md), and
[case manifest](phase4/cases.json) for the completed development evaluation.

## Start and observe

Run this in a terminal and leave it running, or have Codex launch it as a
background command with a persistent process session:

```sh
.venv/bin/python -m conveyor_sim.live serve --episode runtime/conveyor/my_live_trial --seed 7 --target red --instruction 'Reject red cubes; let the others pass.' --speed 0.005
```

From another terminal or Codex tool call:

```sh
.venv/bin/python -m conveyor_sim.live observe --episode runtime/conveyor/my_live_trial
.venv/bin/python -m conveyor_sim.live status --episode runtime/conveyor/my_live_trial
```

Use a fresh directory for each run. The runtime exits automatically at the
collection deadline, even if no commands arrive. `--target` configures the
independent scorer and must match the natural-language instruction. `--speed`
accepts 0.005–0.03 m/s; `--spacing` accepts 0.06–0.12 m. `--scenario mixed` uses
one cube of each color; `stream` uses three cubes of the designated color.

Observations include an opaque `observation_id`, UTC timestamp, simulation time,
wall-clock elapsed time, belt velocity, cube IDs/colors/positions/velocities, and
robot state. An observation request does not pause physics. Use its actual cube
IDs and timestamps rather than values from an earlier episode.

## Schedule a motion

Submit an explicit sequence as a JSON object:

```sh
.venv/bin/python -m conveyor_sim.live submit --episode runtime/conveyor/my_live_trial --command '{"cube_id":"cube_002","observation_id":"REPLACE_WITH_CURRENT_ID","start_at_s":22.0,"expires_at_s":22.05,"primitives":[{"tool":"move_to","xyz":[0.18,0.005,0.065],"seconds":2,"joint":true},{"tool":"move_to","xyz":[0.18,-0.005,0.020],"seconds":1},{"tool":"sweep","xyz":[0.30,0.005,0.020],"seconds":2},{"tool":"retract"}]}'
```

This shows the syntax. Codex must replace the example ID, times, and coordinates
using the observation and instruction. The runtime does not select a color or
calculate interception times for Codex.

With observed simulation time `t`, target position `y`, and belt speed `v`, the
supplied reference recipe uses approach start `t + (-0.015 - y) / v - 2`. The
two-second approach ends as the cube reaches the chosen interception entry.
Descend for one second to Y = `-0.015 + v + 0.005`, then sweep for two seconds
with another `2*v` of Y travel. The request explicitly includes all four primitives.

`expires_at_s` must lie between `start_at_s` and `start_at_s + 0.1`. The evaluated
cases used a 0.05-second allowance. If a request or its preflight arrives too late,
it expires. Overlapping robot reservations are rejected. Neither case silently
pauses the belt or shifts the requested trajectory.

An initial receipt with `status: planning` acknowledges the request, not successful
execution. `status` shows later states: queued, running, completed, expired, or
rejected. A completed motion is still checked by the independent physical scorer.

## Runtime and evidence

The physics owner steps MuJoCo every 2 ms against a monotonic clock. IK preflight
uses private data in a worker thread while physics continues. The owner applies
compiled actuator targets, monitors contacts, and samples frames. It records
maximum simulation lag; the development gate allows at most 0.25 seconds.

The runtime owns its episode directory. Clients write uniquely named requests
atomically and read matching responses. Do not modify queue or status files by
hand. A client response timeout leaves the original request queued, so inspect
status before retrying and creating a duplicate motion.

Each completed episode retains:

- `report.json`: settings, physical outcomes, selections, command errors, source
  hashes, observation/receipt times, planned/actual motion times, and clock lag.
- `episode.npz`: sampled physics trajectory and scores for replay.
- `requests/` and `responses/`: exact local request and response payloads.
- `status.json`: the last periodic runtime status; `report.json` is authoritative
  after completion.

## Replay, video, and matched comparison

```sh
.venv/bin/mjpython -m conveyor_sim view --episode runtime/conveyor/my_live_trial
.venv/bin/mjpython -m conveyor_sim record --episode runtime/conveyor/my_live_trial --output runtime/conveyor/my_live_trial/live.mp4
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m conveyor_sim.phase4_evaluation
```

Phase 4 videos preserve simulation time, including the interval spent waiting for
Codex's command. Their overlays show the instruction, score, queued/executing/
expired status, and measured response gap. They are replays of a wall-paced run,
not screen captures of the Codex interface.

The case launcher starts fixed configurations:

```sh
.venv/bin/python -m conveyor_sim.live_experiment --actor codex_session --cases mixed_0.005_red --root runtime/conveyor/new_live_evaluation
.venv/bin/python -m conveyor_sim.live_experiment --actor conventional --cases mixed_0.005_red --root runtime/conveyor/new_live_evaluation
```

The Codex branch only launches the runtime and returns an observation. Codex must
then submit its decisions. The explicitly labeled conventional branch selects
matching colors and submits the same kind of motion sequence automatically.
Use the same case for each actor. Evaluation expects all twelve fixed cases under
both actor directories and rejects missing or changed configurations.

Runtime videos and trajectories are Git-ignored. The aggregate report in the
experiment folder retains all 24 evaluated episodes and their complete decision
logs. New executions can reproduce the settings, but wall-clock latency and
scheduling jitter depend on the current session and machine load.
