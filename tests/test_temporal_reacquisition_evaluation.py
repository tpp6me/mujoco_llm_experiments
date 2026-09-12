import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from humanoid_sim.temporal_pose import (
    TemporalPose, TemporalReacquisitionPose, TemporalThreeFrameReacquisitionPose
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
            for name in ['baseline_p4', 'reacquisition_candidate']:
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

        comparison_configs = [
            ('baseline_p4', lambda: TemporalPose(reacquisition=False)),
            ('reacquisition_2frame', lambda: TemporalReacquisitionPose(min_reacquisition_frames=2)),
            ('reacquisition_3frame', lambda: TemporalThreeFrameReacquisitionPose()),
        ]

        # Evaluate original stream (seeds=[201], stages=EXPECTED_STAGES)
        res_orig = evaluate_dataset(self.capture_dir, [201], stages=EXPECTED_STAGES, candidate_configs=comparison_configs)
        self.assertEqual(res_orig['status'], 'complete')
        agg_orig_2f = res_orig['candidates']['reacquisition_2frame']['aggregate']['original']
        agg_orig_3f = res_orig['candidates']['reacquisition_3frame']['aggregate']['original']
        # Both must preserve nominal post-warmup targets = 2 (transport, lower)
        self.assertEqual(agg_orig_2f['post_warmup_targets'], 2)
        self.assertEqual(agg_orig_3f['post_warmup_targets'], 2)
        self.assertEqual(agg_orig_2f['expected_responses'], 6)
        self.assertEqual(agg_orig_3f['expected_responses'], 6)

        # Evaluate augmented stream (seeds=[200], stages=AUGMENTED_STAGES)
        res_aug = evaluate_dataset(self.capture_dir, [200], stages=AUGMENTED_STAGES, candidate_configs=comparison_configs)
        self.assertEqual(res_aug['status'], 'complete')
        agg_aug_2f = res_aug['candidates']['reacquisition_2frame']['aggregate']['original']
        agg_aug_3f = res_aug['candidates']['reacquisition_3frame']['aggregate']['original']
        # Nominal post-warmup targets remain fixed at 2 (transport, lower) even with lower_mid!
        self.assertEqual(agg_aug_2f['post_warmup_targets'], 2)
        self.assertEqual(agg_aug_3f['post_warmup_targets'], 2)
        # Expected responses per stream is 7 (7 stages)
        self.assertEqual(agg_aug_2f['expected_responses'], 7)
        self.assertEqual(agg_aug_3f['expected_responses'], 7)

    def test_missing_lower_observation_after_midpoint_retains_accounting_and_invalidates(self):
        # R1: Test missing explicit lower observation when lower_mid is present
        from humanoid_sim.temporal_reacquisition_evaluation import AUGMENTED_STAGES
        seed_dir = self.capture_dir / "seed-300"
        seed_dir.mkdir(parents=True)
        # 7 stages in private_records.json
        records = [
            {'stage': 'lift', 'time_s': 8.5, 'image': '04-lift.png', 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'lift_hold', 'time_s': 9.0, 'image': '05-lift_hold.png', 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'transport', 'time_s': 11.0, 'image': '06-transport.png', 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'lower_mid', 'time_s': 12.0, 'image': '06b-lower_mid.png', 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'lower', 'time_s': 13.0, 'image': '07-lower.png', 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'release', 'time_s': 15.0, 'image': '08-release.png', 'private_true_xyz_m': [0.2, -0.2, 0.9]},
            {'stage': 'retract', 'time_s': 17.0, 'image': '09-retract.png', 'private_true_xyz_m': [0.2, -0.2, 0.9]},
        ]
        (seed_dir / "private_records.json").write_text(json.dumps(records))
        from tests.test_humanoid_temporal_pose import observation
        for r in records:
            if r['stage'] == 'lower':
                continue  # OMIT 07-lower observation file!
            prefix = r['image'].split('-')[0]
            obs = observation(0)
            obs['time_s'] = r['time_s']
            obs['observation_id'] = f"obs-{prefix}"
            (seed_dir / f"{prefix}-observation.json").write_text(json.dumps(obs))

        # Also write 08-observation.json (which old index lookup would have erroneously loaded for lower)
        obs_rel = observation(0)
        obs_rel['time_s'] = 15.0
        obs_rel['observation_id'] = "obs-08"
        (seed_dir / "08-observation.json").write_text(json.dumps(obs_rel))

        results = evaluate_dataset(self.capture_dir, [300], stages=AUGMENTED_STAGES)
        self.assertEqual(results['status'], 'incomplete')
        rec_lower = next(r for r in results['candidates']['baseline_p4']['records'] if r['stage'] == 'lower')
        # Explicit file reference must be authoritative: Lower MUST NOT load Release 08!
        self.assertEqual(rec_lower['status'], 'missing_observation_file')
        self.assertIn('missing or could not be loaded', rec_lower['error_message'])

    def test_mismatched_observation_timestamp_invalidates_and_marks_incomplete(self):
        # R1: Observation has mismatched timestamp vs frame_info
        tracker = TemporalReacquisitionPose()
        from tests.test_humanoid_temporal_pose import observation
        tracker.observe(observation(0))
        self.assertEqual(len(tracker.frames), 1)

        bad_obs = observation(1)
        bad_obs['time_s'] = 99.0  # Timestamp mismatch vs record time 9.0s
        stage_obs = {
            'lift_hold': ({'stage': 'lift_hold', 'time_s': 9.0, 'private_true_xyz_m': [0.2, -0.2, 0.9]}, bad_obs)
        }
        records = evaluate_stream(lambda: tracker, 820, stage_obs, 'original')
        lift_hold_rec = next(r for r in records if r['stage'] == 'lift_hold')
        self.assertEqual(lift_hold_rec['status'], 'mismatched_observation')
        self.assertIn('does not match record timestamp', lift_hold_rec['error_message'])
        # Tracker history must be invalidated on mismatch!
        self.assertEqual(len(tracker.frames), 0)

    def test_cli_default_invocation_preserves_task001_path_without_comparison(self):
        # R2: Prove default CLI without --compare never calls evaluate_evidence or render_augmented_dataset
        with patch('humanoid_sim.temporal_reacquisition_evaluation.evaluate_dataset') as mock_eval_ds, \
             patch('humanoid_sim.temporal_reacquisition_evaluation.evaluate_evidence') as mock_eval_ev, \
             patch('humanoid_sim.temporal_reacquisition_evaluation.render_augmented_dataset') as mock_render, \
             patch('sys.argv', ['eval_script', '--capture-dir', str(self.capture_dir), '--start-seed', '820', '--count', '1']):
            mock_eval_ds.return_value = {'status': 'complete'}
            from humanoid_sim.temporal_reacquisition_evaluation import main
            main()
            mock_eval_ds.assert_called_once()
            mock_eval_ev.assert_not_called()
            mock_render.assert_not_called()

    def test_derive_midpoint_schedule_production_function(self):
        # R3-B: Exercise production schedule selection with non-11/13 s endpoints
        from humanoid_sim.temporal_reacquisition_evaluation import derive_midpoint_schedule

        # Non-standard endpoints: transport at 10.4s, lower at 14.8s -> target 12.6s
        records = [
            {'stage': 'lift', 'time_s': 8.0},
            {'stage': 'transport', 'time_s': 10.4},
            {'stage': 'lower', 'time_s': 14.8},
        ]
        time_arr = np.linspace(10.0, 15.0, 501)  # step 0.01s: index 260 is 12.6s
        sched = derive_midpoint_schedule(records, time_arr)
        self.assertAlmostEqual(sched['requested_time_s'], 12.6, places=6)
        self.assertAlmostEqual(sched['actual_time_s'], 12.6, places=6)
        self.assertEqual(sched['episode_step_index'], 260)

        # Non-standard endpoints with discrete step rounding: transport at 10.1s, lower at 12.0s -> target 11.05s
        records_2 = [
            {'stage': 'transport', 'time_s': 10.1},
            {'stage': 'lower', 'time_s': 12.0},
        ]
        time_arr_2 = np.array([9.5, 10.2, 10.72, 10.82, 11.04, 11.12, 11.9])
        sched_2 = derive_midpoint_schedule(records_2, time_arr_2)
        self.assertAlmostEqual(sched_2['requested_time_s'], 11.05, places=6)
        self.assertAlmostEqual(sched_2['actual_time_s'], 11.04, places=6)
        self.assertEqual(sched_2['episode_step_index'], 4)
        self.assertTrue(10.1 < sched_2['actual_time_s'] < 12.0)

        # Error cases
        with self.assertRaisesRegex(ValueError, 'missing transport or lower'):
            derive_midpoint_schedule([{'stage': 'transport', 'time_s': 10.0}], time_arr)
        with self.assertRaisesRegex(ValueError, 'strictly greater'):
            derive_midpoint_schedule([{'stage': 'transport', 'time_s': 12.0}, {'stage': 'lower', 'time_s': 10.0}], time_arr)
        with self.assertRaisesRegex(ValueError, 'must not be empty'):
            derive_midpoint_schedule(records, np.array([]))
        with self.assertRaisesRegex(ValueError, 'does not lie strictly within'):
            derive_midpoint_schedule(records, np.array([5.0, 6.0]))  # No samples in (10.4, 14.8)

    def test_render_source_output_overlap_rejected(self):
        # R3: Overlapping source and output directories must raise ValueError
        from humanoid_sim.temporal_reacquisition_evaluation import render_augmented_dataset
        with self.assertRaisesRegex(ValueError, 'must not overlap'):
            render_augmented_dataset(self.capture_dir, self.capture_dir, [820])
        with self.assertRaisesRegex(ValueError, 'must not overlap'):
            render_augmented_dataset(self.capture_dir, self.capture_dir / "sub", [820])

    def _setup_mock_source_and_augmented(self, tmp_dir):
        from humanoid_sim.temporal_reacquisition_evaluation import (
            file_sha256, get_scene_sha256,
            AUGMENTED_MANIFEST_VERSION, AUGMENTED_GENERATION_REVISION,
            AUGMENTED_SCHEDULE_RULE, AUGMENTED_REPLAY_MODE, AUGMENTED_CAMERA_CONFIG
        )
        src_root = tmp_dir / "source"
        out_root = tmp_dir / "output"
        src_seed = src_root / "seed-820"
        out_seed = out_root / "seed-820"
        (src_seed / "episode").mkdir(parents=True)
        (out_seed / "episode").mkdir(parents=True)

        src_records = [
            {'stage': 'lift', 'time_s': 8.5, 'image': '04-lift.png'},
            {'stage': 'transport', 'time_s': 11.0, 'image': '06-transport.png'},
            {'stage': 'lower', 'time_s': 13.0, 'image': '07-lower.png'},
        ]
        src_rec_bytes = json.dumps(src_records).encode('utf-8')
        (src_seed / "private_records.json").write_bytes(src_rec_bytes)

        # Dummy episode npz
        npz_bytes = b"DUMMY_EPISODE_NPZ_DATA_820"
        (src_seed / "episode" / "episode.npz").write_bytes(npz_bytes)
        (out_seed / "episode" / "episode.npz").write_bytes(npz_bytes)

        # Dummy observations in src
        obs_06 = {'time_s': 11.0, 'rgb_png_base64': 'AA=='}
        obs_07 = {'time_s': 13.0, 'rgb_png_base64': 'BB=='}
        (src_seed / "06-observation.json").write_text(json.dumps(obs_06))
        (src_seed / "07-observation.json").write_text(json.dumps(obs_07))

        # Copy to output
        (out_seed / "06-observation.json").write_text(json.dumps(obs_06))
        (out_seed / "07-observation.json").write_text(json.dumps(obs_07))

        # Output records with lower_mid
        out_records = [
            {'stage': 'lift', 'time_s': 8.5, 'image': '04-lift.png'},
            {'stage': 'transport', 'time_s': 11.0, 'image': '06-transport.png'},
            {'stage': 'lower_mid', 'time_s': 12.0, 'image': '06b-lower_mid.png'},
            {'stage': 'lower', 'time_s': 13.0, 'image': '07-lower.png'},
        ]
        (out_seed / "private_records.json").write_text(json.dumps(out_records))
        (out_seed / "06b-observation.json").write_text(json.dumps({'time_s': 12.0}))
        (out_seed / "06b-lower_mid.png").write_bytes(b"PNG_BYTES")

        src_obs_hashes = {
            '06-observation.json': file_sha256(src_seed / "06-observation.json"),
            '07-observation.json': file_sha256(src_seed / "07-observation.json"),
        }

        manifest = {
            'manifest_version': AUGMENTED_MANIFEST_VERSION,
            'generation_revision': AUGMENTED_GENERATION_REVISION,
            'schedule_rule': AUGMENTED_SCHEDULE_RULE,
            'replay_mode': AUGMENTED_REPLAY_MODE,
            'camera_config': AUGMENTED_CAMERA_CONFIG,
            'scene_sha256': get_scene_sha256(),
            'seeds': {
                '820': {
                    'source_records_sha256': file_sha256(src_seed / "private_records.json"),
                    'source_episode_npz_sha256': file_sha256(src_seed / "episode" / "episode.npz"),
                    'source_observations_sha256': src_obs_hashes,
                    'requested_time_s': 12.0,
                    'actual_time_s': 11.99,
                    'episode_step_index': 367,
                }
            }
        }
        (out_root / "augmented_manifest.json").write_text(json.dumps(manifest))
        return src_root, out_root

    def test_is_augmented_cache_valid_production_paths(self):
        # R3-B: Validate all production provenance fields against current run
        from humanoid_sim.temporal_reacquisition_evaluation import is_augmented_cache_valid

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src, out = self._setup_mock_source_and_augmented(tmp_path)

            # 1. Valid cache returns True
            self.assertTrue(is_augmented_cache_valid(src, out, [820]))

            # 2. Changed source records invalidates cache
            orig_records = (src / "seed-820" / "private_records.json").read_text()
            (src / "seed-820" / "private_records.json").write_text("[]")
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))
            (src / "seed-820" / "private_records.json").write_text(orig_records)
            self.assertTrue(is_augmented_cache_valid(src, out, [820]))

            # 3. Changed source episode npz invalidates cache
            (src / "seed-820" / "episode" / "episode.npz").write_bytes(b"MODIFIED_NPZ")
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))
            (src / "seed-820" / "episode" / "episode.npz").write_bytes(b"DUMMY_EPISODE_NPZ_DATA_820")
            self.assertTrue(is_augmented_cache_valid(src, out, [820]))

            # 4. Changed source observation invalidates cache
            orig_obs = (src / "seed-820" / "06-observation.json").read_text()
            (src / "seed-820" / "06-observation.json").write_text("{\"tampered\": true}")
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))
            (src / "seed-820" / "06-observation.json").write_text(orig_obs)
            self.assertTrue(is_augmented_cache_valid(src, out, [820]))

            # 5. Tampered destination observation invalidates cache (bound to source)
            orig_out_obs = (out / "seed-820" / "06-observation.json").read_text()
            (out / "seed-820" / "06-observation.json").write_text("{\"tampered_out\": true}")
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))
            (out / "seed-820" / "06-observation.json").write_text(orig_out_obs)
            self.assertTrue(is_augmented_cache_valid(src, out, [820]))

            # 6. Wrong generation_revision rejected
            manifest_file = out / "augmented_manifest.json"
            manifest = json.loads(manifest_file.read_text())
            manifest['generation_revision'] = 'wrong_revision'
            manifest_file.write_text(json.dumps(manifest))
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

            # 7. Wrong schedule_rule rejected
            manifest = json.loads(manifest_file.read_text())
            manifest['generation_revision'] = 'humanoid_sim.temporal_reacquisition_evaluation.render_augmented_dataset.v2'
            manifest['schedule_rule'] = 'wrong_rule'
            manifest_file.write_text(json.dumps(manifest))
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

            # 8. Wrong replay_mode rejected
            manifest['schedule_rule'] = 't_mid = (t_transport + t_lower) / 2.0'
            manifest['replay_mode'] = 'wrong_replay'
            manifest_file.write_text(json.dumps(manifest))
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

            # 9. Wrong camera_config rejected
            manifest['replay_mode'] = 'qpos_kinematic_replay'
            manifest['camera_config'] = {'camera_name': 'head'}
            manifest_file.write_text(json.dumps(manifest))
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

            # 10. Wrong scene_sha256 rejected
            manifest = json.loads(manifest_file.read_text())
            from humanoid_sim.temporal_reacquisition_evaluation import AUGMENTED_CAMERA_CONFIG
            manifest['camera_config'] = AUGMENTED_CAMERA_CONFIG
            manifest['scene_sha256'] = '0' * 64
            manifest_file.write_text(json.dumps(manifest))
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

            # 11. Missing required hash field rejected
            from humanoid_sim.temporal_reacquisition_evaluation import get_scene_sha256
            manifest['scene_sha256'] = get_scene_sha256()
            manifest['seeds']['820']['source_records_sha256'] = None
            manifest_file.write_text(json.dumps(manifest))
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

            # 12. Missing generated observation rejected
            (out / "seed-820" / "06b-observation.json").unlink()
            manifest['seeds']['820']['source_records_sha256'] = 'a' * 64
            manifest_file.write_text(json.dumps(manifest))
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

    def test_render_rejects_non_empty_directory_and_cannot_certify_stale_bytes(self):
        # R3-A: Prove invalid cache cannot be recertified in-place; non-empty directory is rejected
        from humanoid_sim.temporal_reacquisition_evaluation import (
            render_augmented_dataset, evaluate_evidence, is_augmented_cache_valid
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src, out = self._setup_mock_source_and_augmented(tmp_path)

            # Alter source timestamp so cache is now invalid
            src_records_path = src / "seed-820" / "private_records.json"
            records = json.loads(src_records_path.read_text())
            transport = next(r for r in records if r['stage'] == 'transport')
            transport['time_s'] += 0.2
            src_records_path.write_text(json.dumps(records))

            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

            # Tag existing midpoint with known stale bytes
            stale_midpoint_bytes = b"OLD_STALE_MIDPOINT_BYTES_DO_NOT_CERTIFY"
            midpoint_path = out / "seed-820" / "06b-observation.json"
            midpoint_path.write_bytes(stale_midpoint_bytes)

            # Direct call to render_augmented_dataset must reject non-empty directory
            with self.assertRaisesRegex(ValueError, "exists and is not empty"):
                render_augmented_dataset(src, out, [820])

            # Calling evaluate_evidence must reject stale non-empty directory
            with self.assertRaisesRegex(ValueError, "invalid or stale, but is not empty"):
                evaluate_evidence(src, out, [820], render_if_missing=True)

            # Stale bytes must be unchanged and cache must remain invalid
            self.assertEqual(midpoint_path.read_bytes(), stale_midpoint_bytes)
            self.assertFalse(is_augmented_cache_valid(src, out, [820]))

    def test_evaluate_evidence_retains_provenance_manifest_in_evidence_output(self):
        # R3-B: Prove provenance manifest is retained in evidence output JSON
        from humanoid_sim.temporal_reacquisition_evaluation import evaluate_evidence

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src, out = self._setup_mock_source_and_augmented(tmp_path)
            output_evidence_file = tmp_path / "evidence.json"

            dummy_result = {
                'status': 'complete',
                'candidates': {
                    'baseline_p4': {'aggregate': {'original': {'accepted': 1}}, 'records': []},
                    'reacquisition_2frame': {'aggregate': {'original': {'accepted': 1}}, 'records': []},
                    'reacquisition_3frame': {'aggregate': {'original': {'accepted': 1}}, 'records': []},
                }
            }

            with patch('humanoid_sim.temporal_reacquisition_evaluation.evaluate_dataset', return_value=dummy_result):
                evidence = evaluate_evidence(src, out, [820], output_file=output_evidence_file, render_if_missing=False)

            self.assertEqual(evidence['status'], 'complete')
            self.assertIn('cache_manifest', evidence)
            manifest = evidence['cache_manifest']
            self.assertIsNotNone(manifest)
            self.assertEqual(manifest['generation_revision'], 'humanoid_sim.temporal_reacquisition_evaluation.render_augmented_dataset.v2')
            self.assertEqual(manifest['schedule_rule'], 't_mid = (t_transport + t_lower) / 2.0')
            self.assertEqual(manifest['replay_mode'], 'qpos_kinematic_replay')
            self.assertIn('camera_config', manifest)
            self.assertIn('scene_sha256', manifest)
            self.assertIn('820', manifest['seeds'])
            self.assertIn('source_observations_sha256', manifest['seeds']['820'])

            # Verify saved file also contains cache_manifest
            saved_evidence = json.loads(output_evidence_file.read_text())
            self.assertEqual(saved_evidence['cache_manifest']['generation_revision'], manifest['generation_revision'])


if __name__ == '__main__':
    unittest.main()
