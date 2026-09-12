# RGB perception during manipulation

`humanoid_sim.perception.PerceptionSession` combines the public RGB observation
boundary with conservative perception validity. It is intended to be instantiated
at episode reset, when the declared initial upright/table-support prior holds.

```python
from humanoid_sim.visual import RGBRenderer, VisualSession
from humanoid_sim.perception import PerceptionSession

renderer = RGBRenderer(env, camera='fixed')
try:
    session = PerceptionSession(VisualSession(env, renderer))
    observation, perception = session.capture()
    # Construct a shared-interface request, then consume this observation once:
    # response = session.execute(observation['observation_id'], request)
finally:
    renderer.close()
```

Perception contains two separate results:

- `visibility`: detected red pixels, their count, centroid and bounds. This assumes
  a single red object; unrelated red regions are not disambiguated. Detection does
  not establish a grasp, full visibility, a 3D position or physical task success.
- `pose`: the P1 initial supported-block estimate, or an explicit unavailable result.
  The table prior expires before the first action attempt, including a rejected
  attempt, and on observed time advancement. After that, images cannot restore it.
  No previous position is returned as a current measurement.

The wrapper delegates action freshness to `VisualSession`. Repeated observation
IDs and time reversal are rejected by perception. Start a new session for a new
episode; all acting-policy commands must use this wrapper. It does not isolate an
arbitrary Python program from simulator internals, and it cannot infer an unseen
external state change at the same timestamp. Initialization itself is a declared
prior, not an RGB proof that the object is upright and supported.

This implements a validity guard and visibility diagnostics. **It does not estimate
carried-object 3D pose, detect every occlusion, or control the task from RGB.**
See the [P2 results](PERCEPTION_RESULTS.md) for evidence and limitations.

## Reproduce the private audit

```sh
.venv/bin/mjpython -m humanoid_sim.perception_evaluation \
  --output runtime/humanoid/perception-P2-repeat --start-seed 760 --count 20
```

The output directory must be new. Reusing these seeds is reproduction, not a fresh
validation. On macOS, rendering needs graphics access. The evaluator drives the
G2 conventional **exact-state** policy and records RGB at reset and after each
attempted action. It never claims the policy acted from the perception result.
The protocol and source hashes are saved before episode generation.

Per-episode `*-observation.json` and `*-perception.json` contain public inputs and
outputs. `private_records.json`, `summary.json`, saved episodes and scoring data
are evaluator-only artifacts. The initial P1 estimator is also deliberately applied
to every image as a private invalid-prior diagnostic, outside the acting interface.

## Remaining work

- Implement and validate carried-object 3D pose under declared sensor and geometry
  assumptions; unavailable output is required when the observation is ambiguous.
- Evaluate visibility and recovery within actions, not only at action endpoints.
- Integrate a conventional RGB controller without exact-state grasp checks or
  release offsets. Qualify its full physical task before a matched visual LLM run.

The subsequent [P3 carried-center candidate](CARRIED_POSE_RESULTS.md) was
implemented and evaluated independently. It failed its frozen screen and remains
disconnected from control; the P2 support-prior guard remains in effect.
