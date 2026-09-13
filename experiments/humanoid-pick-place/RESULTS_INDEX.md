# Humanoid results index

All results use a fixed pelvis. The mechanical matrices below use conventional
exact-state control; the separate L2 pilot adds LLM exact-state control, and C1 adds
one signed-in Codex visual-control development case. Free-standing balance and
walking have not been evaluated.

| Configuration | Seeds | Physical success | Strict success | Gate | Evidence |
|---|---|---|---|---|---|
| V1 | 100–199 | 93/100 | 89/100 | Fail | [Outcomes](results/mechanical_v1.json), [source](results/mechanical_v1_source.zip) |
| V2 | 200–299 | 80/100 | 79/100 | Fail | [Outcomes](results/mechanical_v2.json), [source](results/mechanical_v2_source.zip) |
| V3 | 300–399 | 96/100 | 92/100 | Fail | [Outcomes](results/mechanical_v3.json), [source](results/mechanical_v3_source.zip) |
| V4 | 400–499 | 98/100 | 96/100 | Pass | [Outcomes](results/mechanical_v4.json), [source](results/mechanical_v4_source.zip) |
| Guarded G1 | 500–599 | 99/100 | 85/100 | Fail | [Outcomes](results/guarded_g1.json), [source](results/guarded_g1_source.zip) |
| Guarded G2 | 600–699 | 100/100 | 97/100 | Pass | [Outcomes](results/guarded_g2.json), [source](results/guarded_g2_source.zip) |

These matrices use different seeds and controller versions. V1/V2 use a narrower
block than V3 onward. Guarded G1/G2 add the shared-interface collision safeguard.
The table is an outcome index, not a paired or controlled comparison of models.

- [Historical V3 report](RESULTS.md) and [frozen V3 protocol](PLAN.md#historical-reference--frozen-v3-mechanical-protocol).
- [V4 report](V4_RESULTS.md) and [protocol](protocols/V4.md).
- [Guarded reports and retained development probes](GUARDED_RESULTS.md),
  [G1 protocol](protocols/G1.md), [G2 protocol](protocols/G2.md).
- [Shared interface](INTERFACE.md), [run guide](README.md), [living checklist](PLAN.md).

Summary reports and source snapshots are retained with the repository. Complete
physics trajectories and videos are local, ignored artifacts under `runtime/humanoid/`;
the reports specify each directory. Model assets, provenance and checksums remain
in `models/g1/`. Source archives do not duplicate the model mesh assets.

## Exact-state LLM development pilots

| Pilot | Cases | Conventional task / strict | LLM task / strict | Interpretation |
|---|---|---|---|---|
| L1 | 700–702 | 3/3 / 2/3 | No model output | Three HTTP 400 schema errors; integration failure |
| L2 | 700–702 | 3/3 / 2/3 | 0/3 / 0/3 | One LLM sustained lift; two guard rejections; small development pilot |

[Full pilot report](LLM_RESULTS.md), [runner](LLM_RUNNER.md),
[L1 outcomes](results/llm_L1.json), [L2 outcomes](results/llm_L2.json).

## Visual infrastructure development

[C1 signed-in Codex visual controller](CODEX_C1_RESULTS.md), development seed 820:
0/1 placements, 0/1 sustained lifts, 3 CLI decisions, 2 completed actions and one
guard rejection. Peak object penetration was 6.291 mm, above the 2 mm quality limit.
No direct API integration or keys; all prompts/images and event logs audited.
[Results](results/codex_C1.json), [episode archive](results/codex_C1_episode.zip),
[retained probes](results/codex_C1_probes.zip). This is not a matched model comparison.

[Five-capture checks and limitations](VISUAL.md): calibration bounds and exact
state preservation passed; the centroid/known-plane estimate has up to 2.983 cm
XY error. The head view crops the task. These are infrastructure checks, not
visual-controller success rates. [Private validation data](results/visual_v1_validation.json).

[P1 initial RGB position estimation](POSE_RESULTS.md), seeds 720–739: 20/20 fresh
reset images within 5 mm XY error (mean 0.518 mm, maximum 2.418 mm). The previous
centroid method averaged 23.463 mm on the same images. This uses known block/table
geometry and fixed lighting; it is perception development, not robot qualification.
[Private validation records](results/pose_P1.json).

[P2 visibility and support-prior audit](PERCEPTION_RESULTS.md), seeds 760–779:
240/240 endpoint images from 20 exact-state-driven episodes. Red detected in all
images; the wrapper withheld 3D pose in all 220 post-action frames. Raw P1 accepted
73/80 post-release frames with >5 mm 3D error (maximum 13.010 mm). This is a
validity/visibility audit, not carried-pose or visual-control qualification.

[P3 experimental carried-center estimate](CARRIED_POSE_RESULTS.md), seeds 800–809:
40 original carried frames from 10 exact-state-driven episodes plus 80 correlated
sensor corruptions. Originals: 19 accepted, 18 within 20 mm, one accepted error
20.885 mm; partial blackout: one accepted error 22.992 mm. All 40 blank frames
refused. The frozen screen failed; no estimator/control integration.

[P4 temporal RGB/hand-motion candidate](TEMPORAL_POSE_RESULTS.md), seeds 820–829:
14/20 nominal post-warmup targets within 20 mm (mean 3.645 mm, maximum 7.420 mm).
No positions on release/retract or altered transport frames. The 16/20 coverage
screen failed. Three correlated streams produced 180 responses from 10 episodes;
no temporal estimate drove an action.

[Temporal reacquisition development (Task 001)](TEMPORAL_REACQUISITION_DEVELOPMENT.md), seeds 820–829:
17/20 post-warmup targets accepted, 16/20 within 20 mm (mean 4.744 mm). Seed 820 accepted at
21.944 mm error due to optical-axis depth ambiguity. Zero accepted on release/retract or
corrupted streams. Proposed protocol [P5](protocols/P5_PROPOSAL.md).

[Multi-view reacquisition evidence (Task 002)](TEMPORAL_REACQUISITION_EVIDENCE.md), seeds 820–829:
Comparing 2-frame vs 3-frame reacquisition across original (endpoint-only) and augmented
(lowering midpoint) streams. On the augmented stream, the 3-frame candidate recovers 17/20
post-warmup targets with 100% within 20 mm (mean over accepted original targets: 5.872 mm,
all-accepted mean: 5.066 mm, maximum: 14.848 mm). Seed 820 error drops from 21.937 mm to 14.848 mm.
Zero accepted on release, retract, or corrupted streams.
Results: [evidence development data](results/temporal_reacquisition_evidence_development.json).

Task 002 is [accepted for development-only integration](../../coordination/agy/reviews/002-acceptance.md).
The proposed 5.0 mm accepted-original-target mean gate remains unmet.

[P5 protocol preparation and gate runner (Task 003)](../../coordination/agy/tasks/003-p5-preparation.md):
- Revised proposed protocol: [P5 Revised Proposal](protocols/P5_REVISED_PROPOSAL.md) (proposed, not frozen, not executed; seeds 840–849 remain untouched; earlier [P5 Proposal](protocols/P5_PROPOSAL.md) retained as historical planning evidence).
- Production wrapper: `humanoid_sim/p5_evaluation.py` with explicit preflight, gate evaluation, held-out seed guards (seeds 840–849 strictly forbidden in this task), and fresh capture disabled.
- Retained development evidence and gate reports under `results/p5_preparation/`:
  - [Preflight report](results/p5_preparation/preflight_report.json): hashes, grid specification (1,170 expected responses across 3 candidates), input availability.
  - [Artifact rescore gate report](results/p5_preparation/gate_report_rescore.json): evaluates the 5 continuation gates against accepted Task 002 evidence.
  - [Development dry run evidence](results/p5_preparation/p5_development_evidence.json) and [development gate report](results/p5_preparation/gate_report_development.json): exercises the production runner on saved development captures (seeds 820–829).
  - [Task manifest](results/p5_preparation/manifest.json): records provenance, hashes, and execution status.
- Findings: On the primary condition (`TemporalThreeFrameReacquisitionPose` on the augmented schedule), coverage passes (17/20 >= 16), max error passes (14.848 mm <= 20 mm, midpoint max error 5.114 mm), release/retract safety passes (0/20), and corrupted transport robustness passes (0/20). The 5.0 mm accuracy gate is strictly preserved and unmet: the accepted original-target mean is **5.8715 mm** and fails the gate. Midpoint estimates (mean 3.109 mm) are accounted separately and do not dilute the original post-warmup denominator.
- Status: Prepared and ready for review; no fresh P5 execution or held-out seed evaluation has occurred.

Task 003 is [accepted with integration fixes](../../coordination/agy/reviews/003-acceptance.md).
Codex refreshed the gate reports by rescoring unchanged saved estimates and bound
reports to their source/input hashes. Fresh P5 remains unexecuted; the 5.0 mm mean
gate remains unmet. [Visual policy runner scaffolding (Task 004)](../../coordination/agy/tasks/004-visual-policy-scaffold.md):
- Implementation: `humanoid_sim/visual_policy_runner.py` with `VisualPolicySession` adapter, allowlist extraction, strict structured response validation, injectable clock timing, and single-use fresh observation enforcement.
- Documentation: [Visual Policy Runner Guide](VISUAL_POLICY_RUNNER.md).
- Verification: 16 focused tests in `tests/test_humanoid_visual_policy_runner.py` covering allowlist isolation (deliberately planted private fields in observations, responses, and history are stripped), single-use observation IDs, stale ID rejection, refusal/malformed/exception handling, collision guard termination without fallback, action limit / deadline budget enforcement, wall latency separation, and held-out seed rejection.
- Retained development demo: [Seed 820 smoke check](results/visual_policy_scaffold/report.json) using scripted plumbing stub (4 calls, 4 completed actions, `placement_success_claimed: false`, separate [evaluator report](results/visual_policy_scaffold/evaluator_report.json), sample [public request payload](results/visual_policy_scaffold/demo_request_payload.json)).
- Status: Scaffolding and offline verification complete. No live model calls, API keys, or fresh P5 runs occurred.
