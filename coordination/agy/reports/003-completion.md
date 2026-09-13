# AGY completion — task 003 (Revision addressing Codex Review Findings R1–R3)

Status: ready for review
Task brief: `coordination/agy/tasks/003-p5-preparation.md`
Codex review: `coordination/agy/reviews/003-review.md`
Branch: `agy/003-p5-preparation`
Starting commit: `55479a189af716316d133a9ca543f09934889726`
First submitted tip: `c711ff0152613c5175894df06c3bc701b4961108`

---

## 1. Finding-by-Finding Responses to Codex Review R1–R3

### R1 (High) — Rigorous Evidence Structure and Grid Validation; Zero False PASS
- **Review Finding:** Gate reporting could falsely certify incomplete/inconsistent evidence (e.g., empty records with stale passing summary, missing disruption streams, or `running` status defaulting to complete). Safety checks interpreted absent records as no emission.
- **Implemented Fixes:**
  - Implemented `validate_evidence_structure` in `humanoid_sim/p5_evaluation.py`, called before gate scoring.
  - Requires top-level and stream status to be explicitly `'complete'`. `running`, `incomplete`, or missing status immediately returns `is_complete=False` and `overall_outcome='INCOMPLETE'`.
  - For comparative envelopes, validates that required comparators (`baseline_p4`, `reacquisition_2frame`, `reacquisition_3frame`) are present and complete.
  - Enforces complete record grid validation: exactly 1 record per (seed, stage, variant) for all declared seeds ($10 \text{ seeds} \times 7 \text{ stages} \times 3 \text{ variants} = 210 \text{ records}$ for a full 10-seed screen). Missing, unexpected, or duplicate grid entries immediately return `INCOMPLETE`.
  - Inspects every record: status must be `'evaluated'`, ground truth must be valid 3D coordinates (`is_valid_truth_xyz`), and accepted estimates must have finite error values (`np.isfinite(error_3d_m)`).
  - Validates that all disruption variants (`black_transport`, `frozen_transport_rgb`) are present in the aggregate and records. Never certifies missing corruption or release cases from zero defaults.
  - Recomputes summary aggregates directly from validated records using `compute_aggregate(...)` and verifies strict numerical and count agreement against candidate summaries; mismatches immediately yield `INCOMPLETE`.
  - Disaggregates midpoint metrics cleanly without uncaught exceptions or formatting errors when metrics are `None` (e.g. all-refused).
- **Regressions Added:**
  - `test_successful_complete_synthetic_grid_passes_all_gates`: complete 210-record grid passing all gates.
  - `test_incomplete_evidence_empty_records_with_stale_passing_summary`: empty records with stale summary returns `INCOMPLETE`.
  - `test_incomplete_evidence_missing_variant_aggregates`: omitted disruption variants returns `INCOMPLETE`.
  - `test_incomplete_evidence_running_or_missing_status`: `running` or `None` status returns `INCOMPLETE`.
  - `test_incomplete_evidence_duplicate_grid_entries`: duplicate grid entries return `INCOMPLETE`.
  - `test_incomplete_evidence_missing_or_non_finite_truth_or_error`: missing ground truth or NaN/inf errors return `INCOMPLETE`.
  - `test_incomplete_evidence_summary_record_disagreement`: summary/record count or mean mismatch returns `INCOMPLETE`.
  - `test_all_refused_results_complete_grid`: complete grid with all refusals cleanly fails coverage/accuracy without formatting exceptions.

### R2 (High) — Unique Integer Seed Enforcement and Embedded Rescore Protection
- **Review Finding:** `validate_seeds_guard([820] * 10)` succeeded, inflating duplicate observations into 10 episodes. Rescore guarded CLI default seeds rather than seeds inside the loaded artifact; synthetic held-out metadata could reach gate computation.
- **Implemented Fixes:**
  - Strengthened `validate_seeds_guard` in `humanoid_sim/p5_evaluation.py`:
    - Materializes seeds into a list once and enforces `len(seeds_list) == len(set(seeds_list))` (duplicates forbidden).
    - Requires non-boolean integer types (`isinstance(s, bool)` rejected, `isinstance(s, int)` required).
    - Strictly rejects held-out seeds 840–849 (`HELD_OUT_SEEDS`) with clear error message.
    - Rejects out-of-scope seeds (outside 820–829) in development/executable mode.
  - In `run_rescore_command`:
    - Inspects embedded seeds in the loaded evidence artifact *first*.
    - Passes embedded seeds through `validate_seeds_guard(embedded_seeds, allow_non_development=False)` before any gate calculation or file output. Synthetic artifacts declaring 840–849 or duplicate seeds are immediately rejected with `ValueError` and no report is written.
    - If CLI seeds are explicitly supplied, verifies they match the artifact's embedded seeds (`set(cli_validated) == set(validated_embedded_seeds)`); mismatches raise `ValueError`. If not supplied, CLI adopts the artifact's validated embedded seeds.
  - Preserved subset dry run behavior: subsets (<10 seeds) are explicitly marked `not_applicable` for full-screen coverage/mean gates and result in `NOT_APPLICABLE_SUBSET`.
- **Regressions Added:**
  - `test_duplicate_seeds_forbidden`: duplicate seeds rejected.
  - `test_non_integer_seeds_forbidden`: boolean and non-integer types rejected.
  - `test_rescore_cli_rejects_embedded_held_out_seeds_without_writing_output`: rescore rejects embedded held-out seeds and writes no output file.
  - `test_rescore_cli_rejects_disagreeing_cli_seeds`: rescore rejects CLI seed mismatch and writes no output file.
  - `test_rescore_cli_succeeds_with_valid_artifact`: valid artifact rescore succeeds and writes output file.
  - `test_subset_dry_run_marks_gates_not_applicable`: subset dry run marks gates `not_applicable`.

### R3 (Medium) — Dependency Lock Provenance, Honest Source Snapshots, and Non-Executable Future Capture API Sketch
- **Review Finding:** Dependency lock hash was missing from preflight; rescore report omitted input hashes and producing source snapshot; manifest gave base commit without explaining uncommitted wrapper state; documented future CLI command `python -m humanoid_sim.perception_evaluation audit ... --protocol ...` was invalid.
- **Implemented Fixes:**
  - Added dependency lock hash (`requirements-lock.txt`: `2494fa442b86b7a4b6ff45602a5ca7b207225bb526fc148c49e85532ea9bd732`) and `requirements.txt` hash to `build_preflight_report`, `manifest.json`, and gate reports.
  - `compute_gate_report` records `evidence_sha256` (exact hash of rescored evidence), `evidence_path`, and `source_code_snapshot` containing git commit, dirty status, provenance note, and individual file hashes (`temporal_pose.py`, `temporal_reacquisition_evaluation.py`, `p5_evaluation.py`).
  - `manifest.json` clearly distinguishes optimizer evidence generation (`2026-09-13T01:46:12Z`) from report rescoring (`2026-09-13T02:27:00Z`), documents exact SHA-256 for all 4 artifact files, and explains the git provenance relationship relative to base commit `55479a1` and task branch `agy/003-p5-preparation`.
  - Replaced the invented future CLI command in `P5_REVISED_PROPOSAL.md` (Section 7), `p5_evaluation.py` (`FUTURE_CAPTURE_API_SKETCH`), and `--fresh-capture` refusal message with a clearly labeled, non-executable Python API sketch calling `audit(output=Path('runtime/humanoid/temporal-P5/capture'), seeds=range(840, 850), protocol=Path('experiments/humanoid-pick-place/protocols/P5_REVISED_PROPOSAL.md'), protocol_id='P5_capture')`.
  - Documented actual supported CLI modes (`--output`, `--start-seed`, `--count`) for `perception_evaluation.py` in Section 7.
- **Regressions Added:**
  - `test_preflight_report_generation`: asserts dependency lock hash, git provenance (head commit, dirty status), and non-executable Python API sketch.
  - `test_fresh_capture_flag_raises_error_with_future_sketch`: asserts `--fresh-capture` raises `RuntimeError` documenting the API sketch.

---

## 2. Validation and Execution Evidence

All commands executed in worktree `/private/tmp/mujoco-llms-agy-003` using interpreter `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`.

### Test Execution Summary
1. **Targeted Test Suite (41 Tests):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest tests/test_p5_evaluation.py tests/test_temporal_reacquisition_evaluation.py -v > coordination/agy/reports/003-targeted-tests.log 2>&1
   ```
   - **Outcome:** **41/41 passed in 35.762s**.
   - Retained log: `coordination/agy/reports/003-targeted-tests.log`.
2. **Full Repository Discovery (141 Tests):**
   ```sh
   /Users/praveen/work/github/mujoco-llms/.venv/bin/python -m unittest discover -s tests -v > coordination/agy/reports/003-full-discovery.log 2>&1
   ```
   - **Outcome:** **141/141 passed in 137.065s** across all repository test suites without regressions.
   - Retained log: `coordination/agy/reports/003-full-discovery.log`.

### Preflight and Rescore Artifact Generation
- Preflight report regenerated:
  `experiments/humanoid-pick-place/results/p5_preparation/preflight_report.json`
  - SHA-256: `e91f0d3c7b84c83c612810e33e215bcaa9df6f46b793825eaa13d825cfc5375e`
  - Records requirements lock SHA-256: `2494fa442b86b7a4b6ff45602a5ca7b207225bb526fc148c49e85532ea9bd732`
- Gate report rescore:
  `experiments/humanoid-pick-place/results/p5_preparation/gate_report_rescore.json`
  - SHA-256: `a7c7ec6c1b05d5a59994930ba21ddf8043f1e19c81004f0b7ecf553b3cf7eadc`
- Development gate report rescore:
  `experiments/humanoid-pick-place/results/p5_preparation/gate_report_development.json`
  - SHA-256: `738445c7587abbd502b290ff630e925f9f93ee77880fb36cf7f9de571331b856`
- Saved 10-seed optimizer development evidence (reused, not rerun):
  `experiments/humanoid-pick-place/results/p5_preparation/p5_development_evidence.json`
  - SHA-256: `fcc087663c3bca20d66299d116bcb7600cd1e22b2da700a794c984b8836bfb5f`
  - Generation timestamp: `2026-09-13T01:46:12Z`
- Provenance manifest updated:
  `experiments/humanoid-pick-place/results/p5_preparation/manifest.json`

---

## 3. Experiment Evidence and Gate Outcomes

### Evaluation Summary: Primary Condition (`TemporalThreeFrameReacquisitionPose` on Augmented Stream)
- Evaluated seeds: **820–829** (10 development episodes; held-out seeds 840–849 remain untouched).
- Source captures: `/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture` (read-only).
- Augmented cache: `/private/tmp/mujoco-llms-agy-002/runtime/humanoid/temporal-P4-augmented/capture` (read-only).
- Validated record grid: **210 records** ($10 \text{ seeds} \times 7 \text{ stages} \times 3 \text{ variants}$), zero missing or duplicate entries, all evaluated with valid ground truth and finite errors.

### Gate Report Across Development Seeds 820–829

| Gate | Description | Threshold | Numerator / Value | Denominator | Scored / Unscored | Status | Reason |
|---|---|---|---|---|---|---|---|
| **Gate 1** | Nominal post-warmup coverage | $\ge 16/20$ | 17 | 20 | 17 / 0 | **PASS** | Accepted 17/20 post-warmup targets ($\ge 16$ required) |
| **Gate 2** | Nominal post-warmup accuracy | $\le 5.0$ mm mean error | **5.8715 mm** | 17 | 17 / 0 | **FAIL** | Mean error 5.8715 mm exceeds 5.0 mm threshold (gate strictly preserved) |
| **Gate 3** | Maximum nominal error | $\le 20.0$ mm max error | 14.8479 mm | 24 | 24 / 0 | **PASS** | Maximum error 14.8479 mm $\le 20.0$ mm (midpoint max error: 5.1140 mm) |
| **Gate 4** | Relationship loss safety | 0 accepted on release/retract | 0 | 20 | 0 / 0 | **PASS** | 0/20 positions emitted on release or retract endpoints |
| **Gate 5** | Sensor disruption robustness | 0 accepted on corrupted transport | 0 | 20 | 0 / 0 | **PASS** | 0/20 positions emitted on corrupted transport frames |
| **Overall** | Continuation Screen | All 5 gates pass | 4 pass, 1 fail | — | Complete | **FAIL** | Failed accuracy gate (5.8715 mm > 5.0 mm) |

### Disaggregated Midpoint Metrics
- Accepted midpoint responses: **7 / 10**.
- Mean midpoint error: **3.1093 mm**.
- Maximum midpoint error: **5.1140 mm**.
- **Denominator Separation:** Midpoint responses do not enter the nominal post-warmup denominator ($N=20$) and do not dilute the original-target mean (which remains 5.8715 mm). All-accepted mean across all 24 nominal responses is 5.0659 mm.

### Disruption and Refusal Breakdown
- `black_transport`: 0 accepted across all 70 responses.
- `frozen_transport_rgb`: 0 accepted across all 70 responses.
- Refusals in nominal stream: 33 `insufficient_motion_history` (warmup and recovering stages), 13 `inconsistent_rigid_transform`.

---

## 4. Limitations and Recommendation

### Limitations
1. **Known Accuracy Gate Failure:** The accepted original-target mean on development trajectories is **5.8715 mm**, which exceeds the $\le 5.0$ mm gate. The gate was strictly preserved without relaxation.
2. **Development Data Only:** All evidence is from development trajectories (seeds 820–829). No held-out seeds (840–849) were executed, captured, or rendered.
3. **Kinematic Replay:** Midpoint observations rely on saved `qpos` kinematics; full dynamic integration velocities are marked unavailable.
4. **Control Disconnection:** Tracking remains strictly passive and disconnected from robot control.

### Recommendation for Next Checkpoint
- Proceed with Codex review of this revised preparation task (`003-p5-preparation`).
- Because development evidence shows an accepted-target mean of 5.8715 mm against a 5.0 mm gate, Codex should decide whether to:
  1. **Freeze and execute Protocol P5 on seeds 840–849 as an exploratory screen**, recognizing that a failed gate on held-out seeds is an informative, valid scientific outcome; or
  2. **Pause before consuming held-out seeds** to explore further estimator improvements (e.g. additional motion windows or feature improvements) if a $\le 5.0$ mm gate is a strict prerequisite.
