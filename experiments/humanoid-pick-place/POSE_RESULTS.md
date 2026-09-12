# P1 RGB supported-block position estimator

Date: 2026-09-12. **20/20 fresh reset images produced accepted estimates within
5 mm XY error**, using only RGB, camera calibration and declared geometry priors.
This is perception development, not a grasp/control qualification.

| Metric, seeds 720–739 | Previous all-red centroid | Bright top-surface estimator |
|---|---|---|
| Mean XY error | 23.463 mm | 0.518 mm |
| Maximum XY error | 29.555 mm | 2.418 mm |
| Estimates within 5 mm | 0/20 | 20/20 |
| Accepted estimates | 20/20 | 20/20 |

All 20 captures preserved the full integration state exactly. No refusals or
failed cases were excluded. Source was frozen before the image set was generated;
images 700–704 were development data. The [P1 protocol](protocols/P1.md) defines the
accounting and the 5 mm development screen, which is not a validated grasp tolerance.
The prior centroid measurements on different images remain in [visual results](VISUAL.md).

## Method and information boundary

The previous estimator mixed top and side surfaces, then projected their combined
centroid onto the top plane. The new method separates red pixels into two brightness
clusters and selects the largest connected bright patch. Under the current fixed
lighting, this is assumed to be the top surface. Camera rays map that patch onto
the known horizontal top plane. Its center and principal axes give XY and a yaw
estimate modulo pi; the support/height prior supplies Z.

Known top-face dimensions provide coverage and extent checks. Ambiguous brightness,
multiple substantial patches, low coverage or incompatible shape produce a refusal.
A unit regression verifies rejection of a synthetically obscured patch. This is not
a complete occlusion detector and does not prove the support or lighting assumptions.

Inputs are PNG bytes, calibrated camera geometry, table height 0.70 m and block
size 0.05 × 0.07 × 0.12 m. The estimator imports no environment, simulator state,
scorer or truth access. Private truth is used only by the external validation
script to measure error. The estimator's Z is a prior, not measured depth.
Yaw accuracy was not scored and must not be treated as qualified orientation control.

## Limits and next step

This estimator is valid only as a candidate for the initial upright, table-supported
block under the declared fixed camera and lighting. It cannot track a freely held,
tilted, fallen or partly hidden object without new modeling and validation. One
red object is assumed; unrelated red regions and changed illumination are outside
this check. No RGB-driven manipulation or visual LLM trial has been run.

The subsequent [P2 audit and validity guard](PERCEPTION_RESULTS.md) measures
endpoint visibility and prevents reuse of this initial support prior after actions.
It does not add a carried-object pose estimator.

Next: validate carried-object pose and occlusion handling, build a conventional
visual controller using only public observations, then qualify the full task before
a matched visual LLM comparison. Initial image accuracy alone is not task success.

## Artifacts

- [All 20 private validation records](results/pose_P1.json), including the previous
  method's errors for every image and source hashes.
- [Frozen source and validation script](results/pose_P1_source.zip).
- [Tests](../../tests/test_humanoid_vision_pose.py), including saved RGB fixtures,
  missing-object handling, calibration-size rejection and synthetic occlusion.
- [Full suite: 70 passing tests](results/pose_P1_tests.txt), [plan](PLAN.md), [visual boundary](VISUAL.md).

The full image set is retained locally in `runtime/humanoid/pose-P1/`; these runtime
images are ignored by Git. Two earlier RGB development fixtures are included with
the tests. The source ZIP does not duplicate robot meshes; use the pinned assets
and dependency lockfile in the repository. No model/API calls were made for P1.
