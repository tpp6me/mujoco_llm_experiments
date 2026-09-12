# Visual observation development

Date: 2026-09-12. The RGB/proprioception boundary is implemented and tested.
No visual LLM or complete conventional vision policy has been evaluated yet.

## Capture

Use an existing episode, or create a fresh reset with the normal CLI:

```sh
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/visual-example reset --seed 700 --randomize
.venv/bin/mjpython -m humanoid_sim.visual --episode runtime/humanoid/visual-example --output runtime/humanoid/visual-example-capture --camera fixed
```

Capture requires a new output directory and writes `rgb.png` and `observation.json`.
The JSON includes the PNG as base64 so it is self-contained and contains no local
image path. Use `--camera head` to inspect the existing robot camera. On macOS,
rendering needs `mjpython` and the graphics session. Capture does not save over,
advance or modify the episode. No API credentials or paid calls are involved.

## Public boundary and freshness

`VisualSession(env, renderer).capture()` returns exactly:

- `schema_version`: `humanoid-visual-v1`.
- `observation_id`: an opaque, random ID for this capture.
- `time_s`: the image/robot observation's simulation timestamp.
- `robot_state`: the existing robot-state-only interface observation.
- `camera`: intrinsics, world camera pose and coordinate conventions.
- `rgb_png_base64`: unannotated RGB pixels; site markers are hidden.

Object pose/identity labels, object contacts, scorer flags, source hashes, seed,
private reports, depth and segmentation are not exported. Camera geometry is a
declared calibration prior, not object truth. The robot interface retains its
declared binary robot-link contact readings. The scene still has its original
simulated materials, including translucent basket walls; visual claims must
retain that assumption. The camera code does not alter the scene or physics.

Call `execute(observation_id, request)` with the same version-2 action request used
by the other policies. A capture permits one attempt, including a rejected attempt.
A new capture invalidates the old one. An intervening integration-state change
invalidates the image even if simulation time is unchanged. Rejected stale actions
do not advance physics and are logged privately. The freshness fingerprint is
private and is never part of the public observation. The model/camera configuration
must stay fixed during an episode, with one writer.

The CLI exports a standalone observation only. Its process exits, so a future
closed-loop runner must retain a live `VisualSession` to submit actions against
its IDs. It must whitelist these public fields and map the PNG into an image input.
Python objects and private files are not a security sandbox; do not grant an
acting model general access to the process, archives, scorer or filesystem.
There is currently no model API wiring for this visual boundary.

## Camera calibration and checks

The fixed viewpoint looks at (0.24, −0.24, 0.8) m from distance 1.35 m, azimuth
90 degrees and elevation −65 degrees. It provides a 960 × 720 RGB view. Calibration
is derived from the renderer's averaged OpenGL camera, matching MuJoCo's mono
rendering convention. The exported frame is X right, Y down, Z forward, with
zero-indexed pixel centers. See the official [MuJoCo visualization documentation](https://mujoco.readthedocs.io/en/latest/programming/visualization.html).

Five randomized reset captures (seeds 700–704) were checked privately. All preserved
the complete integration state exactly. The detected red-pixel bounds fell within
the projected physical block bounds, allowing two pixels for rasterization, in
all five cases. Unit checks also cover projection/plane-ray round trips. These
checks validate the basic projection convention, not full workspace coverage or
perception accuracy during occlusion and manipulation.

The fixed initial view visibly covers block, hand and basket. The existing head
camera's initial view crops the block and basket at the image edges; it is not
qualified for the primary task. Its aim/coverage needs a separately documented
revision before a head-camera evaluation. The original model camera is preserved.

## Conventional perception helper and its limit

`detect_red_pixels(png)` thresholds RGB and returns visible red-pixel count,
centroid and bounds. It assumes one red object and merges all qualifying pixels;
it does not identify multiple objects, infer hidden surfaces, or estimate pose.
`pixel_to_plane` requires an explicit known plane and is not a depth sensor.

On the five initial captures, mapping the visible red centroid onto the assumed
block-top plane Z=0.82 m produced up to **0.02983 m XY error** against private
simulator truth. Side faces, perspective and occlusion make the centroid different
from a top-face center. This helper is therefore **not a qualified grasp-position
estimator or a conventional visual manipulation comparator**. It must not receive
private truth as a correction in a future visual benchmark.

The subsequent [P1 estimator](POSE_RESULTS.md) separates the bright top surface
and uses declared table/block geometry. On 20 fresh initial images it achieved
0.518 mm mean and 2.418 mm maximum XY error, with all 20 within 5 mm.
This validates an initial supported-block estimate under fixed lighting; Z comes
from a prior and yaw accuracy was not scored. It does not qualify visual control.

Next: validate carried-object pose and occlusion handling, then integrate and
qualify a conventional visual policy before a matched visual LLM comparison.

## Evidence

- [Private five-capture validation](results/visual_v1_validation.json), kept separate
  from policy observations and never sent to an acting model.
- [Observation/test source](results/visual_v1_source.zip), [test log](results/visual_v1_tests.txt).
- [L2 grasp-failure audit](GRASP_AUDIT.md), [living checklist](PLAN.md).

Fixed/head RGB examples and validation images remain locally under
`runtime/humanoid/visual-v1/`. The public JSON contains no scoring data. The private
validation file includes true poses only for post-hoc error measurement.

## Perception validity during manipulation

Use the [perception wrapper](PERCEPTION.md) when pairing images with position
estimates. It expires the initial table-support prior before any action attempt,
including rejection. Later red-pixel detections never restore a table-based pose.
The [P2 endpoint audit](PERCEPTION_RESULTS.md) records visibility and diagnostic
errors through grasp, transport and release; carried 3D pose remains unavailable.
