# Phase 4 results — the belt moves while Codex thinks

Date: 2026-09-09. **The slowest-speed development gate passed.** Codex sorted
all three mixed-color cases at 0.5 cm/s with physics advancing continuously.
Faster trials exposed command-latency failures, and the dense stream exposed
the robot's cycle-time limit.

The [complete report](results/phase4_comparison.json) preserves all twelve Codex
episodes and twelve matched conventional episodes, including every failure.
No evaluated case was retried or excluded. Initial cube layouts matched exactly
between controllers. All 72 cubes across both controllers received final outcomes.

## Observed results

| Condition | Codex episodes passed | Codex targets rejected | Conventional episodes passed | Conventional targets rejected |
|---|---:|---:|---:|---:|
| Mixed colors, 0.5 cm/s, 12 cm spacing | 3/3 | 3/3 | 3/3 | 3/3 |
| Mixed colors, 1 cm/s, 12 cm spacing | 2/3 | 2/3 | 3/3 | 3/3 |
| Mixed colors, 2 cm/s, 12 cm spacing | 0/3 | 0/3 | 3/3 | 3/3 |
| Mixed colors, 3 cm/s, 12 cm spacing | 0/1 | 0/1 | 1/1 | 1/1 |
| Three red targets, 1 cm/s, 8 cm spacing | 0/1 | 2/3 | 1/1 | 3/3 |
| Three red targets, 1 cm/s, 6 cm spacing | 0/1 | 1/3 | 0/1 | 2/3 |
| **Total** | **5/12** | **8/16** | **11/12** | **15/16** |

Both controllers selected the correct IDs in every case. Both passed all 20
non-target cubes, made zero wrong-color rejections, and had no unintended cube
or fixture contacts. Codex's unsuccessful episodes were timing failures rather
than incorrect color choices.

## Timing evidence

| Measurement | Codex session | Conventional selector |
|---|---:|---:|
| Observation-to-submission gap, minimum | 12.105 s | 0.010 s |
| Median gap | 15.772 s | 0.016 s |
| Empirical 95th percentile gap | 16.370 s | 0.046 s |
| Maximum gap | 16.519 s | 0.053 s |
| Largest simulation lag behind wall clock | 0.031 s | 0.047 s |
| Largest tool endpoint error | 0.282 mm | 0.331 mm |

The response gaps include Codex reasoning, tool execution, serialization, and
orchestration. Some decisions were batched across independently running cases.
These are measured end-to-end gaps, not isolated model inference latency. There
were 16 submitted motion sequences per controller; those are not model-call counts.
Exact model version, token usage, and cost are unavailable in this session.

Every runtime met the predefined maximum-lag criterion of 0.25 seconds, including
while IK compiled in a separate worker. MuJoCo continued stepping during model/tool
latency, queue waiting, and arm motion. Observation age in simulation time tracked
the corresponding wall-clock gap. The belt was not slowed or paused to make a
command succeed.

## Where the failures came from

At 0.5 cm/s, the leading red target's approach was scheduled for simulation time
22.607 s. Codex submitted it at 12.972 s, leaving about 9.64 seconds of margin;
the physical rejection succeeded.

For the corresponding 1 cm/s case, the planned approach started at 10.313 s,
but the command arrived at 12.834 s. The runtime expired it, and the red cube
continued into collection as `target_missed`. The blue and green targets started
farther upstream, leaving longer windows; those two cases passed.

At 2 cm/s, all three submissions were late. The blue case narrowly missed its
0.05-second allowance: requested start 16.338 s, latest start 16.388 s, receipt
16.434 s. The 3 cm/s red command was also late. These results concern the fixed
interception entry and no-retry policy used here; they do not prove that later
interceptions elsewhere in the workspace are physically impossible.

Codex had seven expired sequences and one rejected reservation. In the 8 cm
stream, the leading target's request expired; the other two were rejected
physically into the tray. In the 6 cm stream, the leading request expired, the
middle target was physically rejected, and the final request conflicted with
the reserved robot cycle. The conventional selector also encountered a cycle
conflict at 6 cm spacing, missing one target despite fast command submission.

## Interpretation and limits

**0.5 cm/s at 12 cm spacing is the tested condition where all mixed-color Codex
cases passed in this session.** Success fell to 2/3 cases at 1 cm/s and 0/3 at
2 cm/s. The conventional controller's faster responses supported every tested
mixed-color speed, including the single 3 cm/s probe. Its dense-stream failure
shows that removing LLM latency alone does not remove the arm's cycle limit.

There are only three mixed-color layouts. For these seeds, the shuffled order
happened to place red in front, green in the middle, and blue at the back in all
three layouts. Target color is therefore confounded with available lead time;
these results must not be read as differences in color-recognition ability.
The matched controller comparison controls layout, but a formal benchmark should
counterbalance target position and use many more seeds.

This extends Phase 3's successful paused-time decisions into a working continuous
runtime and demonstrates a practical latency constraint. It does not establish
a universal speed limit, a population success rate, or physical-robot performance.
The LLM had exact state and a known motion recipe, with prior development context.
The case settings were fixed before live evaluation, and all failures remain in
the aggregate.

## Checks and demonstrations

All 28 automated tests passed, including checks that time and cube positions
advance with no commands, expired and overlapping requests are rejected, queued
motion physically rejects the chosen cube, and failed preflight leaves live
state unchanged. Existing pickup, transport, scoring, and paused-time tests remain
covered. The aggregate checks matching initial layouts, complete accounting,
and controller source hashes.

- [Continuous-time success video](../../runtime/conveyor/phase4/codex_continuous_success.mp4):
  red sorting at 0.5 cm/s, including the interval spent waiting for Codex.
- [Expired-command failure video](../../runtime/conveyor/phase4/codex_expired_command.mp4):
  red at 2 cm/s continues to collection after its command arrives late.

Both recordings show simulation timestamps, instructions, outcomes, and command
status. The success video is 171.93 seconds and the failure video 47.53 seconds;
both are 960 × 720, 30 fps, H.264. Full FFmpeg decoding passed for both, and frames
showing the completed rejection and the expired command were visually inspected.
See the [runtime guide](PHASE4.md) for reproduction and the
[progress checklist](PLAN.md) for later phases. The subsequent camera comparison
is documented in [Phase 5 results](PHASE5_RESULTS.md).
