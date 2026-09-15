"""Reproduce C2's saved failure without physics steps, resets, or model invocations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from humanoid_sim.scene import ROOT
from scripts.audit_codex_c2 import audit


class C2AuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        archive_path = ROOT / 'experiments/humanoid-pick-place/results/codex_C2_episode.zip'
        with zipfile.ZipFile(archive_path) as z:
            for name in z.namelist():
                if name.startswith('seed-820/'):
                    z.extract(name, self.root)
        self.episode = self.root / 'seed-820'

    def test_saved_c2_failure_reproduces_with_physics_and_model_disabled(self):
        with (
            patch('mujoco.mj_step', side_effect=AssertionError('No physics steps allowed')),
            patch('humanoid_sim.environment.Environment.reset', side_effect=AssertionError('No fresh reset allowed')),
            patch('subprocess.run', side_effect=AssertionError('No external subprocess/model calls allowed')),
        ):
            output_dir = self.root / 'audit'
            result = audit(self.episode, output_dir)

        # Zero physics advance or model decisions
        self.assertEqual(result['physics_steps'], 0)
        self.assertEqual(result['model_invocations'], 0)

        # Action 4 kinematics: ~154.27 mm horizontal displacement and toppling
        act4 = result['action_4_analysis']
        self.assertAlmostEqual(act4['object_xy_displacement_m'], 0.15426949, places=6)
        self.assertLess(act4['object_upright_axis_z_final'], 0.001)
        self.assertAlmostEqual(act4['object_rotation_deg'], 166.578, places=2)

        # Action 4 contacts
        first_c = act4['first_sampled_hand_contact']
        self.assertIsNotNone(first_c)
        self.assertEqual(first_c['object_hand_contacts'][0]['body_names'][1], 'right_hand_middle_0_link')
        self.assertAlmostEqual(first_c['time_s'], 3.761, places=2)

        # Distinguish 1 kHz scorer telemetry from sampled geometry
        scorer_telem = result['telemetry_vs_sampled_geometry']['full_rate_scorer_telemetry']
        self.assertEqual(scorer_telem['rate_hz'], 1000)
        self.assertAlmostEqual(scorer_telem['peak_time_s'], 3.795, places=3)
        self.assertEqual(scorer_telem['other_body'], 'right_hand_middle_0_link')
        self.assertAlmostEqual(scorer_telem['penetration_m'], 0.005184672, places=6)
        self.assertAlmostEqual(scorer_telem['normal_force_at_peak_penetration_n'], 25.506541, places=3)

        sampled_geom = result['telemetry_vs_sampled_geometry']['sampled_qpos_geometry']
        self.assertEqual(sampled_geom['rate_hz'], 30)
        self.assertEqual(sampled_geom['nearest_sample_index'], 118)

        # Action 9 IK rejection reproduced on scratch data without mutating state
        act9 = result['action_9_rejection']
        expected_err = 'Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m'
        self.assertEqual(act9['production_error'], expected_err)
        self.assertEqual(act9['reproduced_error'], expected_err)
        self.assertAlmostEqual(act9['ik_residual_m'], 0.0542, places=4)
        self.assertTrue(act9['final_integration_state_unchanged'])

        # Authoritative evaluator report
        self.assertFalse(result['authoritative_private_score']['success'])
        self.assertFalse(result['authoritative_private_score']['lifted'])
        self.assertAlmostEqual(
            result['authoritative_private_score']['max_object_penetration_m'],
            0.005184672,
            places=6,
        )

        # Artifact existence and non-emptiness
        self.assertTrue((output_dir / 'audit.json').is_file())
        self.assertTrue((output_dir / 'contact_sheet.png').is_file())
        self.assertGreater((output_dir / 'contact_sheet.png').stat().st_size, 50000)
        self.assertTrue((output_dir / 'public_proprioception_history.json').is_file())
        self.assertTrue((output_dir / 'private_trajectory_annotations.json').is_file())

        public_history = json.loads((output_dir / 'public_proprioception_history.json').read_text())
        self.assertEqual(len(public_history), 7)
        self.assertEqual([entry['call'] for entry in public_history], list(range(3, 10)))

        private_annotations = json.loads((output_dir / 'private_trajectory_annotations.json').read_text())
        self.assertEqual(len(private_annotations['decisions_3_to_9_ground_truth']), 7)
        self.assertIn('action_4_trajectory_samples', private_annotations)

    def test_modified_evidence_is_rejected_before_output(self):
        path = self.episode / 'call_004.json'
        call = json.loads(path.read_text())
        call['command']['arguments']['xyz_m'][2] = 0.9
        path.write_text(json.dumps(call))
        with self.assertRaisesRegex(ValueError, 'archive manifest'):
            audit(self.episode, self.root / 'audit')
        self.assertFalse((self.root / 'audit').exists())

    def test_source_mismatch_is_rejected_before_output(self):
        report_path = self.episode / 'report.json'
        report = json.loads(report_path.read_text())
        report['provenance']['source_sha256']['humanoid_sim/environment.py'] = '0' * 64
        report_path.write_text(json.dumps(report))
        # This will be caught by manifest or source check
        with self.assertRaises(ValueError):
            audit(self.episode, self.root / 'audit')
        self.assertFalse((self.root / 'audit').exists())

    def test_scene_mismatch_is_rejected_before_output(self):
        with patch('scripts.audit_codex_c2.digest', side_effect=lambda p: '0' * 64 if p.name == 'g1_pick_place.xml' else 'f' * 64):
            with self.assertRaises(ValueError):
                audit(self.episode, self.root / 'audit')
        self.assertFalse((self.root / 'audit').exists())

    def test_overlap_and_existing_output_are_rejected(self):
        for bad_output in (self.episode, self.episode / 'audit', self.root):
            with self.assertRaisesRegex(ValueError, 'must not overlap'):
                audit(self.episode, bad_output)
        existing = self.root / 'existing'
        existing.mkdir()
        with self.assertRaisesRegex(ValueError, 'must be new'):
            audit(self.episode, existing)


if __name__ == '__main__':
    unittest.main()
