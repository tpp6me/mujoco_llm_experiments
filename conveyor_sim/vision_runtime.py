"""Camera-only public interface; ground truth is used only by the private scorer."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np

from .camera import calibration, pixel_to_world
from .environment import ROOT
from .realtime import RealtimeTrial, Runtime, utc, write_json


class VisionTrial(RealtimeTrial):
    def __init__(self, config, capture=True):
        self.contacts_by_label = {}
        super().__init__(config, capture)

    def _step(self):
        super()._step()
        if self.active_target is not None:
            touched = self.contacts_by_label.setdefault(self.active_target, set())
            for c in self.data.contact:
                if c.dist > 0 or c.efc_address < 0:
                    continue
                for arm, other in [(int(c.geom1), int(c.geom2)), (int(c.geom2), int(c.geom1))]:
                    if arm in self.arm_geoms and other in self.cube_geom_ids:
                        touched.add(self.cube_geom_ids[other])


class VisionRuntime(Runtime):
    def __init__(self, env, directory):
        super().__init__(env, directory)
        self.private = self.directory / "private"
        self.private.mkdir(exist_ok=True)
        (self.private / "render_requests").mkdir(exist_ok=True)
        (self.directory / "images").mkdir(exist_ok=True)
        self.truth, self.pending = {}, {}

    def begin_image(self, id):
        now = time.monotonic()
        observation = {"observation_id": id, "instruction": self.env.config.instruction,
                       "time_s": float(self.env.data.time), "observed_at_utc": utc(),
                       "time_mode": "continuous_wall_clock_camera",
                       "belt_velocity_m_s": [0, self.env.config.belt_speed, 0],
                       "calibration": calibration(), "image_path": str((self.directory / "images" / f"{id}.png").resolve())}
        self.observations[id] = {"observation": observation, "monotonic": now}
        # This oracle record is never returned to an agent or used for motion.
        self.truth[id] = [{"id": c.id, "color": c.color,
                           "xy": list(self.env.observations()[c.id].position[:2])} for c in self.env.cubes]
        target = self.private / "render_requests" / f"{id}.npz"
        with target.with_suffix(".tmp").open("wb") as file:
            np.savez(file, qpos=self.env.data.qpos.copy(), time_s=self.env.data.time)
        target.with_suffix(".tmp").replace(target)
        self.pending[id] = observation

    def submit(self, command, request_id):
        try:
            required = {"object_id", "pixel_xy", "perceived_color", "observation_id",
                        "start_at_s", "expires_at_s", "primitives"}
            if set(command) != required or not re.fullmatch(r"object_[A-Za-z0-9_]{1,32}", command["object_id"]):
                raise ValueError("Use a neutral object_ID label and the documented camera command fields")
            if command["perceived_color"] not in {"red", "blue", "green"}:
                raise ValueError("Declare the color you see")
            xy = pixel_to_world(command["pixel_xy"])
            perception = {"object_id": command["object_id"], "pixel_xy": command["pixel_xy"],
                          "perceived_color": command["perceived_color"], "estimated_world_xy_m": xy}
            # The label is only a queue/contact-log handle. No oracle position or
            # physical cube ID is resolved here. Motion uses supplied coordinates.
            label = command["object_id"]
            self.env.cube_body_ids[label] = -1
            internal = {k: command[k] for k in ["observation_id", "start_at_s", "expires_at_s", "primitives"]}
            internal["cube_id"] = label
            event = super().submit(internal, request_id)
            event["perception"] = perception
            return event
        except (ValueError, TypeError, KeyError) as error:
            event = {"request_id": request_id, "command": {}, "status": "rejected", "error": str(error),
                     "received_at_utc": utc(), "received_at_sim_s": float(self.env.data.time),
                     "actual_start_s": None, "actual_end_s": None}
            self.env.events.append(event)
            return event

    def poll_requests(self):
        for path in sorted((self.directory / "requests").glob("*.json")):
            response = self.directory / "responses" / path.name
            if response.exists():
                continue
            try:
                request = json.loads(path.read_text())
                if request["kind"] == "observe":
                    if path.stem not in self.pending:
                        self.begin_image(path.stem)
                    observation = self.pending[path.stem]
                    if not Path(observation["image_path"]).exists():
                        continue
                    observation["capture_to_image_ready_wall_s"] = time.monotonic() - self.observations[path.stem]["monotonic"]
                    observation["image_ready_at_utc"] = utc()
                    result = {"observation": observation}
                elif request["kind"] == "submit":
                    result = {"receipt": self.submit(request["command"], path.stem)}
                else:
                    raise ValueError("Unknown camera request kind")
            except (ValueError, TypeError, KeyError) as error:
                result = {"error": str(error)}
            write_json(response, result)

    def report(self):
        report = super().report()
        audits, matched, unintended = [], [], set()
        for event in self.env.events:
            if "perception" not in event or event["command"].get("observation_id") not in self.truth:
                continue
            perception = event["perception"]
            objects = self.truth[event["command"]["observation_id"]]
            nearest = min(objects, key=lambda c: np.linalg.norm(np.asarray(c["xy"]) - perception["estimated_world_xy_m"]))
            delta = np.asarray(perception["estimated_world_xy_m"]) - nearest["xy"]
            identified = float(np.linalg.norm(delta)) <= 0.03
            if identified:
                matched.append(nearest["id"])
            touched = self.env.contacts_by_label.get(perception["object_id"], set())
            unintended.update(touched - ({nearest["id"]} if identified else set()))
            audits.append({"request_id": event["request_id"], **perception,
                           "matched_physical_id": nearest["id"] if identified else None,
                           "true_color": nearest["color"], "true_world_xy_m": nearest["xy"],
                           "position_error_m": float(np.linalg.norm(delta)), "y_error_m": float(delta[1]),
                           "color_correct": bool(identified and perception["perceived_color"] == nearest["color"]),
                           "is_target": bool(identified and nearest["color"] == self.env.config.target_color),
                           "touched_physical_ids": sorted(touched)})
        selection_correct = (set(matched) == set(self.env.target_ids) and len(audits) == len(self.env.events)
                             and all(a["color_correct"] and a["is_target"] for a in audits))
        outcomes = report["scoring"]["outcomes"]
        physical = (self.env.completed and outcomes.get("correct_reject", 0) == len(self.env.target_ids)
                    and outcomes.get("correct_pass", 0) == self.env.config.count - len(self.env.target_ids)
                    and set(self.env.target_ids).issubset(self.env.contact_cubes) and not unintended
                    and not self.env.fixture_contacts and not self.env.neighbor_contacts
                    and self.env.max_tracking_error <= 0.005)
        report.update(phase=5, time_mode="continuous_wall_clock_camera", perception_audits=audits,
                      selection_correct=selection_correct, selected_cube_ids=matched,
                      unintended_cube_contacts=sorted(unintended), push_success=bool(physical),
                      sorting_success=bool(physical and selection_correct and report["realtime_healthy"]
                                           and report["timing_failures"] == 0),
                      note="Agent saw camera pixels and calibration only. Physical IDs/positions were matched "
                           "post hoc for scoring, never used to choose or position a motion.")
        for name in ["conveyor_sim/camera.py", "conveyor_sim/vision_runtime.py", "conveyor_sim/vision_render.py",
                     "conveyor_sim/vision.py", "experiments/conveyor-color-sorting/phase5/PROTOCOL.md",
                     "experiments/conveyor-color-sorting/phase5/cases.json"]:
            path = ROOT / name
            if path.exists():
                report["source_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return report

    def run(self):
        write_json(self.private / "config.json", asdict(self.env.config))
        with (self.private / "renderer.log").open("w") as log:
            renderer = subprocess.Popen([str(ROOT / ".venv/bin/mjpython"), "-m", "conveyor_sim.vision_render",
                                         "--episode", str(self.directory)], stdout=log, stderr=subprocess.STDOUT)
        until = time.monotonic() + 30
        while not (self.private / "renderer_ready.json").exists():
            if renderer.poll() is not None or time.monotonic() > until:
                renderer.terminate()
                renderer.wait(timeout=5)
                raise RuntimeError("Camera initialization failed; see private/renderer.log")
            time.sleep(0.01)
        self.env.wait(0.5)
        self.epoch = time.monotonic() - self.env.data.time
        self.wall_started = utc()
        write_json(self.directory / "ready.json", {"started_at_utc": self.wall_started,
                   "instruction": self.env.config.instruction, "observation_mode": "camera"})
        try:
            while self.env.data.time < self.env.deadline:
                now = time.monotonic()
                if now >= self.next_poll:
                    self.poll_requests()
                    self.prepare_jobs()
                    self.next_poll = now + 0.01
                elapsed = time.monotonic() - self.epoch
                self.max_lag = max(self.max_lag, elapsed - self.env.data.time)
                if elapsed >= self.env.data.time + self.env.model.opt.timestep:
                    self.control_before_step()
                    self.env._step()
                    self.control_after_step()
                else:
                    time.sleep(min(0.001, self.env.data.time + self.env.model.opt.timestep - elapsed))
                if now >= self.next_status:
                    write_json(self.directory / "status.json", {"time_s": float(self.env.data.time),
                               "max_lag_s": self.max_lag, "completed": False,
                               "jobs": [{"object_id": e.get("perception", {}).get("object_id"),
                                         "status": e["status"], "error": e["error"]} for e in self.env.events]})
                    self.next_status = now + 0.5
        except KeyboardInterrupt:
            self.interrupted = True
        except Exception:
            self.interrupted = True
            raise
        finally:
            self.wall_finished = utc()
            for job in self.jobs:
                if job["event"]["status"] in {"planning", "queued", "running"}:
                    job["event"].update(status="unfinished", error="Episode ended before command completed")
            self.pool.shutdown(wait=True)
            (self.private / "render_stop").touch()
            renderer.wait(timeout=10)
            self.env._sample()
            self.env.scorer.finish()
            self.env.completed = True
            write_json(self.private / "report.json", self.report())
            np.savez_compressed(self.private / "episode.npz", phase=5, config=json.dumps(asdict(self.env.config)),
                                frames=np.asarray(self.env.frames), times=np.asarray(self.env.frame_times),
                                score_frames=json.dumps(self.env.score_frames))
            write_json(self.directory / "status.json", {"time_s": float(self.env.data.time), "completed": True})
        return self.report()
