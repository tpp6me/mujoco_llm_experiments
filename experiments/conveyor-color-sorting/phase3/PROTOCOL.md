# Phase 3 development protocol

Frozen before the nine scored Codex episodes on 2026-09-09.

## Conditions

Use seeds 9000, 9001, and 9002, each crossed with red, blue, and green as the
declared rejection color. Each episode contains three cubes, one of each color,
with shuffled color order, ±6 mm lateral jitter, ±4 mm longitudinal jitter,
and ±0.15 rad yaw. The belt runs at 1 cm/s, with nominal 12 cm cube spacing.
No episode retries or exclusions are permitted in the aggregate.

For seed 9000, use “Reject COLOR cubes; let the others pass.” For seed 9001,
use “Push only COLOR blocks into the side tray. Leave other colors on the belt.”
For seed 9002, name the two colors to keep: “Keep OTHER1 and OTHER2 on the conveyor;
remove COLOR into the side tray.” Every instruction has exactly one target color.

The existing Codex conversation is the LLM controller. Its prior context includes
the Phase 2 mechanics and this protocol; this is not an independent or blinded
evaluation. No separate model API, local model, or autonomous nested agent is used.
The runtime's exact model version, isolated inference latency, token usage, and
cost are unavailable and must remain unreported rather than estimated.

## Agent observations and capabilities

Observations supply the literal instruction, simulation time, belt velocity,
robot joint position/velocity, tool position, and each cube's neutral ID, color,
position, velocity, contacts, and physical destination. They omit the grader's
target-color field and list of correct target IDs. The experiment setup is still
visible to the developing Codex session; this is not a secrecy guarantee.

The agent explicitly chooses a cube ID, coordinates, action order, and waiting
durations. `move_to` interpolates joint or Cartesian actuator targets; `sweep`
performs a bounded Cartesian motion; `retract` executes the validated clear pose;
`wait` advances physics; `observe` reads state; `finish` scores the current state.
No interactive primitive parses the instruction or chooses a target by color.
Selecting a wrong-color cube is allowed and must be scored as an error.

Phase 2 motion reference: high approach at (0.18, 0.005, 0.065) m, 2 seconds,
joint interpolation. Wait for the chosen cube's center to reach Y = −0.015 m.
Descend for 1 second to X = 0.18, Z = 0.020, with Y led by belt speed × 1 second
plus 0.005 m. Sweep for 2 seconds to X = 0.30, leading Y by another belt speed ×
2 seconds. Retract to (0.22, 0.005, 0.075) m over 1.5 seconds. The agent receives
this reference but must issue the primitive commands itself. This evaluates
instruction-following and tool use with supplied motion knowledge, not discovery
of a new control policy.

Simulation advances only during explicit actions and initial 0.5-second settling.
Persist the complete MuJoCo integration state, scorer state, contacts, frames,
and before/after action observations. Save UTC receipt times and simulation times.
Wall-clock gaps include filesystem, orchestration, and reasoning overhead;
do not call them isolated model inference latency. Video replays simulation time
and omits thinking pauses.

## Comparator and gate

Run a labeled conventional color selector on all nine identical configurations.
It uses the same interactive motion primitives and scoring rules. Preserve its
observations/actions as well. Report per-color and total target rejection,
wrong rejection, complete episode success, contact failures, tool errors, and
simulation-time throughput. All cubes, including unfinished or lost cubes, remain
in the denominator. Preserve full failure reports.

The Phase 3 development gate requires all nine Codex episodes to finish with
correct selections, physical target rejection, non-target collection, no unintended
cube/fixture contacts, and endpoint errors ≤5 mm. The matched conventional episodes
must pass too. Report results even if the gate fails; do not change settings and
silently replace failing trials.

This small gate demonstrates behavior across three colors and three wordings.
It does not measure a population success rate or establish an advantage over
the conventional sorter. Formal evaluation, confidence intervals, vision, and
continuous simulation during reasoning remain later work in the main plan.
