"""Reproduce C2's saved failure without physics steps, resets, or model invocations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from humanoid_sim.scene import ROOT
import scripts.audit_codex_c2
from scripts.audit_codex_c2 import audit, PINNED_C2_ARCHIVE_SHA256


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
            patch('subprocess.Popen', side_effect=AssertionError('No subprocess.Popen calls allowed')),
            patch('subprocess.run', side_effect=AssertionError('No subprocess.run calls allowed')),
        ):
            output_dir = self.root / 'audit'
            result = audit(self.episode, output_dir)

        # Zero physics advance or model decisions
        self.assertEqual(result['physics_steps'], 0)
        self.assertEqual(result['model_invocations'], 0)

        # Action 4 kinematics: ~154.27 mm horizontal displacement and toppling
        act4 = result['action_4_analysis']
        self.assertAlmostEqual(act4['object_xy_displacement_m'], 0.15426949, places=6)
        self.assertAlmostEqual(act4['object_3d_displacement_m'], 0.15521163, places=6)
        self.assertLess(act4['object_upright_axis_z_final'], 0.001)
        self.assertAlmostEqual(act4['object_rotation_deg'], 166.578, places=2)

        # Action 4 contacts: first contact sample 117
        first_c = act4['first_sampled_hand_contact']
        self.assertIsNotNone(first_c)
        self.assertEqual(first_c['sample_index'], 117)
        self.assertAlmostEqual(first_c['time_s'], 3.761, places=2)
        self.assertEqual(first_c['contacts'][0]['body_names'][1], 'right_hand_middle_0_link')
        self.assertAlmostEqual(first_c['penetration_m'], 0.000274, places=5)

        # Scorer telemetry vs sampled qpos geometry
        scorer_telem = result['telemetry_vs_sampled_geometry']['full_rate_scorer_telemetry']
        self.assertEqual(scorer_telem['rate_hz'], 1000)
        self.assertAlmostEqual(scorer_telem['peak_time_s'], 3.795, places=3)
        self.assertEqual(scorer_telem['other_body'], 'right_hand_middle_0_link')
        self.assertAlmostEqual(scorer_telem['penetration_m'], 0.005184672, places=6)
        self.assertAlmostEqual(scorer_telem['normal_force_at_peak_penetration_n'], 25.506541, places=3)

        sampled_geom = result['telemetry_vs_sampled_geometry']['sampled_qpos_geometry']
        self.assertEqual(sampled_geom['rate_hz'], 30)
        self.assertEqual(sampled_geom['nearest_to_scorer_peak_sample_index'], 118)
        self.assertAlmostEqual(sampled_geom['nearest_sample_time_s'], 3.794, places=3)
        self.assertAlmostEqual(sampled_geom['nearest_sample_penetration_m'], 0.005184672, places=6)
        self.assertEqual(sampled_geom['max_contact_sample_index'], 118)
        self.assertAlmostEqual(sampled_geom['max_sampled_penetration_m'], 0.005184672, places=6)

        # Action 9 IK rejection reproduced on scratch data without mutating state
        act9 = result['action_9_rejection']
        expected_err = 'Unreachable hand pose [0.15, -0.48, 0.9]: residual 0.0542 m'
        self.assertEqual(act9['production_error'], expected_err)
        self.assertEqual(act9['reproduced_error'], expected_err)
        self.assertEqual(act9['ik_residual_m'], 0.0542)
        self.assertEqual(act9['ik_residual_precision'], 'four_decimals')
        self.assertTrue(act9['final_integration_state_unchanged'])

        # Descriptive C1 vs C2 comparison derived dynamically
        comp = result['descriptive_c1_c2_comparison']
        self.assertAlmostEqual(comp['c1']['first_damaging_action_xy_displacement_mm'], 84.6396, places=2)
        self.assertAlmostEqual(comp['c1']['first_damaging_action_3d_displacement_mm'], 91.5908, places=2)
        self.assertAlmostEqual(comp['c2']['first_damaging_action_xy_displacement_mm'], 154.2695, places=2)
        self.assertAlmostEqual(comp['c2']['first_damaging_action_3d_displacement_mm'], 155.2116, places=2)
        self.assertAlmostEqual(comp['c2']['action_4_start_to_action_5_end_3d_displacement_mm'], 804.1448, places=2)
        self.assertIn('c1_archive_sha256', comp['evidence_sources'])
        self.assertIn('c2_archive_sha256', comp['evidence_sources'])

        # Artifact existence and non-emptiness
        self.assertTrue((output_dir / 'audit.json').is_file())
        self.assertTrue((output_dir / 'contact_sheet.png').is_file())
        self.assertGreater((output_dir / 'contact_sheet.png').stat().st_size, 50000)
        self.assertTrue((output_dir / 'public_proprioception_history.json').is_file())
        self.assertTrue((output_dir / 'private_trajectory_annotations.json').is_file())

    def test_r1_public_proprioception_matches_archived_requests_and_rejects_missing(self):
        output_dir = self.root / 'audit'
        audit(self.episode, output_dir)

        public_history = json.loads((output_dir / 'public_proprioception_history.json').read_text())
        self.assertEqual(len(public_history), 7)
        self.assertEqual([entry['call'] for entry in public_history], list(range(3, 10)))

        for entry in public_history:
            c_num = entry['call']
            call_data = json.loads((self.episode / f'call_{c_num:03}.json').read_text())
            archived_req = call_data['request']
            archived_obs = archived_req['observation']

            # Must distinguish input preceding decision from subsequent command/outcome
            self.assertIn('input_preceding_decision', entry)
            self.assertIn('subsequent_command_and_execution', entry)
            inp = entry['input_preceding_decision']
            sub = entry['subsequent_command_and_execution']

            # Public robot state must be non-null and match archived observation exactly
            self.assertIsNotNone(inp['public_robot_state'])
            self.assertEqual(inp['public_robot_state'], archived_obs['robot_state'])
            self.assertEqual(len(inp['public_robot_state']['robot']['joint_names']), 43)
            self.assertEqual(len(inp['public_robot_state']['robot']['joint_position_rad']), 43)
            self.assertEqual(len(inp['public_robot_state']['robot']['joint_velocity_rad_s']), 43)
            self.assertEqual(len(inp['public_robot_state']['robot']['hand_xyz_m']), 3)
            self.assertEqual(len(inp['public_robot_state']['robot']['hand_quaternion_wxyz']), 4)

            # Public history must match archived request history
            self.assertEqual(inp['public_history'], archived_req['history'])

            # Image identity must match archived request
            self.assertEqual(inp['image_sha256'], call_data['image_sha256'])

            # Command and outcome
            self.assertEqual(sub['command'], call_data['command'])
            self.assertEqual(sub['execution_status'], call_data['status'])

        # Explicit rejection test: corrupt robot_state in call_003 and verify ValueError
        call_3_path = self.episode / 'call_003.json'
        call_3_data = json.loads(call_3_path.read_text())
        del call_3_data['request']['observation']['robot_state']['robot']['joint_names']
        call_3_path.write_text(json.dumps(call_3_data))

        fail_dir = self.root / 'audit_fail'
        with self.assertRaisesRegex(ValueError, 'missing or null robot field: joint_names|archive member manifest'):
            audit(self.episode, fail_dir)
        self.assertFalse(fail_dir.exists())

    def test_r2_penetration_and_samples_distinct_and_derived(self):
        output_dir = self.root / 'audit'
        result = audit(self.episode, output_dir)

        sampled_geom = result['telemetry_vs_sampled_geometry']['sampled_qpos_geometry']

        # Nearest sample to scorer peak is 118 with ~5.185 mm penetration
        self.assertEqual(sampled_geom['nearest_to_scorer_peak_sample_index'], 118)
        self.assertAlmostEqual(sampled_geom['nearest_sample_penetration_m'], 0.005184672, places=6)

        # First sampled contact sample is 117 with ~0.274 mm penetration
        self.assertEqual(sampled_geom['first_contact_sample_index'], 117)
        self.assertAlmostEqual(sampled_geom['first_contact_penetration_m'], 0.000274117, places=6)
        self.assertEqual(sampled_geom['first_sampled_contact_sample_index'], 117)
        self.assertAlmostEqual(sampled_geom['first_sampled_contact_penetration_m'], 0.000274117, places=6)

        # Verify they are distinct values
        self.assertNotEqual(
            sampled_geom['nearest_sample_penetration_m'],
            sampled_geom['first_contact_penetration_m'],
        )
        self.assertGreater(
            sampled_geom['nearest_sample_penetration_m'],
            sampled_geom['first_contact_penetration_m'] * 10,
        )

        # Max contact sample index derived dynamically
        self.assertEqual(sampled_geom['max_contact_sample_index'], 118)
        self.assertAlmostEqual(sampled_geom['max_sampled_penetration_m'], 0.005184672, places=6)

        # IK residual derived from reproduced error message
        act9 = result['action_9_rejection']
        self.assertEqual(act9['ik_residual_m'], 0.0542)
        self.assertEqual(act9['ik_residual_precision'], 'four_decimals')

    def test_source_mismatch_is_rejected_before_output(self):
        # Episode bytes stay intact; perturb only the source file digest check
        orig_digest = scripts.audit_codex_c2.digest

        def mock_digest(path):
            if Path(path).name == 'environment.py':
                return '0' * 64
            return orig_digest(path)

        fail_dir = self.root / 'audit_source_mismatch'
        with patch('scripts.audit_codex_c2.digest', side_effect=mock_digest):
            with self.assertRaisesRegex(ValueError, 'Execution source changed: humanoid_sim/environment.py'):
                audit(self.episode, fail_dir)
        self.assertFalse(fail_dir.exists())

    def test_scene_mismatch_is_rejected_before_output(self):
        # Episode bytes stay intact; perturb only the scene file digest check
        orig_digest = scripts.audit_codex_c2.digest

        def mock_digest(path):
            if Path(path).name == 'g1_pick_place.xml':
                return '0' * 64
            return orig_digest(path)

        fail_dir = self.root / 'audit_scene_mismatch'
        with patch('scripts.audit_codex_c2.digest', side_effect=mock_digest):
            with self.assertRaisesRegex(ValueError, 'Scene changed'):
                audit(self.episode, fail_dir)
        self.assertFalse(fail_dir.exists())

    def test_archive_digest_mismatch_is_rejected_before_output(self):
        fail_dir = self.root / 'audit_archive_mismatch'
        with patch('scripts.audit_codex_c2.PINNED_C2_ARCHIVE_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'does not match pinned C2 archive digest'):
                audit(self.episode, fail_dir)
        self.assertFalse(fail_dir.exists())

    def test_modified_evidence_is_rejected_before_output(self):
        path = self.episode / 'call_004.json'
        call = json.loads(path.read_text())
        call['command']['arguments']['xyz_m'][2] = 0.9
        path.write_text(json.dumps(call))
        with self.assertRaisesRegex(ValueError, 'archive member manifest'):
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
