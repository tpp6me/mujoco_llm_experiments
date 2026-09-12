import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from humanoid_sim.temporal_reacquisition_evaluation import (
    EXPECTED_STAGES, evaluate_dataset
)


class TemporalReacquisitionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.capture_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_invalid_seed_requests_rejected(self):
        with self.assertRaisesRegex(ValueError, 'non-empty'):
            evaluate_dataset(self.capture_dir, [])
        with self.assertRaisesRegex(ValueError, 'non-negative'):
            evaluate_dataset(self.capture_dir, [-5])
        with self.assertRaisesRegex(ValueError, 'non-negative'):
            evaluate_dataset(self.capture_dir, ['not-a-seed'])

    def test_empty_records_list_retains_accounting_and_marks_incomplete(self):
        seed_dir = self.capture_dir / "seed-100"
        seed_dir.mkdir(parents=True)
        (seed_dir / "private_records.json").write_text("[]")

        results = evaluate_dataset(self.capture_dir, [100])
        self.assertEqual(results['status'], 'incomplete')
        for name in ['baseline_p4', 'reacquisition_candidate']:
            agg = results['candidates'][name]['aggregate']['original']
            self.assertEqual(agg['expected_responses'], 6)
            self.assertEqual(agg['evaluated_responses'], 0)
            self.assertEqual(agg['missing_responses'], 6)
            self.assertEqual(agg['post_warmup_targets'], 2)
            self.assertEqual(agg['post_warmup_accepted'], 0)
            self.assertEqual(agg['post_warmup_missing_or_refused'], 2)

    def test_early_stopped_episode_retains_accounting(self):
        seed_dir = self.capture_dir / "seed-101"
        seed_dir.mkdir(parents=True)
        # Episode with only lift and lift_hold
        records = [
            {'stage': 'lift', 'time_s': 8.5, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'lift_hold', 'time_s': 9.0, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
        ]
        (seed_dir / "private_records.json").write_text(json.dumps(records))
        from tests.test_humanoid_temporal_pose import observation
        for idx in [0, 1]:
            obs = observation(idx)
            (seed_dir / f"{idx:02d}-observation.json").write_text(json.dumps(obs))

        results = evaluate_dataset(self.capture_dir, [101])
        self.assertEqual(results['status'], 'incomplete')
        for name in ['baseline_p4', 'reacquisition_candidate']:
            agg = results['candidates'][name]['aggregate']['original']
            self.assertEqual(agg['expected_responses'], 6)
            self.assertEqual(agg['evaluated_responses'], 2)
            self.assertEqual(agg['missing_responses'], 4)
            self.assertEqual(agg['post_warmup_targets'], 2)
            self.assertEqual(agg['post_warmup_missing_or_refused'], 2)

    def test_missing_observation_file_retains_accounting(self):
        seed_dir = self.capture_dir / "seed-102"
        seed_dir.mkdir(parents=True)
        # Lists lift, but observation file does not exist
        records = [{'stage': 'lift', 'time_s': 8.5, 'private_true_xyz_m': [0.2, -0.2, 0.9]}]
        (seed_dir / "private_records.json").write_text(json.dumps(records))

        results = evaluate_dataset(self.capture_dir, [102])
        self.assertEqual(results['status'], 'incomplete')
        for name in ['baseline_p4', 'reacquisition_candidate']:
            rec = results['candidates'][name]['records'][0]
            self.assertEqual(rec['status'], 'missing_observation_file')
            self.assertEqual(rec['stage'], 'lift')

    def test_estimator_exception_retains_accounting_and_details(self):
        seed_dir = self.capture_dir / "seed-103"
        seed_dir.mkdir(parents=True)
        records = [{'stage': 'lift', 'time_s': 8.5, 'private_true_xyz_m': [0.2, -0.2, 0.9]}]
        (seed_dir / "private_records.json").write_text(json.dumps(records))
        obs = {
            'observation_id': 'obs-0',
            'time_s': 8.5,
            'camera': {
                'camera_world_xyz_m': [0.5, 0.0, 1.2],
                'world_to_camera_rotation': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                'focal_xy_px': [900, 900],
                'principal_xy_px': [480, 360],
                'width': 960,
                'height': 720,
            },
            'robot_state': {
                'robot': {
                    'hand_xyz_m': [0.25, -0.2, 0.95],
                    'hand_quaternion_wxyz': [1, 0, 0, 0],
                }
            },
            'rgb_png_base64': 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
        }
        (seed_dir / "00-observation.json").write_text(json.dumps(obs))

        with patch('humanoid_sim.temporal_reacquisition_evaluation.TemporalPose.observe',
                   side_effect=RuntimeError('Simulated crash')):
            results = evaluate_dataset(self.capture_dir, [103])

        self.assertEqual(results['status'], 'incomplete')
        rec = results['candidates']['baseline_p4']['records'][0]
        self.assertEqual(rec['status'], 'estimator_error')
        self.assertIn('Simulated crash', rec['error_message'])


if __name__ == '__main__':
    unittest.main()
