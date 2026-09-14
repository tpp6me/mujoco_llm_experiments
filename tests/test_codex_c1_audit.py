"""Reproduce C1's saved failure without physics steps or new model decisions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.audit_codex_c1 import audit
from humanoid_sim.scene import ROOT


class C1AuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        with zipfile.ZipFile(ROOT / 'experiments/humanoid-pick-place/results/codex_C1_episode.zip') as z:
            for name in z.namelist():
                if name.startswith('seed-820/'):
                    z.extract(name, self.root)
        self.episode = self.root / 'seed-820'

    def test_saved_failure_reproduces_with_physics_disabled(self):
        with patch('mujoco.mj_step', side_effect=AssertionError('No physics steps allowed')), patch('humanoid_sim.environment.Environment.reset', side_effect=AssertionError('No fresh reset allowed')):
            result = audit(self.episode, self.root / 'audit')
        self.assertEqual(result['physics_steps'], 0)
        self.assertEqual(result['model_invocations'], 0)
        self.assertAlmostEqual(result['object_displacement_m'][0], -.081994156, places=6)
        self.assertLess(result['approach_end']['object_upright_axis_z_abs'], .001)
        first = result['rejected_path']['first_violation']
        self.assertEqual(first['sample_index'], 62)
        self.assertEqual({v['body_names'][1] for v in first['violations']},
                         {'right_hand_middle_1_link', 'right_hand_index_1_link'})
        self.assertTrue(all(v['geom_names'][0] == 'table' for v in first['violations']))
        self.assertTrue(result['rejected_path']['final_integration_state_unchanged'])
        self.assertAlmostEqual(result['authoritative_private_score']['max_object_penetration_m'], .006290933918)
        self.assertLess(result['max_sampled_object_hand_penetration']['penetration_m'],
                        result['authoritative_private_score']['max_object_penetration_m'])

    def test_modified_evidence_is_rejected_before_output(self):
        path = self.episode / 'call_003.json'
        call = json.loads(path.read_text())
        call['command']['arguments']['xyz_m'][2] = .9
        path.write_text(json.dumps(call))
        with self.assertRaisesRegex(ValueError, 'archive manifest'):
            audit(self.episode, self.root / 'audit')
        self.assertFalse((self.root / 'audit').exists())

    def test_overlap_and_existing_output_are_rejected(self):
        for output in (self.episode, self.episode / 'audit', self.root):
            with self.assertRaises(ValueError):
                audit(self.episode, output)
        existing = self.root / 'existing'
        existing.mkdir()
        with self.assertRaisesRegex(ValueError, 'must be new'):
            audit(self.episode, existing)


if __name__ == '__main__':
    unittest.main()
