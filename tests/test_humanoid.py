"""Mechanics, independent scoring, and persistent action checks for supported G1."""
import tempfile
from pathlib import Path
import unittest

import mujoco
import numpy as np

from humanoid_sim.baseline import run_baseline
from humanoid_sim.environment import Environment
from humanoid_sim.scene import BASKET, TABLE_Z


class HumanoidTests(unittest.TestCase):
    def test_supported_model_and_free_object(self):
        env = Environment()
        free_joints = np.flatnonzero(env.model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)
        self.assertEqual([env.model.joint(int(j)).name for j in free_joints], ['object_free'])
        self.assertEqual(env.model.nu, 43)
        self.assertEqual(env.model.neq, 0, 'No grasp weld or other equality attachment')
        self.assertAlmostEqual(env.observe()['object_bottom'], TABLE_Z, delta=.0005)

    def test_bad_action_preserves_integration_state(self):
        env = Environment()
        qpos, qvel, ctrl, timestamp = env.data.qpos.copy(), env.data.qvel.copy(), env.data.ctrl.copy(), env.data.time
        for action in [lambda: env.move([5, 0, 1]), lambda: env.move([np.nan, -.2, .9]),
                       lambda: env.hand(1.1), lambda: env.hold(float('nan')),
                       lambda: env.move([.24, -.18, .94], -1)]:
            with self.assertRaises(ValueError):
                action()
            np.testing.assert_array_equal(env.data.qpos, qpos)
            np.testing.assert_array_equal(env.data.qvel, qvel)
            np.testing.assert_array_equal(env.data.ctrl, ctrl)
            self.assertEqual(env.data.time, timestamp)

    def test_physical_pick_place_and_resume(self):
        env = Environment()
        self.assertIsNone(run_baseline(env))
        result = env.scorer.report()
        self.assertTrue(result['success'])
        self.assertTrue(result['lifted'])
        self.assertTrue(result['basket_floor_contact'])
        self.assertFalse(result['hand_contact'])
        self.assertLess(result['max_object_penetration_m'], .002)
        with tempfile.TemporaryDirectory() as folder:
            env.save(folder)
            restored = Environment()
            restored.load(folder)
            self.assertEqual(restored.scorer.report(), env.scorer.report())
            np.testing.assert_array_equal(restored.data.qpos, env.data.qpos)
            env.hold(.1)
            restored.hold(.1)
            np.testing.assert_allclose(restored.data.qpos, env.data.qpos, atol=1e-12, rtol=0)
            self.assertEqual(restored.scorer.success, env.scorer.success)
            self.assertTrue((Path(folder)/'metadata.json').exists())

    def test_scorer_requires_lift_dwell_and_revokes_arrival(self):
        env = Environment()
        q = env.model.joint('object_free').qposadr[0]
        env.data.qpos[q:q+3] = [*BASKET, TABLE_Z+.075]
        env.data.qvel[:] = 0
        mujoco.mj_forward(env.model, env.data)
        env.hold(3)
        self.assertFalse(env.scorer.success, 'An object initially in the basket was never picked')
        # Inject only the historical lift flag to isolate the dwell and revocation rules.
        env.scorer.lifted = True
        env.scorer.settled_dwell = 0
        env.hold(1)
        self.assertFalse(env.scorer.success)
        env.hold(1.2)
        self.assertTrue(env.scorer.success)
        env.data.qpos[q:q+3] = [.55, -.05, TABLE_Z+.075]
        mujoco.mj_forward(env.model, env.data)
        env.scorer.update(env.data)
        self.assertFalse(env.scorer.success)
        self.assertEqual(env.scorer.settled_dwell, 0)

    def test_release_falls_under_gravity(self):
        env = Environment()
        env.move([.255, -.18, .975])
        env.move([.255, -.18, .775])
        env.hand(1)
        env.move([.255, -.18, .975])
        height = env.observe()['object_xyz'][2]
        self.assertTrue(env.scorer.lifted)
        env.hand(0)
        env.hold(1)
        self.assertLess(env.observe()['object_xyz'][2], height-.08)
        self.assertFalse(env.scorer.hand_contact)
        self.assertFalse(env.scorer.success)


if __name__ == '__main__':
    unittest.main()
