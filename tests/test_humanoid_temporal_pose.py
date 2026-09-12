import base64
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from humanoid_sim.temporal_pose import (CORNERS, TemporalPose, TemporalReacquisitionPose,
                                        convex_hull, fit_window, prepare_frame,
                                        rotation_vector_matrix)
from humanoid_sim.carried_pose import select_hypotheses

FIXTURES = Path(__file__).parent/'fixtures/humanoid_carried_rgb'
CASES = json.loads((FIXTURES/'temporal_cases.json').read_text())


def observation(index):
    case = CASES[index]
    result = copy.deepcopy(case['observation'])
    result['rgb_png_base64'] = base64.b64encode((FIXTURES/case['image']).read_bytes()).decode()
    return result


def rigid_features(angles=(.7, .3, .2)):
    """Exact analytic projected edges, not rendered or scored robot episodes."""
    camera = observation(0)['camera']
    camera = {'origin': np.array(camera['camera_world_xyz_m']),
              'rotation': np.array(camera['world_to_camera_rotation']),
              'focal': np.array(camera['focal_xy_px']),
              'principal': np.array(camera['principal_xy_px'])}
    offset = np.array([-.03, 0, -.04])
    rotation = rotation_vector_matrix(np.array(angles))
    frames = []
    for hand in [[.24, -.18, .975], [.19, -.36, .975], [.21, -.36, .88]]:
        hand = np.array(hand)
        world = CORNERS@rotation.T+hand+offset
        local = (world-camera['origin'])@camera['rotation'].T
        pixels = local[:, :2]/local[:, 2, None]*camera['focal']+camera['principal']
        polygon = convex_hull(pixels)
        edges = np.concatenate([a+np.arange(25)[:, None]/25*(b-a)
                                for a, b in zip(polygon, np.roll(polygon, -1, axis=0))])
        interior = polygon.mean(axis=0)+.5*(edges-polygon.mean(axis=0))
        frames.append({'hand': hand, 'rotation': np.eye(3), 'camera': camera,
                       'points': np.concatenate([edges, interior]), 'edge_count': len(edges),
                       'time_s': float(len(frames))})
    return frames, frames[-1]['hand']+offset


class TemporalPoseTests(unittest.TestCase):
    def test_rigid_positive_control_recovers_center_in_optimizer(self):
        frames, truth = rigid_features()
        hypotheses = fit_window(frames)
        self.assertTrue(hypotheses)
        self.assertLess(hypotheses[0]['rms_px'], .1)
        self.assertLess(np.linalg.norm(np.array(hypotheses[0]['center_xyz_m'])-truth), .002)
        # The aligned rigid positive control also passes hypothesis selection.
        frames, truth = rigid_features((0., 0., 0.))
        selected = select_hypotheses(fit_window(frames))
        self.assertTrue(selected['detected'], selected)
        self.assertLess(np.linalg.norm(np.array(selected['object_center_xyz_m'])-truth), .002)
        # Analytic edges test geometry; they do not qualify RGB segmentation.

    def test_real_slipping_sequence_refuses_without_stale_position(self):
        tracker = TemporalPose()
        first = tracker.observe(observation(0))
        second = tracker.observe(observation(1))
        self.assertEqual(first['reason'], 'insufficient_motion_history')
        self.assertEqual(second['reason'], 'insufficient_motion_history')
        result = tracker.observe(observation(2))
        self.assertFalse(result['detected'])
        self.assertEqual(result['reason'], 'inconsistent_rigid_transform')
        self.assertNotIn('object_center_xyz_m', result)
        self.assertFalse(result['rigid_grasp_confirmed'])
        self.assertEqual(tracker.frames, [])

    def test_visibility_loss_and_time_gap_require_new_history(self):
        tracker = TemporalPose()
        tracker.observe(observation(0))
        hidden = observation(1)
        buffer = io.BytesIO()
        Image.new('RGB', (960, 720)).save(buffer, format='PNG')
        hidden['rgb_png_base64'] = base64.b64encode(buffer.getvalue()).decode()
        result = tracker.observe(hidden)
        self.assertFalse(result['detected'])
        self.assertEqual(result['history_size'], 0)
        result = tracker.observe(observation(2))
        self.assertEqual(result['history_size'], 1)
        later = observation(0)
        later.update(observation_id='later', time_s=100)
        result = tracker.observe(later)
        self.assertEqual(result['reason'], 'insufficient_motion_history')
        self.assertEqual(result['history_size'], 1)

    def test_malformed_metadata_clears_history(self):
        for invalid in [{'time_s': 10}, {'observation_id': 'bad', 'time_s': 'not-a-time'}]:
            tracker = TemporalPose()
            tracker.observe(observation(0))
            with self.assertRaisesRegex(ValueError, 'metadata'):
                tracker.observe(invalid)
            self.assertEqual(tracker.frames, [])

    def test_reused_or_nonadvancing_frames_clear_history(self):
        for same_id in [True, False]:
            tracker = TemporalPose()
            original = observation(0)
            tracker.observe(original)
            reused = copy.deepcopy(original)
            if not same_id:
                reused['observation_id'] = 'new-id-same-time'
            with self.assertRaisesRegex(ValueError, 'strictly increasing'):
                tracker.observe(reused)
            self.assertEqual(tracker.frames, [])

    def test_default_temporal_pose_preserves_p4_behavior(self):
        tracker = TemporalPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        result = tracker.observe(observation(2))
        self.assertFalse(result['detected'])
        self.assertEqual(result['reason'], 'inconsistent_rigid_transform')
        self.assertFalse(result['reacquisition_mode'])
        self.assertNotIn('reacquisition_seeded', result)
        self.assertEqual(tracker.frames, [])

    def test_reacquisition_seeds_valid_image_without_immediate_position(self):
        tracker = TemporalReacquisitionPose()
        first = tracker.observe(observation(0))
        second = tracker.observe(observation(1))
        self.assertEqual(first['reason'], 'insufficient_motion_history')
        self.assertEqual(second['reason'], 'insufficient_motion_history')
        result = tracker.observe(observation(2))
        self.assertFalse(result['detected'])
        self.assertEqual(result['reason'], 'inconsistent_rigid_transform')
        self.assertNotIn('object_center_xyz_m', result)
        self.assertTrue(result['reacquisition_mode'])
        self.assertTrue(result['reacquisition_seeded'])
        # Exactly one valid frame is retained as the new recovery seed
        self.assertEqual(len(tracker.frames), 1)
        self.assertEqual(tracker.frames[0]['time_s'], observation(2)['time_s'])

    def test_reacquisition_insufficient_motion_after_seed(self):
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        # Feed next observation with hand moved only 2 cm (< 80 mm threshold)
        small_motion = copy.deepcopy(observation(2))
        small_motion['observation_id'] = 'small-motion-next'
        small_motion['time_s'] = observation(2)['time_s'] + 0.5
        hand_xyz = list(small_motion['robot_state']['robot']['hand_xyz_m'])
        hand_xyz[2] += 0.02  # 20 mm translation
        small_motion['robot_state']['robot']['hand_xyz_m'] = hand_xyz
        res = tracker.observe(small_motion)
        self.assertFalse(res['detected'])
        self.assertEqual(res['reason'], 'insufficient_motion_history')
        self.assertNotIn('object_center_xyz_m', res)
        self.assertEqual(len(tracker.frames), 2)

    def test_reacquisition_sufficient_motion_fits_fresh_window(self):
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        # Feed next observation with hand moved 10 cm (>= 80 mm baseline)
        large_motion = copy.deepcopy(observation(2))
        large_motion['observation_id'] = 'large-motion-next'
        large_motion['time_s'] = observation(2)['time_s'] + 1.0
        hand_xyz = list(large_motion['robot_state']['robot']['hand_xyz_m'])
        hand_xyz[2] -= 0.10  # 100 mm translation
        large_motion['robot_state']['robot']['hand_xyz_m'] = hand_xyz

        mock_hypothesis = [
            {
                'rms_px': 0.05,
                'frame_rms_px': [0.05, 0.05],
                'center_xyz_m': [0.2, -0.35, 0.88],
                'object_to_hand_offset_m': [0.0, 0.0, 0.0],
            }
            for _ in range(3)
        ]
        with patch('humanoid_sim.temporal_pose.fit_window', return_value=mock_hypothesis) as mock_fit:
            res = tracker.observe(large_motion)
            mock_fit.assert_called_once()
            fitted_frames = mock_fit.call_args[0][0]
            # Assert fitted window contains exactly the fresh seed and new frame (length 2)
            self.assertEqual(len(fitted_frames), 2)
            self.assertEqual(fitted_frames[0]['time_s'], observation(2)['time_s'])
            self.assertEqual(fitted_frames[1]['time_s'], large_motion['time_s'])
            # Rejected old window (observations 0 and 1) is excluded
            self.assertNotIn(observation(0)['time_s'], [f['time_s'] for f in fitted_frames])
            self.assertNotIn(observation(1)['time_s'], [f['time_s'] for f in fitted_frames])
            self.assertTrue(res['detected'])
            self.assertEqual(res['object_center_xyz_m'], [0.2, -0.35, 0.88])
            self.assertEqual(len(tracker.frames), 2)

    def test_reacquisition_visibility_loss_clears_seeded_history(self):
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        hidden = copy.deepcopy(observation(2))
        hidden['observation_id'] = 'hidden-after-seed'
        hidden['time_s'] = observation(2)['time_s'] + 0.5
        buffer = io.BytesIO()
        Image.new('RGB', (960, 720)).save(buffer, format='PNG')
        hidden['rgb_png_base64'] = base64.b64encode(buffer.getvalue()).decode()
        result = tracker.observe(hidden)
        self.assertFalse(result['detected'])
        self.assertEqual(result['history_size'], 0)
        self.assertEqual(tracker.frames, [])

    def test_reacquisition_malformed_metadata_clears_seeded_history(self):
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        invalid = {'observation_id': 'bad', 'time_s': 'not-a-time'}
        with self.assertRaisesRegex(ValueError, 'metadata'):
            tracker.observe(invalid)
        self.assertEqual(tracker.frames, [])

    def test_reacquisition_reused_or_nonadvancing_clears_seeded_history(self):
        # 1. Duplicate ID with advanced time
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        dup_id = copy.deepcopy(observation(2))
        dup_id['time_s'] = observation(2)['time_s'] + 0.5
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            tracker.observe(dup_id)
        self.assertEqual(tracker.frames, [])

        # 2. Distinct ID with equal time
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        equal_time = copy.deepcopy(observation(2))
        equal_time['observation_id'] = 'distinct-id-equal-time'
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            tracker.observe(equal_time)
        self.assertEqual(tracker.frames, [])

        # 3. Distinct ID with regressing time
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        regressing_time = copy.deepcopy(observation(2))
        regressing_time['observation_id'] = 'distinct-id-regressing-time'
        regressing_time['time_s'] = observation(2)['time_s'] - 1.0
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            tracker.observe(regressing_time)
        self.assertEqual(tracker.frames, [])

    def test_reacquisition_time_gap_clears_seeded_history(self):
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        delayed = copy.deepcopy(observation(2))
        delayed['observation_id'] = 'delayed-frame'
        delayed['time_s'] = observation(2)['time_s'] + 10.0  # > 3.0 s MAX_GAP_S
        result = tracker.observe(delayed)
        self.assertEqual(result['reason'], 'insufficient_motion_history')
        # Time gap cleared seed before adding new frame, so history size is 1
        self.assertEqual(result['history_size'], 1)
        self.assertEqual(len(tracker.frames), 1)

    def test_reacquisition_release_invalidation(self):
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        tracker.observe(observation(2))
        self.assertEqual(len(tracker.frames), 1)
        # Explicit invalidation on release
        tracker.invalidate()
        self.assertEqual(tracker.frames, [])
        fresh = copy.deepcopy(observation(2))
        fresh['observation_id'] = 'fresh-after-release'
        fresh['time_s'] = observation(2)['time_s'] + 0.5
        result = tracker.observe(fresh)
        self.assertEqual(result['reason'], 'insufficient_motion_history')
        self.assertEqual(result['history_size'], 1)
        self.assertEqual(len(tracker.frames), 1)

    def test_reacquisition_episode_reset_isolation(self):
        tracker1 = TemporalReacquisitionPose()
        tracker1.observe(observation(0))
        tracker1.observe(observation(1))
        tracker1.observe(observation(2))
        self.assertEqual(len(tracker1.frames), 1)

        # Episode reset creates a fresh tracker instance
        tracker2 = TemporalReacquisitionPose()
        self.assertEqual(tracker2.frames, [])
        # Reset accepts earlier time_s without failing strictly-increasing checks
        reset_obs = copy.deepcopy(observation(0))
        reset_obs['time_s'] = 0.5  # Earlier than observation(2) time_s (~10.5s)
        res = tracker2.observe(reset_obs)
        self.assertEqual(res['reason'], 'insufficient_motion_history')
        self.assertEqual(res['history_size'], 1)
        self.assertEqual(len(tracker2.frames), 1)
        # Cannot retain frames or transforms from prior episode
        self.assertNotEqual(tracker2.frames[0]['time_s'], tracker1.frames[0]['time_s'])

    def test_invalid_camera_rotation_rejected_and_never_seeds(self):
        # Check zero matrix, scaled matrix, reflection matrix
        bad_rotations = [
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],  # Zero matrix
            (2.0 * np.eye(3)).tolist(),  # Scaled matrix
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, -1.0]],  # Reflection matrix (det = -1)
        ]
        for bad_rot in bad_rotations:
            tracker = TemporalReacquisitionPose()
            tracker.observe(observation(0))
            tracker.observe(observation(1))
            bad_obs = copy.deepcopy(observation(2))
            bad_obs['observation_id'] = f'bad-cam-rot-{bad_rot[0][0]}'
            bad_obs['camera']['world_to_camera_rotation'] = bad_rot
            with self.assertRaisesRegex(ValueError, 'camera rotation'):
                tracker.observe(bad_obs)
            # Must not be retained as seed; history is purged
            self.assertEqual(tracker.frames, [])

        # Valid calibrated rotation passes prepare_frame
        valid_obs = copy.deepcopy(observation(2))
        valid_obs['observation_id'] = 'valid-rot-obs'
        frame, diag = prepare_frame(valid_obs)
        self.assertIsNotNone(frame)

    def test_malformed_robot_and_calibration_inputs_after_seed_clears_history(self):
        malformed_cases = [
            ('robot hand position with NaN', lambda o: o['robot_state']['robot'].__setitem__('hand_xyz_m', [np.nan, 0, 0])),
            ('robot hand quaternion all zeros', lambda o: o['robot_state']['robot'].__setitem__('hand_quaternion_wxyz', [0, 0, 0, 0])),
            ('negative focal length', lambda o: o['camera'].__setitem__('focal_xy_px', [-900, 900])),
            ('infinite camera origin', lambda o: o['camera'].__setitem__('camera_world_xyz_m', [np.inf, 0, 0])),
            ('zero camera rotation', lambda o: o['camera'].__setitem__('world_to_camera_rotation', [[0, 0, 0]] * 3)),
        ]

        for name, modifier in malformed_cases:
            tracker = TemporalReacquisitionPose()
            tracker.observe(observation(0))
            tracker.observe(observation(1))
            tracker.observe(observation(2))
            self.assertEqual(len(tracker.frames), 1)

            bad_obs = copy.deepcopy(observation(2))
            bad_obs['observation_id'] = f'bad-{hash(name)}'
            bad_obs['time_s'] = observation(2)['time_s'] + 0.5
            modifier(bad_obs)
            with self.assertRaises(ValueError):
                tracker.observe(bad_obs)
            self.assertEqual(tracker.frames, [], f"Failed to clear history on {name}")

    def test_truncated_or_corrupt_image_never_seeds(self):
        # 1. Corrupt base64 string
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        corrupt_b64 = copy.deepcopy(observation(2))
        corrupt_b64['observation_id'] = 'corrupt-b64'
        corrupt_b64['rgb_png_base64'] = 'not-valid-base64!!@#'
        with self.assertRaises(Exception):
            tracker.observe(corrupt_b64)
        self.assertEqual(tracker.frames, [])

        # 2. Corrupt PNG bytes (valid base64 but invalid image)
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        corrupt_png = copy.deepcopy(observation(2))
        corrupt_png['observation_id'] = 'corrupt-png'
        corrupt_png['rgb_png_base64'] = base64.b64encode(b'this is not a valid png file').decode()
        with self.assertRaises(Exception):
            tracker.observe(corrupt_png)
        self.assertEqual(tracker.frames, [])

        # 3. Truncated / empty image where silhouette_features returns edges is None
        tracker = TemporalReacquisitionPose()
        tracker.observe(observation(0))
        tracker.observe(observation(1))
        empty_img = copy.deepcopy(observation(2))
        empty_img['observation_id'] = 'empty-black-frame'
        buf = io.BytesIO()
        Image.new('RGB', (960, 720)).save(buf, format='PNG')
        empty_img['rgb_png_base64'] = base64.b64encode(buf.getvalue()).decode()
        res = tracker.observe(empty_img)
        self.assertFalse(res['detected'])
        self.assertEqual(res['history_size'], 0)
        self.assertNotIn('reacquisition_seeded', res)
        self.assertEqual(tracker.frames, [])


if __name__ == '__main__':
    unittest.main()
