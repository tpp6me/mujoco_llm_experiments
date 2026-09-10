# Phase 5 results — camera input and continuous motion

Date: 2026-09-09. **The camera measurement gate is complete.** Codex selected
the correct color in all 16 submitted estimates, but physically rejected only
6/16 targets. Ten commands expired before execution. All 20 non-target cubes
passed correctly. A conventional image-color baseline rejected 15/16 targets.

The [complete report](results/phase5_comparison.json) retains twelve Codex and
twelve conventional episodes, with every failure. All 72 cubes received final
outcomes. Configurations and initial physical layouts match Phase 4 exactly.
Codex made its pixel selections in this session; no scripted selector supplied
those decisions. All Codex submissions finished before private scoring reports
were opened.

## Physical outcomes

| Condition | Codex episodes passed | Codex targets rejected | Vision baseline episodes passed | Vision baseline targets rejected |
|---|---:|---:|---:|---:|
| Mixed colors, 0.5 cm/s, 12 cm spacing | 2/3 | 2/3 | 3/3 | 3/3 |
| Mixed colors, 1 cm/s, 12 cm spacing | 2/3 | 2/3 | 3/3 | 3/3 |
| Mixed colors, 2 cm/s, 12 cm spacing | 0/3 | 0/3 | 3/3 | 3/3 |
| Mixed colors, 3 cm/s, 12 cm spacing | 0/1 | 0/1 | 1/1 | 1/1 |
| Three red targets, 1 cm/s, 8 cm spacing | 0/1 | 1/3 | 1/1 | 3/3 |
| Three red targets, 1 cm/s, 6 cm spacing | 0/1 | 1/3 | 0/1 | 2/3 |
| **Total** | **4/12** | **6/16** | **11/12** | **15/16** |

Both controllers passed all 20 non-targets with zero wrong rejections or
unintended contacts. Codex's six executed sequences all succeeded physically;
the remaining ten expired. The baseline's single miss was a robot-cycle overlap
at 6 cm spacing. There were no lost, stuck, or unresolved cubes.

## Perception and timing

Errors below compare submitted pixel estimates with hidden state at image capture,
including estimates attached to expired commands. They measure selected objects,
not exhaustive detection or tracking.

| Measurement | Codex camera | Conventional vision |
|---|---:|---:|
| Correct perceived colors / estimates | 16/16 | 16/16 |
| Estimates associated with actual targets | 16/16 | 16/16 |
| Median position error | 0.707 mm | 0.629 mm |
| Maximum position error | 1.303 mm | 4.330 mm |
| Maximum absolute belt-direction error | 1.188 mm | 4.321 mm |
| Median capture-to-image-ready delay | 0.159 s | 0.166 s |
| Maximum capture-to-image-ready delay | 0.198 s | 0.373 s |
| Minimum observation-to-submission gap | 16.192 s | 0.186 s |
| Median gap | 20.466 s | 0.228 s |
| Empirical 95th percentile gap | 28.677 s | 0.331 s |
| Maximum gap | 29.592 s | 0.446 s |
| Largest simulation lag | 0.056 s | 0.050 s |

All 24 runtimes stayed below the frozen 0.25-second lag threshold. Physics
continued while a separate graphics process rendered the captured state and
while Codex inspected images and submitted commands. End-to-end response gaps
include rendering, delivery, reasoning, tool calls, and batching across cases;
they are not measurements of isolated model inference time.

## Comparison with supplied state

| Controller | Phase 4 target rejections | Phase 5 target rejections | Phase 4 median gap | Phase 5 median gap |
|---|---:|---:|---:|---:|
| Codex session | 8/16 | 6/16 | 15.772 s | 20.466 s |
| Conventional | 15/16 | 15/16 | 0.016 s | 0.228 s |

Codex missed two additional targets: the leading red cube at 0.5 cm/s and the
middle cube in the 8 cm stream. Both camera commands expired. For the slow red
case, the requested approach start was 22.732 s and receipt was about 30.114 s.
Blue and green targets farther upstream still allowed successful interceptions
at 0.5 and 1 cm/s. Every mixed-color camera command at 2 cm/s, and the red probe
at 3 cm/s, arrived late. In both camera stream trials, the first two requests
expired and the last target was rejected successfully.

There were no observed color-selection errors to explain these misses. The
camera run had longer response gaps, but the study cannot isolate how much came
from visual reasoning versus image handling, batching, or other session overhead.
Expiry concerns the fixed planned start and no-retry policy; it does not establish
that a later interception elsewhere in the workspace was physically impossible.

## Evidence, validation, and limits

All 31 automated tests passed. New checks verify that public observations omit
oracle object fields, changing private truth does not change compiled actuator
commands, and a wrong color claim is scored without automatic correction.
The development camera check detected all three colors with maximum error
1.657 mm on seed 42. That is a development check, not a general error bound:
the evaluated conventional baseline's largest error was 4.330 mm.

The aggregate verifies frozen runtime/controller source hashes, matching initial
states, complete outcome accounting, and the public observation field whitelist.
It includes decision logs, perception audits, and hashes for all
[24 input images](phase5/inputs).

- [Camera success video](../../runtime/conveyor/phase5/codex_camera_success.mp4):
  green target at 0.5 cm/s, showing the original input image and completed push.
- [Expired-command video](../../runtime/conveyor/phase5/codex_camera_expired.mp4):
  red target at 2 cm/s, showing the late command and resulting miss.

The success recording is 171.97 seconds and the failure recording 47.53 seconds;
both are 960 × 720, 30 fps, H.264. Full FFmpeg decoding passed for both.
Frames showing the completed green rejection and expired red command were
visually inspected, including the clearly labeled original-image inset.

This is a small development demonstration using one initial image per case,
known calibration and belt velocity, fixed lighting, and a known motion recipe.
The session already knew the Phase 4 layouts; it is not a blinded benchmark.
Red is leading, green middle, and blue trailing in the three mixed-color layouts,
confounding target color with available lead time. The public interface excludes
oracle metadata, but the shared filesystem does not enforce isolation. Exact
runtime model version, model calls, token usage, and cost are unavailable.

The Phase 5 gate requires an auditable comparison, not successful sorting in every
case. These results demonstrate visual target selection and some physical task
completion; they do not demonstrate superiority over conventional vision or a
general robotics policy. Subsequent robustness and adaptability work is documented
in [Phase 6 results](PHASE6_RESULTS.md).
See the [camera tool guide](PHASE5.md) and [progress checklist](PLAN.md).
