# C2 proposal: explicit hand geometry and visual reassessment

Defined 2026-09-14 after the [C1 diagnosis](../CODEX_C1_DIAGNOSIS.md).
**Status: specified; not implemented, frozen or executed.** C1 remains immutable.
This is the next development condition, not a revision of C1's result.

## Question and declared changes

Does explaining the occupied geometry around the grasp reference, together with an
explicit instruction to reassess displaced objects, reduce approach and descent
failures? C1 struck the block during approach and then requested a table-colliding
descent near its old location. A generic site-reference warning was insufficient
in that episode. This condition changes two related instruction elements together;
it cannot isolate their individual effects or establish a general success rate.

Retain C1's `VISUAL_PROMPT`, JSON schema and decision-only instruction. Append the
following fixed text before the public observation JSON on every decision:

```text
Additional robot geometry and feedback contract:
The right_grasp site is a reference embedded within the hand geometry. It is not
the lowest fingertip, an empty grasp cavity, or the desired object centre.
With fully open fingers and the declared downward orientation, nominal collision
geometry occupies approximately these world-axis offsets relative to the site:
X [-0.074, +0.058] m, Y [-0.042, +0.042] m, Z [-0.077, +0.085] m.
These are rounded bounds on solid robot geometry from its description. Actual
extents change with finger articulation, orientation and tracking error. They do
not specify where to place an object within the hand or certify a safe path.
A grasp-site target above the table can still put fingertips through the table.
Likewise, putting the site at an object's visible top does not guarantee clearance
between the open hand and the object. Plan clearance for the entire hand and its
path, not only the reference point. The guard does not certify object contacts.
After every completed motion, use the current image to reassess the object's
position and orientation. If it moved or toppled, do not keep descending toward
its former position or assume that it remains upright. A completed motion is not
evidence of a grasp. Replan using the new visual observation and public hand state.
```

The nominal numbers come from a separate robot-only kinematic calculation with
closure=0 and downward orientation, retained in the C1 audit's
`nominal_open_hand_geometry`. The calibration's arbitrary site location is not a
task waypoint and must not be included in the prompt. Geometry comes from collision
mesh vertices and box corners, not private block state. Before freezing C2, verify
the rounded bounds enclose that nominal geometry and label them as posture-specific.

## Unchanged execution condition

- One planned randomized development episode, seed **820**, explicitly reused
  after development inspection. No held-out or independence claim; no seeds 840–849.
- Signed-in ChatGPT Codex CLI, reviewed version 0.154.0, requested model
  `gpt-5.6-sol`, low reasoning. Fail preflight if the installed version differs;
  review any version change as a separate recorded condition.
- Fixed 960 x 720 RGB, public calibration/proprioception and bounded public action
  history. No private state, scores, pose-estimator output or exact-state recipe.
- Fresh ephemeral decision sessions with the existing tool-disabling configuration
  and event audit. No AGY, direct API integration, API keys or wrapper retry.
- Same guarded primitives, workspace, 2 mm guard threshold, physics and scorer.
  At most 20 decisions, simulated t=25 s including reset, 120 s per CLI decision.
- Same stop rules for rejection, malformed output, timeout and budget exhaustion.
  No rescue action or edited prompt after the run starts.

## Outcomes and accounting

Primary outcome remains full basket placement under the existing scorer, reported
as 0/1 or 1/1. Also report sustained lift, maximum object penetration, rejected
actions, simulation duration, CLI invocation count and latency. Strict success
requires placement, <=2 mm maximum penetration, the deadline, no rejection or
execution failure. Normal budget exhaustion is reported separately from execution
errors; no failure or missing episode disappears from the one-trial denominator.

For diagnosis, report private per-action object displacement and orientation, the
first sustained lift if present, and where any preflight rejection occurs. Do not
invent a separate approach-success threshold after seeing the result. An initially
gentler approach alone does not establish a successful grasp or placement.

C1 versus C2 is a descriptive comparison on a reused seed with nondeterministic
model decisions, not a paired statistical test. No matched conventional visual
comparator is ready. P5's 5.0 mm mean-error gate remains unchanged and unmet.

## Implementation and execution checklist

- [x] Diagnose C1 using preserved states and name the specific contact failures.
- [x] Specify exact added text and unchanged trial/accounting rules.
- [ ] Implement an explicit `c2` condition alongside immutable `c1` selection.
  Keep existing C1 defaults and its prompt bytes unchanged. Save the condition ID,
  exact complete prompt hash, geometry evidence hash and source commit.
- [ ] Test prompt isolation: no C1 private coordinates, audit text or tuned waypoints
  reach the decision; no C2 paragraph enters C1; altered configurations cannot
  retain a C1/C2 protocol label silently. Test the nominal rounded geometry bounds.
- [ ] Pass affected controller/runner tests; freeze source, prompt and C2 protocol
  in git before execution. This proposal does not bypass C1's locked CLI entry point.
- [ ] Execute exactly one declared C2 episode, retain every decision/failure, then
  audit images/prompts/events and private scoring before interpreting the result.
- [ ] Update results and the living plan; choose any further condition separately.
