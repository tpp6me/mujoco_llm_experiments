# Codex acceptance — task 002

Date: 2026-09-13.
Reviewed exact tip: `a351053f6c933d82380a611121989c008a26eafa`.
Branch: `agy/002-reacquisition-evidence`.
Decision: **accepted for development-only integration**.
The merge containing this record retains the complete AGY revision history.
Earlier reviews remain historical records of the corresponding tips.

## Findings closed

- R1: explicit observation mappings are authoritative. Missing or mismatched
  observations retain their grid entry and invalidate tracking history.
- R2: Task 001's historical result JSON is byte-identical to base `64bc19a`.
  Its default command remains offline. Comparison is opt-in and writes separate
  Task 002 evidence, evaluating three distinct candidates without a duplicate alias.
- R3-A: direct rendering requires a new/empty directory. Evaluation rejects an
  invalid non-empty cache. The former midpoint skip and stale recertification
  path are removed; a manifest is written after successful generation completes.
- R3-B: production schedule selection is tested with different endpoints; cache
  validation checks generation/schedule/replay identifiers, declared camera
  configuration, scene and source hashes, and copied source observations. The
  manifest is embedded in the committed evidence. Kinematic replay explicitly
  marks historical joint velocities unavailable.
- R4: original-target means and maxima are separate from all-accepted metrics;
  schedule improvement is distinguished from the stricter minimum-window refusal
  rule. The 5.0 mm mean criterion remains unchanged and unmet on development data.

The handoff/completion report incorrectly described a head camera at 640x480.
The actual implementation, embedded manifest and all ten midpoint observations
use the fixed 960x720 camera with lookat [0.24, -0.24, 0.8], distance 1.35,
azimuth 90 and elevation -65. Codex corrected that report text during integration;
no estimator, capture code, input or numeric evidence changed in integration.

## Independent verification

- Full suite run in `/private/tmp/mujoco-llms-agy-002` using
  `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v`:
  **118 tests passed in 162.015 s**. [Retained log](002-r3-tests.txt).
- Repeated the stale-cache scenario using temporary copies of seed 820: changed
  source Transport time by 0.2 s; both direct rendering and evidence evaluation
  rejected the old output. Old manifest/midpoint bytes stayed unchanged and the
  cache remained invalid. No renderer was invoked.
- Validated the full runtime cache for seeds 820–829 and verified its manifest
  equals the embedded committed manifest, including source-observation hashes.
- Checked all ten midpoint observations: 960x720, actual time
  11.989999999998794 s, historical joint velocities unavailable. Requested time is
  approximately 12.0 s; these are saved qpos samples, not full dynamic-state replay.
- Confirmed historical Task 001 artifact byte equality and a clean
  `git diff --check 64bc19a..a351053`. The estimator is unchanged since the first
  Task 002 reviewed tip. Integration changes are documentation/coordination only.
- Confirmed retained nominal aggregate results and their declared denominators.
  This review validated artifacts/cache and ran tests; it did not independently
  regenerate all RGB captures or rerun all 1,170 development estimates.

## Accepted result and limits

On the augmented development schedule, both reacquisition candidates accept
17/20 original Transport/Lower targets, all within 20 mm. Accepted original-target
mean is 5.871509 mm and maximum is 14.847913 mm. All-accepted mean, including seven
additional midpoint estimates, is 5.0659 mm. The midpoint reduces seed 820's known
21.9367 mm error, while both candidates behave identically on the augmented stream.
The three-frame rule additionally refuses three endpoint-only recovery cases.
This does not prove the depth-error mechanism or an incremental augmented-stream
accuracy benefit of the minimum-frame rule.

No carried-pose qualification, control integration, fresh P5 execution, model API
experiment or real-time controller performance is approved by this acceptance.
The prior proposed 5.0 mm target mean gate remains unmet. Seeds 840–849 remain
reserved for a separately reviewed and frozen experiment.

## Next checkpoint

[Task 003](../tasks/003-p5-preparation.md) prepares a revised passive P5 proposal
and a small preflight/gate-report runner using existing development inputs. It
must retain the failed mean criterion, keep historical evidence unchanged and
stop for review before any held-out capture or evaluation.
