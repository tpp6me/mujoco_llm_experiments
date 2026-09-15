# C3 development result — explicit visual assessment

2026-09-15. **0/1 placement, 0/1 sustained lift, 0/1 strict pass.** One frozen
seed-820 episode completed without retries. C3 collected valid visual assessments
but did not achieve a grasp or placement.

## Execution and evidence

[Protocol](protocols/C3.md), [freeze](protocols/C3_FREEZE.json), execution source
`19b78537ff52b348f30a10e5147ab5012c5c1ef1`; AGY handoff
`7710356d183928c1cad005bb338d956c27c1d2ce`. Signed-in Codex CLI 0.154.0,
requested `gpt-5.6-sol`, low reasoning, fresh tool-disabled sessions. AGY operated
the harness; Codex supplied all VLA decisions. No direct API integration/calls,
model probes, retries or held-out seeds. Physics, guards and scorer were unchanged.

| Measure | Observed |
|---|---:|
| Requested / executed episodes | 1 / 1 |
| Decisions / completed actions | 18 / 17 |
| Rejected actions | 1 |
| Refusals / malformed outputs / unknown execution outcomes | 0 / 0 / 0 |
| Final simulation time | 13.700 s |
| Peak object penetration | 1.611 mm |
| Object penetration quality / deadline check | pass / pass |
| Full placement / sustained lift / strict pass | 0/1 / 0/1 / 0/1 |
| Mean / maximum CLI decision latency | 19.604 / 34.268 s |

Action 18 was rejected because the commanded joint path predicted robot/environment
penetration over 2 mm. It did not advance physics. Passing the object penetration
threshold does not establish task success or validate every robot clearance.
Runner process exit was zero; this is distinct from the failed physical outcome.

The [machine summary](results/codex_C3.json) and [episode archive](results/codex_C3_episode.zip)
retain all 137 runtime files, plus an archive member-hash manifest (138 members).
Archive SHA-256: `08202990a01ecd22adc2c860ff2260b126bfae57579963285bba6595e7198972`.
Codex verified all file hashes, all 92 frozen inputs, all 18 prompt/PNG reproductions,
full response/event agreement, unchanged command forwarding, no assessment history
leakage, and 18 distinct CLI session IDs. [Independent evidence audit](../../coordination/agy/reviews/011-independent-review.json).
CLI-reported totals: 218,639 input tokens (12,032 cached), 7,382 output tokens
(including 6,104 reasoning tokens). These are CLI usage fields, not an independent
network-request count or direct API billing estimate.

## Image review before unblinding

Codex reviewed saved public PNGs without opening their assessments, commands or
private scores. All 18 labels and image hashes were committed at
`cd2c4888a8b56469a69263db6a30c9e93f3b7bfc` before unblinding.
[Immutable labels](../../coordination/agy/reviews/011-blind-labels.json),
[full comparison and action review](../../coordination/agy/reviews/011-assessment-comparison.json).
The reviewer had prior familiarity with C1/C2 on this reused seed; this is not an
independent, validated perception benchmark.

| Field | Exact agreement, all 18 | Reviewer uncertain | Model uncertain | Agreement when both determinate |
|---|---:|---:|---:|---:|
| Visibility | 6/18 | 0/18 | 0/18 | 6/18 |
| Relation to fingers | 9/18 | 6/18 | 1/18 | 9/11 |

All 18 responses had valid assessment fields; none is missing or malformed. The
11 determinate relation pairs are a diagnostic subset; the seven pairs involving
abstention remain in the 18-response accounting and the one-trial denominator.
The visibility disagreement largely reflects the reviewer consistently marking
basket-rim occlusion as partly visible, while the model often used visible. Both
identified the red block; these disagreements do not establish failed detection.

The reviewer visibility label was `partly_visible` for every row. Abbreviations
below: V = visible, P = partly_visible, S = separate, B = between, U = uncertain.

| Call | Model visibility | Model relation | Reviewer relation | Next command | Execution |
|---:|---|---|---|---|---|
| 1 | V | S | S | hand 0.0 | completed |
| 2 | V | S | S | move [0.25, -0.14, 0.895] | completed |
| 3 | V | S | S | move [0.248, -0.18, 0.875] | completed |
| 4 | P | B | S | hand 0.65 | completed |
| 5 | P | B | S | hand 1.0 | completed |
| 6 | V | S | S | hand 0.0 | completed |
| 7 | V | S | S | move [0.18, -0.2, 0.875] | completed |
| 8 | V | S | U | move [0.18, -0.15, 0.875] | completed |
| 9 | V | S | U | move [0.245, -0.15, 0.875] | completed |
| 10 | V | S | S | move [0.245, -0.23, 0.875] | completed |
| 11 | V | S | S | move [0.205, -0.15, 0.875] | completed |
| 12 | V | S | S | move [0.19, -0.22, 0.84] | completed |
| 13 | P | B | U | hand 1.0 | completed |
| 14 | P | B | U | move [0.19, -0.22, 0.96] | completed |
| 15 | V | S | S | hand 0.0 | completed |
| 16 | V | S | U | move [0.23, -0.22, 0.84] | completed |
| 17 | P | U | S | hand 1.0 | completed |
| 18 | P | B | U | move [0.19, -0.39, 0.98] | rejected |

## Separate private trajectory pass and interpretation

[Saved-qpos endpoint review](../../coordination/agy/reviews/011-private-trajectory-review.json),
[reproduction script](../../coordination/agy/reviews/011-private-trajectory-check.py).
No simulation reset or physics step was used for this analysis. The selected action
boundaries coincide with saved samples; sampled geometry does not reconstruct forces
or prove finger enclosure.

- The first close, action 4, moved the block **86.244 mm in XY** and rotated it
  approximately **90 degrees**. Its center dropped about 35 mm as it tipped onto
  its side. The model had labelled it between the fingers; the blind reviewer
  labelled it separate. Call 5 repeated between and closed further, while the
  reviewer again labelled separate and the block remained effectively stationary.
- The model subsequently reported separate and repositioned repeatedly. Calls 13
  and 14 reported between, then closed and moved upward. The reviewer abstained
  on these images. Private endpoints show no meaningful object movement through
  that close/lift sequence, consistent with the scorer's lack of sustained lift.
- Call 17 reported uncertain and closed. Call 18 reported between and requested a
  higher move toward the basket region. The reviewer abstained on call 18; the
  guard rejected its path. A between label is not proof of a physical grasp.

C3 exposes reported visual state and makes these disagreements reviewable. The
commands often follow the model's own stated relation, so the evidence does not
support a blanket claim that it ignored its assessment. Several reported between
states still preceded unsuccessful closes/lifting. This cannot isolate internal
beliefs, distinguish all visual ambiguity from mechanical alignment error, or prove
that the assessment intervention caused the lower penetration seen in this run.
C1, C2 and C3 each remain 0/1 placements on a reused development seed; this is not
a qualified controller or a statistical comparison.

## Next step

[AGY Task 012](../../coordination/agy/tasks/012-c3-grasp-audit.md) prepares an offline
audit of the failed closes and rejected path from preserved data. Codex will use
that evidence to choose a separately declared successor. No new prompt, physics,
guard, scoring threshold or experiment is introduced by this result. P5's 5.0 mm
mean gate remains unchanged and unmet; seeds 840–849 remain unused.
