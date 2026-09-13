"""Focused tests for the bounded provider-neutral offline visual policy runner."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image

from humanoid_sim.environment import Environment
from humanoid_sim.interface import PolicyInterface, VERSION, INSTRUCTION_VERSION
from humanoid_sim.visual import VisualSession, calibration, integration_state
from humanoid_sim.visual_policy_runner import (
    MAX_CALLS,
    DEADLINE,
    VISUAL_PROMPT,
    ModelRefusalError,
    MalformedResponseError,
    strict_json,
    action_schema,
    allowlist_camera,
    allowlist_robot,
    allowlist_robot_state,
    allowlist_observation,
    build_public_payload,
    parse_and_validate_response,
    VisualPolicySession,
    HoldStub,
    ScriptedDemoStub,
    RefusalStub,
    MalformedStub,
    ExceptionStub,
    CollisionStub,
    get_named_stub,
    provenance,
    run_visual_episode
)


def make_dummy_png():
    img = np.zeros((30, 40, 3), dtype=np.uint8)
    img[10:20, 15:25, 0] = 200
    import io
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format='PNG')
    return buf.getvalue()


def make_dummy_camera():
    return calibration(SimpleNamespace(
        forward=[0, 0, -1], up=[0, 1, 0], pos=[0.24, -0.8, 2.0],
        frustum_near=0.1, frustum_top=0.05, frustum_bottom=-0.05, frustum_center=0
    ))


class MockRenderer:
    def __init__(self):
        self.png_bytes = make_dummy_png()
        self.camera_dict = make_dummy_camera()

    def capture(self):
        return self.png_bytes, copy.deepcopy(self.camera_dict)

    def close(self):
        pass


class MockClock:
    def __init__(self, start=1000.0, step=0.35):
        self.time = start
        self.step = step

    def __call__(self):
        current = self.time
        self.time += self.step
        return current


class VisualPolicyRunnerTests(unittest.TestCase):

    def test_allowlist_excludes_planted_private_fields(self):
        # Load saved development capture if available, or construct synthetic
        sample_path = Path('/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture/seed-820/00-observation.json')
        if sample_path.exists():
            obs = json.loads(sample_path.read_text())
        else:
            png_bytes = make_dummy_png()
            cam = make_dummy_camera()
            env = Environment()
            env.reset(820, randomize=True)
            rs = PolicyInterface(env, 'robot_state').observe()
            obs = {
                'schema_version': 'humanoid-visual-v1',
                'observation_id': 'test-obs-001',
                'time_s': 0.5,
                'camera': cam,
                'robot_state': rs,
                'rgb_png_base64': base64.b64encode(png_bytes).decode('ascii')
            }

        # Plant malicious / private fields in observation, robot_state, camera, and history
        obs['secret_object_truth'] = [0.24, -0.18, 0.76]
        obs['task_state'] = {'object_pose': [0.24, -0.18, 0.76]}
        obs['score'] = {'placement_success': True, 'max_penetration': 0.001}
        obs['private_scorer_report'] = {'cheating': True}
        obs['robot_state']['task_state'] = {'object': 'block'}
        obs['robot_state']['private_diagnostics'] = 'leak_data'
        obs['camera']['planted_camera_tag'] = 'oracle_cam'

        history = [
            {
                'action': {
                    'action': 'hold',
                    'arguments': {'seconds': 0.5},
                    'request_id': 'h-1',
                    'planted_action_metadata': 'secret'
                },
                'response': {
                    'request_id': 'h-1',
                    'status': 'completed',
                    'start_time_s': 0.0,
                    'end_time_s': 0.5,
                    'score': {'success': True},
                    'task_state': {'leak': 123},
                    'planted_response_metadata': 'secret'
                }
            }
        ]

        payload = build_public_payload(obs, history, deadline=25.0, max_calls=20, calls=1)
        serialized = json.dumps(payload, allow_nan=False)

        # Verify allowed public elements are present
        self.assertIn('rgb_png_base64', payload['observation'])
        self.assertIn('rgb_sha256', payload['observation'])
        self.assertIn('camera', payload['observation'])
        self.assertIn('robot_state', payload['observation'])
        self.assertIn('robot', payload['observation']['robot_state'])
        self.assertEqual(payload['remaining_actions'], 19)
        self.assertAlmostEqual(payload['remaining_time_s'], 25.0 - obs['time_s'])
        self.assertIn('joint_position_rad', payload['observation']['robot_state']['robot'])

        # Verify visual prompt does NOT say "no images are supplied"
        self.assertNotIn('no images are supplied', payload['instruction'])
        self.assertIn('visual observations', payload['instruction'])

        # Verify ZERO planted fields survive in observation and history
        self.assertNotIn('score', payload['observation'])
        self.assertNotIn('score', payload['history'][0]['response'])
        self.assertNotIn('secret_object_truth', serialized)
        self.assertNotIn('planted', serialized)
        self.assertNotIn('task_state', serialized)
        self.assertNotIn('private_scorer_report', serialized)
        self.assertNotIn('private_diagnostics', serialized)
        self.assertNotIn('oracle_cam', serialized)
        self.assertNotIn('cheating', serialized)

    def test_valid_command_uses_captured_id_and_single_use(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()))

        obs1 = session.capture()
        obs_id_1 = obs1['observation_id']

        hold_req = {
            'schema_version': VERSION,
            'instruction_version': INSTRUCTION_VERSION,
            'request_id': 'req-1',
            'action': 'hold',
            'arguments': {'seconds': 0.1}
        }

        # First execution with matching ID must succeed
        res1 = session.execute(obs_id_1, hold_req)
        self.assertEqual(res1['status'], 'completed')
        self.assertAlmostEqual(env.data.time, 0.6)  # reset 0.5s + 0.1s

        # Second execution with same observation ID must be rejected as stale
        hold_req_2 = {
            'schema_version': VERSION,
            'instruction_version': INSTRUCTION_VERSION,
            'request_id': 'req-2',
            'action': 'hold',
            'arguments': {'seconds': 0.1}
        }
        res2 = session.execute(obs_id_1, hold_req_2)
        self.assertEqual(res2['status'], 'rejected')
        self.assertIn('Stale or unknown', res2['error'])
        # Physics must not advance
        self.assertAlmostEqual(env.data.time, 0.6)

        # Capturing fresh observation allows next execution
        obs2 = session.capture()
        self.assertNotEqual(obs2['observation_id'], obs_id_1)
        res3 = session.execute(obs2['observation_id'], hold_req_2)
        self.assertEqual(res3['status'], 'completed')
        self.assertAlmostEqual(env.data.time, 0.7)

    def test_stale_or_invalid_id_rejected_without_movement(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()))
        session.capture()

        before_qpos = env.data.qpos.copy()
        before_time = env.data.time

        res = session.execute('fabricated-fake-id', {
            'schema_version': VERSION,
            'instruction_version': INSTRUCTION_VERSION,
            'request_id': 'fake-req',
            'action': 'hold',
            'arguments': {'seconds': 0.1}
        })
        self.assertEqual(res['status'], 'rejected')
        self.assertIn('Stale or unknown', res['error'])
        self.assertEqual(env.data.time, before_time)
        np.testing.assert_array_equal(env.data.qpos, before_qpos)

    def test_model_refusal_terminates_cleanly_without_retries(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()))

        with tempfile.TemporaryDirectory() as tmpdir:
            calls_made = []

            def refusal_model(payload):
                calls_made.append(payload)
                return {'refusal': 'I decline to operate robot manipulators.'}

            episode_folder = Path(tmpdir) / 'episode'
            report = run_visual_episode(
                folder=episode_folder,
                session=session,
                model_callable=refusal_model,
                max_calls=20,
                seed=820,
                controller_name='test_refusal'
            )

            self.assertEqual(report['termination_reason'], 'refusal')
            self.assertEqual(report['model_calls'], 1)
            self.assertEqual(report['completed_actions'], 0)
            self.assertEqual(report['refusals'], 1)
            self.assertIn('decline', report['error'])
            self.assertEqual(len(calls_made), 1)

            # Check call file
            call_log = json.loads((episode_folder / 'call_001.json').read_text())
            self.assertEqual(call_log['status'], 'refusal')

    def test_malformed_response_and_json_terminates_cleanly(self):
        # Case A: invalid JSON string
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()))

        with tempfile.TemporaryDirectory() as tmpdir:
            episode_folder = Path(tmpdir) / 'episode'
            report = run_visual_episode(
                folder=episode_folder,
                session=session,
                model_callable=lambda p: 'NOT_VALID_JSON{',
                max_calls=20,
                seed=820,
                controller_name='test_malformed'
            )
            self.assertEqual(report['termination_reason'], 'malformed_response')
            self.assertEqual(report['model_calls'], 1)
            self.assertEqual(report['completed_actions'], 0)
            self.assertEqual(report['errors'], 1)

        # Case B: valid JSON but invalid action name
        env2 = Environment()
        env2.reset(820, randomize=True)
        session2 = VisualPolicySession(VisualSession(env2, MockRenderer()))
        with tempfile.TemporaryDirectory() as tmpdir2:
            episode_folder2 = Path(tmpdir2) / 'episode'
            report2 = run_visual_episode(
                folder=episode_folder2,
                session=session2,
                model_callable=lambda p: {'command': {'action': 'teleport', 'arguments': {}}},
                max_calls=20,
                seed=820,
                controller_name='test_malformed_action'
            )
            self.assertEqual(report2['termination_reason'], 'malformed_response')
            self.assertIn('teleport', report2['error'])

    def test_model_exception_terminates_cleanly(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()))

        with tempfile.TemporaryDirectory() as tmpdir:
            def crashing_stub(payload):
                raise ConnectionResetError('Simulated transport fault')

            episode_folder = Path(tmpdir) / 'episode'
            report = run_visual_episode(
                folder=episode_folder,
                session=session,
                model_callable=crashing_stub,
                max_calls=20,
                seed=820,
                controller_name='test_exception'
            )
            self.assertEqual(report['termination_reason'], 'exception')
            self.assertEqual(report['model_calls'], 1)
            self.assertIn('ConnectionResetError', report['error'])

    def test_collision_rejection_terminates_without_fallback(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()))

        with tempfile.TemporaryDirectory() as tmpdir:
            # Table is at z=0.70; targeting z=0.65 penetrates table and triggers preflight guard
            collision_model = CollisionStub()

            episode_folder = Path(tmpdir) / 'episode'
            report = run_visual_episode(
                folder=episode_folder,
                session=session,
                model_callable=collision_model,
                max_calls=20,
                seed=820,
                controller_name='test_collision'
            )
            self.assertEqual(report['termination_reason'], 'rejected_action')
            self.assertEqual(report['model_calls'], 1)
            self.assertEqual(report['completed_actions'], 0)
            self.assertIn('penetration', report['error'])

    def test_action_limit_and_deadline_budget_enforcement(self):
        # Test max_calls = 3 limit
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            episode_folder = Path(tmpdir) / 'episode'
            report = run_visual_episode(
                folder=episode_folder,
                session=session,
                model_callable=HoldStub(seconds=0.1),
                max_calls=3,
                deadline=25.0,
                seed=820,
                controller_name='test_action_limit'
            )
            self.assertEqual(report['termination_reason'], 'action_limit')
            self.assertEqual(report['model_calls'], 3)
            self.assertEqual(report['completed_actions'], 3)

        # Test simulated deadline rejection including boundary rounding
        env2 = Environment()
        env2.reset(820, randomize=True)
        env2.hold(10.0)
        env2.hold(10.0)
        env2.hold(4.0)
        self.assertAlmostEqual(env2.data.time, 24.5)

        session2 = VisualPolicySession(VisualSession(env2, MockRenderer()), max_calls=20, deadline=25.0)

        with tempfile.TemporaryDirectory() as tmpdir2:
            episode_folder2 = Path(tmpdir2) / 'episode'
            # Action requests 0.6s, but only 0.5s remain until 25.0s
            report2 = run_visual_episode(
                folder=episode_folder2,
                session=session2,
                model_callable=HoldStub(seconds=0.6),
                max_calls=20,
                deadline=25.0,
                seed=820,
                controller_name='test_deadline_exceeded'
            )
            self.assertEqual(report2['termination_reason'], 'rejected_action')
            self.assertIn('deadline', report2['error'])
            self.assertEqual(report2['completed_actions'], 0)
            self.assertAlmostEqual(env2.data.time, 24.5)

    def test_injectable_clock_measures_wall_latency_separately(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=2)

        clock = MockClock(start=500.0, step=0.42)

        with tempfile.TemporaryDirectory() as tmpdir:
            episode_folder = Path(tmpdir) / 'episode'
            report = run_visual_episode(
                folder=episode_folder,
                session=session,
                model_callable=HoldStub(seconds=0.05),
                clock=clock,
                max_calls=2,
                deadline=25.0,
                seed=820,
                controller_name='test_clock'
            )
            self.assertEqual(report['model_calls'], 2)
            self.assertAlmostEqual(report['total_wall_latency_s'], 0.84, places=4)
            call1 = json.loads((episode_folder / 'call_001.json').read_text())
            call2 = json.loads((episode_folder / 'call_002.json').read_text())
            self.assertAlmostEqual(call1['wall_latency_s'], 0.42, places=4)
            self.assertAlmostEqual(call2['wall_latency_s'], 0.42, places=4)
            self.assertAlmostEqual(report['simulated_time_s'], 0.6)

    def test_completed_actions_do_not_claim_placement_success(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            def claiming_stub(payload):
                return {
                    'command': {'action': 'hold', 'arguments': {'seconds': 0.1}},
                    'claim': 'I have successfully placed the object into the basket.'
                }

            episode_folder = Path(tmpdir) / 'episode'
            report = run_visual_episode(
                folder=episode_folder,
                session=session,
                model_callable=claiming_stub,
                max_calls=2,
                deadline=25.0,
                seed=820,
                controller_name='test_no_false_success'
            )
            self.assertFalse(report['placement_success_claimed'])

    def test_no_network_and_no_credentials_access(self):
        """Verify default/offline mode executes without network calls or credential access."""
        import socket
        import urllib.request
        from unittest.mock import patch

        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=1)

        with tempfile.TemporaryDirectory() as tmpdir:
            episode_folder = Path(tmpdir) / 'episode'
            with patch('socket.socket', side_effect=AssertionError('Network socket created in offline mode')):
                with patch('urllib.request.urlopen', side_effect=AssertionError('Network call in offline mode')):
                    report = run_visual_episode(
                        folder=episode_folder,
                        session=session,
                        model_callable=HoldStub(seconds=0.05),
                        max_calls=1,
                        deadline=25.0,
                        seed=820,
                        controller_name='test_no_network'
                    )
            self.assertEqual(report['model_calls'], 1)
            self.assertEqual(report['completed_actions'], 1)

    def test_held_out_seed_guard_in_cli_and_smoke_check_820(self):
        scripted = get_named_stub('scripted')
        self.assertIsInstance(scripted, ScriptedDemoStub)
        with self.assertRaises(ValueError):
            get_named_stub('nonexistent_stub')

        # Run small 2-step smoke check on authorized development seed 820
        env = Environment()
        env.reset(820, randomize=True)
        renderer = MockRenderer()
        session = VisualPolicySession(VisualSession(env, renderer), max_calls=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            episode_folder = Path(tmpdir) / 'episode'
            report = run_visual_episode(
                folder=episode_folder,
                session=session,
                model_callable=scripted,
                max_calls=2,
                deadline=25.0,
                seed=820,
                controller_name='stub_scripted'
            )
            self.assertEqual(report['model_calls'], 2)
            self.assertEqual(report['completed_actions'], 2)
            self.assertFalse(report['placement_success_claimed'])
            self.assertEqual(len(report['image_identities']), 2)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite(self):
        with self.assertRaises(ValueError):
            strict_json('{"a": 1, "a": 2}')
        with self.assertRaises(ValueError):
            strict_json('{"a": NaN}')
        with self.assertRaises(ValueError):
            strict_json('{"a": Infinity}')

    def test_nonfinite_and_out_of_bounds_primitives_rejected(self):
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_response({
                'command': {
                    'action': 'move',
                    'arguments': {'xyz_m': [float('inf'), 0.0, 0.0], 'quaternion_wxyz': [1, 0, 0, 0], 'seconds': 1.0}
                }
            })
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_response({
                'command': {
                    'action': 'hand',
                    'arguments': {'closure': float('nan'), 'seconds': 1.0}
                }
            })
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_response({
                'command': {
                    'action': 'hold',
                    'arguments': {'seconds': 0.001}  # below 0.02s
                }
            })

    def test_cli_rejects_held_out_seeds(self):
        import subprocess
        import sys
        res = subprocess.run(
            [sys.executable, '-m', 'humanoid_sim.visual_policy_runner', '--seed', '842', '--output', '/tmp/held_out_test_dir'],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('840-849', res.stderr)

    def test_provenance_metadata_structure_and_hashes(self):
        prov = provenance('test_stub')
        self.assertEqual(prov['protocol_id'], 'humanoid-visual-policy-scaffold-v1')
        self.assertEqual(prov['task'], 'AGY-004')
        self.assertEqual(prov['max_actions'], 20)
        self.assertEqual(prov['deadline_s'], 25.0)
        self.assertTrue(prov['offline_only'])
        self.assertIn('prompt_sha256', prov)
        self.assertIn('action_schema_sha256', prov)
        self.assertIn('humanoid_sim/visual_policy_runner.py', prov['source_sha256'])
        self.assertIn('humanoid_sim/visual.py', prov['source_sha256'])


if __name__ == '__main__':
    unittest.main()
