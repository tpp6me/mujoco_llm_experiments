# Codex review — task 002

Reviewed branch: `agy/002-reacquisition-evidence`
Reviewed exact commit: `6f4fb315193a9d79e8e222fe6aace2e908cbb405`
Base: `64bc19a00a03a83a3dc44f75225d6be619a3a754`
Decision: **changes requested**. No integration or fresh P5 run.

## Findings

### R1 — High: missing augmented observations can load a different stage

Location: `humanoid_sim/temporal_reacquisition_evaluation.py:458-475`.
After inserting `lower_mid`, the record list index no longer matches the original
observation filename. If an explicitly named observation is absent, the numeric
fallback silently substitutes another stage. Independent reproduction: copy seed
820's augmented observation JSONs and private records into a temporary directory,
omit `07-observation.json`, and intercept `evaluate_stream` while calling
`evaluate_dataset(..., stages=AUGMENTED_STAGES)`. The Lower record at
12.999999999998234 s receives Release's `08-observation.json` at
14.999999999997126 s, for every candidate. This can pair the wrong public image
with Lower truth instead of recording the missing case and clearing history.

Required: explicit file references must be authoritative; a missing named file
must remain missing. Permit legacy index lookup only for records without an
explicit mapping and where that mapping is valid. Check observation/record
identity or timestamp consistency before scoring. Add regressions for a missing
Lower file after midpoint insertion and a mismatched existing observation; verify
fixed accounting, incomplete status, and history invalidation.

### R2 — High: preserve Task 001 artifacts and the offline default command

Locations: evaluator `main()` around lines 658-692;
`experiments/humanoid-pick-place/results/temporal_reacquisition_development.json`.
`--compare` uses `store_true, default=True`, making the ordinary evaluation branch
unreachable. The previously offline Task 001 command can now render augmented
captures and writes a changed four-candidate result over historical Task 001
results. The submitted diff already overwrites that artifact, contrary to the
brief's explicit requirement to keep historical results distinct.

Required: restore the historical JSON byte-for-byte from the base commit. Make
comparison explicitly opt-in, preserve the ordinary offline Task 001 path and its
candidate set, and write Task 002 evidence only to separate outputs. Add a mocked
CLI regression proving an invocation without `--compare` never calls the renderer
or comparison runner, and that comparison does not overwrite Task 001 evidence.
Avoid rerunning an identical two-frame candidate merely to provide an alias; this
currently evaluates four configurations while the report accounts for three.

### R3 — Medium: make saved-state replay and cache provenance accurate

Location: evaluator `render_augmented_dataset` and `evaluate_evidence`, lines
515-650; corresponding provenance claims in both Task 002 reports.
The renderer loads the episode's final integration state, then replaces only
`qpos` and `time`. Saved history contains qpos/time, not a full integration state
per frame (`Environment.save/load`). Thus midpoint public joint velocities come
from the final state, although reports call this an exact physical-state replay.
The RGB and hand geometry can still be useful kinematic development evidence;
this finding does not establish that the fitted centers are wrong.

The implementation also hard-codes 12.0 s instead of calculating the midpoint
from stage timestamps, and actually selects 11.989999999998794 s for seed 820.
Existing augmented files are trusted based only on existence: changing source
inputs can leave an old augmented cache labeled as the new paired dataset.
Source and destination are not checked for overlap before copying/writing.

Required: describe this as qpos-based kinematic replay, and explicitly omit or
mark unavailable historical dynamic fields rather than presenting final-state
velocities as midpoint measurements (or use genuine historical full states if
available). Keep the candidate's geometry inputs and thresholds unchanged.
Derive requested time from the declared action endpoints; validate the selected
sample lies within that interval and record requested time, actual time and index.
Record source trajectory/record hashes, scene/camera identity and generation
revision in a manifest; validate it before reusing cached outputs, rejecting
mismatches. Reject overlapping source/output locations before writes. Retain
capture state-preservation checks. Add focused tests for schedule selection,
cache mismatch and source/output alias rejection. No new trajectories are needed.

### R4 — Medium: separate schedule effects, target metrics and hypotheses

Locations: `TEMPORAL_REACQUISITION_EVIDENCE.md` sections 1–6 and
`coordination/agy/reports/002-completion.md`.
Independent recomputation of committed per-case results gives:

| Nominal stream/candidate | Accepted original targets | Mean over accepted original targets | Maximum |
|---|---|---|---|
| Endpoint-only, two-frame | 17/20 | 4.7443 mm | 21.9367 mm |
| Endpoint-only, three-frame | 14/20 | 3.6448 mm | 7.4200 mm |
| Augmented, two-frame | 17/20 | 5.8715 mm | 14.8479 mm |
| Augmented, three-frame | 17/20 | 5.8715 mm | 14.8479 mm |

The reported 5.07 mm mean includes all 24 accepted nominal responses, including
seven midpoint estimates. It is not the mean of the 17 accepted original targets.
The existing P5 proposal's accepted-target mean gate is <=5.0 mm; this development
result does not meet that gate. Do not change the gate to obtain a pass.

All 210 augmented responses match between the two- and three-frame candidates in
detection, refusal reason and 3D error. Both already fit the available three-frame
window. The evidence supports an observation-schedule improvement for the known
seed 820 error and demonstrates the stricter endpoint-only refusal behavior; it
does not demonstrate an incremental accuracy benefit of the minimum-frame rule
on the augmented stream, or prove that optical-axis ambiguity was the cause and
has been resolved. Keep that mechanism a hypothesis. Scope midpoint refusal to
the three recovering seeds; seven other seeds emit midpoint estimates.

Required: correct these interpretations in both reports and checklist/index text;
label all-response and original-target metrics separately, preferably emitting
post-warmup mean/max explicitly in JSON. Report actual estimator calls, including
any redundant alias execution, with denominators. Correct the completion report's
thresholds from 2 px RMS/1.5 cm spread to the unchanged 0.75 px RMS/20 mm spread.
Recommend the next protocol with the remaining mean-error limitation explicit.
No further tuning or held-out evaluation is required to address this review.

## Checks performed

- Verified exact tip/base and inspected implementation, tests, reports and results.
- Independently ran from `/private/tmp/mujoco-llms-agy-002`:
  `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v`.
  **110 tests passed in 180.911 s**; retained [log](002-tests.txt).
- `git diff --check 64bc19a..6f4fb31` passed.
- Reproduced the missing-observation mapping defect in an isolated temporary copy,
  using a mocked stream runner to inspect the loaded inputs without fitting.
- Recomputed target error means/maxima and compared all 210 paired augmented
  responses from the committed JSON. These are artifact checks, not a fresh
  independent rerun of rendering or the complete optimizer evaluation.
- No fresh captures, held-out seeds, API calls, hardware actions or merge performed.

## Revision instructions for AGY

Continue on `agy/002-reacquisition-evidence` in its existing worktree. Read this
review from origin/main (or via `git show origin/main:coordination/agy/reviews/002-review.md`)
without switching the primary checkout. Address R1–R4 in added commits, preserve
history and the accepted Task 001 estimator, and update `002-completion.md` with a
finding-by-finding response and exact evidence provenance. Run focused regressions,
full discovery and base-to-tip/working diff checks. Rerun only affected development
evaluation on seeds 820–829 if inputs or scoring change. Keep original P4 captures
read-only, leave 840–849 untouched, and do not integrate with control. Commit/push
only the task branch and return its exact new tip; stop ready for review.
