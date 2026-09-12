import base64
import io
import json
from pathlib import Path
import unittest
from PIL import Image

from humanoid_sim.perception import RGBPerception, PerceptionSession

FIXTURES = Path(__file__).parent / 'fixtures'
CAMERA = json.loads((FIXTURES/'humanoid_rgb/cases.json').read_text())['camera']


def observation(name='initial', time=.5, identifier='frame-0'):
    path = (FIXTURES/'humanoid_rgb/seed-700.png' if name == 'initial'
            else FIXTURES/f'humanoid_carried_rgb/{name}.png')
    return {'observation_id': identifier, 'time_s': time, 'camera': CAMERA,
            'rgb_png_base64': base64.b64encode(path.read_bytes()).decode()}


class PerceptionTests(unittest.TestCase):
    def test_visible_carried_and_released_block_do_not_restore_support(self):
        tracker = RGBPerception()
        self.assertTrue(tracker.observe(observation())['pose']['detected'])
        tracker.invalidate_support()
        for i, name in enumerate(['carried', 'released'], 1):
            result = tracker.observe(observation(name, i*2, f'frame-{i}'))
            self.assertTrue(result['visibility']['detected'])
            self.assertFalse(result['pose']['detected'])
            self.assertNotIn('object_center_xyz_m', result['pose'])
            self.assertFalse(result['support_prior_valid'])

    def test_time_advancement_expires_support_without_action_notification(self):
        tracker = RGBPerception()
        tracker.observe(observation())
        result = tracker.observe(observation(time=.6, identifier='new'))
        self.assertFalse(result['support_prior_valid'])
        self.assertFalse(result['pose']['detected'])

    def test_reused_or_regressing_observation_is_rejected(self):
        tracker = RGBPerception()
        tracker.observe(observation())
        with self.assertRaisesRegex(ValueError, 'reused'):
            tracker.observe(observation())
        with self.assertRaisesRegex(ValueError, 'regressing'):
            tracker.observe(observation(time=.4, identifier='new'))

    def test_total_visibility_loss_does_not_return_old_position(self):
        tracker = RGBPerception()
        tracker.observe(observation())
        tracker.invalidate_support()
        frame = observation(time=1, identifier='hidden')
        buffer = io.BytesIO()
        Image.new('RGB', (960, 720)).save(buffer, format='PNG')
        frame['rgb_png_base64'] = base64.b64encode(buffer.getvalue()).decode()
        result = tracker.observe(frame)
        self.assertFalse(result['visibility']['detected'])
        self.assertFalse(result['pose']['detected'])
        self.assertNotIn('object_center_xyz_m', result['pose'])

    def test_rejected_attempt_still_expires_prior(self):
        class Session:
            count = 0
            def capture(self):
                self.count += 1
                return observation(identifier=f'frame-{self.count}')
            def execute(self, identifier, request):
                return {'status': 'rejected'}
        session = PerceptionSession(Session())
        frame, result = session.capture()
        self.assertTrue(result['pose']['detected'])
        self.assertEqual(session.execute(frame['observation_id'], {})['status'], 'rejected')
        _, result = session.capture()
        self.assertFalse(result['pose']['detected'])


if __name__ == '__main__':
    unittest.main()
