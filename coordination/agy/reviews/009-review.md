# Task 009 review — changes requested

2026-09-15. Reviewed tip: `78511286eace3d7fa0875941497ba40eed1d2907`.
Eight C2/C1 audit tests independently pass (1.069 s). The reported C2 displacement,
scorer peak, and final-state IK rejection reproduce. No new episode was run.
The handoff is not accepted because the evidence below is incomplete or mislabeled.

## R1 — Missing public proprioception (high)

`scripts/audit_codex_c2.py` exports `obs.get('robot')`, but archived observations
use `robot_state`. All seven `robot_proprioception` values are null despite the
report claiming exact public proprioception is retained. Use the actual required
public field, reject missing/invalid input explicitly, regenerate artifacts, and
assert each exported state/history/image identity matches its archived request.
Do not merely test that seven rows exist. Distinguish inputs preceding a decision
from the command/outcome afterward. Remove the contact sheet's interpretive summary
card ("damaging action", "block on floor", etc.); retain original images and factual
time/command labels, with private geometry in its separately labelled artifact.
Codex owns the visual interpretation.

## R2 — Penetration associated with the wrong sample (medium)

`sampled_qpos_geometry` labels sample 118 / t=3.794 s as nearest to scorer peak,
but `nearest_penetration_m` is 0.0002741165 m from the **first contact** at t=3.761 s.
The nearest sample's maximum overlap is 0.0051846716 m. Select the nearest index
from the recorded times and peak time, then derive every associated measurement
from that same sample. Derive the max-contact index too; do not hard-code 118.
Test that the different first-contact and nearest-peak rows retain their own
correct times/values. Derive the reported IK residual from the reproduced result
and label its four-decimal precision rather than inserting a literal measurement.

## R3 — Geometry and comparison overclaims (high)

The report says descending below the block top "necessarily caused collision"
and infers a 97 mm finger sweep through the block from Z intervals. Overlapping
bounding boxes do not prove mesh collision; neither does a site below object top.
Use the actual recorded contact pairs and sampled path as evidence for this case.
Remove necessity/universal claims and the solid-fill interpretation of the envelope.

The prompt supplied approximate posture-specific bounds. Actual lower Z bounds
already extend below -0.077 m (about -0.0778 pre-approach); do not call the bounds
exactly enclosing or infer fully open/measured downward posture from command alone.
Retain actual per-sample hand bounds across Action 4, quantify departure from the
nominal envelope, and record measured finger joints/site orientation versus their
nominal references. Explain applicability as approximate, with its measured limits.

Derive the C1/C2 comparison from retained evidence instead of hard-coded result
numbers, retain those input hashes, and compare the same displacement metric and
interval. C2's 804.145 mm is a 3D displacement from Action-4 start to Action-5 end;
it is not displacement during Action 5 alone. C1's 84.640 mm is XY, not comparable
as a "total" 3D displacement. Label both intervals and dimensions consistently.
Commands returning to the prior region are observed; "open-loop" or intended
transfer/recovery are not established by command JSON. Fix prose/JSON together.

## R4 — Reproducible integrity checks and meaningful failure tests (medium)

The audit reads `sha256.json` but does not itself verify the frozen ZIP digest or
all archive member bytes. Pin the accepted C2 archive digest, verify unique/complete
member accounting and each byte hash before trusting its manifest, and retain this
verification in the audit. Keep extraction confined to a new output location.

Current source/scene mismatch tests alter a recorded report or mock every digest,
so they stop at episode-manifest mismatch without exercising the source/scene
checks they name. Keep episode bytes intact and perturb the actual source lookup
for the specific file (delegating other digests to the original helper); assert
the specific source/scene failure and absence of output. Strengthen the no-model
check to cover the actual subprocess launch path (`Popen`), not only `run`, while
retaining reset/physics guards. Add focused regressions for R1/R2 and rerun the
C1/C2 audit tests. A repository-wide suite is unnecessary for this standalone audit.

Regenerate only Task 009 artifacts from the immutable C2 archive, update hashes,
report and checklist, and run `git diff --check d125d74..HEAD`. Commit/push the same
task branch and return its exact revised tip. No source-controller fixes, model
calls, physics steps, new trial or main integration are authorized for revisions.
