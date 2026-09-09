"""Physical rejection, neighboring-cube clearance, and controller failure checks."""

import unittest
import numpy as np

from conveyor_sim.pushing import PushConfig, PushTrial


class PushingTests(unittest.TestCase):
    def test_stationary_and_moving_rejections_have_contact_evidence(self):
        for speed in [0, 0.01]:
            with self.subTest(speed=speed):
                env = PushTrial(PushConfig(belt_speed=speed), capture=False)
                report = env.run()
                self.assertTrue(report["push_success"], report)
                self.assertEqual(report["touched_cube_ids"], ["cube_000"])
                self.assertEqual(report["scoring"]["outcomes"], {"correct_reject": 1})
                self.assertEqual(report["fixture_contacts"], [])

    def test_neighbors_pass_without_any_unintended_contact(self):
        env = PushTrial(PushConfig(scenario="neighbors", target_color="blue"), capture=False)
        report = env.run()
        self.assertTrue(report["push_success"], report)
        self.assertEqual(report["touched_cube_ids"], ["cube_001"])
        self.assertEqual(report["unintended_cube_contacts"], [])
        self.assertEqual(report["cube_neighbor_contacts_on_belt"], [])
        self.assertEqual(report["scoring"]["outcomes"], {"correct_pass": 2, "correct_reject": 1})

    def test_consecutive_targets_at_supported_spacing(self):
        env = PushTrial(PushConfig(scenario="stream", spacing=0.08), capture=False)
        report = env.run()
        self.assertTrue(report["push_success"], report)
        self.assertEqual(report["scoring"]["outcomes"], {"correct_reject": 3})
        self.assertEqual(len(report["rejections"]), 3)

    def test_overload_is_reported_as_failure(self):
        env = PushTrial(PushConfig(scenario="stream", spacing=0.06), capture=False)
        report = env.run()
        self.assertFalse(report["push_success"])
        self.assertIn("interception", report["controller_error"])
        self.assertGreater(report["scoring"]["outcomes"].get("target_missed", 0), 0)
        self.assertEqual(report["scoring"]["classified_cubes"], 3)

    def test_ik_failure_before_motion_preserves_live_state(self):
        env = PushTrial(capture=False)
        qpos, ctrl, time = env.data.qpos.copy(), env.data.ctrl.copy(), env.data.time
        with self.assertRaises(ValueError):
            env.move([0.35, 0, 0.20], 1.0)
        np.testing.assert_array_equal(env.data.qpos, qpos)
        np.testing.assert_array_equal(env.data.ctrl, ctrl)
        self.assertEqual(env.data.time, time)


if __name__ == "__main__":
    unittest.main()
