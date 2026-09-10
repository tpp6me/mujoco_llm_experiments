"""Continuous time, expiry, reservation, and physical queued-motion checks."""

import tempfile
import threading
import time
import unittest

import numpy as np

from conveyor_sim.live import request
from conveyor_sim.realtime import RealtimeConfig, RealtimeTrial, Runtime, compile_motion


def primitives(speed=0.01):
    y = -0.015 + speed + 0.005
    return [{"tool": "move_to", "xyz": [0.18, 0.005, 0.065], "seconds": 2, "joint": True},
            {"tool": "move_to", "xyz": [0.18, y, 0.020], "seconds": 1},
            {"tool": "sweep", "xyz": [0.30, y + 2 * speed, 0.020], "seconds": 2},
            {"tool": "retract"}]


class RealtimeTests(unittest.TestCase):
    def test_clock_and_cubes_advance_without_commands(self):
        class ShortTrial(RealtimeTrial):
            @property
            def deadline(self):
                return 2.0

        with tempfile.TemporaryDirectory() as directory:
            env = ShortTrial(RealtimeConfig(actor="test"))
            runtime = Runtime(env, directory)
            worker = threading.Thread(target=runtime.run)
            worker.start()
            try:
                from pathlib import Path
                limit = time.monotonic() + 3
                while not (Path(directory) / "ready.json").exists() and time.monotonic() < limit:
                    time.sleep(0.01)
                before = request(directory, {"kind": "observe"})["observation"]
                time.sleep(0.25)
                after = request(directory, {"kind": "observe"})["observation"]
                delta = after["time_s"] - before["time_s"]
                self.assertGreater(delta, 0.20)
                self.assertLess(delta, 0.6)
                self.assertAlmostEqual(after["cubes"][0]["position"][1] - before["cubes"][0]["position"][1],
                                       delta * env.config.belt_speed, delta=0.0001)
            finally:
                worker.join(timeout=4)
            self.assertFalse(worker.is_alive())
            self.assertTrue(runtime.report()["realtime_healthy"])
            self.assertEqual(runtime.report()["scoring"]["classified_cubes"], 3)

    def test_expired_unknown_observation_and_overlap_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            env = RealtimeTrial(RealtimeConfig(actor="test"))
            env.wait(0.5)
            runtime = Runtime(env, directory)
            runtime.epoch = time.monotonic() - env.data.time
            runtime.snapshot("obs")
            command = {"cube_id": "cube_002", "observation_id": "obs", "start_at_s": 2,
                       "expires_at_s": 2.05, "primitives": primitives()}
            try:
                expired = runtime.submit({**command, "start_at_s": 0, "expires_at_s": 0.05}, "old")
                self.assertEqual(expired["status"], "expired")
                missing = runtime.submit({**command, "observation_id": "missing"}, "missing")
                self.assertEqual(missing["status"], "rejected")
                runtime.submit(command, "one")
                runtime.jobs[-1]["future"].result()
                runtime.prepare_jobs()
                runtime.submit({**command, "cube_id": "cube_001", "start_at_s": 3, "expires_at_s": 3.05}, "two")
                runtime.jobs[-1]["future"].result()
                runtime.prepare_jobs()
                self.assertEqual(env.events[-1]["status"], "rejected")
                self.assertIn("overlaps", env.events[-1]["error"])
                self.assertAlmostEqual(env.data.time, 0.5)
            finally:
                runtime.pool.shutdown()

    def test_queued_sequence_physically_rejects_selected_cube(self):
        with tempfile.TemporaryDirectory() as directory:
            env = RealtimeTrial(RealtimeConfig(actor="test", belt_speed=0.01, scenario="stream"))
            env.wait(0.5)
            runtime = Runtime(env, directory)
            runtime.epoch = time.monotonic() - env.data.time
            runtime.snapshot("obs")
            entry = env.data.time + (-0.015 - env.observations()["cube_002"].position[1]) / 0.01
            command = {"cube_id": "cube_002", "observation_id": "obs", "start_at_s": entry - 2,
                       "expires_at_s": entry - 1.95, "primitives": primitives()}
            try:
                runtime.submit(command, "physical")
                runtime.jobs[0]["future"].result()
                runtime.prepare_jobs()
                while env.data.time < entry + 7:
                    runtime.control_before_step()
                    env._step()
                    runtime.control_after_step()
                self.assertEqual(env.events[0]["status"], "completed")
                self.assertEqual(env.scorer.results["cube_002"]["destination"], "reject")
                self.assertEqual(env.contact_cubes, {"cube_002"})
                self.assertFalse(env.unintended_contacts or env.fixture_contacts or env.neighbor_contacts)
                self.assertLess(env.max_tracking_error, 0.005)
            finally:
                runtime.pool.shutdown()

    def test_bad_preflight_preserves_live_state(self):
        env = RealtimeTrial(RealtimeConfig(actor="test"))
        qpos = env.data.qpos.copy()
        bad = primitives()
        bad[2]["xyz"] = [0.4, 0, 0.020]
        with self.assertRaises(ValueError):
            compile_motion(env.model, env.data.qpos.copy(), bad)
        np.testing.assert_array_equal(qpos, env.data.qpos)
        self.assertEqual(env.data.time, 0)


if __name__ == "__main__":
    unittest.main()
