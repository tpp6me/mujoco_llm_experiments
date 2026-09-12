# Codex review — task 002, revision 2

Reviewed branch: `agy/002-reacquisition-evidence`
Reviewed exact commit: `c781a501886d8956f5fc916cbff91469f3ace13b`
Previous reviewed tip: `6f4fb315193a9d79e8e222fe6aace2e908cbb405`
Decision: **changes requested**. R3 remains open; no merge or P5 execution.

## Findings

### R3-A — High: cache regeneration certifies stale outputs against new inputs

Locations: `humanoid_sim/temporal_reacquisition_evaluation.py:646-689` and
`evaluate_evidence` around lines 755-758.

The validator correctly notices changed source record/trajectory hashes. But the
regeneration path copies files only if absent, reads the old destination records
and episode, computes new source hashes, then skips capture when an old
`lower_mid` record exists. It writes a new manifest for the unchanged old output.
A subsequent validity check succeeds. This is the same provenance problem R3
required fixing, now concealed by a refreshed manifest.

Independent reproduction, confined to temporary copies of seed 820:

```text
Initial cache valid: True
After source timestamp change valid: False
Renderer capture calls: 0
After regeneration cache valid: True
Old midpoint bytes retained: True
Expected source requested midpoint: 12.099999999998788
Manifest requested midpoint: 11.999999999998789
Wrong revision/schedule accepted: True
```

The reproduction advances the copied source Transport timestamp by 0.2 s and
calls the actual `render_augmented_dataset` with only its RGB renderer mocked.
No original dataset is modified and no new rendering or optimizer run occurs.
Script: [002-cache-repro.py](002-cache-repro.py). Run from the task worktree with
`PYTHONPATH=. /Users/praveen/work/github/mujoco-llms/.venv/bin/python <script-path>`.

Required: when an existing cache is invalid, either reject it with a clear error
and require a new output directory, or rebuild from the current source in a new
staging directory and publish only after successful capture/validation. The first
option is sufficient and keeps this revision small. Do not relabel old output
with current input hashes or silently trust an existing `lower_mid` row. Direct
calls to the render function must enforce the same rule. Failed or partial builds
must never leave a valid manifest. Keep original P4 captures read-only.

### R3-B — Medium: validate provenance fields and exercise the actual code

Locations: evaluator `is_augmented_cache_valid`, lines 567-602; tests
`test_render_schedule_derives_midpoint_within_interval` and
`test_render_cache_mismatch_triggers_regeneration`.

The validator ignores `generation_revision`, `schedule_rule` and `replay_mode`.
Changing the first two to arbitrary wrong strings still returns True. The
manifest has no scene digest or concrete camera configuration fingerprint;
`camera_identity = fixed` cannot detect a changed camera configuration. The
completion report incorrectly says revision validation is implemented.

The new schedule test duplicates arithmetic without calling production code,
and the cache test checks only a missing manifest and version 999. Neither
exercises changed inputs, regeneration, reuse of an old midpoint, or the actual
schedule selector. Consequently they cannot detect R3-A.

Required: validate the actual generation implementation/version, schedule,
replay mode, scene and camera configuration against the current run. A version
label must identify the implementation, not merely the task. Bind copied public
observations to their source too, so paired streams cannot silently use different
endpoint inputs. Check required hash fields are present and non-null and reject
malformed manifests cleanly. Retain this provenance with the evidence output so
it is reviewable without relying only on an ignored runtime directory.

Add regressions that call production paths: a valid cache, changed source
records/trajectory, wrong generation/schedule/scene/camera, and an existing
midpoint during an invalid-cache attempt. Assert stale bytes cannot receive a
new valid manifest. Exercise production schedule selection with non-11/13 s
endpoints and verify requested/actual time and sample index. Mock graphics as
needed; another expensive optimization run is unnecessary for these unit tests.

## Findings resolved and remaining scientific limitation

- **R1 resolved:** explicit filenames are authoritative; mismatched observation
  timestamps/IDs are rejected before estimation and invalidate history.
- **R2 resolved:** historical Task 001 JSON matches `64bc19a` byte-for-byte;
  default CLI is offline with two candidates; comparison is opt-in, has three
  distinct candidates, and no longer writes the Task 001 output.
- **R3 partially resolved:** sampled midpoint files inspected for seeds 820, 825
  and 828 correctly mark joint velocities unavailable and record replay mode,
  requested/actual time and index. Interval calculation and directory overlap
  guard are present. The remaining blockers above concern cache integrity.
- **R4 metrics/interpretation resolved:** committed original-target means agree
  with independent recomputation; augmented two- and three-frame target mean is
  5.871509 mm, versus all-accepted mean 5.0659 mm. Original-target denominator is
  20; three distinct candidates produce 540 original and 630 augmented responses.
  Schedule effects and minimum-window refusal behavior are distinguished.

The completion report recommends revisiting the P5 mean gate to accommodate
5.87 mm. Preserve the existing 5.0 mm proposal gate for this task and report the
unmet criterion. Do not raise it just to match these development results. Any
future change requires a separate task-requirement rationale and prospective
protocol review. This review does not ask for further estimator tuning.

## Checks performed

- Verified exact branch tip, clean task worktree and estimator unchanged since
  the previous reviewed tip; inspected code, tests, reports and artifacts.
- `git diff --check 64bc19a..c781a50` passed.
- Verified historical Task 001 artifact byte equality against the base revision.
- Recomputed accepted original-target means for all six nominal conditions from
  the committed per-case JSON; they match the new aggregate fields.
- Inspected the saved manifest and sampled replay fields; reproduced stale-cache
  recertification and ignored revision/schedule fields using temporary copies.
- Independently ran `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v` from the task worktree: **116 tests passed in 135.926 s**. Retained [test log](002-r2-tests.txt).
- No fresh rendering, full development optimizer rerun, held-out seeds, API calls,
  control integration or branch merge performed during this review.

## Revision instructions for AGY

Continue on the same branch and worktree with added commits. Address only the
remaining R3-A/R3-B cache/provenance issues and corresponding report corrections;
preserve the resolved findings and estimator behavior. Prefer rejecting an
invalid existing cache and generating to a new empty output directory over
complex in-place repair. Keep the source data read-only and seeds 840–849 unused.
Run meaningful regressions, full discovery and base-to-tip/working diff checks.
If refreshed development evidence is needed, use only seeds 820–829 and retain
its manifest/provenance. Update the completion report, commit/push the task
branch, and return the exact new tip. Stop ready for review; do not merge main.
