import base64
import copy
import io
import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from humanoid_sim.temporal_pose import (CORNERS, TemporalPose, convex_hull, fit_window,
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


if __name__ == '__main__':
    unittest.main()
