"""Phase 3 state persistence, action boundaries, and independent failure scoring."""

from dataclasses import replace
import tempfile
import unittest

import numpy as np

from conveyor_sim.interactive import InteractiveConfig, InteractiveTrial
from conveyor_sim.phase3 import conventional


class InteractiveTests(unittest.TestCase):
    def test_resume_preserves_physics_and_scorer(self):
        config = InteractiveConfig(seed=12, actor="test")
        continuous, resumed = InteractiveTrial(config), InteractiveTrial(config)
        for env in [continuous, resumed]:
            env.wait(0.5)
            event = env.execute({"tool": "move_to", "cube_id": "cube_002",
                                 "xyz": [0.18, 0.005, 0.065], "seconds": 2, "joint": True})
            self.assertIsNone(event["error"])
        with tempfile.TemporaryDirectory() as folder:
            resumed.save(folder)
            resumed = InteractiveTrial.load(folder)
            initial_time = resumed.data.time
            before = resumed.data.qpos.copy()
            observation = resumed.execute({"tool": "observe"})
            self.assertEqual(initial_time, resumed.data.time)
            np.testing.assert_array_equal(before, resumed.data.qpos)
            self.assertNotIn("target_ids", observation["after"])
            self.assertNotIn("target_color", observation["after"])
            self.assertEqual(resumed.active_target, "cube_002")
            for env in [continuous, resumed]:
                env.execute({"tool": "wait", "seconds": 5})
            np.testing.assert_allclose(continuous.data.qpos, resumed.data.qpos, atol=1e-12, rtol=0)
            np.testing.assert_allclose(continuous.data.qvel, resumed.data.qvel, atol=1e-12, rtol=0)
            self.assertEqual(continuous.scorer.summary(), resumed.scorer.summary())

    def test_wrong_color_is_allowed_but_fails_independent_scoring(self):
        env = InteractiveTrial(InteractiveConfig(seed=13, target_color="red", actor="test"))
        env.wait(0.5)
        # Drive a blue-selection baseline while keeping the independent scorer red.
        env.config = replace(env.config, target_color="blue")
        conventional(env)
        report = env.report()
        self.assertFalse(report["selection_correct"])
        self.assertFalse(report["sorting_success"])
        self.assertEqual(report["scoring"]["outcomes"],
                         {"correct_pass": 1, "target_missed": 1, "wrong_reject": 1})

    def test_invalid_actions_and_early_finish_are_accounted_for(self):
        env = InteractiveTrial(InteractiveConfig(actor="test"))
        original = env.data.qpos.copy()
        for command in [{"tool": "reject_color", "color": "red"},
                        {"tool": "wait", "seconds": -1},
                        {"tool": "move_to", "xyz": [0.35, 0, 0.20], "seconds": 1},
                        {"tool": "sweep", "xyz": [0.30, 0, 0.020], "seconds": 2}]:
            self.assertIsNotNone(env.execute(command)["error"])
            self.assertEqual(env.data.time, 0)
            np.testing.assert_array_equal(env.data.qpos, original)
        env.execute({"tool": "finish"})
        report = env.report()
        self.assertFalse(report["sorting_success"])
        self.assertEqual(report["scoring"]["classified_cubes"], 3)
        self.assertEqual(report["tool_errors"], 4)
        self.assertIsNotNone(env.execute({"tool": "wait", "seconds": 1})["error"])

    def test_conventional_comparator_uses_physical_primitives(self):
        env = InteractiveTrial(InteractiveConfig(seed=14, target_color="green", actor="conventional"))
        env.wait(0.5)
        conventional(env)
        self.assertTrue(env.report()["sorting_success"], env.report())
        self.assertEqual(env.report()["scoring"]["outcomes"], {"correct_pass": 2, "correct_reject": 1})
        with tempfile.TemporaryDirectory() as folder:
            env.save(folder)
            saved = InteractiveTrial.load(folder)
            self.assertEqual(saved.report(), env.report())


if __name__ == "__main__":
    unittest.main()
