# Phase 3 results — Codex chooses and executes sorting actions

Date: 2026-09-09. **Phase 3 development gate passed.** Codex read structured
observations and selected the correct cube across all three colors and three
instruction wordings. It then issued explicit approach, wait, descent, sweep,
retraction, collection-wait, and finish commands. No interactive tool selected
cubes by color or automatically ran the complete rejection sequence.

## Comparison

The [complete report](results/phase3_comparison.json) contains all nine Codex
episodes and nine matched conventional episodes, with full observations and
action logs. Initial cube states matched exactly for every pair.

| Metric | Codex session | Conventional selector |
|---|---:|---:|
| Successful episodes | 9/9 | 9/9 |
| Correct cube selections | 9/9 | 9/9 |
| Targets rejected | 9/9 | 9/9 |
| Non-targets collected | 18/18 | 18/18 |
| Wrong rejections | 0/18 | 0/18 |
| Episodes with unintended contacts | 0 | 0 |
| Primitive calls, including finish | 63 | 63 |
| Tool errors | 0 | 0 |
| Largest tool endpoint error | 0.282 mm | 0.282 mm |
| Correct cubes per simulation minute | 2.226 | 2.226 |

Each color passed three episodes: 3/3 red, 3/3 blue, and 3/3 green target
rejections, with 6/6 non-targets collected per color condition. No failed episodes
were retried or removed. Every cube received a final physical outcome.

The throughput figure includes initial travel and final collection for these
short batches. It excludes thinking pauses and is not continuous-operation or
wall-clock throughput. Each controller accumulated 727.92 simulation seconds
over nine episodes.

## What Codex contributed

The current Codex session interpreted the literal instructions, mapped colors
to observed cube IDs, and supplied action order, coordinates, and wait durations.
It used the known Phase 2 motion recipe and received new observations after each
primitive. For example, “Keep red and green on the conveyor; remove blue into the
side tray” led to selecting the observed blue cube, waiting for its interception
position, and pushing it while the other two continued to collection.

The motion controller solved inverse kinematics and interpolated actuator targets.
MuJoCo moved the cubes through physical contacts. The independent scorer checked
tray containment, support, settling, and all cube outcomes. Actions used neutral
cube IDs and did not consult the grader's target color. Explicit numerical waits
and coordinates were chosen in the Codex conversation; no conventional selection
function ran within those nine episodes.

The conventional comparator read its configured color and executed the same
primitives. Its equally successful result means this experiment establishes
successful LLM instruction-following and tool use, without establishing an
advantage over a simple conventional sorter.

## Scope and checks

The [frozen protocol](phase3/PROTOCOL.md) uses seeds 9000–9002 crossed with all
three colors, at 1 cm/s and 12 cm nominal spacing. Each scene contains one cube
of each color. Wording varies between direct rejection, “push only,” and naming
the colors to keep. Color order and initial position/yaw are randomized by seed.

This is an interactive development demonstration with accurate state, a supplied
motion reference, and prior context about the experiment. The same Codex session
built and operated it; it is not a blinded benchmark or a measurement of physical
robot reliability. Nine episodes over three layouts are insufficient for a broad
reliability claim. The larger formal benchmark remains future work.

All 24 automated tests passed. New checks verify that observation preserves
simulation time, resumed integration matches uninterrupted physics, scoring and
contact state survive persistence, invalid actions are recorded, finishing early
accounts for every cube, and an intentionally wrong-color push is scored as a
wrong rejection and a missed target. That negative control is a labeled test,
not an excluded evaluated episode. Source hashes matched the completed trials.

UTC receipt timestamps and simulation timestamps are retained. Model-call count,
exact runtime model identifier, token usage, cost, and isolated model inference
latency are unavailable in this interactive session. Primitive-call counts must
not be described as model-call counts. No API usage or latency was invented.

## Demonstration

The [Codex sorting video](../../runtime/conveyor/phase3/codex_blue_sorting.mp4)
replays the `9002_blue` episode. The instruction tells Codex to keep red and green
on the conveyor and remove blue into the side tray. Blue settles in the reject
tray; red and green settle in the collection tray. The video retains simulation
time and explicitly labels the pauses between actions.
The MP4 is 81.1 seconds, 960 × 720, 30 fps, H.264. Full FFmpeg decoding passed;
frames after rejection and at final collection were visually inspected.

See the [tool guide](PHASE3.md) to run new episodes and the
[progress checklist](PLAN.md) for subsequent work. Continuous conveyor motion
during LLM reasoning is evaluated separately in [Phase 4](PHASE4_RESULTS.md).
