# P3 carried-block center results

Date: 2026-09-12. **The experimental monocular estimator failed its frozen
continuation screen and remains disconnected from control.** It produced accepted
centers within 20 mm on 18/40 original carried images (45%), below the required
32/40. There was one accepted error above 20 mm in the original images and one in
the partial-occlusion variants. No thresholds were changed after this evaluation.

This is progress from table-only position estimation to a tested carried-center
candidate, not a qualified carried-pose estimator or RGB manipulation controller.
The P2 wrapper continues to withhold post-action positions.

## Frozen data and results

The [P3 protocol](protocols/P3.md) was frozen after development on seeds 740–742.
Ten fresh exact-state G2 trajectories, seeds 800–809, completed without driver
failures. All 120 reset/action-endpoint captures preserved integration state.
Four carried endpoints per trajectory supplied the 40 originals: lift, lift hold,
transport and lower. Private truth measured long-axis tilt from vertical between
45.88° and 63.61°. No failed episode or frame was replaced or excluded.

Each original also generated a partial-blackout and fully black sensor image.
These are 80 correlated corruptions of the same 40 frames, not additional
independent episodes or physical occlusion/recovery trials.

| Input condition | Cases | Accepted | Within 20 mm, all cases | Accepted >20 mm | Accepted mean / max error |
|---|---:|---:|---:|---:|---:|
| Original RGB | 40 | 19 | 18/40 | 1 | 13.108 / 20.885 mm |
| Partial blackout | 40 | 1 | 0/40 | 1 | 22.992 / 22.992 mm |
| Fully black | 40 | 0 | 0/40 | 0 | Not applicable |

Original refusals: 20 ambiguous fits and one insufficient visible boundary.
Partial-blackout refusals: 26 ambiguous fits and 13 insufficient boundaries.
All 40 fully black images refused for insufficient boundary evidence. The black
image condition tests appropriate unavailability, not expected successful estimation.

| Original endpoint | Images | Accepted | Within 20 mm |
|---|---:|---:|---:|
| Lift | 10 | 4 | 4 |
| Lift hold | 10 | 4 | 3 |
| Transport | 10 | 2 | 2 |
| Lower | 10 | 9 | 9 |

The exploratory 20 mm screen is not a mechanically justified grasp/release tolerance.
Accepted-only errors omit refusals, so they must be read with the all-case counts.
Orientation was fitted internally but not scored or exposed as qualified output.

## Why the checks were insufficient

Two retained accepted errors illustrate the remaining problem:

- Seed 806, original lift-hold image: 20.885 mm true center error despite 0.152 px
  fit RMS and 16.239 mm sampled center spread among four near-best fits.
- Seed 804, partially blacked-out lift-hold image: 22.992 mm error despite 0.115 px
  RMS and 19.854 mm sampled spread among four near-best fits.

The sampled optimizer solutions are not an exhaustive ambiguity set. Similar
silhouettes can agree in pixels while differing in 3D, and occlusion/color rules
can remove useful constraints. The empirical errors show that small residual and
small sampled spread do not guarantee the desired center accuracy.

The [method guide](CARRIED_POSE.md) declares the fixed scene-color rules, known
block dimensions, and 0.13 m hand-proximity prior. That prior is not grasp
confirmation; it must not be used to conceal a fall or slip. No table height or
object truth enters the candidate. Private truth was used only after estimation.

## Validation and limitations

The complete automated suite passed **79 tests**, including real tilted images,
ambiguous competing centers, total loss, image-edge truncation and malformed inputs.
Passing tests confirm the implementation's stated behavior; they do not override
the failed fresh-data screen. Original-frame estimator time averaged 0.829 s,
maximum 0.963 s on this local run; these are diagnostic timings, not a controlled
performance benchmark or real-time control qualification.

The driver used exact state, and the estimator ran offline after capture. No
image-driven action was executed. Endpoint sampling does not cover intermediate
occlusion, slip dynamics or recovery. Synthetic blackouts do not replace natural
loss trajectories. No model/API calls were made.

## Next step

Keep P3 frozen and disabled. Develop a separately declared estimator that combines
successive RGB views with measured hand motion, explicitly testing the assumed
object/hand relationship rather than treating it as proof of a rigid grasp. First
check whether that evidence resolves depth ambiguity on development trajectories;
if it does, freeze a new protocol and use new seeds, including slip/loss cases.
Any additional camera or depth input must be a separately labeled sensor condition.
Only a qualified perception result can support the full conventional RGB controller
and a matched visual LLM comparison.

## Artifacts

- [All candidate records, refusals and frozen hashes](results/carried_P3.json).
- [All private capture records and driving outcomes](results/carried_P3_capture.json).
- [Frozen source, fixtures, protocol and development prototypes](results/carried_P3_source.zip).
- [79-test log](results/carried_P3_tests.txt), [method/run guide](CARRIED_POSE.md),
  [living checklist](PLAN.md).

Original RGB images and public observation/perception payloads remain under
`runtime/humanoid/carried-P3/capture/` (ignored by Git). Corruptions are regenerated
exactly by the frozen pixel-only transformation. Development fixtures for lift,
transport and lower are tracked in `tests/fixtures/humanoid_carried_rgb/`. The
source archive uses the repository's pinned G1 assets rather than duplicating meshes.

The subsequent [P4 temporal candidate](TEMPORAL_POSE_RESULTS.md) combines RGB
with hand motion. Its accepted centers were accurate on the fresh set, but it
failed the coverage screen and remains disconnected from control. Reacquisition
after a rejected window is the next development step.
