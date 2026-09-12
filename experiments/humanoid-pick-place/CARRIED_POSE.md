# Experimental carried-block center estimator

`humanoid_sim.carried_pose.estimate_carried_block` fits the known cuboid to RGB
silhouette evidence and measured hand position. It produces a candidate 3D center
or an explicit refusal. It does not assume table support, return measured depth,
confirm a grasp, qualify orientation, or control the robot.

```python
import base64
from humanoid_sim.carried_pose import estimate_carried_block

result = estimate_carried_block(
    base64.b64decode(observation['rgb_png_base64']),
    observation['camera'],
    observation['robot_state']['robot']['hand_xyz_m'],
)
# Experimental only: do not turn this result into a control command.
```

The candidate remains separate from `PerceptionSession`. That wrapper continues
to withhold post-action 3D position using the P2 validity guard. The [P3 report](CARRIED_POSE_RESULTS.md)
records the frozen candidate's fresh-data results and whether it met its exploratory
continuation screen. This is not a qualified visual manipulation comparator.

## Method and declared priors

Inputs contain only RGB, camera calibration and robot hand XYZ. Block dimensions
are fixed at 0.05 × 0.07 × 0.12 m. Candidate centers must lie within 0.13 m of the
hand. That is a geometric assumption; contact, slip and a fallen object are not
inferred from it. There is no object truth, object depth, scorer or table plane
access in the estimator module.

The image extractor finds red object pixels and boundaries adjacent to the current
scene's yellow table, cyan basket or slate background. Neutral robot pixels are
treated as unknown occluders. These are scene-specific color rules, not semantic
segmentation. Changed lighting, colored robot surfaces, unrelated red objects or
other backgrounds can invalidate them. Image-edge truncation and insufficient
visible boundary cause refusal.

For each of 20 deterministic rotation starts, a damped finite-difference optimizer
fits translation and rotation of the known cuboid. The loss measures visible
boundary distance to the projected cuboid outline and penalizes red pixels outside
it. Unknown boundaries behind the hand are not treated as observed object edges.
The hand-proximity penalty constrains the search; camera-front and proximity checks
filter the resulting candidates.

A small projection residual does not establish a unique 3D position. Multiple
solutions are also a known issue for planar pose methods; see the
[IPPE authors' ambiguity discussion](https://github.com/tobycollins/IPPE). This
implementation uses its own cuboid silhouette optimizer, not IPPE or OpenCV.

Accept only when the best RMS is at most 0.75 px, at least three sampled fits are
within 0.15 px of best, and the maximum pairwise center spread among those fits is
at most 20 mm. Return the best sampled center. The spread is a search diagnostic,
not a calibrated confidence interval or a guarantee all possible poses were found.
Repeated optimizer convergence is not independent statistical evidence.

Returned results always identify the method as experimental and orientation as
unqualified. Refusals contain no `object_center_xyz_m`; callers must not substitute
the previous position or an internally best hypothesis as a fresh measurement.
Rotation matrices are internal fit hypotheses, not qualified orientation output.

## Reproduce P3

```sh
.venv/bin/mjpython -m humanoid_sim.carried_pose_evaluation \
  --output runtime/humanoid/carried-P3-repeat --start-seed 800 --count 10
```

Use a new output directory. Reusing seeds reproduces the development check; it is
not a fresh validation. On macOS, capture requires graphics access. No additional
Python dependencies or model/API calls are required.

The evaluator first uses the exact-state G2 driver to capture reset/action endpoint
observations. Only after capture does it run the candidate on lift, lift-hold,
transport and lower images. Private truth is consulted after estimation for errors
and tilt diagnostics. This offline audit is not image-driven closed-loop control.

Each original also produces a black mask through median visible-red X and a fully
black image. These deterministic sensor corruptions retain camera/robot inputs and
use no truth to choose the mask. They test loss/partial occlusion behavior but are
not physical recovery trajectories. All original and corrupted cases are retained
separately; they do not increase the count of independent episodes.
