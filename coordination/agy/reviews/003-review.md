# Codex review — task 003

Date: 2026-09-13.
Reviewed branch: `agy/003-p5-preparation`.
Reviewed exact commit: `c711ff0152613c5175894df06c3bc701b4961108`.
Base: `55479a189af716316d133a9ca543f09934889726`.
Decision: **changes requested**. No merge or fresh P5 execution.

## R1 — High: gate reporting can certify incomplete or inconsistent evidence

Location: `humanoid_sim/p5_evaluation.py:206-354` (`compute_gate_report`).
Completeness relies on optional summary fields and defaults absent status to
`complete`. Missing variant aggregates are skipped. The record grid is not
validated, and safety checks interpret an absent record as no emission.

Independent reproduction: pass ten distinct development seeds, an `original`
aggregate claiming 20 accepted targets at 4 mm mean / 10 mm maximum, and
`records=[]`, omitting both disruption aggregates. The result is **PASS** with
`is_complete=True`, including both containment gates. Changing top-level status
to `running` still returns PASS. The positive synthetic test itself has only
seven records without seed IDs despite claiming a complete ten-seed dataset.

Required: validate the supported evidence structure before evaluating gates.
Require explicit completed status, all required variants, and exactly one
record per declared seed/stage/variant for each required condition. Detect
missing, duplicate and unexpected entries; inspect record status, truth and
finite scored values. Recompute gate metrics from validated records with the
accepted aggregation helper, or reject mismatches between records and supplied
summaries. Never certify a missing corruption/release case from zero defaults.
For a full comparison envelope, propagate incompleteness from required schedules
and comparators as specified by the protocol. Return actionable INCOMPLETE
results for malformed/partial evidence, without uncaught exceptions or PASS.

Add production regressions for empty/truncated records with stale passing
summaries, missing variants, running/missing status, duplicate grid entries,
missing/non-finite truth/error and summary/record disagreement. Replace the
partial positive fixture with a complete synthetic grid that passes for valid
reasons. Retain all-refused behavior with a complete grid: fail coverage/accuracy,
not a formatting exception. Preserve the real development mean failure.

## R2 — High: repeated seeds inflate episodes and rescore bypasses seed guard

Locations: `validate_seeds_guard`, `compute_gate_report` seed counting, and
`run_rescore_command` (around lines 55, 233 and 511).
`validate_seeds_guard([820] * 10)` succeeds, and `len(seeds)==10` then treats these
as a full screen. This can inflate repeated observations into ten episodes.
`--rescore` guards CLI default seeds, not the seeds inside the loaded artifact.
With a synthetic artifact declaring 840–849, the actual `run_rescore_command`
computes a gate report instead of rejecting it. This reproduction used fabricated
metadata only; no held-out capture or evidence was accessed.

Required: materialize seed lists once, require unique non-boolean integers and
validate the seed set at every executable/rescore boundary before scoring or
writing reports. Gate completeness must agree with the unique seed/grid set;
a full Task 003 development screen requires exactly 820–829. Subsets remain
explicitly not applicable for full-screen coverage/mean gates. Reject held-out
or out-of-scope seeds embedded in rescore inputs, not just CLI seed arguments.
A supplied CLI seed list must not silently disagree with the evidence seed list.
Add regressions through the production CLI/rescore paths, proving rejected
artifacts do not reach gate computation or write output. Preserve preflight's
read-only behavior and the fresh-capture refusal.

## R3 — Medium: finish reproducibility metadata and correct future command

Locations: preflight/rescore/manifest generation and
`P5_REVISED_PROPOSAL.md` section 7.
The task requires dependency hashes; preflight omits the dependency lock hash.
The standalone rescore report records an input path but not its content hash or
the report-producing source snapshot. The development manifest gives base commit
`55479a1`, where the new wrapper does not exist, without explaining the uncommitted
source state or binding its report/evidence files to hashes. The separate preflight
wrapper hash does match the final reviewed source, which is useful evidence;
make the provenance relationship explicit rather than implying the base commit
alone reproduces this run.

The documented future command, `python -m humanoid_sim.perception_evaluation audit
... --protocol ...`, is not supported by that module's argparse interface. It
accepts `--output`, `--start-seed` and `--count`, and its default protocol is P2.
Do not present this invented syntax as an executable reviewed P5 command.

Required: record the dependency lock hash and source/input/output hashes needed
to reproduce gate reporting, including the exact rescore input. Label uncommitted
source snapshots honestly and distinguish optimizer generation from later report
rescores. Refresh preflight/report manifests after final code/report edits without
rerunning optimization. Correct the future capture instructions: a clearly labeled
non-executable Python API sketch calling `audit` with explicit P5 protocol/id is
sufficient; actual fresh execution remains a future reviewed task. Add accurate
usage examples for currently supported modes and update the completion report.

## Checks performed

- Verified local and origin task refs at the exact reviewed tip and a clean task
  worktree; primary main checkout was unchanged at start of review.
- Inspected the wrapper, tests, proposed protocol, completion report and saved
  preflight/development artifacts. Historical estimator/evaluator code unchanged.
- `git diff --check 55479a1..c711ff0` passed.
- Reproduced false PASS for empty records/missing variants and for running status;
  reproduced duplicate-seed acceptance and held-out metadata accepted through
  rescore, using only synthetic temporary artifacts. No real held-out data used.
- Checked preflight's wrapper SHA-256 matches the reviewed file. The retained
  development artifact is complete and still reports 17/20 targets accepted,
  5.8715 mm original-target mean, and FAIL at the unchanged 5.0 mm threshold.
- Independently ran `/Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v` from the task worktree: **131 tests passed in 136.763 s**. [Retained log](003-tests.txt).
- This review did not rerun the 25-minute optimizer or access any fresh seeds.

## Direct revision instructions for AGY

Resume the same conversation/branch/worktree. Read this review and address R1–R3
in added commits, preserving the accepted estimators, numerical thresholds and
historical results. Reuse the completed development evidence; gate validation,
report formatting and metadata changes do not justify another full optimizer run.
Run meaningful targeted tests and full discovery, retain logs, refresh only affected
reports by rescore, and record exact provenance. Update `003-completion.md` with a
finding-by-finding response. Commit and push only the task branch, return exact
local/remote tip hashes, and stop ready for review. Do not merge main, run fresh P5,
change dependencies or touch held-out seeds. No model API experiments or hardware.
