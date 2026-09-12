# V4 — supported G1 mechanical qualification

Date: 2026-09-11. Acting policy: conventional exact-state controller.

**Mechanical gate passed: 96/100 strict passes; 98/100 physical task successes.**
All 100 trials reached the unchanged 25-second deadline. The predeclared gate was
at least 95 strict passes. No trial was excluded, retried, or replaced.

## Protocol and change

The [frozen V4 protocol](protocols/V4.md) reserved seeds 400–499 before execution.
Trials ran sequentially, with no concurrent rendering or controller changes.
The generated scene is byte-identical to V3: fixed pelvis, overhead ready pose,
5 × 7 × 12 cm block, fixed basket, ±1.5 cm object XY and ±0.15 rad yaw reset range.
Model assets, contact physics, 2 mm penetration limit, independent placement
criteria, and 25-second deadline are unchanged.

Instrumented replays reproduced all eight V3 failures. The four V3 penetration
peaks occurred during opening or withdrawal. The controller now estimates the
held block's offset from the grasp site and adjusts its release target toward
the basket center, with hand X capped at 0.235 m for reachability. It opens at
Z = 0.86 m, withdraws vertically to 0.975 m, then returns above the table.
The final hold is six seconds to keep total duration at 25 seconds. This offset
calculation belongs to the exact-state policy; the shared move primitive does
not silently correct targets for other policies.

All eight previous failed seeds passed as development regressions. Twelve
selected development cases passed the final release probe; these are not part
of the held-out 100-trial result. V3 achieved 92 strict passes on different seeds,
so the V3/V4 counts are descriptive, not a paired statistical comparison.

## All strict failures

| Seed | Physical task | Maximum penetration | Failure |
|---|---|---|---|
| 401 | Pass | 5.397 mm | Middle proximal finger contact during opening at 13.799 s; 1.338 N normal force at the penetration peak |
| 403 | Pass | 4.305 mm | Middle proximal finger contact during opening at 13.817 s; 8.790 N normal force at the penetration peak |
| 482 | Fail | 0.985 mm | Placement criteria not sustained at deadline; final settled dwell 0 s |
| 483 | Fail | 1.110 mm | Only 1.013 s of settled dwell at deadline; 2 s required |

Both placement failures had lifted the block and ended with basket-floor contact
and no hand contact. That alone is insufficient for success: full containment,
low velocity, withdrawal, and continuous dwell are also required. No recovery
was added after observing these qualification results.

## Evidence and reproduction

- [Complete 100-trial summary](results/mechanical_v4.json), including every failure,
  initial/final state, contact diagnostics, dependency versions, and source hashes.
- [Frozen source archive](results/mechanical_v4_source.zip), including protocol,
  generated scene, tests, and development diagnostic scripts.
- [Eight development regressions](results/v4_regressions.json).
- [Original V3 failure diagnosis](results/v3_failure_diagnosis.json),
  [release probes](results/v4_release-probes.json), and
  [centered-release probes](results/v4_centered-probes.json).
- [Automated test log](results/v4_tests.txt): **42 tests passed**, including severe
  release and settling regressions and backward-compatible episode loading.
- [Run guide](README.md) and [living checklist](PLAN.md).

All 100 trial seed IDs and source/protocol hashes were verified against the
archived configuration. The source ZIP preserves paths relative to repository
root; use it with the pinned model assets and recorded dependency versions.
Development scripts in its `development/` directory document probes; they may
require the historical V3 source and their original runtime inputs.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m humanoid_sim validate --output runtime/humanoid/v4-reproduction --seeds 100 --first-seed 400
```

Use a new output directory. Exact numerical reproduction is scoped to the
recorded dependency/platform configuration. Full trajectories and per-action
logs remain locally in `runtime/humanoid/mechanical-v4-100/`; development
regressions are in `runtime/humanoid/v4-regression/`. These ignored runtime
artifacts are not included in the source ZIP or Git. The new nominal replay and
video are in `runtime/humanoid/v4-demo/`; the earlier V3 demo is preserved.
The nominal demo passes the strict criteria. Its 751-frame, 960 × 720, 30 fps
MP4 decoded without errors; extracted lift and placement frames were inspected.

## Interpretation and next step

This qualifies a narrow supported-body conventional manipulation recipe. Two
contact-quality failures and two placement failures remain; arbitrary targets,
objects, collision-free paths, and ordinary-posture startup are not qualified.
There is no LLM, visual policy, free-standing balance, walking, or physical-robot
result yet. Phase 3 now defines and validates the shared action/observation
interface before a paused-time exact-state LLM comparison.
