"""Unit tests for P5 preparation, preflight wrapper, and gate evaluation logic."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from humanoid_sim.temporal_reacquisition_evaluation import (
    AUGMENTED_STAGES, EXPECTED_VARIANTS, NOMINAL_POST_WARMUP_STAGES, compute_aggregate
)
from humanoid_sim.p5_evaluation import (
    HELD_OUT_SEEDS, DEVELOPMENT_SEEDS, PRIMARY_CANDIDATE,
    GATE_MIN_COVERAGE_TARGETS, GATE_TOTAL_TARGETS,
    GATE_MAX_MEAN_ERROR_M, GATE_MAX_NOMINAL_ERROR_M,
    validate_seeds_guard, build_preflight_report,
    compute_gate_report, run_rescore_command, main,
    TASK_002_EVIDENCE_PATH, FUTURE_CAPTURE_API_SKETCH
)


def make_synthetic_evidence(
    seeds=None,
    candidate_name=PRIMARY_CANDIDATE,
    nominal_detections=None,
    corrupted_transport_accepted=0,
    release_retract_accepted=0,
    status='complete',
    records_override=None,
    aggregate_override=None,
    omit_disruption_aggregates=False,
    duplicate_grid_entry=False,
    non_finite_error=False,
    missing_truth=False,
):
    """Build a complete, mathematically consistent synthetic evidence dictionary.

    Default configuration produces a fully complete, valid grid (len(seeds) x 7 stages x 3 variants)
    that passes all 5 evaluation gates.
    """
    if seeds is None:
        seeds = list(range(820, 830))
    else:
        seeds = list(seeds)

    if nominal_detections is None:
        nominal_detections = {
            'transport': (True, 0.0040),
            'lower': (True, 0.0040),
            'lower_mid': (True, 0.0035),
        }

    corrupt_rem = corrupted_transport_accepted
    rel_ret_rem = release_retract_accepted
    records = []

    for s in seeds:
        for st in AUGMENTED_STAGES:
            for v in EXPECTED_VARIANTS:
                truth = [0.1, 0.2, 0.3]
                if v == 'original':
                    if st in ('release', 'retract') and rel_ret_rem > 0:
                        detected = True
                        err = 0.010
                        rel_ret_rem -= 1
                    else:
                        detected, err = nominal_detections.get(st, (False, None))
                else:
                    if st == 'transport' and corrupt_rem > 0:
                        detected = True
                        err = 0.050
                        corrupt_rem -= 1
                    else:
                        detected = False
                        err = None

                if missing_truth and s == seeds[0] and st == 'lower' and v == 'original':
                    truth = None
                if non_finite_error and s == seeds[0] and st == 'lower' and v == 'original':
                    err = float('nan')

                rec = {
                    'seed': s,
                    'stage': st,
                    'variant': v,
                    'status': 'evaluated',
                    'private_true_xyz_m': truth,
                    'estimate': {
                        'detected': detected,
                        'pose_xyz_m': [0.1, 0.2, 0.3] if detected else None,
                        'reason': 'insufficient_motion_history' if not detected else None,
                    },
                    'error_3d_m': err,
                }
                records.append(rec)
                if duplicate_grid_entry and s == seeds[0] and st == 'lower' and v == 'original':
                    records.append(dict(rec))

    if records_override is not None:
        records = records_override

    if aggregate_override is not None:
        agg = aggregate_override
    else:
        agg = compute_aggregate(records, seeds, stages=AUGMENTED_STAGES, post_warmup_stages=NOMINAL_POST_WARMUP_STAGES)
        if omit_disruption_aggregates:
            agg = {'original': agg['original']}

    return {
        'status': status,
        'seeds': seeds,
        'augmented_stream': {
            'status': status,
            'seeds': seeds,
            'candidates': {
                candidate_name: {
                    'aggregate': agg,
                    'records': records,
                }
            }
        }
    }


class TestP5Evaluation(unittest.TestCase):

    def test_held_out_seeds_strictly_forbidden(self):
        """Held-out validation seeds 840-849 must be rejected immediately."""
        for seed in [840, 845, 849]:
            with self.assertRaisesRegex(ValueError, "held-out seed.*strictly forbidden"):
                validate_seeds_guard([seed])
        with self.assertRaisesRegex(ValueError, "held-out seed.*strictly forbidden"):
            validate_seeds_guard(range(840, 850))

    def test_duplicate_seeds_forbidden(self):
        """Duplicate seeds must be rejected to prevent episode count inflation (R2)."""
        with self.assertRaisesRegex(ValueError, "Duplicate seeds are forbidden"):
            validate_seeds_guard([820, 820])
        with self.assertRaisesRegex(ValueError, "Duplicate seeds are forbidden"):
            validate_seeds_guard([820] * 10)

    def test_non_integer_seeds_forbidden(self):
        """Non-integer types and booleans must be rejected as invalid seeds (R2)."""
        for bad in [[True], [False], [820.5], ['820'], [None]]:
            with self.assertRaisesRegex(ValueError, "Seed must be an integer"):
                validate_seeds_guard(bad)

    def test_non_development_seeds_rejected_in_executable_mode(self):
        """Seeds outside 820-829 are rejected in executable development mode."""
        with self.assertRaisesRegex(ValueError, "outside authorized development seeds"):
            validate_seeds_guard([800])
        with self.assertRaisesRegex(ValueError, "outside authorized development seeds"):
            validate_seeds_guard([900])
        with self.assertRaisesRegex(ValueError, "non-empty"):
            validate_seeds_guard([])

    def test_known_development_failure_at_unchanged_gate(self):
        """Known 5.8715 mm post-warmup mean must fail the strictly preserved 5.0 mm gate."""
        evidence_file = Path(TASK_002_EVIDENCE_PATH)
        self.assertTrue(evidence_file.is_file(), f"Missing evidence file: {evidence_file}")
        evidence = json.loads(evidence_file.read_text())

        report = compute_gate_report(evidence, candidate_name=PRIMARY_CANDIDATE, is_rescore=True)

        self.assertEqual(report['candidate'], PRIMARY_CANDIDATE)
        self.assertEqual(report['seed_count'], 10)
        self.assertTrue(report['is_complete'])

        gates = report['gates']
        # Gate 1: Coverage passes (17/20 >= 16)
        self.assertEqual(gates['gate_1_coverage']['status'], 'pass')
        self.assertEqual(gates['gate_1_coverage']['numerator'], 17)
        self.assertEqual(gates['gate_1_coverage']['denominator'], 20)

        # Gate 2: Accuracy FAILS at unchanged 5.0 mm gate (5.8715 mm > 5.0 mm)
        self.assertEqual(gates['gate_2_accuracy']['status'], 'fail')
        self.assertAlmostEqual(gates['gate_2_accuracy']['metric_value_mm'], 5.871509, places=4)
        self.assertEqual(gates['gate_2_accuracy']['threshold_mm'], 5.0)
        self.assertIn("exceeds 5.0 mm threshold", gates['gate_2_accuracy']['reason'])

        # Gate 3: Maximum error passes (14.8479 mm <= 20.0 mm)
        self.assertEqual(gates['gate_3_nominal_max_error']['status'], 'pass')
        self.assertAlmostEqual(gates['gate_3_nominal_max_error']['metric_value_mm'], 14.847913, places=4)
        self.assertAlmostEqual(gates['gate_3_nominal_max_error']['midpoint_max_error_mm'], 5.113997, places=4)

        # Gate 4: Release/retract safety passes (0/20)
        self.assertEqual(gates['gate_4_relationship_loss_safety']['status'], 'pass')
        self.assertEqual(gates['gate_4_relationship_loss_safety']['accepted_count'], 0)

        # Gate 5: Disruption robustness passes (0/20)
        self.assertEqual(gates['gate_5_disruption_robustness']['status'], 'pass')
        self.assertEqual(gates['gate_5_disruption_robustness']['corrupted_transport_accepted'], 0)

        # Overall outcome must be FAIL
        self.assertEqual(report['overall_outcome'], 'FAIL')
        self.assertIn("accuracy", report['overall_reason'])

    def test_successful_complete_synthetic_grid_passes_all_gates(self):
        """Complete 210-record synthetic grid meeting all criteria must result in PASS (R1)."""
        synthetic_evidence = make_synthetic_evidence()
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertTrue(report['is_complete'])
        self.assertEqual(report['overall_outcome'], 'PASS')
        self.assertEqual(report['gates']['gate_1_coverage']['status'], 'pass')
        self.assertEqual(report['gates']['gate_2_accuracy']['status'], 'pass')
        self.assertEqual(report['gates']['gate_3_nominal_max_error']['status'], 'pass')
        self.assertEqual(report['gates']['gate_4_relationship_loss_safety']['status'], 'pass')
        self.assertEqual(report['gates']['gate_5_disruption_robustness']['status'], 'pass')

    def test_incomplete_evidence_empty_records_with_stale_passing_summary(self):
        """Empty or truncated records with stale passing summary must return INCOMPLETE (R1)."""
        synthetic_evidence = make_synthetic_evidence(records_override=[])
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertFalse(report['is_complete'])
        self.assertEqual(report['overall_outcome'], 'INCOMPLETE')
        self.assertIn("Candidate 'records' list is empty or invalid", report['overall_reason'])
        for gate_name, gate in report['gates'].items():
            self.assertEqual(gate['status'], 'incomplete')

    def test_incomplete_evidence_missing_variant_aggregates(self):
        """Candidate aggregate missing required disruption variants must return INCOMPLETE (R1)."""
        synthetic_evidence = make_synthetic_evidence(omit_disruption_aggregates=True)
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertFalse(report['is_complete'])
        self.assertEqual(report['overall_outcome'], 'INCOMPLETE')
        self.assertIn("missing required disruption variant", report['overall_reason'])

    def test_incomplete_evidence_running_or_missing_status(self):
        """Non-complete status (running, missing, incomplete) must return INCOMPLETE (R1)."""
        for bad_status in ['running', 'incomplete', None, 'pending']:
            synthetic_evidence = make_synthetic_evidence(status=bad_status)
            report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

            self.assertFalse(report['is_complete'])
            self.assertEqual(report['overall_outcome'], 'INCOMPLETE')
            self.assertIn("expected 'complete'", report['overall_reason'])

    def test_incomplete_evidence_duplicate_grid_entries(self):
        """Duplicate (seed, stage, variant) entries in records must return INCOMPLETE (R1)."""
        synthetic_evidence = make_synthetic_evidence(duplicate_grid_entry=True)
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertFalse(report['is_complete'])
        self.assertEqual(report['overall_outcome'], 'INCOMPLETE')
        self.assertIn("does not match expected grid count", report['overall_reason'])

    def test_incomplete_evidence_missing_or_non_finite_truth_or_error(self):
        """Records with missing ground truth or non-finite error values must return INCOMPLETE (R1)."""
        # Non-finite error
        ev_nan = make_synthetic_evidence(non_finite_error=True)
        rep_nan = compute_gate_report(ev_nan, candidate_name=PRIMARY_CANDIDATE)
        self.assertFalse(rep_nan['is_complete'])
        self.assertEqual(rep_nan['overall_outcome'], 'INCOMPLETE')
        self.assertIn("non-finite error_3d_m", rep_nan['overall_reason'])

        # Missing ground truth
        ev_truth = make_synthetic_evidence(missing_truth=True)
        rep_truth = compute_gate_report(ev_truth, candidate_name=PRIMARY_CANDIDATE)
        self.assertFalse(rep_truth['is_complete'])
        self.assertEqual(rep_truth['overall_outcome'], 'INCOMPLETE')
        self.assertIn("missing/invalid truth", rep_truth['overall_reason'])

    def test_incomplete_evidence_summary_record_disagreement(self):
        """Mismatches between record data and claimed summaries must return INCOMPLETE (R1)."""
        ev = make_synthetic_evidence()
        # Artificially alter summary aggregate to disagree with records
        ev['augmented_stream']['candidates'][PRIMARY_CANDIDATE]['aggregate']['original']['accepted'] = 999
        report = compute_gate_report(ev, candidate_name=PRIMARY_CANDIDATE)

        self.assertFalse(report['is_complete'])
        self.assertEqual(report['overall_outcome'], 'INCOMPLETE')
        self.assertIn("disagrees with records", report['overall_reason'])

    def test_all_refused_results_complete_grid(self):
        """Complete grid with all-refused results must fail coverage/accuracy without exception (R1)."""
        synthetic_evidence = make_synthetic_evidence(nominal_detections={})
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertTrue(report['is_complete'])
        self.assertEqual(report['gates']['gate_1_coverage']['status'], 'fail')
        self.assertEqual(report['gates']['gate_2_accuracy']['status'], 'fail')
        self.assertEqual(report['gates']['gate_3_nominal_max_error']['status'], 'fail')
        self.assertEqual(report['gates']['gate_4_relationship_loss_safety']['status'], 'pass')
        self.assertEqual(report['gates']['gate_5_disruption_robustness']['status'], 'pass')
        self.assertEqual(report['overall_outcome'], 'FAIL')
        self.assertIn("accuracy (zero accepted post-warmup targets)", report['overall_reason'])

    def test_midpoint_denominator_separation(self):
        """Midpoint estimates must never dilute or enlarge the original-target denominator."""
        evidence_file = Path(TASK_002_EVIDENCE_PATH)
        evidence = json.loads(evidence_file.read_text())
        report = compute_gate_report(evidence, candidate_name=PRIMARY_CANDIDATE)

        # Gate 1 post-warmup denominator is strictly 20 (not 30)
        self.assertEqual(report['gates']['gate_1_coverage']['denominator'], 20)

        # Gate 2 denominator is strictly the accepted original targets (17, not 24)
        self.assertEqual(report['gates']['gate_2_accuracy']['denominator_accepted_original_targets'], 17)

        # The evaluated mean must be 5.8715 mm (original targets), NOT 5.0659 mm (all-accepted)
        self.assertAlmostEqual(report['gates']['gate_2_accuracy']['metric_value_mm'], 5.871509, places=4)
        all_mean = report['descriptive_metrics']['all_accepted_metrics']['all_accepted_mean_error_mm']
        self.assertAlmostEqual(all_mean, 5.065868, places=4)
        self.assertNotEqual(report['gates']['gate_2_accuracy']['metric_value_mm'], all_mean)

        # Descriptive metrics isolate midpoint
        mid = report['descriptive_metrics']['midpoint_metrics']
        self.assertEqual(mid['midpoint_accepted'], 7)
        self.assertAlmostEqual(mid['midpoint_mean_error_mm'], 3.109311, places=4)
        self.assertAlmostEqual(mid['midpoint_max_error_mm'], 5.113997, places=4)

    def test_subset_dry_run_marks_gates_not_applicable(self):
        """Subset dry runs (<10 seeds) must mark gates not_applicable rather than passing/failing (R2)."""
        single_seed_evidence = make_synthetic_evidence(seeds=[820])
        report = compute_gate_report(single_seed_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertEqual(report['seed_count'], 1)
        self.assertEqual(report['gates']['gate_1_coverage']['status'], 'not_applicable')
        self.assertEqual(report['gates']['gate_2_accuracy']['status'], 'not_applicable')
        self.assertEqual(report['overall_outcome'], 'NOT_APPLICABLE_SUBSET')

    def test_corrupted_transport_emission_fails_gate_5(self):
        """Accepted pose on corrupted transport frame must fail Gate 5."""
        synthetic_evidence = make_synthetic_evidence(corrupted_transport_accepted=1)
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertEqual(report['gates']['gate_5_disruption_robustness']['status'], 'fail')
        self.assertEqual(report['overall_outcome'], 'FAIL')

    def test_release_retract_emission_fails_gate_4(self):
        """Accepted pose on release/retract endpoint must fail Gate 4."""
        synthetic_evidence = make_synthetic_evidence(release_retract_accepted=1)
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertEqual(report['gates']['gate_4_relationship_loss_safety']['status'], 'fail')
        self.assertEqual(report['overall_outcome'], 'FAIL')

    def test_max_error_exceeding_20mm_fails_gate_3(self):
        """Accepted nominal error exceeding 20.0 mm must fail Gate 3."""
        synthetic_evidence = make_synthetic_evidence(
            nominal_detections={'transport': (True, 0.0250), 'lower': (True, 0.0040), 'lower_mid': (True, 0.0035)}
        )
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)

        self.assertEqual(report['gates']['gate_3_nominal_max_error']['status'], 'fail')
        self.assertEqual(report['overall_outcome'], 'FAIL')

    def test_preflight_report_generation(self):
        """Preflight report must document dependency hashes, git provenance, and future sketch (R3)."""
        report = build_preflight_report(
            source_capture_dir='/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture',
            augmented_capture_dir='/private/tmp/mujoco-llms-agy-002/runtime/humanoid/temporal-P4-augmented/capture',
            seeds=list(range(820, 830))
        )
        self.assertEqual(report['status'], 'development_preparation')
        self.assertFalse(report['fresh_validation_executed'])
        self.assertFalse(report['held_out_seeds_touched'])
        self.assertIn('audit(', report['future_capture_api_sketch'])
        self.assertIn('DO NOT RUN IN TASK 003', report['future_capture_api_sketch'])

        # Dependency lock hash check
        dep_hashes = report['provenance_hashes']['dependency_hashes']
        self.assertIn('requirements_lock_sha256', dep_hashes)
        self.assertIn('requirements_txt_sha256', dep_hashes)

        # Git provenance check
        git_prov = report['git_provenance']
        self.assertIn('head_commit', git_prov)
        self.assertIn('is_dirty', git_prov)
        self.assertIn('provenance_note', git_prov)

        hashes = report['provenance_hashes']
        self.assertIsNotNone(hashes['scene_sha256'])
        self.assertIsNotNone(hashes['protocol_revised_sha256'])
        self.assertIsNotNone(hashes['protocol_historical_sha256'])
        self.assertIn('temporal_pose.py', hashes['code_sha256'])
        self.assertIn('p5_evaluation.py', hashes['code_sha256'])

    def test_rescore_cli_rejects_embedded_held_out_seeds_without_writing_output(self):
        """Rescore command must reject embedded held-out seeds before scoring or writing output (R2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            held_out_art = tmp_path / "held_out_evidence.json"
            held_out_art.write_text(json.dumps({'status': 'complete', 'seeds': list(range(840, 850))}))

            out_dir = tmp_path / "out"
            args = argparse.Namespace(
                rescore=held_out_art,
                candidate=PRIMARY_CANDIDATE,
                output_dir=out_dir,
                report_name='gate_report_rescore.json',
                root_dir=None,
                seeds=None,
                start_seed=None,
                count=None,
                seeds_explicitly_set=False
            )
            with self.assertRaisesRegex(ValueError, "held-out seed 840.*strictly forbidden"):
                run_rescore_command(args)

            self.assertFalse((out_dir / "gate_report_rescore.json").exists())

    def test_rescore_cli_rejects_disagreeing_cli_seeds(self):
        """Rescore command must reject CLI seeds that disagree with embedded artifact seeds (R2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            valid_art = tmp_path / "valid_evidence.json"
            valid_art.write_text(json.dumps({'status': 'complete', 'seeds': list(range(820, 830))}))

            out_dir = tmp_path / "out"
            args = argparse.Namespace(
                rescore=valid_art,
                candidate=PRIMARY_CANDIDATE,
                output_dir=out_dir,
                report_name='gate_report_rescore.json',
                root_dir=None,
                seeds=[820, 821],
                start_seed=None,
                count=None,
                seeds_explicitly_set=True
            )
            with self.assertRaisesRegex(ValueError, "Supplied CLI seeds.*do not match evidence artifact seeds"):
                run_rescore_command(args)

            self.assertFalse((out_dir / "gate_report_rescore.json").exists())

    def test_rescore_cli_succeeds_with_valid_artifact(self):
        """Rescore command succeeds on valid complete evidence artifact and writes report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            valid_art = tmp_path / "valid_evidence.json"
            ev = make_synthetic_evidence(seeds=range(820, 830))
            valid_art.write_text(json.dumps(ev))

            out_dir = tmp_path / "out"
            args = argparse.Namespace(
                rescore=valid_art,
                candidate=PRIMARY_CANDIDATE,
                output_dir=out_dir,
                report_name='gate_report_rescore.json',
                root_dir=None,
                seeds=None,
                start_seed=None,
                count=None,
                seeds_explicitly_set=False
            )
            rep = run_rescore_command(args)

            report_file = out_dir / "gate_report_rescore.json"
            self.assertTrue(report_file.is_file())
            self.assertEqual(rep['overall_outcome'], 'PASS')

    def test_fresh_capture_flag_raises_error_with_future_sketch(self):
        """CLI with --fresh-capture must raise RuntimeError documenting the future API sketch (R3)."""
        import sys
        with patch.object(sys, 'argv', ['p5_evaluation', '--fresh-capture']):
            with self.assertRaisesRegex(RuntimeError, "Fresh capture is disabled in Task 003"):
                main()


class TestP5IntegrationIntegrity(unittest.TestCase):
    def test_full_comparison_requires_all_conditions_and_consistent_seeds(self):
        evidence = json.loads(Path(TASK_002_EVIDENCE_PATH).read_text())
        for stream, candidate in (
            ('original_stream', 'baseline_p4'),
            ('original_stream', 'reacquisition_3frame'),
            ('augmented_stream', 'reacquisition_2frame'),
        ):
            for modification in ('remove', 'truncate'):
                with self.subTest(stream=stream, candidate=candidate, modification=modification):
                    changed = copy.deepcopy(evidence)
                    candidates = changed[stream]['candidates']
                    if modification == 'remove':
                        del candidates[candidate]
                    else:
                        candidates[candidate]['records'].pop()
                    self.assertEqual(compute_gate_report(changed)['overall_outcome'], 'INCOMPLETE')
        changed = copy.deepcopy(evidence)
        changed['augmented_stream']['seeds'] = [820]
        self.assertEqual(compute_gate_report(changed)['overall_outcome'], 'INCOMPLETE')

    def test_malformed_numeric_records_and_metadata_return_incomplete(self):
        for invalid_error in ('bad', [0.004], {'value': 0.004}, -0.001, True):
            with self.subTest(error=invalid_error):
                evidence = make_synthetic_evidence()
                rows = evidence['augmented_stream']['candidates'][PRIMARY_CANDIDATE]['records']
                next(row for row in rows if row['estimate']['detected'])['error_3d_m'] = invalid_error
                self.assertEqual(compute_gate_report(evidence)['overall_outcome'], 'INCOMPLETE')
        evidence = make_synthetic_evidence()
        evidence['seeds'] = 820
        self.assertEqual(compute_gate_report(evidence)['overall_outcome'], 'INCOMPLETE')
        evidence = make_synthetic_evidence()
        evidence['augmented_stream']['candidates'][PRIMARY_CANDIDATE]['aggregate']['original']['missing_responses'] = None
        self.assertEqual(compute_gate_report(evidence)['overall_outcome'], 'INCOMPLETE')

    def test_rounded_summary_cannot_mask_threshold_failure(self):
        evidence = make_synthetic_evidence(nominal_detections={
            'transport': (True, .004), 'lower': (True, .004),
            'lower_mid': (True, .0200005),
        })
        self.assertEqual(compute_gate_report(evidence)['gates']['gate_3_nominal_max_error']['status'], 'fail')
        evidence['augmented_stream']['candidates'][PRIMARY_CANDIDATE]['aggregate']['original']['accepted_max_error_m'] = .02
        self.assertEqual(compute_gate_report(evidence)['overall_outcome'], 'INCOMPLETE')

    def test_nested_held_out_metadata_rejected_before_scoring(self):
        evidence = make_synthetic_evidence()
        evidence['augmented_stream']['seeds'] = list(range(840, 850))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            path.write_text(json.dumps(evidence))
            args = argparse.Namespace(rescore=path, output_dir=Path(directory) / 'out')
            with patch('humanoid_sim.p5_evaluation.compute_gate_report') as score:
                with self.assertRaisesRegex(ValueError, 'held-out'):
                    run_rescore_command(args)
                score.assert_not_called()
            self.assertFalse(args.output_dir.exists())


if __name__ == '__main__':
    unittest.main()
