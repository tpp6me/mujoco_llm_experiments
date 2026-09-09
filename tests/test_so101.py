"""Physics integration checks for grasping, release, and rejected motion."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from so101_sim.environment import Environment


class PickupTests(unittest.TestCase):
    def test_pickup_persist_hold_and_release(self):
        env = Environment()
        env.reset()
        env.gripper(1.0)
        env.move([0.22, 0, 0.075])
        env.move([0.22, 0, 0.020])
        closed = env.gripper(0.0)
        self.assertTrue(closed["observation"]["both_jaws_contact"])
        env.move([0.22, 0, 0.080], seconds=3)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "episode.npz"
            env.save(path)
            resumed = Environment()
            resumed.load(path)
        held = resumed.hold(3)
        self.assertTrue(held["held_throughout"])
        self.assertLess(held["cube_drift_m"], 0.005)
        self.assertGreater(held["observation"]["cube_bottom_m"], 0.05)
        # Opening the jaws must drop the free cube back onto the table.
        resumed.gripper(1.0)
        resumed.hold(1)
        dropped = resumed.observe()
        self.assertFalse(dropped["lifted_and_held"])
        self.assertIn("world", dropped["cube_contact_bodies"])
        self.assertAlmostEqual(dropped["cube_xyz_m"][2], 0.015, delta=0.002)

    def test_unreachable_pose_does_not_move_simulation(self):
        env = Environment()
        env.reset()
        original_qpos = env.data.qpos.copy()
        original_ctrl = env.data.ctrl.copy()
        original_time = env.data.time
        with self.assertRaises(ValueError):
            env.move([0.25, 0, 0.20])
        np.testing.assert_array_equal(env.data.qpos, original_qpos)
        np.testing.assert_array_equal(env.data.ctrl, original_ctrl)
        self.assertEqual(env.data.time, original_time)


if __name__ == "__main__":
    unittest.main()
