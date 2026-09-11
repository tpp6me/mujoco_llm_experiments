# Supported G1 mechanical results

Date: 2026-09-11. **Mechanical qualification gate remains open. No LLM trials have run.**

The current implementation performs contact-based pickup and basket placement
with the right hand of a fixed-pelvis G1. The final 100-trial matrix completed
96 tasks; 92 also passed the contact-quality requirement. This is below the
predeclared 95/100 strict gate. The successful nominal demonstration is useful
for inspecting the implementation, but does not establish qualified reliability.

## Current configuration and result

The free block is 5 × 7 × 12 cm and 60 g. Trials randomize its X/Y position by
±1.5 cm and yaw by ±0.15 rad. The basket and robot remain fixed. The robot starts
with its arm in an overhead ready pose. Physics advances during actions and is
not synchronized to wall time. No LLM, vision policy, balance policy, or walking
controller participates.

| Metric | Final matrix, seeds 300–399 |
|---|---:|
| Episodes | 100 |
| Sustained physical lifts | 100/100 |
| Full task successes, including placement dwell | 96/100 |
| Maximum-penetration quality passes | 96/100 |
| Strict successes satisfying both | 92/100 |
| Required strict successes | ≥95/100 |
| Worst object contact penetration | 15.378 mm |
| Normal episode deadline | 25 simulated seconds |
| Automated tests | 40 passed |

The scorer requires actual lift contact, full bounding-box containment below the
basket rim, floor support, no right-hand contact, low linear/angular velocity,
a withdrawn hand, and two seconds of sustained settling. It revokes arrival
when those conditions cease. Strict success also requires maximum object contact
penetration ≤2 mm. See the [frozen protocol](PLAN.md).

The four placement failures ended with the block contacting the basket floor,
but had not accumulated two seconds of qualifying dwell by the deadline. The
other four failed gates completed placement but exceeded the contact tolerance.
No failed seed was retried or removed from the final matrix.

| Seed | Gate failure |
|---|---|
| 300 | Placement dwell 0.744 s at deadline; 2 s required |
| 312 | Maximum object penetration 2.816 mm; 2 mm permitted |
| 352 | Maximum object penetration 15.378 mm; 2 mm permitted |
| 357 | Placement dwell 1.701 s at deadline; 2 s required |
| 358 | Placement dwell 1.274 s at deadline; 2 s required |
| 365 | Maximum object penetration 6.551 mm; 2 mm permitted |
| 373 | Maximum object penetration 2.751 mm; 2 mm permitted |
| 393 | Placement dwell 0.865 s at deadline; 2 s required |

## Development history retained

| Revision | Seeds | Block dimensions | Task successes | Strict successes | Worst penetration |
|---|---|---|---:|---:|---:|
| V1 | 100–199 | 5 × 5 × 12 cm | 93/100 | 89/100 | 31.389 mm |
| V2 | 200–299 | 5 × 5 × 12 cm | 80/100 | 79/100 | 29.415 mm |
| V3, current | 300–399 | 5 × 7 × 12 cm | 96/100 | 92/100 | 15.378 mm |

V1 exposed unstable thumb contacts and missed grasps. V2 reduced right-hand
joint torque limits from ±0.35 to ±0.15 Nm and added 1.5 cm of palm clearance;
this did not qualify the narrow object. V3 widened the object across the two
fingers, increased carry height to 0.975 m, shifted the basket approach toward
its center, and lowered the release pose to 0.86 m. The task geometry and seed
sets changed between revisions, so this table is development history, not a
controlled comparison of controller efficacy or LLM models.

All 300 matrix outcomes are retained in [V1](results/mechanical_v1.json),
[V2](results/mechanical_v2.json), and [V3](results/mechanical_v3.json). Each revision
also has a source ZIP in `results/`, including its generated scene and protocol.
Raw trajectories remain under `runtime/humanoid/mechanical-100`,
`runtime/humanoid/mechanical-v2-100`, and `runtime/humanoid/mechanical-v3-100`.
Development force, offset, width, and final-clearance probes are retained as
separate JSON files. They were used for tuning and are not held-out results.
Every final trial's source hashes were verified against the current implementation.

## Inspect the demonstration

```sh
.venv/bin/mjpython -m humanoid_sim view
```

The successful nominal episode is in `runtime/humanoid/demo/`. Its MP4 and
snapshots are generated after the scored runs, without advancing saved physics.
The 25.03-second, 960 × 720, 30 fps MP4 passed full FFmpeg decoding and visual
inspection of an encoded lift frame and the saved lift/final snapshots. The video
explicitly labels the fixed pelvis, conventional controller, and absence of an LLM. See the [command guide](README.md) for new episodes and primitive actions.

## Remaining work before LLM comparison

Investigate the transient finger/object penetrations in seeds 312, 352, 365,
and 373; validate the hand contact model and commanded closure under those poses.
Improve controlled release so settling completes within the declared deadline.
Keep the current failures as regression/development cases, then freeze another
configuration and qualify it on new seeds. Do not relax the existing gate or
retroactively extend the deadlines to turn these runs into passes.

Once qualified, add the exact-state LLM runner through the same primitive action
interface, followed by isolated visual observations. Free-standing balance and
walking remain separate later milestones. Results here do not measure LLM/VLA
performance or physical G1 performance.
