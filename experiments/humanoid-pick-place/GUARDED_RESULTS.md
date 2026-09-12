# Guarded-controller qualification results

Date: 2026-09-11. **G2 gate passed: 97/100 strict passes, 100/100 physical successes, zero guard rejections.**

G1 remains a failed qualification: 85/100 strict passes and 99/100 physical successes.

## What changed

The conventional policy now issues only versioned `move`, `hand`, and `hold`
requests through the shared exact-state interface. It has no scorer access through
its policy argument. A separate evaluator reads physics outcomes and records
all attempts, rejections, errors, dependency versions and source hashes.

The guard uses measured arm joints as the start of its sampled path. Under load,
commanded targets can differ from the actual pose; version 1 could predict
collisions at a starting configuration that the physical robot did not occupy.
Version 2 still rejects sampled intersections and remains a kinematic approximation.
It does not predict finger flexion, carried-object collisions or dynamic tracking.

The policy releases at 0.90 m with closure 0.4, keeping the fingers partly curled
while the block drops. It then withdraws vertically and parks. This is an explicit
policy choice through the same action contract available to a future LLM.
The scene, actuator physics, task scorer, 2 mm object-contact penetration threshold
and 25-second deadline remain unchanged. The original V4 and interface-v1 artifacts
are preserved; those outcomes belong to their archived configurations.

## Development evidence

All three probes used the same 20 randomized development seeds:
0, 300, 312, 352, 357, 358, 365, 373, 393, 401, 403, 482, 483,
301, 302, 303, 304, 305, 306, 307.

| Probe | Guard | Release Z / closure | Physical successes | Strict passes |
|---|---|---|---|---|
| 01 | Version 1, commanded start | 0.90 m / 0 | 15/20 | 11/20 |
| 02 | Version 2, measured start | 0.88 m / 0 | 14/20 | 11/20 |
| 03 | Version 2, measured start | 0.90 m / 0.4 | 20/20 | 19/20 |

Probe 03 had no rejected actions. Seed 401 still exceeded the object penetration
limit (5.354 mm) during finger opening and remains a failed development case.
These selected, repeatedly used cases are not held-out performance estimates.

- Probe 01: [outcomes](results/guarded_development_01.json), [source](results/guarded_development_01_source.zip).
- Probe 02: [outcomes](results/guarded_development_02.json), [source](results/guarded_development_02_source.zip).
- Probe 03: [outcomes](results/guarded_development_03.json), [source](results/guarded_development_03_source.zip).

## Frozen qualification

[Protocol G1](protocols/G1.md) reserves seeds **500–599** before execution. The
100 trials run sequentially, without concurrent physics tests or rendering.
Any rejection or execution error terminates the trial and counts as failure;
there are no automatic retries, recovery actions, seed replacements or exclusions.
The gate requires at least **95/100 strict passes**. Every trial checks the frozen
configuration; an incomplete matrix cannot pass.

[Source snapshot](results/guarded_g1_source.zip) contains the frozen policy,
interface, evaluator, schemas, protocols, generated scene and regression tests.
The robot assets remain at their pinned revision in the repository.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m humanoid_sim.guarded_evaluation --output runtime/humanoid/guarded-g1-reproduction --count 100 --first-seed 500
```

Use a new output directory. Full trajectories and all action attempts are retained
locally in `runtime/humanoid/guarded-g1-100/`. Runtime directories are ignored by
Git; summary outcomes and source archives are retained in this experiment folder.
Development trajectories are in `runtime/humanoid/guarded-development-01/`, `-02/`
and `-03/`. Exact numerical reproduction is scoped to the recorded dependencies
and platform. V4 comparisons use different seeds and different policy/interface
configurations; they are not a paired benchmark.

## Validation and limits

**52 automated tests passed.** Additional evaluator smoke checks verified a
complete successful physical trial and matching saved report, that a one-trial
run cannot pass the gate, and that existing directories or changed configuration
are rejected. Tests also verify the policy works through an object exposing only
`observe` and `execute`, and stops after a rejection without hidden retries.

This remains a fixed-pelvis, exact-state, paused-time conventional controller.
No LLM, vision, free-standing balance, walking, hardware execution, or arbitrary
orientation/workspace capability has been measured.

## G1 held-out outcome

[All 100 outcomes](results/guarded_g1.json) are retained. Every trial reached 25 s.
All 100 source/protocol/schema hashes matched the frozen configuration.
All failures below remain in the denominator; placement and contact quality are separate criteria.

| Seed | Physical task | Penetration (mm) | Contact body at peak |
|---|---|---|---|
| 506 | Pass | 2.221 | basket |
| 523 | Pass | 2.141 | basket |
| 537 | Pass | 5.209 | right_hand_middle_1_link |
| 541 | Pass | 2.185 | basket |
| 550 | Pass | 2.068 | basket |
| 553 | Pass | 2.221 | basket |
| 556 | Pass | 3.832 | right_hand_middle_1_link |
| 567 | Pass | 2.001 | basket |
| 569 | Pass | 2.505 | basket |
| 571 | Pass | 2.027 | basket |
| 573 | Pass | 2.217 | basket |
| 576 | Fail | 1.238 | basket |
| 579 | Pass | 2.533 | right_hand_middle_1_link |
| 582 | Pass | 2.121 | basket |
| 588 | Pass | 4.176 | right_hand_middle_1_link |

The next development probe lowered release to 0.88 m while retaining closure 0.4.
Qualification seeds 500–599 are now development-only for subsequent tuning.

## G2 development and frozen qualification

Probe 04 used all 20 earlier development seeds plus every G1 strict failure.
All 35 placements succeeded; 29 passed the strict criteria with no rejections.
The six retained quality failures were seeds 401, 304, 537, 556, 579 and 588.
Five involved the middle finger; seed 304 involved the basket floor. This
selection deliberately includes known failures and is not an unbiased estimate.

[Probe outcomes](results/guarded_development_04.json) and
[source](results/guarded_development_04_source.zip) preserve all cases.
The [G2 protocol](protocols/G2.md) freezes release at 0.88 m and closure 0.4 on
new seeds **600–699**, retaining the same physics, guard and scoring thresholds.
The evaluator now requires the exact declared seed range and 100-trial count for
a qualification pass; other ranges/counts are diagnostics.

**G2 complete: 97/100 strict passes and 100/100 physical successes.** All 100 trials
reached 25 s, executed 11 actions, and had zero rejections or policy/runtime errors.
Every seed and source/protocol/schema hash matched the frozen configuration.
[All 100 outcomes](results/guarded_g2.json) are retained, including the three
quality failures below.

[Source snapshot](results/guarded_g2_source.zip) and
[53-test log](results/guarded_g2_tests.txt) are retained. The new evaluator test
verifies a real G2 development episode, report accounting, a diagnostic run's
ineligibility for qualification, overwrite protection and configuration freezing.

```sh
.venv/bin/python -m humanoid_sim.guarded_evaluation --output runtime/humanoid/guarded-g2-reproduction --protocol g2 --count 100 --first-seed 600
```

G2 runtime trajectories are in `runtime/humanoid/guarded-g2-100/` and its development
probe is in `runtime/humanoid/guarded-development-04/`. The G1 source archive
preserves the exact original evaluator; the current evaluator also exposes the
G1 motion configuration using `--protocol g1`.

## G2 retained failures and interpretation

| Seed | Physical task | Maximum penetration | Contact body at peak |
|---|---|---|---|
| 647 | Pass | 3.587 mm | right_hand_middle_1_link |
| 656 | Pass | 2.086 mm | basket |
| 682 | Pass | 2.878 mm | right_hand_middle_1_link |

The gate qualifies this narrow conventional recipe through the shared interface.
It does not establish arbitrary-target or arbitrary-orientation reliability. The
three contact-quality failures remain unresolved; the gate allows up to five
strict failures, so no exclusions or scoring changes were needed to pass.
The original G1 failure remains part of the experiment record.

Phase 4 can now implement the paused-time exact-state LLM runner using the same
interface. A matched comparison must freeze its own model, prompts, action limits,
budgets and unused seeds. No model has been connected or evaluated yet.

A qualified replay from seed 600 is saved locally as
`runtime/humanoid/guarded-g2-100/seed-0600/pick_place.mp4`.
The 751-frame, 960 × 720, 30 fps video decoded without errors; extracted lift and
placement frames were inspected. The overlay identifies fixed pelvis,
conventional controller and no LLM. Full episode state and attempts remain beside it.
