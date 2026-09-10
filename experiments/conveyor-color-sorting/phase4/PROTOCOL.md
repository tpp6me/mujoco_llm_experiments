# Phase 4 continuous-time development protocol

Frozen before scored live trials. MuJoCo advances against a monotonic wall clock
at one simulation second per wall-clock second, with a 2 ms physics timestep.
Only initialization and 0.5-second settling precede the timed run. Every run ends
at its predefined physical outcome deadline. No pauses or speed changes are allowed.

## Cases and gate

The fixed case manifest contains twelve cases per controller:

- Mixed colors at 0.5, 1, and 2 cm/s: one red, blue, and green instruction at each
  speed, seeds 10000, 10001, and 10002 respectively; 12 cm nominal spacing.
- One mixed-color red-instruction probe at 3 cm/s, seed 10000, 12 cm spacing.
- Three consecutive red targets at 1 cm/s, seed 11000, at 8 cm and 6 cm spacing.

The leading cube starts near Y = −0.14 m; the other two start upstream by the
declared spacing, with ±4 mm longitudinal jitter, ±6 mm lateral jitter, and
±0.15 rad yaw. Colors are shuffled independently of the instruction in mixed cases.

Run both Codex and a conventional selector on identical initial layouts. The
development gate requires successful sorting in all three slowest-speed Codex
cases and their comparators, with no unintended contacts, tool endpoint errors
≤5 mm, and maximum wall/simulation lag ≤0.25 seconds. Faster and denser cases
characterize limits and remain in the results even if they fail. No retries or
exclusions. Higher-speed evidence is exploratory and must not be generalized
beyond these few layouts or this Mac's measured runtime conditions.

## Agent responsibility and scheduling

Codex receives a timestamped structured observation, including a unique observation
ID. It chooses each cube ID, absolute simulation start time, expiry, and the explicit
approach/descent/sweep/retract sequence. A single submission may queue that entire
sequence, like Phase 3's explicit command lists. It does not call a color-specific
sort function. The supplied motion recipe is unchanged in intent from Phase 2.

For belt speed v and observation (time t, cube Y position y), the reference
approach start is t + (−0.015 − y)/v − 2 seconds. Descent starts two seconds later,
at X = 0.18, Z = 0.020, Y = −0.015 + v + 0.005. The two-second sweep ends at
X = 0.30 and Y increased by 2v. Retraction returns to the validated clear pose.
The agent must supply these numerical choices; the runtime does not identify the
correct color or automatically predict an interception time.

Commands expire at their latest permissible start, at most 0.1 seconds after
their requested start. Late arrival, late preflight, and robot-cycle conflicts
are recorded. Physics continues during preflight in a separate worker. Queued
motion is compiled before its start and executed by the physics owner, which
monitors every contact step. No arbitrary model code runs in the physics loop.

The conventional selector uses the same queue, compiler, actuator interpolation,
and scorer, with negligible instruction interpretation time. It attempts each
matching target; overlapping reservations may fail under overload. The Codex
branch of the launcher only starts the runtime and returns an observation. It
never chooses IDs or submits motion commands.

## Evidence and limitations

Retain every cube's outcome, accepted and rejected commands, observation timestamps,
receipt timestamps, requested/actual start/end times, queue waits, physical contacts,
endpoint errors, dependency versions, source hashes, and replay frames. Report
observation-to-submission wall gaps, simulation age, runtime lag, and interception
margin. Wall gaps include Codex reasoning and tool/orchestration overhead; they
are not isolated model inference latency. Model token counts and costs are unavailable.

Source and settings are frozen before the live trials. Codex operates from this
existing development conversation with exact state and a known motion recipe.
These are development demonstrations, not a blinded model benchmark or physical
robot validation. Speed/spacing comparisons include scheduling and physical
limitations; missed targets must be attributed to recorded evidence rather than
assumed to be a reasoning failure.
