import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from humanoid_sim.temporal_pose import (
    TemporalPose, TemporalReacquisitionPose
)
from humanoid_sim.temporal_reacquisition_evaluation import (
    EXPECTED_STAGES, evaluate_dataset, evaluate_stream
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

    def test_corrupt_transport_metadata_retains_accounting_and_clears_history(self):
        # R2-A review reproduction: observation has no 'camera' key in black_transport
        tracker = TemporalReacquisitionPose()
        # Seed tracker with a valid frame first
        from tests.test_humanoid_temporal_pose import observation
        tracker.observe(observation(0))
        self.assertEqual(len(tracker.frames), 1)

        stage_obs = {
            'transport': ({'stage': 'transport', 'private_true_xyz_m': [0.2, -0.2, 0.9]}, {})
        }
        records = evaluate_stream(lambda: tracker, 820, stage_obs, 'black_transport')
        self.assertEqual(len(records), 6)
        transport_rec = next(r for r in records if r['stage'] == 'transport')
        self.assertEqual(transport_rec['status'], 'preparation_error')
        self.assertIn("Missing 'camera'", transport_rec['error_message'])
        # Tracker history must be cleared when corrupt observation interrupts stream
        self.assertEqual(len(tracker.frames), 0)

    def test_malformed_loaded_json_structure_retains_accounting(self):
        # R2-A: private_records.json is a dict instead of a list
        seed_dir = self.capture_dir / "seed-104"
        seed_dir.mkdir(parents=True)
        (seed_dir / "private_records.json").write_text("{\"error\": \"corrupt\"}")

        results = evaluate_dataset(self.capture_dir, [104])
        self.assertEqual(results['status'], 'incomplete')
        for name in ['baseline_p4', 'reacquisition_candidate']:
            agg = results['candidates'][name]['aggregate']['original']
            self.assertEqual(agg['expected_responses'], 6)
            self.assertEqual(agg['evaluated_responses'], 0)
            self.assertEqual(agg['missing_responses'], 6)

        # Also test non-dict observation file
        seed_dir_2 = self.capture_dir / "seed-105"
        seed_dir_2.mkdir(parents=True)
        records = [{'stage': 'lift', 'time_s': 8.5, 'private_true_xyz_m': [0.2, -0.2, 0.9]}]
        (seed_dir_2 / "private_records.json").write_text(json.dumps(records))
        (seed_dir_2 / "00-observation.json").write_text("\"not-a-dict\"")

        results2 = evaluate_dataset(self.capture_dir, [105])
        self.assertEqual(results2['status'], 'incomplete')
        rec = results2['candidates']['baseline_p4']['records'][0]
        self.assertEqual(rec['status'], 'missing_observation_file')

    def test_unavailable_frozen_image_source_marks_stimulus_unavailable(self):
        # R2-A: frozen_transport_rgb where lift_hold is missing or invalid
        tracker = TemporalReacquisitionPose()
        from tests.test_humanoid_temporal_pose import observation
        tracker.observe(observation(0))
        self.assertEqual(len(tracker.frames), 1)

        # lift_hold is missing
        stage_obs = {
            'transport': ({'stage': 'transport', 'private_true_xyz_m': [0.2, -0.2, 0.9]}, observation(2))
        }
        records = evaluate_stream(lambda: tracker, 820, stage_obs, 'frozen_transport_rgb')
        transport_rec = next(r for r in records if r['stage'] == 'transport')
        self.assertEqual(transport_rec['status'], 'stimulus_unavailable')
        self.assertIn('Lift-hold source observation unavailable', transport_rec['error_message'])
        self.assertEqual(len(tracker.frames), 0)

        # lift_hold is present but has empty rgb_png_base64
        obs_empty = observation(1)
        obs_empty['rgb_png_base64'] = ''
        stage_obs_2 = {
            'lift_hold': ({'stage': 'lift_hold', 'private_true_xyz_m': [0.2, -0.2, 0.9]}, obs_empty),
            'transport': ({'stage': 'transport', 'private_true_xyz_m': [0.2, -0.2, 0.9]}, observation(2)),
        }
        records_2 = evaluate_stream(TemporalReacquisitionPose, 820, stage_obs_2, 'frozen_transport_rgb')
        transport_rec_2 = next(r for r in records_2 if r['stage'] == 'transport')
        self.assertEqual(transport_rec_2['status'], 'stimulus_unavailable')
        self.assertIn('Lift-hold source image missing or empty', transport_rec_2['error_message'])

    def test_null_absent_and_nonfinite_truth_retains_acceptance_and_marks_incomplete(self):
        # R2-B: Test null, absent, and nonfinite truth with a mock returning accepted poses
        from tests.test_humanoid_temporal_pose import observation

        mock_tracker = MagicMock()
        mock_tracker.observe.return_value = {
            'detected': True,
            'object_center_xyz_m': [0.2, -0.2, 0.9],
            'reason': None,
        }

        cases = [
            ('null_truth', None),
            ('absent_truth', 'OMIT_KEY'),
            ('nonfinite_truth', [float('nan'), 0.0, 0.9]),
        ]

        for case_name, truth_val in cases:
            seed_int = abs(hash(case_name)) % 10000 + 1000
            seed_dir = self.capture_dir / f"seed-{seed_int}"
            seed_dir.mkdir(parents=True)
            records = []
            for idx, stage in enumerate(EXPECTED_STAGES):
                rec = {'stage': stage, 'time_s': 8.5 + idx * 0.5}
                if truth_val != 'OMIT_KEY':
                    rec['private_true_xyz_m'] = truth_val
                records.append(rec)
                obs = observation(min(idx, 2))
                obs['time_s'] = 8.5 + idx * 0.5
                obs['observation_id'] = f'obs-{case_name}-{idx}'
                (seed_dir / f"{idx:02d}-observation.json").write_text(json.dumps(obs))
            (seed_dir / "private_records.json").write_text(json.dumps(records))

            with patch('humanoid_sim.temporal_reacquisition_evaluation.TemporalPose',
                       return_value=mock_tracker), \
                 patch('humanoid_sim.temporal_reacquisition_evaluation.TemporalReacquisitionPose',
                       return_value=mock_tracker), \
                 patch('humanoid_sim.temporal_reacquisition_evaluation.TemporalThreeFrameReacquisitionPose',
                       return_value=mock_tracker):
                results = evaluate_dataset(self.capture_dir, [seed_int])

            self.assertEqual(results['status'], 'incomplete',
                             f"Failed on case {case_name}: status should be incomplete")
            for name in ['baseline_p4', 'reacquisition_2frame', 'reacquisition_3frame', 'reacquisition_candidate']:
                agg = results['candidates'][name]['aggregate']['original']
                # Acceptance remains visible!
                self.assertEqual(agg['accepted'], 6,
                                 f"Failed on case {case_name}: accepted poses must remain visible")
                # Scored responses must be zero because truth cannot be scored
                self.assertEqual(agg['scored_responses'], 0,
                                 f"Failed on case {case_name}: scored count should be 0")
                self.assertEqual(agg['unscored_accepted'], 6,
                                 f"Failed on case {case_name}: unscored_accepted should be 6")
                self.assertEqual(agg['missing_or_invalid_truth'], 6,
                                 f"Failed on case {case_name}: missing_or_invalid_truth should be 6")
                self.assertEqual(agg['post_warmup_accepted'], 2,
                                 f"Failed on case {case_name}: post-warmup accepted should be 2")
                self.assertEqual(agg['post_warmup_scored'], 0,
                                 f"Failed on case {case_name}: post-warmup scored should be 0")
                # Expected grid retained
                records_list = results['candidates'][name]['records']
                self.assertEqual(len(records_list), 18)  # 6 stages * 3 variants

    def test_three_frame_reacquisition_evaluation_accounting_original_vs_augmented(self):
        from humanoid_sim.temporal_reacquisition_evaluation import AUGMENTED_STAGES
        from tests.test_humanoid_temporal_pose import observation

        seed_dir = self.capture_dir / "seed-200"
        seed_dir.mkdir(parents=True)
        # Stages: lift, lift_hold, transport, lower_mid, lower, release, retract
        records = [
            {'stage': 'lift', 'time_s': 8.5, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'lift_hold', 'time_s': 9.0, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'transport', 'time_s': 11.0, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'lower_mid', 'time_s': 12.0, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'lower', 'time_s': 13.0, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'release', 'time_s': 15.0, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'retract', 'time_s': 17.0, 'private_true_xyz_m': [0.2, -0.2, 0.9]},
        ]
        (seed_dir / "private_records.json").write_text(json.dumps(records))
        # Write observations: 00..06
        for idx in range(7):
            obs = observation(min(idx, 2))
            obs['time_s'] = records[idx]['time_s']
            obs['observation_id'] = f'obs-seed200-{idx}'
            (seed_dir / f"{idx:02d}-observation.json").write_text(json.dumps(obs))

        # 1. Original 6-stage stream (without lower_mid)
        orig_seed_dir = self.capture_dir / "seed-201"
        orig_seed_dir.mkdir(parents=True)
        orig_records = [r for r in records if r['stage'] != 'lower_mid']
        (orig_seed_dir / "private_records.json").write_text(json.dumps(orig_records))
        for idx in range(6):
            obs = observation(min(idx, 2))
            obs['time_s'] = orig_records[idx]['time_s']
            obs['observation_id'] = f'obs-seed201-{idx}'
            (orig_seed_dir / f"{idx:02d}-observation.json").write_text(json.dumps(obs))

        # Evaluate original stream (seeds=[201], stages=EXPECTED_STAGES)
        res_orig = evaluate_dataset(self.capture_dir, [201], stages=EXPECTED_STAGES)
        self.assertEqual(res_orig['status'], 'complete')
        agg_orig_2f = res_orig['candidates']['reacquisition_2frame']['aggregate']['original']
        agg_orig_3f = res_orig['candidates']['reacquisition_3frame']['aggregate']['original']
        # Both must preserve nominal post-warmup targets = 2 (transport, lower)
        self.assertEqual(agg_orig_2f['post_warmup_targets'], 2)
        self.assertEqual(agg_orig_3f['post_warmup_targets'], 2)
        self.assertEqual(agg_orig_2f['expected_responses'], 6)
        self.assertEqual(agg_orig_3f['expected_responses'], 6)

        # Evaluate augmented stream (seeds=[200], stages=AUGMENTED_STAGES)
        res_aug = evaluate_dataset(self.capture_dir, [200], stages=AUGMENTED_STAGES)
        self.assertEqual(res_aug['status'], 'complete')
        agg_aug_2f = res_aug['candidates']['reacquisition_2frame']['aggregate']['original']
        agg_aug_3f = res_aug['candidates']['reacquisition_3frame']['aggregate']['original']
        # Nominal post-warmup targets remain fixed at 2 (transport, lower) even with lower_mid!
        self.assertEqual(agg_aug_2f['post_warmup_targets'], 2)
        self.assertEqual(agg_aug_3f['post_warmup_targets'], 2)
        # Expected responses per stream is 7 (7 stages)
        self.assertEqual(agg_aug_2f['expected_responses'], 7)
        self.assertEqual(agg_aug_3f['expected_responses'], 7)


if __name__ == '__main__':
    unittest.main()
