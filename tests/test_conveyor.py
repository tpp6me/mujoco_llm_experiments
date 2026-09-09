"""Independent outcome scoring and physical conveyor integration checks."""

import unittest

import numpy as np

from conveyor_sim.environment import Config, Conveyor
from conveyor_sim.scoring import Cube, Observation, Scorer


def sample(position=(0.22, 0.55, -0.235), contacts=("pass_bin_floor",), velocity=(0, 0, 0)):
    return Observation(position, (0.015, 0.015, 0.015), velocity, contacts)


class ScoringTests(unittest.TestCase):
    def test_color_and_destination_outcomes(self):
        for color, destination, expected in [
            ("red", "pass", "target_missed"), ("blue", "pass", "correct_pass"),
            ("red", "reject", "correct_reject"), ("blue", "reject", "wrong_reject"),
        ]:
            with self.subTest(color=color, destination=destination):
                scorer = Scorer([Cube("object", color)])
                observation = sample() if destination == "pass" else sample(
                    (0.40, 0, -0.135), ("reject_bin_floor",))
                scorer.update(0, {"object": observation})
                scorer.update(0.31, {"object": observation})
                self.assertEqual(scorer.finish()["cubes"][0]["outcome"], expected)

    def test_declared_target_changes_scoring(self):
        scorer = Scorer([Cube("object", "blue")], target_color="blue")
        scorer.update(0, {"object": sample()})
        scorer.update(0.31, {"object": sample()})
        self.assertEqual(scorer.finish()["cubes"][0]["outcome"], "target_missed")

    def test_arrival_requires_containment_contact_and_dwell(self):
        for observation, end_time in [
            (sample(), 0.1),  # Too early to establish arrival.
            (sample(contacts=()), 0.4),  # Passing through the volume, unsupported.
            (sample(position=(0.115, 0.55, -0.235)), 0.4),  # Partly outside tray.
            (sample(velocity=(0, 0.2, 0)), 0.4),  # Still moving quickly.
        ]:
            with self.subTest(observation=observation, end_time=end_time):
                scorer = Scorer([Cube("object", "red")])
                scorer.update(0, {"object": observation})
                scorer.update(end_time, {"object": observation})
                self.assertEqual(scorer.finish()["cubes"][0]["outcome"], "unresolved")

    def test_stacked_cubes_require_support_chain(self):
        scorer = Scorer([Cube("bottom", "red"), Cube("top", "green")])
        observations = {"bottom": sample(contacts=("pass_bin_floor", "top")),
                        "top": sample(position=(0.22, 0.55, -0.205), contacts=("bottom",))}
        scorer.update(0, observations)
        scorer.update(0.4, observations)
        self.assertEqual(scorer.summary()["classified_cubes"], 2)
        unsupported = {"bottom": sample(contacts=("top",)), "top": observations["top"]}
        scorer.update(0.5, unsupported)
        self.assertEqual(scorer.summary()["classified_cubes"], 0)

    def test_soft_contact_tolerance_does_not_admit_outside_cubes(self):
        for y, expected in [(0.4249, "target_missed"), (0.423, "unresolved")]:
            with self.subTest(y=y):
                scorer = Scorer([Cube("object", "red")])
                observation = sample((0.22, y, -0.235), ("pass_bin_front",))
                scorer.update(0, {"object": observation})
                scorer.update(0.4, {"object": observation})
                self.assertEqual(scorer.finish()["cubes"][0]["outcome"], expected)

    def test_cube_leaving_tray_loses_its_arrival(self):
        scorer = Scorer([Cube("object", "green")])
        scorer.update(0, {"object": sample()})
        scorer.update(0.4, {"object": sample()})
        scorer.update(0.5, {"object": sample((0.55, 0.55, -0.335), ("world_floor",))})
        result = scorer.finish()
        self.assertEqual(result["cubes"][0]["outcome"], "lost")
        self.assertEqual(result["classified_cubes"], 1)

    def test_stuck_lost_and_unresolved_are_distinct(self):
        cubes = [Cube(id, "red") for id in ("stuck", "lost", "moving")]
        scorer = Scorer(cubes)
        observations = {"stuck": sample((0.22, 0, 0.015), ("belt",)),
                        "lost": sample((0.6, 0, -0.335), ("world_floor",)),
                        "moving": sample((0.22, 0.1, 0.015), ("belt",), (0, 0.03, 0))}
        scorer.update(0, observations)
        scorer.update(2.1, observations)
        outcomes = {r["id"]: r["outcome"] for r in scorer.finish()["cubes"]}
        self.assertEqual(outcomes, {"stuck": "stuck", "lost": "lost", "moving": "unresolved"})

    def test_missing_cube_and_backwards_time_are_rejected(self):
        scorer = Scorer([Cube("object", "green")])
        with self.assertRaises(ValueError):
            scorer.update(0, {})
        scorer.update(1, {"object": sample()})
        with self.assertRaises(ValueError):
            scorer.update(0, {"object": sample()})


class ConveyorPhysicsTests(unittest.TestCase):
    def test_all_colors_reach_collection_without_arm_contact(self):
        env = Conveyor(Config(seed=0), capture=False)
        result = env.run()
        self.assertTrue(result["transport_success"], result)
        self.assertEqual(result["collected_cubes"], 6)
        self.assertEqual(result["arm_cube_contact_steps"], 0)
        self.assertEqual(result["scoring"]["outcomes"], {"correct_pass": 4, "target_missed": 2})

    def test_stopped_surface_does_not_transport_cubes(self):
        env = Conveyor(Config(count=1), capture=False)
        env.model.geom_surfacevel[env.model.geom("belt").id] = 0
        original = env.data.qpos.copy()
        result = env.run(seconds=3)
        self.assertFalse(result["transport_success"])
        self.assertEqual(result["scoring"]["outcomes"], {"stuck": 1})
        # The cube's horizontal position stays unchanged under zero belt velocity.
        np.testing.assert_allclose(env.data.qpos[6:8], original[6:8], atol=1e-6)

    def test_short_run_accounts_for_every_cube(self):
        env = Conveyor(capture=False)
        result = env.run(seconds=1)
        self.assertFalse(result["transport_success"])
        self.assertEqual(result["scoring"]["classified_cubes"], 6)
        self.assertEqual(result["scoring"]["outcomes"], {"unresolved": 6})

    def test_seed_reproduces_initial_scene(self):
        first = Conveyor(Config(seed=7), capture=False)
        second = Conveyor(Config(seed=7), capture=False)
        self.assertEqual(first.initial, second.initial)
        np.testing.assert_array_equal(first.data.qpos, second.data.qpos)

    def test_cube_dropping_into_reject_tray_is_scored_physically(self):
        for target, expected in [("red", "correct_reject"), ("green", "wrong_reject")]:
            with self.subTest(target=target):
                env = Conveyor(Config(count=1, target_color=target), capture=False)
                # Test fixture only: initialize a free red cube above the reject tray.
                env.data.qpos[6:9] = [0.4, 0, -0.09]
                result = env.run(seconds=3)
                self.assertEqual(result["scoring"]["outcomes"], {expected: 1})
                self.assertFalse(result["transport_success"])


if __name__ == "__main__":
    unittest.main()
