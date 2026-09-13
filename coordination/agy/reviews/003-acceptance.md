# Codex acceptance — task 003

Date: 2026-09-13.
AGY revision integrated: `ca5948aacc51fd8a6fd8df562f6baa46c75be84a`.
Branch: `agy/003-p5-preparation`.
Decision: **accepted with Codex integration corrections**.
The merge containing this record preserves the full AGY history. Acceptance is
for the final integrated implementation, not the unmodified AGY tip.

## Review resolution

AGY addressed duplicate/held-out seed guards, complete primary-condition grids,
provenance/dependency hashes, and corrected the unsupported fresh capture command
into a clearly disabled Python API sketch. The original all-refused formatting
failure and false PASS from empty records are resolved.

Codex found three residual issues in the revised tip and completed bounded fixes:

- Full comparison envelopes now validate all three prespecified candidates on
  both schedules, with consistent seed declarations and complete per-case grids.
  Missing comparator rows cannot be certified by a complete top-level status.
- Malformed numeric records and metadata return INCOMPLETE; scalar, finite,
  non-negative scores and boolean detections are enforced. Nested held-out seed
  declarations are rejected at the rescore boundary before gate computation.
- All gate metrics use recomputed per-record aggregates. A rounded summary cannot
  mask a value just above the 20 mm limit; inconsistent summaries are rejected.
  Added four regression tests cover these paths and metadata edge cases.

The provenance description now describes the actual source snapshot without
hardcoding the AGY branch name when rescoring from main. No estimator, optimizer,
physics, camera, action policy or accuracy threshold was changed in integration.

## Independent checks

- Final integrated full discovery: **145 tests passed in 140.748 s**, using
  `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v`
  from the primary checkout. [Retained final log](003-integration-tests.txt).
- Ran the P5 focused suite after the integrity fixes: **27 tests passed**.
- Rescored both accepted Task 002 evidence and the completed Task 003 development
  evidence using the integrated validator, covering all six candidate/schedule
  combinations. Both primary gate reports are complete and retain FAIL at the
  unchanged 5.0 mm original-target mean criterion.
- Regenerated preparation metadata and report hashes, recording the report-source
  snapshot, dependency lock, input evidence and outputs. The new manifest keeps
  the original optimizer-generation metadata separate from integration rescoring.
- Preserved the raw development estimates; no repeat of the long optimization,
  fresh rendering, held-out data access, provider calls or hardware use occurred.
- Integration resolves the plan conflict while preserving prior review history.

## Scientific outcome and next step

The development screen accepts 17/20 original Transport/Lower targets, all within
20 mm, with mean 5.871509 mm and maximum 14.847913 mm. The mean exceeds the unchanged
5.0 mm criterion. This preparation task is complete even though the estimator has
not qualified. P5 remains proposed, unfrozen and unexecuted on seeds 840–849.

[Task 004](../tasks/004-visual-policy-scaffold.md) implements an offline, provider-
neutral RGB-to-action loop with injected stub responses. It exercises the visual
input boundary and guarded action path without relying on unqualified temporal
poses or making live model-performance claims. The future model adapter/pilot
and any fresh passive P5 screen remain separate review checkpoints.
