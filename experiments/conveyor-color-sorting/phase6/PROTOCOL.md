# Phase 6 development evaluation protocol

Freeze this protocol, case manifest, and implementation before evaluated runs.
Retain all 24 cases for each of Codex and conventional vision, including failures;
no retries or excluded episodes. Each episode contains three cubes. New seeds
21000–21008 and 23000–23004 were not used for previous scored trials. Debugging
uses seed 42 and separate directories. This is a development evaluation, not the
proposed formal 30 episodes × 20 cubes per condition benchmark.

## Conditions

Nine reference cases cross each declared target color with all three queue
positions using cyclic color permutations. Three matched pose variants increase
lateral spread from ±6 to ±15 mm and yaw from ±0.15 to ±0.75 radians. Three
matched lighting variants scale illumination to 35%; three camera variants
rotate the overhead view by 15 degrees about the vertical axis. Calibration
is provided for that rotation. It is not an oblique-camera test.

One matched 2 cm/s case probes speed, and one all-red 1 cm/s case probes 6 cm
spacing. One case requests red and blue rejection; another requests only the
next two of three green cubes in arrival order. Two cases change target color
at simulation time 20 seconds. All other cases use 0.5 cm/s and 12 cm spacing.
Change one variable at a time within each matched robustness comparison.

## Instructions and transitions

Each public image carries the current instruction and rule version. At 20 seconds,
the switch cases replace the instruction and increment its version. Pending
old-version motions are cancelled; old-version submissions are rejected. A
motion already running would finish under its original rule. These probes place
all cubes upstream so no valid approach begins before the change (earliest
nominal approach is 35 s); running-action transition semantics are not tested.

Both agents receive the initial image and may queue its requested action. After
the change, obtain a new image and submit choices under version 1. The scorer
expects the new color for every cube in these two probes, independent of what
the agent requested. Counting means the first two matching cubes in physical
arrival order, not the first two successful rejections. Missed cubes consume
their place in the requested count. Non-target cubes must pass.

Codex supplies every selected pixel/color estimate explicitly in this session.
An arithmetic helper converts those estimates using public calibration and
schedules the unchanged four-primitive recipe. It performs no object or color
selection. Do not use the conventional detector or read private reports until
all evaluated Codex decisions are finished. Rule-change monitoring may read
only public status and observations. No automatic retry or late replanning.

The conventional comparator uses calibrated RGB segmentation and a declared
finite grammar for single-color, two-color, and next-two instructions. It parses
the same literal instruction and uses the same actions and transition rules.
This deliberately gives the conventional comparator the tested capabilities;
multi-color success alone is not evidence of an LLM advantage.

## Measurement and gate

Keep the continuous wall clock, 0.25-second maximum lag criterion, motion compiler,
actuator limits, camera resolution, image rulers, and physical destination scorer
from Phase 5. Score every cube. Report episode success, target and non-target
outcomes, selected-object color/position accuracy, expired/cancelled/conflicting
commands, response gaps, transition-to-first-new-command delay, and runtime lag.
Report final-rule selection separately from superseded initial choices.

Run matched controllers on identical physical initial states. Copy input images,
preserve requests and audits, and verify source hashes. Report 95% Wilson intervals
for episode success and an episode-paired bootstrap interval for target-rejection
rate difference. The varied-condition aggregate is descriptive of this manifest,
not a population estimate or a claim of independent identically distributed cubes.

The implementation/development gate is complete auditable coverage of every
listed condition, with failures retained and runtime health reported. A runtime
health failure invalidates that trial's timing interpretation and stays visible;
it does not become an LLM failure or trigger a replacement run. Record representative
adaptation/robustness and failure videos. Formal benchmarking remains a separate
unchecked milestone until the larger design is actually run.

Limitations include known scene/controller design, shared conversation context,
workflow-only private-state separation, small per-condition samples, calibrated
camera rotation, fixed language grammar, and response gaps that include tools,
batching, and image delivery. No exact model version, token, call, or cost telemetry
is available. These experiments do not establish physical-robot performance.
