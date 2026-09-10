# SO101 conveyor color-sorting experiment

Date: 2026-09-09
Status: Phases 1–5 complete. Phase 6 development evaluation complete; larger formal benchmark remains outstanding (2026-09-09).

Phase 1 evidence: [results and validation notes](PHASE1_RESULTS.md).
Usage: [conveyor guide](README.md).

## Objective

Evaluate whether an LLM can follow a declared sorting instruction, select the
correct moving cubes, and direct the SO101 to reject them reliably.

Example instruction: **“Reject red cubes; let the others pass.”**

Codex will operate the simulation through tools. MuJoCo runs on the existing
M1 Pro MacBook with 16 GB RAM; no local LLM or model training is required.

A fixed-color sorter is straightforward to implement conventionally. Successful
sorting alone demonstrates task completion. Evidence of LLM value should come
from comparison with conventional methods, especially when instructions change.

## Proposed scene

- SO101 mounted beside a narrow conveyor.
- Initially, 3 cm cubes in red, blue, and green, with generous spacing.
- The user declares which color to reject.
- The arm pushes selected cubes sideways into a reject tray.
- Other cubes continue into a collection area.
- An overhead camera, video recording, and an independent scorer track each cube.

The installed MuJoCo 3.12.0 exposes moving-surface velocity for conveyor
simulation. Use belt friction to transport free cubes through contact forces.
Reference: [MuJoCo surface velocity documentation](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-geom-surfacevel).

## Starting point when this plan was written

- The SO101 model, actuator control, and cube contact physics already work.
- The existing pickup supports observations, motion commands, saved episodes,
  viewer replay, and MP4 export.
- The current controller solves downward gripper poses; a sideways sweep and
  its clearance still need validation.
- The current simulator pauses between commands. Continuous conveyor operation
  during LLM response time requires a different runtime loop.

The phases below are sequential gates. Numerical thresholds are proposed
starting criteria, not achieved results. Final evaluation settings must be
fixed before formal trials.

## Phase 1 — Build and validate the conveyor

Start with the arm parked and cubes widely spaced.

Verify that cubes travel steadily, remain on the belt, and reach the collection
area. Give each cube a unique ID and track its actual destination.

The independent scorer must classify every cube as:

- Correctly rejected.
- Correctly passed.
- Target missed.
- Wrong-color cube rejected.
- Stuck, lost, or otherwise unresolved.

**Gate:** repeated runs transport every cube correctly without robot intervention.
This establishes that later failures come from sorting rather than the conveyor.

## Phase 2 — Establish reliable physical pushing

Stop the belt and place one cube in the working area. Develop a motion that
approaches, pushes sideways, and retracts.

Repeat with the belt moving slowly, using a conventional controller supplied
with the correct target and its position.

Determine belt placement, reachable pushing zone, minimum cube spacing, and
robot cycle time. Validate the sideways sweep and clearance with the existing
SO101 joint limits and controller.

**Gate:** at least 95 successful rejections in 100 isolated trials, with no
unintended contacts with neighboring cubes in the corresponding spacing checks.

## Phase 3 — Let the LLM select and execute actions

Initially pause simulation time while the LLM thinks. Provide structured
observations containing cube IDs, colors, positions, velocities, and robot state.

Expose basic, color-independent tools:

| Proposed tool | Function |
|---|---|
| `observe()` | Read the current scene |
| `move_to(...)` | Position the arm |
| `sweep(...)` | Execute a bounded pushing motion |
| `wait(...)` | Advance simulation time |
| `retract()` | Return to a clear pose |

The LLM chooses the cube and action sequence. The controller handles joint
movement. No tool automatically implements “reject all red cubes.”

Declare different target colors across trials and test equivalent wording.

**Gate:** correct selection and reliable rejection across all three colors.
This phase measures instruction-following with accurate state information;
it does not yet measure vision or real-time responsiveness.

## Phase 4 — Keep the conveyor moving while the LLM thinks

Introduce a continuously running simulation, timestamped observations, and
queued actions. Physics must keep advancing during model and tool latency.

Measure whether:

```text
LLM response time + approach and push time < remaining interception window
```

For example, an 8 cm working zone at 1 cm/s provides approximately eight seconds
of opportunity. These dimensions and speeds are starting assumptions to validate.

Include retraction time when setting the interval between cubes. Reject expired
commands and record them as timing failures.

**Gate:** successful sorting at the slowest tested speed without pausing the
simulation. Then increase speed and reduce spacing until performance deteriorates;
report the resulting operating limit.

## Phase 5 — Replace supplied state with camera observations

Give the LLM timestamped images and camera/workspace calibration. Exact simulation
state remains available only to the scorer.

Use neutral cube IDs and remove color-revealing metadata from agent observations.
Run the same trials again to measure the effect of requiring visual interpretation.

**Gate:** quantify additional perception errors, missed interceptions, and response
time relative to Phase 4. Keep the task and controller comparable.

## Phase 6 — Evaluate adaptability and robustness

Introduce one difficulty at a time:

- Faster belts or closer cube spacing.
- Different starting positions and cube rotations.
- Changes in lighting and camera angle.
- Target-color changes during a run.
- Instructions such as “Reject red and blue” or “Reject the next two green cubes.”

For instruction changes, define exactly when the new rule takes effect and how
pending actions are handled before running scored trials.

## Evaluation design

Compare the following approaches on identical cube sequences:

| Approach | What it establishes |
|---|---|
| Conventional sorter with exact state | Mechanical and timing reference |
| LLM with exact state | Instruction interpretation and action selection |
| Conventional color vision with the same controller | Simple visual sorting baseline |
| LLM with camera images | Combined visual understanding and action selection |

Keep the controller and available action capabilities consistent within each
comparison. Report paused-time and continuous-time results separately. Clearly
state which decisions the LLM makes and which functions the controller supplies.

### Metrics

| Metric | Definition |
|---|---|
| Target rejection rate | Fraction of target cubes correctly removed |
| Wrong rejection rate | Fraction of other cubes incorrectly removed |
| Throughput | Correctly processed cubes per minute |
| Latency | Median and slowest-tail observation-to-action delay |
| Adaptation | Errors after an instruction change |
| Other failures | Collisions, timeouts, stuck/lost cubes, and unresolved outcomes |
| Model usage | Model calls and token usage; cost where available |

Define the scoring regions, outcome deadlines, and handling of unresolved cubes
before formal evaluation. Include every spawned cube in the outcome accounting.

### Trial protocol

1. Start with short debugging runs.
2. Use a proposed 30 episodes of 20 cubes per main condition for formal evaluation.
3. Balance colors and use held-out random seeds with identical sequences across
   compared approaches.
4. Freeze model settings, prompts, controller, and scoring rules before formal runs.
5. Report confidence intervals alongside aggregate results, accounting for cubes
   grouped within episodes.

Preserve instructions, model configuration, seeds, timestamped observations,
actions, physical outcomes, and recordings so results can be inspected and replayed.

## Demonstration deliverables

- Video showing the instruction, conveyor, robot actions, and live score together.
- Aggregate comparison results and representative failure cases.
- Saved configurations and logs for reproducibility.
- A clear description of whether each run used exact state or images, and whether
  simulation time continued while the LLM was responding.

## Recommended next implementation scope

Implement **Phases 1 and 2 first**: a physically credible conveyor and a reliable
push. Once those work, assess the LLM against the established mechanical baseline.

## Phase tracker

- [x] Phase 1: Conveyor and independent scorer validated (30/30 episodes, 180/180 cubes collected).
- [x] Phase 2: Physical pushing baseline validated (270/270 gate episodes; overload failures documented).
- [x] Phase 3: LLM sorting with structured state and paused time (9/9 Codex episodes; 9/9 matched conventional episodes).
- [x] Phase 4: Continuous conveyor with measured observation-to-command delay (3/3 slowest-speed Codex cases passed; faster and denser failures retained).
- [x] Phase 5: Camera-based LLM sorting measured (16/16 correct visual selections; 6/16 targets rejected versus 15/16 for conventional vision).
- [ ] Phase 6: Robustness and adaptability development evaluation complete; larger formal benchmark outstanding.

### Phase 1 progress

- [x] Review the existing SO101 simulation and confirm conveyor surface-velocity support.
- [x] Build a conveyor scene with a parked SO101, colored cubes, and collection/reject areas.
- [x] Implement unique cube IDs and an independent outcome scorer.
- [x] Validate scorer outcomes and physical belt transport with automated checks (15 tests passed, including contact-boundary and existing pickup checks).
- [x] Run repeated transport trials with reproducible seeds and varying belt speeds (seeds 0–9; 1, 3, and 5 cm/s).
- [x] Save the results, a visual demonstration, and instructions for reproducing them (JSON reports, 32.93-second MP4, and conveyor guide).

Phase 1 development note: the initial 30-episode check collected 178/180 cubes
according to the scorer. Inspection found the other two resting in the collection
tray with approximately 0.10 mm and 0.04 mm of simulated wall penetration. The
scorer now allows 0.5 mm of contact penetration, with a regression check that
larger boundary violations remain unclassified. The initial report is retained
in `results/phase1_initial_boundary_check.json`. The complete matrix was rerun
successfully: all 180 cubes were collected across all 30 episodes. The final
report is `results/phase1_transport.json`. This validates transport and scoring;
it is not a measurement of LLM sorting efficacy.

### Phase 2 progress

- [x] Validate the arm's pushing reach and clearance with a stationary cube.
- [x] Implement approach, sideways sweep, and retraction using actuators and contact physics.
- [x] Add a conventional interception controller for a slowly moving belt.
- [x] Measure cycle time, working zone, and tested spacing with neighboring cubes (6.52–6.57 s motion cycle; consecutive targets pass at 8, 10, and 12 cm spacing at 1 cm/s).
- [x] Pass at least 95 of 100 isolated rejection trials and the neighboring-cube checks (100/100 stationary, 100/100 moving, 40/40 neighboring-cube trials).
- [x] Save validation results, a video, and reproduction instructions ([results](PHASE2_RESULTS.md), [guide](PHASE2.md), and 43.67-second MP4).

Phase 2 completion note: all 20 automated tests pass, including stationary/moving
rejection, neighboring-cube clearance, consecutive targets, missed interceptions
under overload, and IK failures that preserve live state. The 100-trial stationary
matrix and the 100-trial moving-belt matrix passed. All 40 neighboring-cube trials
and all 30 consecutive-target trials passed. Across these 270 gate episodes,
330/330 targets were rejected and 80/80 non-targets passed, with no unintended
contacts. The 20 overload episodes remain in the report: only 1/10 trials passed
at 6 cm spacing and 1 cm/s, and 0/10 at 12 cm spacing and 2 cm/s. Eight centimetres
is the smallest tested passing nominal spacing for consecutive targets at 1 cm/s;
it is not a universal minimum. See [Phase 2 results](PHASE2_RESULTS.md).
These runs establish the conventional mechanical baseline.

### Phase 3 progress

- [x] Expose persistent, color-independent observation and motion tools with paused simulation time.
- [x] Preserve instructions, observations, actions, timing, state, and independently scored outcomes.
- [x] Validate persistence, invalid commands, wrong selections, and equivalent controller behavior (24 tests pass).
- [x] Freeze a nine-episode development protocol covering all three colors and varied wording ([protocol](phase3/PROTOCOL.md), [cases](phase3/cases.json)).
- [x] Run Codex decisions and a conventional comparator on identical layouts; retain failures (9/9 episodes passed for each controller; 9 targets rejected and 18 non-targets passed per controller).
- [x] Save comparison results, a demonstration video, and reproduction instructions ([results](PHASE3_RESULTS.md), [tool guide](PHASE3.md), 81.1-second MP4).

Scope: three mixed-color cubes per episode, one of each color, at 1 cm/s and
12 cm nominal spacing. Three seeds crossed with three target colors give nine
Codex episodes and nine matched conventional episodes. The gate requires all
targets rejected, all non-targets passed, and no unintended contacts. This is
an interactive development demonstration, not the proposed formal 30 × 20-cube
benchmark. Continuous-time operation remains outside the Phase 3 implementation.

Phase 3 completion note: Codex selected and physically rejected all nine targets
across all three colors and wordings; all 18 non-targets passed. The conventional
comparator achieved the same result on identical layouts. Both used 63 primitive
calls, with zero tool errors or unintended contacts. All 24 automated tests pass.
The demonstration video was checked by full decoding and visual inspection.
This establishes successful instruction-following with supplied state and a known
motion recipe. It does not establish an advantage over the conventional selector
or continuous-operation performance. Full logs are retained in
`results/phase3_comparison.json`; no evaluated episodes were retried or excluded.

### Phase 4 progress

- [x] Run physics against a monotonic wall clock independently of Codex calls.
- [x] Add timestamped observations, queued explicit motion sequences, expiry, and timing logs.
- [x] Validate continuous advancement, stale/overlapping command rejection, and physical execution (28 tests).
- [x] Run actual Codex trials at the slowest speed and increase speed/reduce spacing; preserve failures (12 Codex cases; 3/3 slowest-speed gate cases passed).
- [x] Compare with a conventional selector using the same runtime and motion capability (12 matched cases; all initial layouts match).
- [x] Save measured operating limits, raw evidence, video, and reproduction instructions ([results](PHASE4_RESULTS.md), [runtime guide](PHASE4.md), success and failure MP4s).

Phase 4 completion note: all 24 live runtimes met the 0.25-second lag criterion
(worst observed lag 0.047 s). At 0.5 cm/s Codex passed 3/3 mixed-color cases; at
1 cm/s it passed 2/3, at 2 cm/s 0/3, and at 3 cm/s 0/1. All selections were
correct; missed start windows and an overlapping reservation explain the failures.
Measured observation-to-submission gaps were 12.10–16.52 seconds, including
orchestration, versus 0.010–0.053 seconds for the conventional selector. Across
all cases, Codex rejected 8/16 targets and the comparator 15/16; both passed every
non-target. Every outcome and failure is retained in `results/phase4_comparison.json`.
The 8 cm and 6 cm stream probes separate late commands from robot-cycle capacity.
All 28 automated tests pass. Both MP4s passed full decoding and visual inspection.
The small, position-confounded sample establishes a session-specific operating
condition, not a universal speed limit.

### Phase 5 progress

- [x] Provide timestamped overhead images and calibration without oracle object metadata.
- [x] Keep rendering and visual decision time independent of the live physics loop.
- [x] Validate observation filtering, calibration, image-only baseline, and post-hoc perception scoring (calibration errors below 1.66 mm on development seed; new isolation checks pass).
- [x] Run the Phase 4 case matrix using Codex image interpretations and retain every failure (12 Codex and 12 matched conventional episodes).
- [x] Compare perception error, command latency, and outcomes with Phase 4 and a conventional visual baseline ([results](PHASE5_RESULTS.md)).
- [x] Save images, decision logs, results, recordings, and reproduction instructions ([camera guide](PHASE5.md), 24 input PNGs, aggregate JSON, success and failure MP4s).

Phase 5 completion note: all 16 Codex pixel estimates selected the correct target
color, with maximum position error 1.303 mm. Six commands executed successfully;
ten expired. Codex rejected 6/16 targets across 4/12 successful episodes, versus
8/16 targets in Phase 4. Conventional vision rejected 15/16 targets across 11/12
successful episodes; its one miss was a cycle overlap. Both passed all 20
non-targets without unintended contacts. All 24 runtimes met the lag criterion
(worst 0.056 s), and all 31 automated tests passed. The camera measurement gate
is complete; it does not require every trial to succeed. Prior layout knowledge,
target-position confounding, and end-to-end orchestration latency limit the
interpretation. Phase 6 development results follow below.

### Phase 6 progress

- [x] Freeze balanced layouts and separate robustness, timing, and instruction tests ([protocol](phase6/PROTOCOL.md), [24 cases](phase6/cases.json)).
- [x] Implement calibrated camera rotation, lighting/pose changes, multi-color/count scoring, and versioned instruction changes.
- [x] Validate rule counting and change semantics, stale-observation rejection, and public-state separation (35 automated tests pass).
- [x] Execute 24 Codex image-based cases and 24 matched conventional cases; retain every failure (144 cubes accounted for).
- [x] Audit outcomes, perception, adaptation delay, source hashes, and paired confidence intervals (18/28 versus 27/28 targets rejected; seven runtime-health failures retained).
- [x] Complete the separately reported new-seed instruction-change check with one pair at a time and no concurrent recording (4/4 runtimes healthy; Codex 0/2 and conventional 2/2 new targets rejected).
- [x] Save representative videos, input images, results, and reproduction instructions (60 input PNGs, two separate aggregate reports, and three decoded/visually inspected MP4s).
- [x] Repeat the frozen 24-case matrix with GPT-5.6 Sol and save it separately ([repeat results](PHASE6_GPT56_SOL_RESULTS.md), [machine-readable report](results/phase6_gpt56_sol_comparison.json)); 23/28 targets were rejected versus 18/28 previously, with 20 runtime-health failures retained.
- [ ] Run the larger formal benchmark (proposed 30 episodes × 20 cubes per condition, held-out seeds, independent model telemetry). This is separate from the 24-case development matrix.

Phase 6 development completion note: the original 48 episodes account for 144
cubes. Codex selected all 28 final-rule targets correctly and rejected 18; the
conventional vision/parser baseline rejected 27. Both passed all 44 non-targets.
Multi-color and counting instructions succeeded for both. Seven original runs
exceeded the runtime-lag limit, including the final switch trials where recording
overlapped live simulation; every such run is retained and flagged. A separately
declared four-run check with new seeds and no recording during live execution
stayed below 0.069 s lag. Codex correctly selected both new colors but submitted
18.188–19.538 s after the rule change, missing both start windows; the comparator
submitted in 0.322–0.370 s and rejected both targets. All 35 tests pass. These are
development demonstrations with a known scene and motion recipe, not evidence
of superiority over conventional control. See [results](PHASE6_RESULTS.md),
[guide](PHASE6.md), and the [remaining formal benchmark](phase6/FORMAL_BENCHMARK.md).

GPT-5.6 Sol repeat note: the separately stored repeat rejected 23/28 targets and
passed all 44 non-targets, compared with 18/28 and 44/44 in the previous Codex
run. Only 4/24 repeat runtimes met the lag gate because many simulations ran
concurrently. The physical improvement is descriptive; changed orchestration
and poor runtime health prevent attributing it to the model alone. See the
[repeat report](PHASE6_GPT56_SOL_RESULTS.md).
