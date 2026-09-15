# C3 proposal — explicit visual-state reporting before action selection

2026-09-15. Proposed after the offline C2 audit; **not implemented, frozen or run**.

C2 displaced the block during its approach and subsequently closed/lifted the hand
in the prior region. Its prompt already required visual reassessment. The saved
commands do not expose whether the controller misread the image or selected an
inconsistent action after recognizing displacement. C3 tests one intervention:
require a brief, structured visual-state report alongside every action. Geometry,
controller primitives and protective checks remain unchanged.

## Exact proposed response contract

Require exactly these top-level fields, with no additional properties:

- `visual_assessment`: an object with exactly `block_visibility` and
  `block_relative_to_fingers`.
- `command`: the existing unchanged action schema.

`block_visibility` is one of `visible`, `partly_visible`, `not_visible`, `uncertain`.
`block_relative_to_fingers` is one of `between`, `separate`, `uncertain`.
All fields are required. Values describe the current image; they are observable
scene judgments, not chain-of-thought or proof of a physical grasp.

## Exact instruction change

Use C2's static instruction and public input construction, with only these format
changes to avoid conflicting action-only instructions:

1. In `VISUAL_PROMPT`, replace `Return only the structured action. Do not claim success in prose.`
   with `Return only the structured C3 response specified below. Do not claim task success.`
2. In `DECISION_INSTRUCTION`, replace `Return exactly one JSON command matching the supplied output schema.`
   with `Return exactly one JSON object matching the supplied C3 output schema.`
3. Retain the entire `C2_INSTRUCTION` unchanged, then append the following text
   before the same public observation JSON:

```text
C3 visual assessment contract:
Report the current visible state of the red block before selecting the next action.
Return visual_assessment and command in the supplied JSON schema.
For block_visibility, use visible when the block is clearly visible, partly_visible
when part is hidden, not_visible when it cannot be seen, and uncertain when unsure.
For block_relative_to_fingers, use between when the image clearly places the block
between the fingers, separate when it is visibly separate from them, and uncertain
when the image does not establish this relation. Apparent alignment in an image
alone does not establish a physical grasp. Use the current image and public robot
state rather than assuming the previous command achieved its purpose. Choose the
next command consistently with this assessment. Do not report private coordinates,
scorer values or additional explanations.
```

The adapter records and validates the entire response, then passes only `command`
to the existing guarded interface. It must not select, repair, veto or replace
commands based on the assessment. Missing/malformed assessment stops the episode
and remains a counted failure. Assessment fields are retained for evaluation but
are not added to the next decision's public history. One CLI invocation produces
both fields; no extra critic, model call, state estimator or fallback is introduced.

## Execution proposal and accounting

Subject to a separate implementation review and freeze: one reused development
seed 820 episode, supported G1, fixed 960 x 720 RGB and current public calibration,
proprioception and action history. Same signed-in Codex CLI 0.154.0, requested
`gpt-5.6-sol`, low reasoning, isolated tool-disabled sessions, 120 seconds per
invocation, 20 invocations, simulated t=25 seconds including reset. No direct API,
API keys, probes, retries, extra rollout or seeds 840–849. A changed CLI version
requires a separately recorded review before any freeze.

Primary endpoint remains the private scorer's full placement, reported out of one
planned trial. Report sustained lift, peak penetration, stop reason, rejections,
unknown outcomes, latency and CLI usage. Strict pass retains the 2 mm limit,
deadline and zero execution failures/rejections. The changed output length and
any resulting latency/token cost are part of this intervention.

Secondary diagnostic: retain every assessment with its image, timestamp and next
command. Codex labels the images without consulting the associated commands or
private trajectory in the first pass, using the same label definitions; uncertain
visual judgments stay uncertain. Report all rows, agreement, abstentions, and
missing/malformed outputs separately; do not drop uncertain or failed cases from
the episode denominator. This is a reviewer interpretation, not an independently
validated perception benchmark. Compare private trajectory only in a separately
labelled post-hoc pass. Do not infer model beliefs or action intent from either.

C3 can expose assessment/action inconsistencies but cannot isolate internal
reasoning, establish a success rate from one reused seed, or qualify the controller.
It does not supply a grasp recipe or promise to resolve the initial collision.
P5 remains separate with its unchanged, unmet 5.0 mm mean gate.

## Before any run

- [ ] Implement opt-in C3 and offline schema/adapter tests; preserve C1/C2 bytes.
- [ ] Verify complete source, instruction, schema and geometry provenance.
- [ ] Codex reviews implementation and fixes; freeze exact source/hashes in git.
- [ ] Issue a separate bounded execution brief; no run is authorized by this proposal.
