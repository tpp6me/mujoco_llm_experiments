import io
import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image
from humanoid_sim.vision_pose import estimate_supported_block

FIXTURES=Path(__file__).parent/'fixtures/humanoid_rgb'


class VisionPoseTests(unittest.TestCase):
    def test_saved_rgb_cases_reduce_side_face_bias(self):
        data=json.loads((FIXTURES/'cases.json').read_text())
        for case in data['cases']:
            with self.subTest(seed=case['seed']):
                result=estimate_supported_block((FIXTURES/f"seed-{case['seed']}.png").read_bytes(),data['camera'])
                self.assertTrue(result['detected'],result)
                error=np.linalg.norm(np.asarray(result['object_center_xyz_m'][:2])-case['private_true_center_xyz'][:2])
                self.assertLess(error,.004)
                self.assertLess(error,case['xy_error_m']/5)

    def test_missing_object_and_wrong_calibration_size(self):
        data=json.loads((FIXTURES/'cases.json').read_text())
        buffer=io.BytesIO();Image.new('RGB',(960,720)).save(buffer,format='PNG')
        self.assertFalse(estimate_supported_block(buffer.getvalue(),data['camera'])['detected'])
        buffer=io.BytesIO();Image.new('RGB',(20,20)).save(buffer,format='PNG')
        with self.assertRaisesRegex(ValueError,'dimensions'):
            estimate_supported_block(buffer.getvalue(),data['camera'])

    def test_occluded_patch_is_rejected(self):
        data=json.loads((FIXTURES/'cases.json').read_text())
        image=Image.open(FIXTURES/'seed-700.png').convert('RGB')
        # Synthetic sensor occlusion for a regression fixture, not a scored episode.
        pixels=np.asarray(image).copy();pixels[:,475:]=0
        buffer=io.BytesIO();Image.fromarray(pixels).save(buffer,format='PNG')
        result=estimate_supported_block(buffer.getvalue(),data['camera'])
        self.assertFalse(result['detected'],result)


if __name__=='__main__':unittest.main()
