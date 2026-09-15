# Task 009 acceptance — offline C2 failure audit

2026-09-15. Accepted tip: `97f1b2c33d2773f9f32b7588500e8ae59a785261`.
Starting commit: `d125d74be4324dad9b938adcd4ef4ded84a2d636`.

AGY completed the offline audit and addressed the two Codex reviews. The result
explains the retained C2 failure without changing or rerunning it. No new model
invocation, API call, simulator reset or physics step was used. C1/C2 evidence,
controller, guards, scorer, thresholds and held-out seeds remain unchanged.

## Verified evidence

Codex independently ran the 11 focused C1/C2 audit tests (2.059 s, all passed),
then reproduced the final audit from a fresh extraction of the pinned C2 archive
with `mj_step`, reset, `subprocess.run` and `Popen` patched to fail. All three JSON
artifacts reproduce, excluding only the temporary source-directory path. The
embedded audit-source hash matches the final script. The contact-sheet PNG is
byte-identical, and each of its seven image panels matches the original archived
PNG after the declared resize. All seven public robot-state/history/image-ID
exports match their archived requests; inputs and subsequent outcomes are distinct.

See the [independent check](009-independent-check.py) and
[verification record](009-independent-review.json). Reproduce from the repo root:

```sh
.venv/bin/python coordination/agy/reviews/009-independent-check.py --worktree /private/tmp/mujoco-llms-agy-009 --output /private/tmp/c2-audit-verification.json
```

The final revision clarifies sampled-contact wording and labels. The final
artifact reproduction and full revision whitespace check pass. C2 archive SHA-256 remains
`940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8`.

## Findings and limits

- Action four displaced the block **154.269 mm horizontally** (155.212 mm in 3D),
  with about 166.58 degrees of endpoint rotation. C1's comparable damaging-action
  displacement was 84.640 mm horizontally (91.591 mm in 3D).
- First **sampled** finger/block contact is t=3.761 s, 0.274 mm overlap. The sample
  nearest the scorer peak is t=3.794 s, 5.185 mm overlap. The private 1 kHz scorer
  recorded its peak at t=3.795 s and 25.51 N normal force at that peak. These are
  distinct records; the sampled trajectory does not establish exact contact onset
  or reconstruct forces.
- Across all 26 approach samples, the lower hand bound reaches -77.782 mm relative
  to the grasp site: 0.782 mm beyond the prompt's approximate -77 mm lower bound.
  Actual contacts establish this episode's collision. Bounding-box overlap or a
  site below the object's top does not establish that every such approach collides.
- Finger readings use `HAND_NAMES` order from the preserved environment code;
  closure-zero references are `[0, -0.1, -0.1, 0, 0, 0, 0]` radians. The stored
  quaternion difference is a component norm for the recorded representation, not
  an angle; quaternion signs can represent the same rotation. It is not a generic
  orientation-error metric.
- The block reached floor height by t=5.000 s. Its 804.145 mm 3D displacement is
  cumulative from action-four start to action-five end, not action-five motion alone.
  The final IK error reproduces exactly with the saved integration state unchanged.

Codex's visual review finds the block displaced and visibly separate from the hand
in decision five's image, before the close command. In decisions six through nine
it is visible below the table edge, away from the hand; private geometry places it
on the floor. Later commands return to the original approach region. This supports
an observed feedback inconsistency, but does not reveal the model's internal belief,
prove it ignored the image, or distinguish perception from action-selection error.
C2 remains **0/1 placement, 0/1 sustained lift, 0/1 strict pass**.

## Next scientific step

The [C3 proposal](../../../experiments/humanoid-pick-place/protocols/C3_PROPOSAL.md)
requires a brief visual assessment alongside each command, in the same Codex
invocation. It leaves geometry, primitives, guard, scorer and budgets unchanged;
assessment values do not trigger an automatic correction. This makes reported
visual state available for comparison with the next action. It does not promise
to fix grasp geometry or establish performance from one reused development seed.

[AGY Task 010](../tasks/010-c3-offline-preparation.md) is ready for offline
implementation and qualification. It is not launched by this acceptance. Codex
must review the implementation before any separate freeze/execution brief. No C3
trial has been run; P5's 5.0 mm mean gate remains unchanged and unmet.
