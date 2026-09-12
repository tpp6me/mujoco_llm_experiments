# Shared policy interface v2

Status: implemented and tested; [G2 guarded qualification](GUARDED_RESULTS.md)
passed with 97/100 strict successes and 100/100 placements. Qualification is
limited to the declared supported-body recipe.
This interface runs paused-time actions on the supported G1. It connects no LLM.
The [V4 mechanical result](V4_RESULTS.md) applies to the archived V4 controller;
it does not automatically qualify new orientations or this stricter interface.

## Use

Create a new episode with the existing reset command, then use the versioned API:

```sh
.venv/bin/python -m humanoid_sim --episode runtime/humanoid/interface-01 reset
.venv/bin/python -m humanoid_sim.interface --episode runtime/humanoid/interface-01 observe
.venv/bin/python -m humanoid_sim.interface --episode runtime/humanoid/interface-01 act --request experiments/humanoid-pick-place/schemas/move-example.json
.venv/bin/python -m humanoid_sim.interface --episode runtime/humanoid/interface-01 --mode robot_state observe
```

Choose a new directory for another reset. Commands are sequential and each episode
must have one writer. Completed baseline trials reject action commands. Python
policies use `PolicyInterface(env, mode).observe()` and `.execute(request)`;
the caller owns episode persistence and single-writer enforcement. The CLI saves
each attempt. Python callers must also respect completed-episode immutability.

## Action contract

[JSON Schema](schemas/action-v2.schema.json) and [example](schemas/move-example.json).
Requests require exactly `schema_version`, `instruction_version`, `request_id`,
`action`, and `arguments`. The version is `humanoid-actions-v2`; instruction
version is currently fixed at integer 1. Dynamic instruction replacement is a
later feature. Request IDs are unique strings of 1–128 characters, including
rejected attempts with a valid ID. Reusing an ID rejects the action; inspect the
saved response instead of retrying a potentially executed action.

| Action | Required arguments | Meaning |
|---|---|---|
| `move` | `xyz_m`, `quaternion_wxyz`, `seconds` | Desired world pose of the right grasp site |
| `hand` | `closure`, `seconds` | Coordinated finger closure from 0 (open) to 1 (closed) |
| `hold` | `seconds` | Retain current actuator targets |

Coordinates use metres and world Z up. Quaternion order is **w, x, y, z** and
represents the grasp-site local frame in world coordinates. Unit norm must be
within 1e-6; accepted values are normalized before conversion. Opposite signs
represent the same rotation. The historical downward orientation is
`[0.5, -0.5, 0.5, 0.5]`. Durations are 0.02–10 seconds and are rounded up to the
1 ms physics step. Closure, duration, XYZ and quaternion components must be finite
numbers; booleans and numeric strings are rejected. Unknown fields, duplicate
JSON keys, nonfinite JSON constants, unsupported versions and malformed requests
are rejected. The runtime additionally checks unit quaternion, reachability,
workspace and collision constraints that JSON Schema alone does not establish.

The declared development bounds are X 0.15–0.55, Y −0.60–−0.05, Z 0.60–1.15 m.
IK can reject poses within these bounds. These are input bounds, not a qualified
workspace. Arbitrary orientations have not been mechanically qualified.

## Observations and outcomes

Every observation has `schema_version`, `instruction_version`, `mode`, `time_s`,
`frame`, `supported_body`, and `robot`. Robot data contains ordered actuator-joint
names, joint positions in radians, joint velocities in radians/second, actual
hand XYZ and quaternion, and `contact_links`. The latter simulates binary contact
sensors on right-arm/hand links: it identifies the robot link touching something,
without identifying the other body or exposing contact forces or the scorer.
These are declared simulator-derived sensors, not a claim about physical G1 hardware.

`exact_state` additionally exposes `task_state`: the legacy simulator-truth
observation, including object and basket locations and object contact identities.
`robot_state` omits task truth and all scoring fields. It currently has **no images**
and is not a vision condition. A future model runner must restrict policy inputs
to its selected mode and prevent access to private files. This Python/CLI boundary
alone is not a sandbox; an unrestricted process can read the simulator and archives.

Action responses include schema version, request ID (null if invalid), status,
start/end simulation timestamps, and a fresh observation. Errors include a
reason. `completed` means the requested actuator interpolation ran; it does not
assert exact pose tracking, grasp success, or task success. Actual hand/joint
feedback is the observation. `rejected` means validation/preflight prevented
execution. Runtime physics errors return `failed` and preserve the advanced
state. This version neither retries nor changes policy targets automatically.
Physics pauses between actions; no wall-time or latency claim is made.

## Controller responsibilities and safeguards

The policy selects approach, grasp, lift, transport, release, withdrawal, recovery,
orientation, closure and duration. Low-level code performs bounded IK, quaternion
conversion, actuator interpolation and validation. There is no `pick` or
`pick_and_place` action and no object-offset correction inside the API.
Conventional and future LLM policies must use this same interface for a matched
comparison. Legacy unguarded commands remain development tools.

Before execution, the safeguard checks 101 samples of an arm-joint path from
the measured pose to the requested joint target, keeping fingers and other joints at measured
positions. It rejects predicted penetration over 2 mm involving the right
arm/hand and other robot/environment geometry. Object contacts are excluded so
the guard does not plan grasps or object transport from private object truth.
The collision scene still supplies robot and static-environment geometry to the
low-level controller; disclose this prior in visual comparisons.

This is a sampled kinematic check, not continuous collision detection or dynamic
prediction. It does not forecast finger flexion, carried-object collisions,
tracking error or between-sample contact. Force-limited finger commands cannot
be treated as exact joint poses. Contact physics and private independent outcome
scoring remain active during execution. General collision-free motion and an
ordinary-posture-to-ready transition remain unqualified.

## Verification and qualification

Tests cover invalid requests without integration-state changes, duplicate/stale
requests after reload, malformed JSON logging, immutable completed trials,
observation field isolation, orientation tracking and quaternion sign equivalence,
collision rejection, and a complete nominal guarded manipulation sequence.

The guard rejects the V4 lowering request at 11 simulated seconds: with fingers
held at measured positions it predicts an index-finger/basket intersection.
The rejection does not advance physics. An explicit policy revision raises the
release target from 0.86 to 0.90 m, then opens, withdraws, parks and holds; that
nominal development case passes the unchanged task/contact criteria at 25 s.
The interface does not perform that recovery automatically. This is a single
case, not randomized qualification of the new release height or guard.

The subsequent guarded policy uses release Z = 0.88 m and closure 0.4. It passed
the [G2 matrix](GUARDED_RESULTS.md) on seeds 600–699. The V4 result, failed G1
qualification and all development guard rejections are retained. Next: connect
the LLM through this same interface and audit its allowed inputs and capabilities.

Evidence: [development episode and all action attempts](results/interface_v1_development.json),
[50-test log](results/interface_v1_tests.txt), and [source snapshot](results/interface_v1_source.zip).
The local replay is `runtime/humanoid/interface-development/nominal/`.

Version 2 changes the guard to start its preview from measured arm joints.
Version 1 used the commanded start pose, which can differ under load.
The version-1 schema, source archive and development results remain historical evidence.

Current validation: [53-test log](results/guarded_g2_tests.txt),
[G2 source snapshot](results/guarded_g2_source.zip), [results index](RESULTS_INDEX.md).
