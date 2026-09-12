# Humanoid VLA experiment — implementation checklist

Started: 2026-09-11. Last updated: 2026-09-12.

Robot: Unitree G1 with hands, simulated in MuJoCo.

Current phase: **Phase 5 — develop and validate RGB perception**

This is the canonical, living plan for the experiment. Use it to choose the next
work item and record progress across sessions. Keep commands in the
[run guide](README.md), measured outcomes in the [results index](RESULTS_INDEX.md), and frozen
protocols/source snapshots with each evaluation. The earlier SO101 experiment
is the starting reference: [SO101 plan](../conveyor-color-sorting/PLAN.md).

## Objective and scope

Evaluate whether a vision-capable LLM can use images, language, and the robot's
own sensor state to repeatedly choose actions that make a humanoid pick the
requested object from a table and place it in a basket.

The primary experiment measures **visual action control**: the model chooses hand
targets, orientation where supported, closure, action duration, and recovery.
A conventional controller converts those requests to actuator commands. Evaluate
calling an automatic pickup skill as a separate high-level planning condition.
Do not attribute that skill's manipulation capability to the LLM.

Start with one object, one arm, a fixed pelvis, paused decision time, and an
externally hosted vision-capable model. Progress to camera observations,
free-standing balance, continuous-time execution, and finally walking/carrying.
Model training, physical hardware deployment, dual-arm manipulation, and full
individual-finger control are outside the initial scope.

## How to maintain this checklist

- `[x]` means implemented or executed with evidence; `[ ]` means pending, partial,
  or a gate that has not passed. A completed experiment can produce a negative
  result; distinguish executing it from meeting a performance gate.
- At the end of each work session, update the current phase, relevant checkboxes,
  evidence links, next actions, and dated progress log.
- Mark a phase complete only when its exit criterion is met. Do not treat a
  successful demonstration or passing unit tests as qualification of a matrix.
- Freeze scene/controller/scorer settings, seeds, deadlines, and failure handling
  before scored trials. Record the actual source and model configuration used.
- When a configuration changes, create a new protocol/result version. Preserve
  old failures and protocols; do not revise old thresholds to change outcomes.
- Keep development and held-out evaluation separate. Once a failed seed informs
  a fix, it is a development/regression case for subsequent qualification.
- Record all evaluated episodes and model attempts, including rejected actions,
  errors, timeouts, and runtime-health failures. Document any retry policy in advance.
- Future numerical gates below are planning targets. Freeze their exact protocol
  before execution. LLM evaluation completion depends on valid measurement and
  reporting, not on the model attaining a desired success rate.

## Status at a glance

| Phase | Status | Evidence / remaining gate |
|---|---|---|
| 1. Model and supported scene | Complete | Pinned assets, scene, provenance, rendered inspection |
| 2. Physical baseline and scorer | Complete | [V4](V4_RESULTS.md): 98/100 task successes, **96/100 strict passes**; ≥95 required |
| 3. Action/observation interface | Complete for the declared recipe | [G2](GUARDED_RESULTS.md): 100/100 placements, 97/100 strict passes, zero rejections through interface v2 |
| 4. LLM with exact state | Development pilot complete | [L2](LLM_RESULTS.md): LLM 0/3 placements, 1/3 lifts; conventional 3/3 placements; formal comparison pending |
| 5. Visual action control | In progress | [RGB boundary](VISUAL.md) and freshness checks implemented; [P1 initial block estimate](POSE_RESULTS.md) passes 20/20 images within 5 mm; [P2 validity guard](PERCEPTION_RESULTS.md) implemented; [P3](CARRIED_POSE_RESULTS.md) and [P4 temporal candidate](TEMPORAL_POSE_RESULTS.md) failed their coverage/accuracy screens; [reacquisition development](TEMPORAL_REACQUISITION_DEVELOPMENT.md) integrated; qualified carried pose, comparator and visual model runner pending |
| 6. Free-standing manipulation | Not started | Balance controller and mechanical requalification |
| 7. Continuous-time execution | Not started | Independent physics/control loop and latency measurement |
| 8. Robustness and recovery | Not started | Frozen challenge sets and recovery evaluation |
| 9. Formal comparison | Not started | Held-out matched benchmark and uncertainty analysis |
| 10. Walking and carrying | Later extension | Qualified locomotion plus manipulation integration |
| 11. Final report and reproducibility | Ongoing | Final comparative report, artifacts, limitations |

## Next actions

- [x] Integrate reviewed AGY task 001: 17/20 development targets accepted, 16 within 20 mm; seed 820 still fails accuracy.
- [ ] Execute [AGY task 002](../../coordination/agy/tasks/002-reacquisition-evidence.md): compare additional fresh-view evidence before any P5 validation.

- [x] Inspect exact-state failures and audit the hand-site/grasp geometry contract; see [grasp audit](GRASP_AUDIT.md).
- [ ] Keep any recipe-assisted prompting as a separately declared condition.
- [x] Implement timestamped camera observations paired with robot-state-only inputs; see [visual boundary](VISUAL.md).
- [x] Test that the visual observation payload excludes object truth and private scoring; model-runner access remains to be audited when connected.
- [x] Validate initial upright block position from RGB and declared priors: [P1](POSE_RESULTS.md), 20/20 fresh images within 5 mm.
- [x] Audit RGB visibility across manipulation endpoints and expire the table-support prior after interaction; see [P2](PERCEPTION_RESULTS.md).
- [x] Implement and evaluate a monocular carried-center candidate on fresh trajectories and sensor corruptions; [P3](CARRIED_POSE_RESULTS.md) failed and remains disabled.
- [ ] Add explicit reacquisition after model mismatch/loss and evaluate fresh motion evidence on new trajectories, counting added actions against the task budget. Implementation and development complete via [AGY task 001](../../coordination/agy/tasks/001-reacquisition.md); see [development report](TEMPORAL_REACQUISITION_DEVELOPMENT.md) and proposed protocol [P5](protocols/P5_PROPOSAL.md); task 001 is accepted for development-only integration, and task 002 precedes any fresh validation.
- [ ] Validate carried-object pose and occlusion handling without private truth inputs.
- [ ] Build a matched conventional vision comparator and freeze larger evaluations on unused seeds.

The live exact-state L2 development pilot is complete: **LLM 0/3 placements,
1/3 sustained lifts; conventional 3/3 placements and 2/3 strict passes**.
All 18 L2 API calls completed. L1's three request-schema errors remain separately
archived. See [pilot results](LLM_RESULTS.md) and the [runner guide](LLM_RUNNER.md).
All 106 automated tests pass. These three cases do not establish a general model
comparison; no visual policy, balance controller or walking policy has been evaluated.

## Phase 1 — Select the robot and build the supported scene

- [x] Vendor G1 assets at a pinned MuJoCo Menagerie revision.
- [x] Retain the upstream license and verify downloaded asset hashes.
- [x] Keep upstream robot XML/meshes unchanged; generate a separate task scene.
- [x] Create a fixed-pelvis humanoid, table, free block, and static basket.
- [x] Add the right-hand grasp site and a scene camera configuration.
- [x] Include a head camera in the model for later observation work.
- [x] Document contact settings, force/gain overrides, and the supported-body assumption.
- [x] Establish reproducible nominal and randomized resets.
- [x] Initialize the arm in an overhead ready pose without attaching the object.
- [x] Verify loading, stepping, and rendered appearance.

**Exit criterion:** the scene loads, steps, renders, and initializes repeatably;
asset provenance and all task-specific changes are documented. **Met.**

Evidence: [model provenance](../../models/g1/SOURCE.md),
[scene generator](../../humanoid_sim/scene.py),
[generated scene](../../scenes/g1_pick_place.xml).

## Phase 2 — Establish physical pickup and basket placement

- [x] Implement IK, smooth actuator motion, and coordinated hand closure.
- [x] Build an exact-state conventional approach/grasp/lift/transport/release recipe.
- [x] Use gravity and contact physics throughout actions; no object teleportation
  after reset and no grasp weld/attachment.
- [x] Implement action-independent lift, containment, support, release, withdrawal,
  settling, and revoked-arrival scoring.
- [x] Track maximum object penetration and keep it separate from task success.
- [x] Save complete integration state, sampled trajectories, actions, and scorer state.
- [x] Test pickup/placement, release under gravity, invalid actions, persistence,
  dwell requirements, and revoked success.
- [x] Execute and retain all four 100-trial development/qualification matrices.
- [x] Record and inspect a successful nominal demonstration; decode the exported MP4.
- [x] Diagnose V3 release/withdrawal failures and pass all eight development regressions.
- [x] Freeze and execute a new qualification matrix on unused seeds.
- [x] Achieve at least **95/100 strict successes** with no selectively excluded trials.
- [x] Publish the qualifying controller, workspace limits, results, and reproducible commands.

**Exit criterion:** ≥95/100 strict successes under a frozen mechanical protocol.
**Met:** V4 achieved 98/100 task successes and 96/100 strict passes on seeds 400–499.
Scene, physics, 2 mm penetration limit, and 25-second deadline are unchanged from V3.

Evidence: [V4 results and all failure seeds](V4_RESULTS.md), [frozen protocol](protocols/V4.md),
[baseline](../../humanoid_sim/baseline.py), [scorer](../../humanoid_sim/scoring.py),
[tests](../../tests/test_humanoid.py). The historical V3 protocol appears below.

## Phase 3 — Define the shared action and observation interface

This interface must make ownership of each decision clear. The Phase 2 mechanical gate is met; complete this interface before scored LLM trials.

- [x] Expose persistent `reset`, `observe`, `move`, `hand`, and `hold` commands.
- [x] Define world-frame metres and bounded action durations/hand closure.
- [x] Reject invalid and unreachable requests before advancing physics.
- [x] Protect completed baseline episodes against command-based modification.
- [x] Save/reload integration state and reject mismatched scene hashes.
- [x] Add hand orientation control with an explicit representation and frame convention.
- [x] Expose joint positions/velocities, hand pose, declared contact sensors,
  observation timestamps, and action execution status through a documented schema.
- [x] Define exactly which conversions the low-level controller performs and which
  approach, grasp, release, and recovery choices belong to the acting policy.
- [x] Implement a sampled arm-path collision safeguard and report rejected actions.
  Finger motion and carried-object dynamics are outside this check; see [limitations](INTERFACE.md).
- [x] Version the action/observation contract and fixed instruction revision; validate finite values,
  joint/workspace constraints, and malformed requests.
- [ ] Validate a clear transition from an ordinary parked posture to the working
  area if that transition is included in later episodes. The current ready pose is a reset assumption.
- [x] Qualify the conventional recipe through the public primitives reserved for
  LLM use; the primary interface has no automatic `pick_and_place` tool.

**Exit criterion:** a documented, replayable interface with tested validation,
clear controller responsibilities, and a shared set of capabilities for both policies.
**Met for the declared supported recipe.** Audit actual LLM-runner access in Phase 4.

Contract and development checks: [interface specification](INTERFACE.md),
[action schema](schemas/action-v2.schema.json), [tests](../../tests/test_humanoid_interface.py).
[G2 qualification](GUARDED_RESULTS.md) passed through the shared interface.
The LLM runner must enforce the same capabilities in Phase 4; instruction changes
remain Phase 7 work.

## Phase 4 — Run the LLM with exact simulator state

- [x] Select and record model identifiers/configuration for the initial comparison.
- [x] Adapt or build an automatic model runner with structured action responses.
- [x] Record instructions, supplied observations, prompt/schema versions, raw responses,
  provider-returned model identity, request IDs, token usage, and cost where available.
- [x] Freeze call/action limits, timeouts, error handling, and a per-run cost budget.
- [x] Keep simulation paused during model decision time for this condition.
- [x] Give the LLM object/basket state and robot state through the declared exact-state interface.
- [x] Let the model choose and revise approach, grasp, lift, transport, release, and withdrawal actions.
- [x] Preserve action history and execution feedback so decisions can be closed-loop.
- [x] Audit that the LLM runner exposes only the same shared-interface capabilities.
- [x] Evaluate conventional and LLM policies on matched initial states and limits.
- [ ] Separate target/sequence mistakes, unreachable requests, tracking errors,
  grasp failures, placement failures, and API/tool errors.
- [x] Publish measured success, failure breakdown, action counts, and representative replays.

**Exit criterion:** reproducible matched exact-state trials with complete logs and
independent scoring. This measures sequencing/control with supplied object state;
it does not establish vision capability or real-time performance. **Met for the three-case development pilot.**
See [L2 results](LLM_RESULTS.md), [frozen protocol](protocols/L2.md) and
[runner tests](../../tests/test_humanoid_llm.py). Larger confirmatory comparisons
and comprehensive failure taxonomy remain pending.

## Phase 5 — Replace object truth with visual observations

- [ ] Implement repeated, timestamped image observations through the model runner.
- [x] Start with a calibrated fixed camera; verify reset coverage/calibration on five development cases.
- [ ] Extend coverage and calibration checks through manipulation and occlusion.
- [x] Expose proprioception and declared sensor readings separately from object truth.
- [ ] Remove ground-truth object positions, identity labels, scorer flags, private
  reports, and other oracle data from the acting policy's accessible inputs.
- [x] Add tests that verify public observation isolation and stale-image handling.
- [x] Validate initial table-supported block position using RGB, calibration and declared geometry priors; [P1 results](POSE_RESULTS.md).
- [x] Implement explicit pose unavailability after the initial support prior expires; validate visibility and prior lifetime across 20 exact-state-driven trajectories ([P2](PERCEPTION_RESULTS.md)).
- [x] Evaluate an experimental carried-center candidate: [P3](CARRIED_POSE_RESULTS.md), 18/40 original frames within 20 mm; screen failed.
- [x] Test temporal rigid-transform consistency and loss handling on 10 new episodes; [P4](TEMPORAL_POSE_RESULTS.md) failed coverage, remains disconnected from control.
- [ ] Extend pose estimation to carried, tilted and occluded blocks.
- [ ] Implement a conventional camera-based perception comparator using equivalent sensor inputs.
- [x] Declare the current observation as RGB-only; RGB-plus-depth remains a separate future condition. Do not supply
  perfect depth or object pose under an RGB-only label.
- [ ] Execute repeated image → action → fresh image control for full task episodes.
- [ ] Compare conventional exact state, LLM exact state, conventional vision, and LLM vision.
- [ ] Validate the head camera and repeat the visual condition from the robot's viewpoint.
- [ ] Measure perception errors post hoc using private truth, without feeding it back to the policy.
- [ ] Report camera/calibration assumptions, perception failures, and physical outcomes separately.

**Exit criterion:** a reproducible visual manipulation comparison with audited
observation isolation and a matched conventional vision baseline. Its conclusion
can be positive or negative; image correctness alone is not task success.

## Phase 6 — Remove body support and add free-standing balance

- [ ] Create a separate free-floating configuration; retain the supported version for comparison.
- [ ] Integrate or implement a continuously operating balance controller below the LLM.
- [ ] Define fall, torso stability, foot-contact, unintended-step, and collision metrics.
- [ ] Validate standing without manipulation for a proposed 60 seconds.
- [ ] Validate empty-hand reaching, then lifting, transport, release, and withdrawal.
- [ ] Measure grasp disturbance and stability changes caused by the carried object.
- [ ] Requalify the conventional controller in a declared workspace before LLM comparisons.
- [ ] Meet the proposed free-standing gate: ≥95/100 complete tasks with **zero falls**,
  using a frozen stability/contact-quality protocol.
- [ ] Repeat matched exact-state and visual LLM conditions on the qualified standing controller.
- [ ] Report supported-body and free-standing results separately.

**Exit criterion:** stable conventional free-standing manipulation under the frozen
mechanical gate, followed by valid matched LLM measurements. IK alone is not a balance controller.

## Phase 7 — Keep physics running while the LLM thinks

- [ ] Run physics, balance, and actuator tracking independently of model/tool calls.
- [ ] Timestamp capture, dispatch, response receipt, parsing, command submission,
  execution start, and completion using defined clocks.
- [ ] Limit outstanding action sequences and prevent overlapping writers/reservations.
- [ ] Reject expired observations/actions and record every expiry or cancellation.
- [ ] Define stable holding behavior on model timeout, malformed output, or interrupted control.
- [ ] Implement instruction versions and declare safe action commitment/cancellation semantics.
- [ ] Measure runtime headroom; freeze acceptable lag/control-deadline criteria before scoring.
- [ ] Run one scored simulation at a time on the current host and render videos afterward.
- [ ] Compare paused-time and continuous-time trials under matched task conditions.
- [ ] Report end-to-end latency separately from provider inference timing when available.
- [ ] Evaluate latency stress and record the practical operating limits, including failures.

**Exit criterion:** independent real-time control with tested timeout/expiry behavior
and trustworthy timing measurements. Retain unhealthy runs and predeclare their
analysis; slow simulation must not silently give the model extra decision time.

## Phase 8 — Challenge robustness, instructions, and recovery

- [ ] Randomize object and basket locations within declared reach limits.
- [ ] Vary object size, shape, orientation, and mass in separately declared conditions.
- [ ] Add multiple objects and target selection by color, position, and simple relations.
- [ ] Test instruction paraphrases and counting/multi-object requests.
- [ ] Vary lighting, background, camera pose, and partial occlusion one factor at a time.
- [ ] Test a missed grasp, a slipped object, and scene changes requiring a fresh observation.
- [ ] Define which recovery attempts are allowed within an episode, their cost/deadline,
  and when an episode is terminated. Preserve unsuccessful recoveries.
- [ ] Test instruction changes with a predeclared commitment boundary for ongoing actions.
- [ ] Add wrong-object, unintended-contact, recovery, and rule-version outcomes to scoring.
- [ ] State the conventional parser's supported grammar; separate unsupported language
  from perception and mechanical failure.
- [ ] Freeze development and held-out challenge sets and publish per-condition outcomes.

**Exit criterion:** documented challenge sets, validated scoring, and complete
comparisons that distinguish instruction following, perception, recovery, and execution.

## Phase 9 — Run the formal LLM/VLA comparison

- [ ] Freeze the research questions, hypotheses, primary endpoint, and meaningful effect size.
- [ ] Define full task success within a fixed deadline as the primary endpoint,
  with explicitly declared runtime/contact/stability validity requirements.
- [ ] Freeze prompts, model configuration, controller/scorer versions, sensor inputs,
  supported body mode, runtime mode, retry policy, and concurrency.
- [ ] Reserve unseen seeds and instruction variants; separate development and acting
  evaluation sessions so the policy cannot inspect prior decisions or private reports.
- [ ] Counterbalance object/target positions and match initial states across policies.
- [ ] Size the experiment using pilot variability and the desired detectable difference;
  approximately 100 episodes per main condition is a starting proposal, not a power analysis.
- [ ] Run the four primary conditions with equivalent motion capabilities:
  conventional exact state, LLM exact state, conventional vision, and LLM vision.
- [ ] Evaluate high-level skill calling as a separate ablation with its extra capability disclosed.
- [ ] Retain every episode and API/runtime failure; do not selectively rerun failed cases.
- [ ] Report task, grasp, and placement success; wrong-object rate; drops, falls,
  contact violations, recovery, completion time, action/model-call counts, latency,
  total cost, and cost per successful episode.
- [ ] Compute uncertainty and matched comparisons at the episode level; account for
  clustered objects and repeated conditions instead of treating them as independent trials.
- [ ] Analyze failure categories and runtime-health sensitivity without dropping them from the main accounting.
- [ ] State what the results establish about the LLM versus the conventional controller,
  including negative or inconclusive findings and limits of simulation-only evidence.

**Exit criterion:** a complete, reproducible comparative report with frozen methods,
all outcomes accounted for, uncertainty estimates, and conclusions supported by the data.

## Phase 10 — Extend to walking and carrying

This is a separate extension after stationary free-standing manipulation qualifies.

- [ ] Select/integrate and independently validate a locomotion controller.
- [ ] Move the object or basket outside the standing manipulation workspace.
- [ ] Implement walk → stop → pick → walk while holding → stop → place transitions.
- [ ] Validate stopping/stance alignment and safe handover between locomotion and manipulation.
- [ ] Measure object retention, balance disturbance, collisions, falls, and destination accuracy.
- [ ] Qualify a conventional walk-and-carry baseline before introducing LLM decisions.
- [ ] Let the LLM select destinations and manipulation actions while the gait controller stabilizes walking.
- [ ] Repeat matched evaluation with explicit travel distance, payload, and terrain limits.
- [ ] Publish walking/carrying results separately from stationary manipulation.

**Exit criterion:** a qualified locomotion/manipulation integration and complete
matched evaluation. Do not generalize a stationary pickup result to mobile humanoid control.

## Phase 11 — Maintain reproducibility and publish the final reference

- [x] Maintain this plan, the command guide, and versioned mechanical results.
- [x] Retain model provenance/license/checksums and source snapshots for executed matrices.
- [x] Retain all 600 mechanical matrix outcomes, including failed qualifications.
- [x] Save and inspect a labeled supported-body demonstration video.
- [x] Create a [results index](RESULTS_INDEX.md); extend it as model, camera, body-support and runtime conditions are added.
- [ ] Package the frozen benchmark manifests and commands for independent reproduction.
- [ ] Document artifact storage/retrieval; runtime trajectories and videos currently remain
  local under ignored `runtime/`, while summary reports and source archives are versioned.
- [ ] Include representative success and failure videos labeled with the actual acting policy and body support.
- [ ] Audit source/model/scorer versions, seed accounting, API usage, costs, and all exclusions/retries.
- [ ] Publish the final report answering the research question, including unresolved limits and next experiments.

**Exit criterion:** another contributor can reproduce the declared conditions and
trace every reported result to its configuration, observations, actions, and scored outcome.

## Progress log

| Date | Work completed | Outcome / next action |
|---|---|---|
| 2026-09-11 | G1 scene, physical baseline, scorer, persistent primitives, replay/video, tests | Implemented; 40 tests passed |
| 2026-09-11 | Three 100-trial mechanical matrices with retained source/results | V3: 96 task successes, 92 strict passes; gate still open |
| 2026-09-11 | Expanded the complete experiment plan into this checklist | Next: diagnose V3 contact and settling failures, then requalify on unused seeds |
| 2026-09-11 | Offset-aware release, vertical withdrawal, per-action score/contact telemetry; 42 tests passed | [V4](V4_RESULTS.md): 98 task successes, 96 strict passes; Phase 2 complete, next Phase 3 |
| 2026-09-11 | Versioned policy interface, quaternion control, robot observations, sampled collision guard and persistent attempt logs; 50 tests passed | [Interface](INTERFACE.md): nominal explicit higher release passes; next qualify the guarded policy |
| 2026-09-11 | Guard v2, partial release, four retained development probes; 53 tests passed; two full guarded matrices | [G1](GUARDED_RESULTS.md): 85 strict passes, failed; G2: 97 strict passes, qualified; next Phase 4 LLM runner |
| 2026-09-12 | Live exact-state runner, schema fix, matched three-case L2 pilot; 61 tests passed | [Results](LLM_RESULTS.md): LLM 0/3 placements, 1/3 lifts; conventional 3/3 placements; next observation isolation and vision |
| 2026-09-12 | Grasp audit, RGB/robot observation boundary, stale-frame rejection, fixed/head captures; 67 tests passed | [Visual checks](VISUAL.md): five calibration/state checks pass; centroid pose error up to 3 cm, head view cropped; no visual policy evaluated |
| 2026-09-12 | Frozen P1 initial RGB estimator tested on 20 fresh reset images; 70 tests passed | [P1](POSE_RESULTS.md): 20/20 within 5 mm; mean 0.518 mm, maximum 2.418 mm; carried-object perception and full visual control remain pending |
| 2026-09-12 | Added RGB visibility tracking and explicit expiry of the initial table-support prior; 75 tests passed | [P2 audit](PERCEPTION_RESULTS.md) covers action endpoints in 20 exact-state-driven episodes; no carried 3D pose or visual control claimed |
| 2026-09-12 | Implemented experimental monocular cuboid center fitting; 79 tests passed | [P3](CARRIED_POSE_RESULTS.md): 18/40 originals within 20 mm; one accepted error in originals and one in partial occlusion; failed screen, no control integration |
| 2026-09-12 | Added temporal RGB/hand-motion candidate and post-audit metadata hardening; current suite 84 tests | [P4](TEMPORAL_POSE_RESULTS.md): 14/20 post-warmup targets, mean 3.645 mm / max 7.420 mm; 16/20 coverage gate failed; release and corrupted transport views withheld |
| 2026-09-12 | Implemented temporal reacquisition candidate, verified input hardening, evaluated on seeds 820–829; 93 tests passed | [Development report](TEMPORAL_REACQUISITION_DEVELOPMENT.md): post-warmup coverage 17/20 accepted, 16/20 within 20 mm; seed 820 depth error 21.94 mm; proposed [P5](protocols/P5_PROPOSAL.md); disconnected from control |
| 2026-09-12 | Accepted AGY task 001 after three reviews; 106 tests independently passed | [Acceptance](../../coordination/agy/reviews/001-acceptance.md): evaluator failures retain accounting; known 21.94 mm error remains; task 002 ready, no fresh P5 run |

Add a dated row for each meaningful implementation, protocol freeze, evaluation,
or change of direction. Link new result files in the row and relevant phase.

## Historical reference — frozen V3 mechanical protocol

The following records the protocol actually used for seeds 300–399. Keep it
unchanged when planning later revisions; add a separately versioned protocol.
Its thresholds must not be retroactively changed to make V3 pass.


- One G1 with fixed pelvis, one right hand, one free red block, one static basket.
- Robot arm begins in an IK-generated overhead ready pose. This is an initialization
  assumption, not a demonstrated transition from the standard standing posture.
- Block dimensions: 5 × 7 × 12 cm, mass: 60 g. Table top: 0.70 m.
- Nominal block center XY: (0.24, −0.18) m. Independently randomize X and Y by
  ±1.5 cm and yaw by ±0.15 rad using NumPy's seeded generator.
- Basket center XY: (0.18, −0.36) m. Interior: 17 × 17 cm. Floor top:
  0.712 m. Rim top: 0.84 m. Basket location is fixed in this milestone.
- Development seeds: 0–19, plus the two failed mechanical matrices (100–199 and 200–299).
  Revised mechanical validation seeds: 300–399. No policy modifications or
  selective retries within any 100-trial matrix. Earlier runs are retained
  in `results/mechanical_v1.json` and `results/mechanical_v2.json` with source archives.
  The wider block is a task-design change, so the revisions are not a controlled
  comparison on identical task geometry.
- Exact-state controller: use a +1.5 cm world-X hand-site offset to keep the palm
  clear of the block, align above object, descend, close, lift, hold 0.5 s,
  carry at hand-site Z = 0.975 m, transport to (0.19, −0.36) m, lower to
  Z = 0.86 m, open, retract, hold 8 s. All movement/hand actions
  use 2 s. Normal completed duration: 25 simulated seconds including reset settling.
- Physics: 1 ms timestep, implicitfast, 50 iterations. Contact and hand overrides
  are documented in `models/g1/SOURCE.md`; object state is only set at reset.
- Each trial runs sequentially, faster than real time. No LLM, no walking, no
  balance controller, and no concurrent video rendering during the matrix.

## Independent scoring

Scoring receives actual physics state and contacts, never action intentions.

A sustained lift requires the object's lowest point to exceed the table by 4 cm
while touching the right hand for at least 0.2 s. After that, success requires:

- The object's full world-axis bounding box inside the basket interior, including
  its top below the rim; allow 0.5 mm contact penetration tolerance.
- Direct contact with the basket floor and no right-hand contact.
- Linear speed below 2 cm/s and angular speed below 0.15 rad/s.
- Grasp site at least 12 cm from the object's center.
- All placement conditions sustained for 2 s; revoke arrival if they cease.

A gate success additionally requires no controller exception and maximum object
contact penetration at most 2 mm over the entire episode. The gate requires
95/100 or more such successes. Individual failures, early stops, and quality
failures remain in the denominator. This is a narrow mechanical development gate,
not a formal LLM benchmark or a physical-robot validation.
