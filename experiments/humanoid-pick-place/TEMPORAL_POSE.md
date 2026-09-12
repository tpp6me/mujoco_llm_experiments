# Experimental temporal RGB/hand-motion consistency model

`humanoid_sim.temporal_pose.TemporalPose` tests whether successive RGB silhouettes
can be explained by one object-to-hand transform. It returns a candidate current
center or an explicit refusal. **It remains disconnected from control.** A rigid
grasp is a model assumption to check, never a supplied fact or confirmed output.
See the [P4 results](TEMPORAL_POSE_RESULTS.md) and [frozen protocol](protocols/P4.md).

```python
from humanoid_sim.temporal_pose import TemporalPose

tracker = TemporalPose()  # New instance for each episode.
result = tracker.observe(observation)  # Fresh public RGB + robot pose.
# On a known release, discard the old grasp relationship:
tracker.invalidate()
```

The acting `PerceptionSession` still uses the P2 prior-lifetime guard. This API is
for offline candidate development. It does not replace the initial table estimator,
confirm a grasp, estimate slip velocity or expose qualified orientation.

## Inputs and model

Public observation inputs are RGB, camera calibration, timestamp, opaque ID, and
hand XYZ/quaternion. The estimator never reads the environment, object state,
scorer or a support plane. It reuses P3's known cuboid dimensions and scene-specific
red/background boundaries. Neutral robot pixels are treated as unknown occlusion.
All P3 color/lighting/single-object limitations still apply.

A window holds up to three frames. Require at least two, an 80 mm measured hand
translation baseline and at most 3 s between successive observations. One relative
translation and rotation maps the known cuboid into every measured hand pose. P3
fits to the latest image seed 20 joint optimization starts; missing starts are
filled deterministically. Those seeds are hypotheses, not accepted P3 positions.
Each joint optimization runs at most 55 iterations and weights frames equally.

Score each solution by its worst per-frame silhouette RMS. Reuse the P3 checks:
best <=0.75 px, at least three sampled fits within 0.15 px of best, and maximum
pairwise center spread <=20 mm. Candidate centers stay within 0.13 m of the hand,
and all projected cuboid corners must be in front of their cameras. These are
heuristic model/optimization checks, not a calibrated uncertainty interval.

## History and loss behavior

- New trackers and low-motion windows return `insufficient_motion_history` without
  a 3D position. Refusals do not carry forward a previous position.
- Missing visible boundaries or image truncation clear history immediately.
- A time gap over 3 s clears history before adding the new frame.
- Reused IDs, nonadvancing/nonfinite timestamps and malformed frame inputs raise
  an error and clear history. No extrapolated output is produced.
- An infeasible or poor joint fit returns `inconsistent_rigid_transform` and clears
  history. Later observations must establish a new window.
- A spread/count ambiguity returns a refusal; the bounded frame window remains.
- Known release should call `invalidate()`. A new episode requires a new instance;
  invalidation does not erase seen IDs or permit time to go backwards.

`inconsistent_rigid_transform` does not uniquely mean physical slip. Occlusion,
segmentation error, calibration error or optimizer failure can produce it too.
The output always keeps `rigid_grasp_confirmed` and `orientation_qualified` false.
A low residual cannot prove the model correct or rule out unobserved slip.

## Reproduce the private audit

```sh
.venv/bin/mjpython -m humanoid_sim.temporal_pose_evaluation \
  --output runtime/humanoid/temporal-P4-repeat --start-seed 820 --count 10
```

Use a new output directory. Reusing seeds reproduces this check, not fresh
validation. On macOS, rendering requires graphics access. Dependencies are unchanged
and no model/API calls are made.

The evaluator captures 10 exact-state G2 episodes, then runs offline on lift,
lift hold, transport, lower, release and retract endpoints. It intentionally omits
a release action hint to challenge visual/hand consistency. This is not the
recommended way to handle a known release in an acting wrapper.

Separate streams replace only transport RGB with black, or with the preceding
lift-hold image while keeping current hand pose/time/ID. Subsequent frames are
normal. These correlated sensor tests are not physical slip or recovery trials.
Private center error and hand-relative drift are computed after the estimator
returns. They are never used to select or correct its hypotheses.

The analytic rigid positive controls in the tests use exact projected boundaries,
not rendered pixels or physical task episodes. They separate geometric optimizer
behavior from the additional difficulty of real rendered segmentation and grasp
motion. They do not qualify the complete RGB pipeline.
