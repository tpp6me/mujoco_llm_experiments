"""Contract, observation isolation, guarded paths, and physical interface execution."""
import json
import tempfile
import subprocess
import sys
from pathlib import Path
import unittest

import mujoco
import numpy as np

from humanoid_sim.environment import Environment, DOWNWARD
from humanoid_sim.interface import PolicyInterface, VERSION, quaternion, rotation_from_quaternion
from humanoid_sim.baseline import run_baseline


def request(action='hold', args=None, request_id='one'):
    return {'schema_version': VERSION, 'instruction_version': 1,
            'request_id': request_id, 'action': action,
            'arguments': {'seconds': .02} if args is None else args}


def state(env):
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    result = np.empty(mujoco.mj_stateSize(env.model, spec))
    mujoco.mj_getState(env.model, env.data, result, spec)
    return result


class InterfaceTests(unittest.TestCase):
    def test_invalid_requests_preserve_state_and_are_logged(self):
        env = Environment(); api = PolicyInterface(env)
        original = state(env)
        invalid = [None, {}, request('pick'), request(args={'seconds': True}),
                   request(args={'seconds': float('nan')}),
                   request('move', {'xyz_m': [.24, -.18, .94], 'quaternion_wxyz': [0, 0, 0, 0], 'seconds': 2}),
                   request('move', {'xyz_m': [5, 0, 1], 'quaternion_wxyz': quaternion(DOWNWARD), 'seconds': 2})]
        for index, action in enumerate(invalid):
            if isinstance(action, dict) and 'request_id' in action: action['request_id'] = str(index)
            result = api.execute(action)
            self.assertEqual(result['status'], 'rejected', result)
            np.testing.assert_array_equal(state(env), original)
        self.assertEqual(len(env.events), len(invalid))

    def test_cli_persistence_malformed_json_and_completed_protection(self):
        env = Environment()
        with tempfile.TemporaryDirectory() as folder:
            episode = Path(folder)/'episode'; env.save(episode)
            path = Path(folder)/'request.json'; path.write_text(json.dumps(request()))
            command = [sys.executable, '-m', 'humanoid_sim.interface', '--episode', str(episode),
                       '--mode', 'robot_state', 'act', '--request', str(path)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'completed')
            restored = Environment(); restored.load(episode)
            before = state(restored)
            path.write_text('{"action":"hold","action":"move"}')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Duplicate JSON field', result.stderr)
            restored.load(episode); np.testing.assert_array_equal(state(restored), before)
            self.assertIn('invalid_interface_json', restored.events[-1])
            (episode/'report.json').write_text('{}')
            prior = (episode/'events.json').read_bytes()
            path.write_text(json.dumps(request(request_id='new')))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('immutable', result.stderr)
            self.assertEqual((episode/'events.json').read_bytes(), prior)

    def test_event_records_are_detached_and_strict_json(self):
        env = Environment(); api = PolicyInterface(env)
        action = request(); response = api.execute(action)
        action['arguments']['seconds'] = 10
        response['status'] = 'tampered'
        self.assertEqual(env.events[-1]['interface_request']['arguments']['seconds'], .02)
        self.assertEqual(env.events[-1]['interface_response']['status'], 'completed')
        api.execute(request(args={'seconds': float('nan')}, request_id='invalid'))
        json.dumps(env.events, allow_nan=False)

    def test_robot_state_has_no_task_or_score_fields(self):
        env = Environment(); api = PolicyInterface(env, 'robot_state')
        obs = api.observe()
        self.assertEqual(set(obs), {'schema_version', 'instruction_version', 'mode', 'time_s', 'frame', 'supported_body', 'robot'})
        self.assertEqual(len(obs['robot']['joint_names']), 43)
        self.assertEqual(len(obs['robot']['joint_velocity_rad_s']), 43)
        result = api.execute(request())
        self.assertNotIn('task_state', result['observation'])
        self.assertNotIn('score', result)
        self.assertIn('score', env.events[-1])  # private evaluation archive only
        json.dumps(result, allow_nan=False)

    def test_duplicate_and_stale_requests_after_reload(self):
        env = Environment(); api = PolicyInterface(env)
        self.assertEqual(api.execute(request())['status'], 'completed')
        with tempfile.TemporaryDirectory() as folder:
            env.save(folder); restored = Environment(); restored.load(folder)
            api = PolicyInterface(restored); before = state(restored)
            self.assertEqual(api.execute(request())['status'], 'rejected')
            stale = request(request_id='two'); stale['instruction_version'] = 0
            self.assertEqual(api.execute(stale)['status'], 'rejected')
            np.testing.assert_array_equal(state(restored), before)

    def test_explicit_orientation_tracks_and_sign_equivalence(self):
        env = Environment(); api = PolicyInterface(env)
        angle = .1
        yaw = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
        rotation = yaw @ DOWNWARD
        quat = quaternion(rotation)
        result = api.execute(request('move', {'xyz_m': [.24, -.18, .94], 'quaternion_wxyz': quat, 'seconds': 2}))
        self.assertEqual(result['status'], 'completed', result.get('error'))
        current = env.data.site_xmat[env.site].reshape(3, 3)
        error = np.arccos(np.clip((np.trace(rotation.T @ current)-1)/2, -1, 1))
        self.assertLess(error, .08)
        np.testing.assert_allclose(env.solve([.24, -.18, .94], rotation),
                                   env.solve([.24, -.18, .94], rotation_from_quaternion([-v for v in quat])))

    def test_collision_rejection_preserves_full_state(self):
        env = Environment(); api = PolicyInterface(env)
        before = state(env)
        result = api.execute(request('move', {'xyz_m': [.24, -.18, .7],
                                             'quaternion_wxyz': quaternion(DOWNWARD), 'seconds': 2}))
        self.assertEqual(result['status'], 'rejected')
        self.assertIn('penetration', result['error'])
        np.testing.assert_array_equal(state(env), before)

    def test_v4_recipe_hits_new_guard_without_advancing_rejected_move(self):
        env = Environment(); api = PolicyInterface(env)
        class Adapter:
            scorer = env.scorer
            def observe(self): return api.observe()['task_state']
            def send(self, action, args):
                result = api.execute(request(action, args, str(len(env.events))))
                if result['status'] != 'completed': raise RuntimeError(result['error'])
            def move(self, xyz, seconds=2): self.send('move', {'xyz_m': list(xyz), 'quaternion_wxyz': quaternion(DOWNWARD), 'seconds': seconds})
            def hand(self, closure, seconds=2): self.send('hand', {'closure': closure, 'seconds': seconds})
            def hold(self, seconds=2): self.send('hold', {'seconds': seconds})
        with self.assertRaisesRegex(RuntimeError, 'penetration'):
            run_baseline(Adapter())
        self.assertAlmostEqual(env.data.time, 11, places=6)
        self.assertEqual(env.events[-1]['interface_response']['status'], 'rejected')
        # An explicit policy revision requests a higher release; the API never
        # rewrites the rejected target or chooses this recovery on the policy's behalf.
        from humanoid_sim.baseline import release_target
        policy = Adapter()
        target = release_target(policy.observe()); target[2] = .90
        policy.move(target)
        policy.hand(0)
        policy.move([target[0], target[1], .975])
        policy.move([.24, -.18, .975])
        policy.hold(6)
        self.assertTrue(env.scorer.success)
        self.assertLessEqual(env.scorer.max_penetration, .002)
        self.assertAlmostEqual(env.data.time, 25, places=6)


if __name__ == '__main__': unittest.main()
