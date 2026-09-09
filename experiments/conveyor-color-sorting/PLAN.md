# SO101 conveyor color-sorting experiment

Date: 2026-09-09
Status: Phases 1 and 2 complete (2026-09-09). Phases 3–6 have not started.

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

## Current starting point

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
- [ ] Phase 3: LLM sorting with structured state and paused time.
- [ ] Phase 4: Continuous conveyor with measured model latency.
- [ ] Phase 5: Camera-based LLM sorting.
- [ ] Phase 6: Robustness, adaptability, and formal comparison.

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
These runs establish the conventional mechanical baseline; Phase 3 will evaluate
LLM decisions and has not started.
