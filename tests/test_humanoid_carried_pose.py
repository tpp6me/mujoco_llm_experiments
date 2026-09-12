import io
import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from humanoid_sim.carried_pose import estimate_carried_block, select_hypotheses

FIXTURES = Path(__file__).parent/'fixtures/humanoid_carried_rgb'
CASES = json.loads((FIXTURES/'carried_pose_cases.json').read_text())


class CarriedPoseTests(unittest.TestCase):
    def test_saved_tilted_views_and_ambiguous_transport(self):
        for case in CASES:
            with self.subTest(name=case['name']):
                result = estimate_carried_block((FIXTURES/f"{case['name']}.png").read_bytes(),
                                                case['camera'], case['hand_xyz_m'])
                if case['name'] == 'carried':
                    self.assertFalse(result['detected'])
                    self.assertEqual(result['reason'], 'ambiguous_depth_or_orientation')
                    self.assertNotIn('object_center_xyz_m', result)
                else:
                    self.assertTrue(result['detected'], result)
                    error = np.linalg.norm(np.array(result['object_center_xyz_m'])-case['private_true_xyz_m'])
                    self.assertLess(error, .02)
                self.assertFalse(result['orientation_qualified'])

    def test_loss_and_image_boundary_truncation_refuse_without_position(self):
        case = CASES[0]
        for truncated in [False, True]:
            image = Image.new('RGB', (960, 720))
            if truncated:
                image.paste((255, 0, 0), (0, 200, 80, 300))
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            result = estimate_carried_block(buffer.getvalue(), case['camera'], case['hand_xyz_m'])
            self.assertFalse(result['detected'])
            self.assertNotIn('object_center_xyz_m', result)

    def test_similarly_good_distant_solutions_are_not_averaged(self):
        result = select_hypotheses([
            {'center_xyz_m': [.2, -.3, z], 'rms_px': .1} for z in [.8, .8, .9]])
        self.assertFalse(result['detected'])
        self.assertEqual(result['reason'], 'ambiguous_depth_or_orientation')
        self.assertNotIn('object_center_xyz_m', result)

    def test_bad_inputs_fail_before_fitting(self):
        case = CASES[0]
        png = (FIXTURES/'lift.png').read_bytes()
        with self.assertRaisesRegex(ValueError, 'hand'):
            estimate_carried_block(png, case['camera'], [float('nan'), 0, 0])
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            estimate_carried_block(png, {**case['camera'], 'width': 10}, case['hand_xyz_m'])
        with self.assertRaisesRegex(ValueError, 'focal'):
            estimate_carried_block(png, {**case['camera'], 'focal_xy_px': [0, 1]}, case['hand_xyz_m'])


if __name__ == '__main__':
    unittest.main()
