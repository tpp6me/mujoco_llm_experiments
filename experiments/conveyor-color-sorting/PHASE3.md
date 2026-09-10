# Phase 3 — Codex with structured state and paused time

Codex reads the instruction and scene, chooses a cube, then issues individual
motion commands. The simulator does not select a color or run the Phase 2
interception routine on Codex's behalf. Physics advances during commanded motions
and waits, and pauses between commands. No separate API key or local LLM is needed
when the current Codex session operates the terminal tools.

The [development protocol](phase3/PROTOCOL.md), [fixed cases](phase3/cases.json),
and [results](PHASE3_RESULTS.md) describe the completed evaluation.

## Start a new episode

From the repository root, choose a fresh directory:

```sh
.venv/bin/python -m conveyor_sim interact reset --episode runtime/conveyor/my_phase3_trial --seed 7 --target red --instruction 'Reject red cubes; let the others pass.'
.venv/bin/python -m conveyor_sim interact observe --episode runtime/conveyor/my_phase3_trial
```

`--target` configures the independent grader and must agree with the instruction.
The action controller never uses it to select cubes. The scene always contains
three cubes, one of each color, on a 1 cm/s belt at nominal 12 cm spacing. Reset
includes 0.5 simulation seconds of settling and refuses to overwrite an existing
episode. Observations include all cube IDs, colors, positions, velocities,
contacts, physical destinations, and robot state.

The state persists across processes. A directory must have only one writer;
execute its commands sequentially. Use different directories for separate trials.

## Primitive commands

Pass a JSON command to `interact act --episode DIRECTORY --actions 'JSON'`:

| Command | Behavior |
|---|---|
| `{"tool":"observe"}` | Read the scene without advancing time |
| `{"tool":"move_to","cube_id":"cube_001","xyz":[0.18,0.005,0.065],"seconds":2,"joint":true}` | Select this ID and approach the near side of the belt |
| `{"tool":"wait","seconds":2}` | Advance physics for the explicitly requested duration |
| `{"tool":"move_to","xyz":[0.18,0,0.020],"seconds":1}` | Move to an explicitly specified descent pose |
| `{"tool":"sweep","xyz":[0.30,0.020,0.020],"seconds":2}` | Sweep from the near belt edge to the supplied endpoint |
| `{"tool":"retract"}` | Follow the validated diagonal retraction and clear the selection |
| `{"tool":"finish"}` | Finalize every cube's outcome at the current simulation time |

These are examples of command syntax, not a complete policy to run blindly.
`cube_001` is an example ID; its color changes with the seed. Codex must read
the observation and choose the ID, waiting time, and coordinates for the actual
scene. `finish` does not wait for collection; finishing early can produce failures.

The motion reference is documented in the protocol. The selected cube should
reach Y = −0.015 m before descent. Account for movement during approach, descent,
and sweep. The color-independent IK controller handles joint targets, actuator
limits, and motion interpolation. It does not plan a general collision-free path.

An explicit list of up to ten commands is also accepted. Execution stops at the
first error and saves it. Every command logs before/after observations, UTC receipt
time, simulation time, arguments, and errors. A wrong-color selection is executable
and causes a scoring failure; it is not silently corrected or rejected by a color
guard. Unknown tools and out-of-bounds motions produce recorded errors.

## Inspect, replay, and record

```sh
.venv/bin/python -m conveyor_sim interact report --episode runtime/conveyor/my_phase3_trial
.venv/bin/mjpython -m conveyor_sim view --episode runtime/conveyor/my_phase3_trial
.venv/bin/mjpython -m conveyor_sim record --episode runtime/conveyor/my_phase3_trial --output runtime/conveyor/my_phase3_trial/sorting.mp4
```

Each episode directory contains `report.json` with the complete event log and
`episode.npz` with MuJoCo integration state, scorer state, and recorded frames.
The video includes the instruction, controller identity, score, and paused-time
label. Replay shows simulation time and omits wall-clock reasoning pauses.

The completed Codex episodes are in `runtime/conveyor/phase3/codex_session/`;
matched conventional episodes are in `runtime/conveyor/phase3/conventional/`.
Runtime files and videos are Git-ignored. The aggregate report preserves all
18 episodes' instructions, observations, actions, and outcomes in the experiment
folder. Re-executing those saved actions would be a deterministic action replay,
not a fresh LLM evaluation.

## Conventional comparator and checks

```sh
.venv/bin/python -m conveyor_sim interact baseline --episode runtime/conveyor/my_baseline --seed 7 --target red --instruction 'Reject red cubes; let the others pass.'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m conveyor_sim.phase3_evaluation
```

`baseline` explicitly runs a conventional selector using the grader color and the
same motion primitives. It is labeled separately and is never called by an
interactive action. For a fair comparison, give it the same seed and target.

The evaluation command reads all fixed cases under the two runtime directories,
checks initial-layout identity and source hashes, and writes
`results/phase3_comparison.json`. Missing or unfinished episodes are errors; scored
failures remain in the aggregate. Run new LLM decisions through Codex for each
fresh trial rather than invoking the comparator and labeling it as LLM behavior.
