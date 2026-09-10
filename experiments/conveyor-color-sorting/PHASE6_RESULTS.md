# Phase 6 development results — robustness and adaptation

Date: 2026-09-09. The original **24-case-per-controller matrix is complete**.
Codex correctly selected every final-rule target and demonstrated multi-color
sorting and counting. Conventional vision achieved better physical completion.
Seven runtime-health failures limit timing conclusions from the original matrix.
The proposed larger formal benchmark is still outstanding.

The [complete original report](results/phase6_comparison.json) retains all 48
episodes and 144 cube outcomes. Cases use new seeds and balanced target positions,
with matched physical initial states across controllers. No episode was retried
or excluded from the original report.

## Original matrix outcomes

| Condition | Codex targets rejected | Conventional targets rejected |
|---|---:|---:|
| Balanced layouts, 0.5 cm/s | 7/9 | 9/9 |
| Wider position/yaw variation | 2/3 | 3/3 |
| Illumination scaled to 35% | 2/3 | 3/3 |
| Calibrated 15° camera rotation | 2/3 | 3/3 |
| 2 cm/s speed probe | 0/1 | 1/1 |
| 6 cm spacing, three red targets | 1/3 | 2/3 |
| Reject red and blue | 2/2 | 2/2 |
| Reject only the next two green cubes | 2/2 | 2/2 |
| Target-color changes at 20 s | 0/2 | 2/2 |
| **Total physical outcomes** | **18/28 (64.3%)** | **27/28 (96.4%)** |

Both controllers passed all 44 non-target cubes without wrong rejections or
unintended contacts. Every cube reached a final destination. Codex physically
completed 15/24 episodes and the conventional controller 23/24. Requiring both
correct sorting and a healthy runtime gives 14/24 versus 19/24; those figures
include infrastructure validity and should not be read as pure robot capability.

Codex had 18 completed commands, ten expired commands, and two old-rule
cancellations. Conventional vision had 27 completed commands, one reservation
conflict at 6 cm spacing, and two old-rule cancellations. All executed Codex
sequences physically rejected their intended targets.

## Visual and instruction understanding

Both controllers correctly identified the perceived colors for all 30 submitted
estimates, including two superseded initial-rule selections. All 28 final-rule
estimates corresponded to actual targets. Codex's median position error was
0.479 mm and its maximum 1.042 mm; conventional vision's median was 0.698 mm and
its maximum 4.582 mm. These are selected-object errors, not exhaustive detection
or tracking scores.

The pose, dim-light, and rotated-camera cases did not introduce observed color
selection errors. Their leading-target Codex commands expired; the farther
upstream targets were rejected. This demonstrates the importance of lead time
even when visual interpretation is accurate. View rotation was only about the
vertical axis with its calibration supplied, not an unknown or oblique camera.

Codex successfully rejected both red and blue while passing green. It also
rejected the first two green cubes and let the third pass. The conventional
parser and controller achieved the same results. Its declared grammar supports
these exact rules, so these successes do not establish a language-model advantage.

In each original rule-change case, the old queued command was cancelled at the
20-second switch. Codex interpreted a fresh image and selected the new requested
color, but the replacement command expired. Both conventional replacements
executed successfully. Every switch occurred before the first eligible approach;
changes during an executing push were not tested.

## Timing, runtime validity, and uncertainty

Original observation-to-submission gaps were 14.269–33.544 seconds for Codex
(median 21.184 s) and 0.230–0.529 seconds for conventional vision (median 0.355 s).
These include image delivery, reasoning, arithmetic, tools, batching, and
orchestration. They are not isolated inference-time measurements.

Seven episodes exceeded the predeclared 0.25-second maximum lag:

| Controller | Case | Maximum lag |
|---|---|---:|
| Codex | `pose_03` | 0.278 s |
| Codex | `switch_01` | 0.718 s |
| Codex | `switch_02` | 0.418 s |
| Conventional | `layout_01` | 0.257 s |
| Conventional | `layout_03` | 0.294 s |
| Conventional | `switch_01` | 0.324 s |
| Conventional | `switch_02` | 0.393 s |

The matrix ran several episodes concurrently, and video rendering was started
while the last switch episodes were still live. That was an orchestration error:
recording should wait until scored live runs finish. The final switch runs all
failed the runtime-health criterion, so their recorded adaptation delays cannot
establish a clean continuous-time operating limit. Their physical outcomes and
command logs remain visible, and they are not reclassified as perception errors.

As a sensitivity check, **19 matched pairs had healthy runtimes on both sides**.
Across those pairs Codex rejected 15/23 targets and conventional vision 22/23;
complete episode success was 12/19 versus 18/19. Approximate 95% Wilson intervals
for episode success are 41.0–80.9% and 75.4–99.1%, respectively. This subset is
reported alongside the full cohort, not substituted for it.

The original cohort's physical target-rate difference, Codex minus conventional,
was −32.1 percentage points. An episode-paired bootstrap gives a descriptive 95%
interval of −50.0 to −16.1 points. It includes runtime-invalid cases and does not
establish a causal timing effect. Conditions are heterogeneous, samples per
condition are tiny, and these exploratory intervals do not support general claims.

## Supplemental check and remaining work

A [separate supplemental protocol](phase6/confirmatory/PROTOCOL.md) uses two new
seeds, only one Codex/conventional pair at a time, and no concurrent recording.
Its results are kept separate rather than replacing original failures.

**All four supplemental runtimes passed**, with maximum lag 0.069 seconds.
The [supplemental report](results/phase6_confirmatory.json) verifies matching
initial states and accounts for all twelve cubes. Both controllers selected the
correct new color in both episodes and cancelled both old-rule motions. Codex's
two replacement commands expired, while both conventional replacements succeeded.
Both controllers passed all four non-target cubes without unintended contacts.

The measured delay from the 20-second instruction change to the first new command
was **18.188–19.538 seconds for Codex**, versus **0.322–0.370 seconds for the
conventional controller**. The planned approach windows were around 35–36 seconds
of simulation time, so the Codex commands arrived too late even with healthy
runtime pacing. This is evidence of a response-time limitation in these two
probes, not an inability to understand the changed color rule. Two pairs are too
few for a meaningful bootstrap comparison interval; none is reported for this
cohort. Reduced concurrency and changed orchestration also prevent attributing
the latency difference from the original matrix solely to any one component.

All 35 automated tests passed, including counting without promoting a missed
target, instruction-change cancellation, stale-observation rejection, balanced
target positions, and calibrated camera conversion. The development graphics
check recognized all three colors under each variation, with maximum error
4.090 mm. Aggregation verifies source hashes, observation filtering, matching
initial layouts, and complete outcome accounting.

## Demonstrations

- [Codex multi-color success](../../runtime/conveyor/phase6/codex_multi_color.mp4):
  red and blue rejected, green passed, from the original matrix.
- [Codex instruction-change failure](../../runtime/conveyor/phase6/codex_rule_switch.mp4):
  correct blue selection after cancelling red, but the replacement arrives late;
  from the healthy supplemental cohort.
- [Matched conventional instruction-change success](../../runtime/conveyor/phase6/conventional_rule_switch.mp4):
  the same new-seed layout and rule change, with timely execution.

Recordings replay saved trajectories. The instruction and queue overlay change
at the appropriate simulation times, and input images are labeled as snapshots.
All three MP4s passed full FFmpeg decoding and visual inspection of the completed
multi-color push, old-rule cancellation, expired replacement, and matched baseline
success. The multi-color video is 172.40 seconds at 30 fps; both rule-change videos
are 176.13 seconds at 15 fps. All are 960 × 720 H.264. There are 52 retained input
images for the original matrix and eight for the supplemental cohort.

The study still shares scene design and development context with the acting
Codex session. Private files are separated by workflow, not OS enforcement.
The baseline grammar is fixed; arbitrary language, long streams, unknown camera
calibration, new lighting distributions, and changes during a push remain untested.
Exact model version, token usage, call count, and cost are unavailable.

The [formal benchmark milestone](phase6/FORMAL_BENCHMARK.md) remains unchecked:
30 episodes of 20 cubes per main condition, a frozen automatic model runner,
independent evaluation context, and model telemetry. See the [tool guide](PHASE6.md)
and [progress checklist](PLAN.md).
