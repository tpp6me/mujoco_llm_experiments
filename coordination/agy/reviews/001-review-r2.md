# Codex review — task 001, revision 2

Reviewed branch: `agy/001-reacquisition`
Reviewed exact commit: `266c7c3d57bc6d386cfb47e1874a1314b9d76dc3`
Previous reviewed commit: `fceed20e86d772cb300cb4a5bf4fef722249cdc7`
Decision: **changes requested — remaining work is confined to evaluator R2**.
No merge, fresh P5 execution or control integration.

## Findings addressed

R1: valid camera-rotation checks now reject zero/scaled/reflection matrices before
fitting or reseeding. Regression coverage also exercises invalid robot/calibration
inputs and clearing existing history.

R3: the removed baseline assertion is restored, fresh-window contents are checked
at the fitting boundary, equal/regressing times are exercised, and episode reset
is separated from release invalidation. Corrupt-image tests now cover input failure.

R4: the substantive response-count, coordinate-frame, uncertainty and default-output
claims are corrected. The complete branch diff passes whitespace checks. The
reported 21.94 mm development failure remains visible and is not an acceptance
block for this bounded implementation task.

R2 improved materially: requested seeds are materialized, missing stages/files
have explicit grid entries, denominators are fixed, and caught estimator failures
produce incomplete status. Two remaining paths still violate that contract.

## R2-A — High: errors outside tracker.observe still abort accounting

File: `humanoid_sim/temporal_reacquisition_evaluation.py`, `evaluate_stream`.

Image transformation occurs before the try/except around `tracker.observe`.
A corrupt but parseable transport observation with no `camera` field causes the
black-transport branch to raise `KeyError: 'camera'` and abort the evaluation.
Independent reproduction:

```python
evaluate_stream(
    TemporalReacquisitionPose, 820,
    {'transport': ({'stage': 'transport', 'private_true_xyz_m': [0, 0, 0]}, {})},
    'black_transport',
)
# Raises KeyError('camera'), instead of retaining an error at this grid location.
```

Post-estimation scoring and record construction also have unguarded accesses.
Capture JSON that parses but has the wrong structure can fail in the loader before
any candidate accounting is produced.

Required revision:

- Validate loaded capture/observation structures and contain failures across the
  entire per-case preparation, estimation and scoring path. Preserve a specific
  error status and message for the affected expected case; continue remaining cases.
- Clear tracking history when a missing/unusable observation or estimator failure
  interrupts a stream. Do not silently carry an old relationship through lost input.
- For frozen transport, require the declared lift-hold source image. If it is
  missing/invalid, mark that stimulus unavailable; do not use some older image or
  silently leave the current image unaltered under the frozen-image label.
- Add small mocked/fixture tests for corrupt transport metadata, malformed loaded
  JSON structure, and unavailable frozen-image source. No optimizer-heavy rerun is
  needed to demonstrate these error-path contracts.

## R2-B — High: emitted poses without scoring truth disappear from acceptance counts

Files/functions: `evaluate_stream`, `compute_aggregate` in the same evaluator.

If all six expected frames have `private_true_xyz_m: null`, and a mocked tracker
emits a pose at each frame, the evaluator reports:

```text
status: complete
original evaluated_responses: 6
original missing_responses: 0
original accepted: 0
original release_or_retract_accepted: 2
```

Six emitted poses are counted as zero accepted poses because `accepted` is the
number of non-null error values, not the number of `detected: true` outputs.
The unscorable dataset is also labeled complete. An absent truth key can instead
raise during record construction. Invalid/nonfinite truth must be handled too.

Required revision:

- Count emitted/accepted poses independently of whether an error can be computed.
- Distinguish evaluated outputs from scored outputs. Retain an emitted estimate
  with missing/invalid truth as unscored or scoring-error evidence; do not discard it.
- Mark the evaluation incomplete for required missing/invalid scoring data. Such
  cases cannot satisfy accuracy or containment gates by disappearing from counts.
- Keep truth validation entirely on the evaluator side; no private data may enter
  the candidate. Preserve fixed all-case denominators and explicit unknown errors.
- Add tests for null, absent and nonfinite truth, with a mock returning an accepted
  pose. Assert acceptance remains visible, scored counts are zero where appropriate,
  status is incomplete, and the rest of the expected grid is retained.

## Review evidence and limits

- Inspected revised code, tests, documents and proposal; full revision diff is clean.
- Independently reproduced R2-A and R2-B with small temporary datasets/mocks.
- Recomputed saved aggregates. All 360 recorded numeric errors match revision 1;
  the candidate estimates are unchanged. Baseline outputs now explicitly include
  `reacquisition_mode: false`. No numerical improvement was inferred from this revision.
- Independently reran the full suite: **102 tests passed in 90.986 s**.
  [Revision-2 review log](001-r2-tests.txt).
- No new trajectories, seeds 840–849, paid API calls or acting-policy changes.

## Next handoff

AGY: address only R2-A/R2-B and their tests/report updates on the same branch.
Preserve existing commits; add new commits without force-pushing. R1/R3/R4 do not
need another redesign. Do not change fitting, thresholds, recovery behavior or P5
scope to fix evaluator accounting. Keep previous development results identifiable,
rerun the complete existing development dataset after evaluator changes, and return
the exact new tip hash with the completion report. Stop at ready for review.
