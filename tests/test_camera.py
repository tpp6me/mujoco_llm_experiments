"""Public observation filtering and separation of perception from ground truth."""

import json
import tempfile
import time
import unittest

import numpy as np

from conveyor_sim.camera import world_to_pixel
from conveyor_sim.realtime import RealtimeConfig
from conveyor_sim.vision_runtime import VisionRuntime, VisionTrial


def command(pixel):
    return {"object_id": "object_A", "pixel_xy": pixel, "perceived_color": "red", "observation_id": "obs",
            "start_at_s": 30, "expires_at_s": 30.05,
            "primitives": [{"tool": "move_to", "xyz": [0.18, 0.005, 0.065], "seconds": 2, "joint": True},
                           {"tool": "move_to", "xyz": [0.18, -0.005, 0.020], "seconds": 1},
                           {"tool": "sweep", "xyz": [0.30, 0.005, 0.020], "seconds": 2}, {"tool": "retract"}]}


class CameraTests(unittest.TestCase):
    def test_public_observation_has_no_oracle_object_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            env = VisionTrial(RealtimeConfig(seed=42, actor="test"))
            runtime = VisionRuntime(env, directory)
            runtime.epoch = time.monotonic()
            try:
                runtime.begin_image("obs")
                observation = runtime.pending["obs"]
                self.assertEqual(set(observation), {"observation_id", "instruction", "time_s", "observed_at_utc",
                                                   "time_mode", "belt_velocity_m_s", "calibration", "image_path"})
                text = json.dumps(observation)
                for name in ["cube_000", "cube_001", "cube_002", "target_color", "initial_cubes", "seed"]:
                    self.assertNotIn(name, text)
                self.assertEqual(env.data.time, 0)
                self.assertEqual(len(runtime.truth["obs"]), 3)
            finally:
                runtime.pool.shutdown()

    def test_oracle_changes_do_not_change_compiled_motion(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            runtimes = [VisionRuntime(VisionTrial(RealtimeConfig(seed=42, actor="test")), folder) for folder in [one, two]]
            try:
                for runtime in runtimes:
                    runtime.epoch = time.monotonic()
                    runtime.begin_image("obs")
                for obj in runtimes[1].truth["obs"]:
                    obj["xy"][0] += 0.5
                    obj["color"] = "blue"
                for runtime in runtimes:
                    event = runtime.submit(command([480, 400]), "request")
                    self.assertEqual(event["command"]["cube_id"], "object_A")
                    self.assertEqual(event["status"], "planning")
                plans = [r.jobs[0]["future"].result() for r in runtimes]
                self.assertEqual(len(plans[0]), len(plans[1]))
                for a, b in zip(*plans, strict=True):
                    np.testing.assert_array_equal(a["ctrl"], b["ctrl"])
                    self.assertEqual(a["steps"], b["steps"])
            finally:
                for runtime in runtimes:
                    runtime.pool.shutdown()

    def test_wrong_color_estimate_is_scored_without_correcting_command(self):
        with tempfile.TemporaryDirectory() as directory:
            env = VisionTrial(RealtimeConfig(seed=42, actor="test"))
            runtime = VisionRuntime(env, directory)
            runtime.epoch = time.monotonic()
            try:
                runtime.begin_image("obs")
                blue = next(c for c in runtime.truth["obs"] if c["color"] == "blue")
                event = runtime.submit(command(world_to_pixel(blue["xy"])), "request")
                self.assertEqual(event["status"], "planning")
                audit = runtime.report()["perception_audits"][0]
                self.assertFalse(audit["color_correct"])
                self.assertEqual(audit["matched_physical_id"], blue["id"])
                self.assertFalse(runtime.report()["selection_correct"])
                self.assertEqual(event["command"]["primitives"], command([0, 0])["primitives"])
            finally:
                runtime.pool.shutdown()


if __name__ == "__main__":
    unittest.main()
