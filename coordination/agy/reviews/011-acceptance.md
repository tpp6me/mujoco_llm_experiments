# Task 011 acceptance — frozen C3 execution

2026-09-15. Accepted handoff: `7710356d183928c1cad005bb338d956c27c1d2ce`.
Frozen execution commit: `19b78537ff52b348f30a10e5147ab5012c5c1ef1`.

AGY executed exactly one seed-820 episode using the frozen signed-in Codex adapter
and packaged the complete evidence. This is acceptance of execution and evidence,
not a passing manipulation result. **0/1 placement, 0/1 sustained lift, 0/1 strict pass.**

## Review order

Codex viewed only public PNGs in the first pass and committed all 18 image labels
at `cd2c4888a8b56469a69263db6a30c9e93f3b7bfc` before opening model assessments,
commands, private scores or trajectories. [Immutable labels](011-blind-labels.json).
The first pass used images as they were saved; their final hashes and the blind
index match all archived PNGs. Prior familiarity with C1/C2 on the same seed remains
a limitation. Six uncertain relation labels remain abstentions, not model errors.

## Independent evidence checks

- All 137 runtime files match the 138-member ZIP including its SHA-256 manifest.
  Archive hash: `08202990a01ecd22adc2c860ff2260b126bfae57579963285bba6595e7198972`.
- All 92 frozen files, protocol/freeze/task hashes and pre-run source/clean status
  checked. The evidence branch changes no controller, interface, scorer, scene,
  model, software test or prior result. No repeated episode or live image probe.
- All 18 prompts and PNGs reproduce from their public requests; every complete
  CLI event stream agrees with the full response. Exactly 18 distinct CLI session
  IDs; requested gpt-5.6-sol, 120 s timeout, unchanged tool-disabled configuration.
  Only returned commands reach the interface; assessment fields do not enter history.
- All 18 assessment rows retained. AGY summary runner and private scorer fields
  match raw artifacts; blind-index fields contain no model or outcome labels.
- Base-to-tip whitespace check passed. This was an evidence-only task; no broad
  software test or additional physics experiment was run for review.

[Reproduction script](011-independent-check.py), [verification](011-independent-review.json),
[comparison](011-assessment-comparison.json), and [post-hoc trajectory check](011-private-trajectory-check.py).
For archive-only reproduction, extract its members into a new worktree-local
`runtime/humanoid/codex-C3/` directory; point --worktree to the unchanged execution
checkout, and --episode to its seed-820 directory for the trajectory check.

## Outcome and interpretation

There were 18 valid decisions, 17 completed actions and one path-guard rejection,
with no refusal, malformed output or unknown execution outcome. Simulation ended
at 13.700 s. Peak object penetration was 1.611 mm; this quality criterion passed,
but the task did not. Mean CLI latency was 19.604 s; maximum 34.268 s.

Relation agreement was 9/18 across all responses, or 9/11 on the explicitly
separate subset where neither reviewer nor model abstained. Reviewer/model
abstentions were 6/18 and 1/18. Visibility agreement was 6/18, largely reflecting
basket-rim occlusion classification; both identified the block. These are reviewer
interpretations, not validated perception accuracy estimates.

Calls 4/5 reported between despite blind separate labels. Private saved endpoints
show action4's close displaced the block 86.244 mm in XY and tipped it about 90°;
action5 did not move it meaningfully. The later close/lift at actions13/14 also left
the block stationary, despite between reports; the blind reviewer abstained there.
Commands generally follow the model's stated relation, but the self-reports do
not verify a physical grasp. The rejected final move cannot be evaluated as an
executed transport. No inference about internal beliefs or causal improvement.

The [full C3 results](../../../experiments/humanoid-pick-place/CODEX_C3_RESULTS.md)
supersede pending-review status in the historical AGY handoff/summary. Those files
and their recorded hashes are preserved. C1/C2 evidence remains unchanged.

## Next step

[Task 012](../tasks/012-c3-grasp-audit.md) is ready for offline evidence preparation,
not launched by this acceptance. AGY investigates saved closing geometry and the
rejected path; Codex interprets the evidence before proposing another condition.
No C4, API transport, new model call, retry or held-out seed is authorized here.
P5 remains separate with its unchanged, unmet 5.0 mm mean gate.
