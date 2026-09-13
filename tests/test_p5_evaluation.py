"""Unit tests for P5 preparation, preflight wrapper, and gate evaluation logic."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from humanoid_sim.p5_evaluation import (
    HELD_OUT_SEEDS, DEVELOPMENT_SEEDS, PRIMARY_CANDIDATE,
    GATE_MIN_COVERAGE_TARGETS, GATE_TOTAL_TARGETS,
    GATE_MAX_MEAN_ERROR_M, GATE_MAX_NOMINAL_ERROR_M,
    validate_seeds_guard, build_preflight_report,
    compute_gate_report, TASK_002_EVIDENCE_PATH
)


class TestP5Evaluation(unittest.TestCase):

    def test_held_out_seeds_strictly_forbidden(self):
        """Held-out validation seeds 840-849 must be rejected immediately."""
        for seed in [840, 845, 849]:
            with self.assertRaisesRegex(ValueError, "held-out seed.*strictly forbidden"):
                validate_seeds_guard([seed])
        with self.assertRaisesRegex(ValueError, "held-out seed.*strictly forbidden"):
            validate_seeds_guard(range(840, 850))

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

    def test_successful_synthetic_metrics_pass_all_gates(self):
        """Synthetic metrics meeting all criteria must result in PASS."""
        synthetic_evidence = {
            'status': 'complete',
            'seeds': list(range(820, 830)),
            'augmented_stream': {
                'status': 'complete',
                'seeds': list(range(820, 830)),
                'candidates': {
                    PRIMARY_CANDIDATE: {
                        'aggregate': {
                            'original': {
                                'expected_responses': 70,
                                'evaluated_responses': 70,
                                'missing_responses': 0,
                                'accepted': 25,
                                'scored_responses': 25,
                                'unscored_accepted': 0,
                                'missing_or_invalid_truth': 0,
                                'within_20mm': 25,
                                'accepted_over_20mm': 0,
                                'accepted_mean_error_m': 0.0040,
                                'accepted_max_error_m': 0.0120,
                                'post_warmup_targets': 20,
                                'post_warmup_accepted': 18,
                                'post_warmup_scored': 18,
                                'post_warmup_within_20mm': 18,
                                'post_warmup_mean_error_m': 0.0042,  # 4.2 mm <= 5.0 mm
                                'post_warmup_max_error_m': 0.0120,  # 12.0 mm <= 20.0 mm
                                'release_or_retract_accepted': 0,
                                'refusals': {'insufficient_motion_history': 30, 'inconsistent_rigid_transform': 15},
                            },
                            'black_transport': {'accepted': 0, 'missing_responses': 0},
                            'frozen_transport_rgb': {'accepted': 0, 'missing_responses': 0},
                        },
                        'records': [
                            {'variant': 'original', 'stage': 'lower_mid', 'estimate': {'detected': True}, 'error_3d_m': 0.0035},
                            {'variant': 'original', 'stage': 'transport', 'estimate': {'detected': True}, 'error_3d_m': 0.0040},
                            {'variant': 'original', 'stage': 'lower', 'estimate': {'detected': True}, 'error_3d_m': 0.0044},
                            {'variant': 'original', 'stage': 'release', 'estimate': {'detected': False}, 'error_3d_m': None},
                            {'variant': 'original', 'stage': 'retract', 'estimate': {'detected': False}, 'error_3d_m': None},
                            {'variant': 'black_transport', 'stage': 'transport', 'estimate': {'detected': False}, 'error_3d_m': None},
                            {'variant': 'frozen_transport_rgb', 'stage': 'transport', 'estimate': {'detected': False}, 'error_3d_m': None},
                        ],
                    }
                }
            }
        }
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)
        self.assertEqual(report['gates']['gate_1_coverage']['status'], 'pass')
        self.assertEqual(report['gates']['gate_2_accuracy']['status'], 'pass')
        self.assertEqual(report['gates']['gate_3_nominal_max_error']['status'], 'pass')
        self.assertEqual(report['gates']['gate_4_relationship_loss_safety']['status'], 'pass')
        self.assertEqual(report['gates']['gate_5_disruption_robustness']['status'], 'pass')
        self.assertEqual(report['overall_outcome'], 'PASS')

    def test_missing_truth_and_unscored_acceptances_never_pass(self):
        """Missing truth or unscored acceptances must render evidence incomplete, never pass."""
        base_agg = {
            'expected_responses': 70,
            'evaluated_responses': 70,
            'missing_responses': 0,
            'accepted': 20,
            'scored_responses': 18,
            'unscored_accepted': 2,  # 2 emitted poses unscored due to invalid/missing truth
            'missing_or_invalid_truth': 2,
            'post_warmup_targets': 20,
            'post_warmup_accepted': 18,
            'post_warmup_scored': 16,
            'post_warmup_mean_error_m': 0.0030,
            'post_warmup_max_error_m': 0.0100,
            'accepted_max_error_m': 0.0100,
            'release_or_retract_accepted': 0,
        }
        synthetic_evidence = {
            'status': 'incomplete',
            'seeds': list(range(820, 830)),
            'augmented_stream': {
                'status': 'incomplete',
                'seeds': list(range(820, 830)),
                'candidates': {
                    PRIMARY_CANDIDATE: {
                        'aggregate': {
                            'original': base_agg,
                            'black_transport': {'accepted': 0},
                            'frozen_transport_rgb': {'accepted': 0},
                        },
                        'records': [],
                    }
                }
            }
        }
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)
        self.assertFalse(report['is_complete'])
        self.assertEqual(report['overall_outcome'], 'INCOMPLETE')
        self.assertIn('incomplete is never a pass', report['overall_reason'].lower())

    def test_all_refused_results(self):
        """All-refused results must fail coverage, accuracy, and overall outcome."""
        all_refused_agg = {
            'expected_responses': 70,
            'evaluated_responses': 70,
            'missing_responses': 0,
            'accepted': 0,
            'scored_responses': 0,
            'unscored_accepted': 0,
            'missing_or_invalid_truth': 0,
            'post_warmup_targets': 20,
            'post_warmup_accepted': 0,
            'post_warmup_scored': 0,
            'post_warmup_mean_error_m': None,
            'post_warmup_max_error_m': None,
            'accepted_max_error_m': None,
            'release_or_retract_accepted': 0,
            'refusals': {'insufficient_motion_history': 50, 'inconsistent_rigid_transform': 20},
        }
        synthetic_evidence = {
            'status': 'complete',
            'seeds': list(range(820, 830)),
            'augmented_stream': {
                'status': 'complete',
                'seeds': list(range(820, 830)),
                'candidates': {
                    PRIMARY_CANDIDATE: {
                        'aggregate': {
                            'original': all_refused_agg,
                            'black_transport': {'accepted': 0},
                            'frozen_transport_rgb': {'accepted': 0},
                        },
                        'records': [],
                    }
                }
            }
        }
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)
        self.assertEqual(report['gates']['gate_1_coverage']['status'], 'fail')
        self.assertEqual(report['gates']['gate_2_accuracy']['status'], 'fail')
        self.assertEqual(report['overall_outcome'], 'FAIL')

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
        """Subset dry runs (<10 seeds) must mark gates not_applicable rather than falsely passing/failing."""
        single_seed_evidence = {
            'status': 'complete',
            'seeds': [820],
            'augmented_stream': {
                'status': 'complete',
                'seeds': [820],
                'candidates': {
                    PRIMARY_CANDIDATE: {
                        'aggregate': {
                            'original': {
                                'expected_responses': 7,
                                'evaluated_responses': 7,
                                'missing_responses': 0,
                                'accepted': 1,
                                'scored_responses': 1,
                                'unscored_accepted': 0,
                                'missing_or_invalid_truth': 0,
                                'post_warmup_targets': 2,
                                'post_warmup_accepted': 1,
                                'post_warmup_scored': 1,
                                'post_warmup_mean_error_m': 0.0148,
                                'post_warmup_max_error_m': 0.0148,
                                'accepted_max_error_m': 0.0148,
                                'release_or_retract_accepted': 0,
                            },
                            'black_transport': {'accepted': 0},
                            'frozen_transport_rgb': {'accepted': 0},
                        },
                        'records': [
                            {'variant': 'original', 'stage': 'lower', 'estimate': {'detected': True}, 'error_3d_m': 0.0148},
                        ],
                    }
                }
            }
        }
        report = compute_gate_report(single_seed_evidence, candidate_name=PRIMARY_CANDIDATE)
        self.assertEqual(report['gates']['gate_1_coverage']['status'], 'not_applicable')
        self.assertEqual(report['gates']['gate_2_accuracy']['status'], 'not_applicable')
        self.assertEqual(report['overall_outcome'], 'NOT_APPLICABLE_SUBSET')

    def test_preflight_report_generation(self):
        """Preflight report must document hashes, configurations, and unexecuted status."""
        report = build_preflight_report(
            source_capture_dir='/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture',
            augmented_capture_dir='/private/tmp/mujoco-llms-agy-002/runtime/humanoid/temporal-P4-augmented/capture',
            seeds=list(range(820, 830))
        )
        self.assertEqual(report['status'], 'development_preparation')
        self.assertFalse(report['fresh_validation_executed'])
        self.assertFalse(report['held_out_seeds_touched'])
        self.assertEqual(report['held_out_seeds_reserved'], list(range(840, 850)))
        self.assertIn('python -m humanoid_sim.perception_evaluation audit', report['future_capture_command'])

        hashes = report['provenance_hashes']
        self.assertIsNotNone(hashes['scene_sha256'])
        self.assertIsNotNone(hashes['protocol_revised_sha256'])
        self.assertIsNotNone(hashes['protocol_historical_sha256'])
        self.assertIn('temporal_pose.py', hashes['code_sha256'])
        self.assertIn('p5_evaluation.py', hashes['code_sha256'])

    def test_corrupted_transport_emission_fails_gate_5(self):
        """Accepted pose on corrupted transport frame must fail Gate 5."""
        synthetic_evidence = {
            'status': 'complete',
            'seeds': list(range(820, 830)),
            'augmented_stream': {
                'status': 'complete',
                'seeds': list(range(820, 830)),
                'candidates': {
                    PRIMARY_CANDIDATE: {
                        'aggregate': {
                            'original': {
                                'expected_responses': 70,
                                'evaluated_responses': 70,
                                'missing_responses': 0,
                                'accepted': 20,
                                'scored_responses': 20,
                                'unscored_accepted': 0,
                                'missing_or_invalid_truth': 0,
                                'post_warmup_targets': 20,
                                'post_warmup_accepted': 17,
                                'post_warmup_scored': 17,
                                'post_warmup_mean_error_m': 0.0040,
                                'post_warmup_max_error_m': 0.0100,
                                'accepted_max_error_m': 0.0100,
                                'release_or_retract_accepted': 0,
                            },
                            'black_transport': {'accepted': 1},
                            'frozen_transport_rgb': {'accepted': 0},
                        },
                        'records': [
                            {'variant': 'black_transport', 'stage': 'transport', 'estimate': {'detected': True}, 'error_3d_m': 0.050},
                        ],
                    }
                }
            }
        }
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)
        self.assertEqual(report['gates']['gate_5_disruption_robustness']['status'], 'fail')
        self.assertEqual(report['overall_outcome'], 'FAIL')

    def test_release_retract_emission_fails_gate_4(self):
        """Accepted pose on release/retract endpoint must fail Gate 4."""
        synthetic_evidence = {
            'status': 'complete',
            'seeds': list(range(820, 830)),
            'augmented_stream': {
                'status': 'complete',
                'seeds': list(range(820, 830)),
                'candidates': {
                    PRIMARY_CANDIDATE: {
                        'aggregate': {
                            'original': {
                                'expected_responses': 70,
                                'evaluated_responses': 70,
                                'missing_responses': 0,
                                'accepted': 20,
                                'scored_responses': 20,
                                'unscored_accepted': 0,
                                'missing_or_invalid_truth': 0,
                                'post_warmup_targets': 20,
                                'post_warmup_accepted': 17,
                                'post_warmup_scored': 17,
                                'post_warmup_mean_error_m': 0.0040,
                                'post_warmup_max_error_m': 0.0100,
                                'accepted_max_error_m': 0.0100,
                                'release_or_retract_accepted': 1,  # 1 emission on release/retract
                            },
                            'black_transport': {'accepted': 0},
                            'frozen_transport_rgb': {'accepted': 0},
                        },
                        'records': [],
                    }
                }
            }
        }
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)
        self.assertEqual(report['gates']['gate_4_relationship_loss_safety']['status'], 'fail')
        self.assertEqual(report['overall_outcome'], 'FAIL')

    def test_max_error_exceeding_20mm_fails_gate_3(self):
        """Accepted nominal error exceeding 20.0 mm must fail Gate 3."""
        synthetic_evidence = {
            'status': 'complete',
            'seeds': list(range(820, 830)),
            'augmented_stream': {
                'status': 'complete',
                'seeds': list(range(820, 830)),
                'candidates': {
                    PRIMARY_CANDIDATE: {
                        'aggregate': {
                            'original': {
                                'expected_responses': 70,
                                'evaluated_responses': 70,
                                'missing_responses': 0,
                                'accepted': 20,
                                'scored_responses': 20,
                                'unscored_accepted': 0,
                                'missing_or_invalid_truth': 0,
                                'post_warmup_targets': 20,
                                'post_warmup_accepted': 17,
                                'post_warmup_scored': 17,
                                'post_warmup_mean_error_m': 0.0040,
                                'post_warmup_max_error_m': 0.0250,  # 25 mm > 20 mm
                                'accepted_max_error_m': 0.0250,
                                'release_or_retract_accepted': 0,
                            },
                            'black_transport': {'accepted': 0},
                            'frozen_transport_rgb': {'accepted': 0},
                        },
                        'records': [],
                    }
                }
            }
        }
        report = compute_gate_report(synthetic_evidence, candidate_name=PRIMARY_CANDIDATE)
        self.assertEqual(report['gates']['gate_3_nominal_max_error']['status'], 'fail')
        self.assertEqual(report['overall_outcome'], 'FAIL')

    def test_fresh_capture_flag_raises_error_with_future_command(self):
        """CLI with --fresh-capture must raise RuntimeError documenting the future command."""
        from humanoid_sim.p5_evaluation import main
        import sys
        with patch.object(sys, 'argv', ['p5_evaluation', '--fresh-capture']):
            with self.assertRaisesRegex(RuntimeError, "Fresh capture is disabled in Task 003"):
                main()


if __name__ == '__main__':
    unittest.main()
