# P2 manipulation visibility and support-prior results

Date: 2026-09-12. **20 episodes, 240/240 expected endpoint images retained.**
The new perception wrapper never returned a supported 3D estimate after an action
attempt. The unguarded P1 diagnostic accepted 73/80 post-release images despite
3D errors above 5 mm, reaching 13.010 mm. This confirms why a plausible red patch
must not silently restore the initial table-support assumption.

These episodes were driven by the conventional **exact-state** G2 policy. They are
not a visual control benchmark. No carried-object 3D pose or visual LLM was tested.

## Frozen evaluation

Seeds 760–779 followed the [P2 protocol](protocols/P2.md), frozen after development
on seeds 740–742. Capture at reset and after each attempted action gives 12 frames
per complete episode. All 20 driving episodes completed without a policy exception
or reported failure; private scoring recorded 20 placements. Those physical outcomes
belong to the exact-state driver, not to the perception wrapper. This run does not
replace the independent G2 mechanical qualification.

| Endpoint | Images | Red detected | Guarded 3D estimates | Raw P1 estimates | Raw P1 errors >5 mm |
|---|---:|---:|---:|---:|---:|
| Reset | 20 | 20 | 20 | 20 | 0 |
| Approach | 20 | 20 | 0 | 20 | 0 |
| Descend | 20 | 20 | 0 | 0 | 0 |
| Close | 20 | 20 | 0 | 0 | 0 |
| Lift | 20 | 20 | 0 | 0 | 0 |
| Lift hold | 20 | 20 | 0 | 0 | 0 |
| Transport | 20 | 20 | 0 | 0 | 0 |
| Lower | 20 | 20 | 0 | 0 | 0 |
| Release | 20 | 20 | 0 | 13 | 13 |
| Retract | 20 | 20 | 0 | 20 | 20 |
| Park | 20 | 20 | 0 | 20 | 20 |
| Settle | 20 | 20 | 0 | 20 | 20 |

The 20 initial estimates had mean **1.082 mm**, maximum **3.621 mm** 3D center
error; all were within the 5 mm development screen. Unlike P1's XY-only headline,
these numbers include Z. No rejected or failed frames were excluded.

All 240 captures preserved integration state exactly. Every detected red bounding
box lay within the privately projected cuboid bounds with 2 px tolerance. The mean
visible-centroid distance from the projected true center was 6.708 px, maximum
21.327 px. These pixel measurements are neither a depth estimate nor an occlusion
fraction. The hand visibly hides parts of the block during carrying even while
red pixels remain detectable.

## What changed

The [perception wrapper](PERCEPTION.md) expires the initial support prior before
the first action attempt, including rejection. Observed time advancement also
expires it. Later images report pixel visibility and explicit pose unavailability;
they cannot revive an old support assumption or return a stale position as measured.

The guard withholds all 220 post-action positions, including the approach images
where the initial estimator happened to remain accurate. This deliberately
conservative lifetime rule is an interface invariant, not an inference that every
action moved the block. A future estimator can replace this limitation only with
separate evidence for its observation and geometry assumptions.

The complete automated suite passed **75 tests**, including real carried/released
RGB fixtures, total synthetic visibility loss, repeated/regressing observations,
time advancement and rejected-action prior expiry. Loss and rejection regressions
are synthetic interface cases, separate from the 240 rendered endpoints.

## Limits and next steps

- No continuous visibility assessment: occlusions within a two-second move may be
  missed by endpoint captures. No natural total-visibility loss occurred here.
- No carried pose, slip estimate, grasp confirmation, placement inference or
  recovery action is produced. Red visibility alone cannot supply these.
- One red object, existing fixed lighting/camera, supported G1 and the same task
  distribution. Head-camera coverage is still unqualified.
- The driver accesses exact state. Only perception receives public inputs; a full
  RGB controller must remove oracle grasp checks and release-offset calculations.

Next: implement a carried-object 3D estimator with explicit ambiguity/occlusion
refusals, validate it on new trajectories including losses and tilts, then build
and qualify the conventional RGB controller before comparing a visual LLM.

## Reproducibility

- [Private per-frame records and frozen hashes](results/perception_P2.json).
- [Frozen source, protocol, fixtures and development evidence](results/perception_P2_source.zip).
- [75-test log](results/perception_P2_tests.txt).
- [Run guide and boundary contract](PERCEPTION.md), [living checklist](PLAN.md).

Images, public observations/perception outputs, private records and trajectories
are retained locally in `runtime/humanoid/perception-P2/` (ignored by Git). Two
representative RGB fixtures from development seed 740 are tracked in
`tests/fixtures/humanoid_carried_rgb/`. The archive includes source and dependency
lockfiles; it relies on the repository's pinned G1 mesh assets. No model/API calls
were made for this work.

The subsequent [P3 carried-center candidate](CARRIED_POSE_RESULTS.md) was
implemented and evaluated independently. It failed its frozen screen and remains
disconnected from control; the P2 support-prior guard remains in effect.
