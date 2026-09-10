"""Wall-clock MuJoCo runtime with asynchronous preflight and expiring commands."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace

import mujoco
import numpy as np

from .environment import COLORS, ROOT
from .interactive import InteractiveTrial
from .pushing import PushTrial
from so101_sim.environment import Environment


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


@dataclass(frozen=True)
class RealtimeConfig:
    seed: int = 0
    target_color: str = "red"
    instruction: str = "Reject red cubes; let the others pass."
    actor: str = "codex_session"
    belt_speed: float = 0.005
    spacing: float = 0.12
    count: int = 3
    scenario: str = "mixed"

    def __post_init__(self):
        if self.seed < 0 or self.target_color not in COLORS or not self.instruction.strip():
            raise ValueError("Invalid seed, color, or instruction")
        if self.actor not in {"codex_session", "conventional", "test"}:
            raise ValueError("Unknown actor")
        if self.count != 3 or self.scenario not in {"mixed", "stream"}:
            raise ValueError("Use three mixed-color cubes or three consecutive target cubes")
        if not math.isfinite(self.belt_speed) or not 0.005 <= self.belt_speed <= 0.03:
            raise ValueError("Belt speed must be 0.005–0.03 m/s")
        if not math.isfinite(self.spacing) or not 0.06 <= self.spacing <= 0.12:
            raise ValueError("Spacing must be 0.06–0.12 m")


class RealtimeTrial(InteractiveTrial):
    def _colors(self, rng):
        if self.config.scenario == "stream":
            return [self.config.target_color] * self.config.count
        return super()._colors(rng)

    def _initial_position(self, i, rng):
        return [0.22 + rng.uniform(-0.006, 0.006),
                -0.14 - (2 - i) * self.config.spacing + rng.uniform(-0.004, 0.004), 0.016]

    def observe(self):
        observation = super().observe()
        observation["time_mode"] = "continuous_wall_clock"
        return observation


def compile_motion(model, qpos, primitives):
    """Preflight on private data in a worker; the physics loop continues running."""
    if not isinstance(primitives, list) or len(primitives) != 4:
        raise ValueError("Supply approach, descent, sweep, and retract explicitly")
    if [p.get("tool") for p in primitives] != ["move_to", "move_to", "sweep", "retract"]:
        raise ValueError("Sequence must be move_to, move_to, sweep, retract")
    scratch = mujoco.MjData(model)
    scratch.qpos[:] = qpos
    adapter = SimpleNamespace(model=model, data=scratch, tool_id=model.site("gripperframe").id)
    segments = []
    for i, primitive in enumerate(primitives):
        if i == 3:
            if set(primitive) != {"tool"}:
                raise ValueError("Retract takes no arguments")
            xyz, seconds, joint = np.array([0.22, 0.005, 0.075]), 1.5, False
        else:
            if set(primitive) - {"tool", "xyz", "seconds", "joint"}:
                raise ValueError("Unknown primitive arguments")
            xyz = np.asarray(primitive["xyz"], dtype=float)
            seconds, joint = float(primitive["seconds"]), primitive.get("joint", False)
            if xyz.shape != (3,) or not np.isfinite(xyz).all() or not isinstance(joint, bool):
                raise ValueError("Invalid position or interpolation mode")
            if not math.isfinite(seconds) or not 0.1 <= seconds <= 5:
                raise ValueError("Duration outside [0.1, 5] seconds")
            if i == 0 and (not joint or xyz[2] < 0.06):
                raise ValueError("Approach requires a joint move to clearance height")
            if i == 1 and (joint or abs(xyz[0] - 0.18) > 0.001 or xyz[2] != 0.020):
                raise ValueError("Descend at the near edge using Cartesian motion")
            if i == 2 and (joint or not (0.27 <= xyz[0] <= 0.30 and abs(xyz[1]) <= 0.10
                                        and xyz[2] == 0.020 and 1 <= seconds <= 3)):
                raise ValueError("Sweep exceeds the validated working area")
        mujoco.mj_forward(model, scratch)
        start = scratch.site_xpos[adapter.tool_id].copy()
        count = 1 if joint else max(1, math.ceil(np.linalg.norm(xyz - start) / 0.005))
        for index, fraction in enumerate(np.linspace(0, 1, count + 1)[1:]):
            joints = Environment.solve_downward(adapter, start + fraction * (xyz - start))
            scratch.qpos[:5] = joints
            segments.append({"ctrl": np.r_[joints, 0.0],
                             "steps": math.ceil(seconds / count / model.opt.timestep),
                             "endpoint": xyz.tolist() if index == count - 1 else None,
                             "label": primitive["tool"]})
    return segments


class Runtime:
    MAX_LAG_S = 0.25

    def __init__(self, env, directory):
        self.env, self.directory = env, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        for name in ["requests", "responses"]:
            (self.directory / name).mkdir(exist_ok=True)
        self.observations, self.jobs = {}, []
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.running = None
        self.epoch = None
        self.max_lag = 0.0
        self.wall_started = None
        self.wall_finished = None
        self.interrupted = False
        self.next_poll = self.next_status = 0.0

    def snapshot(self, observation_id):
        now = time.monotonic()
        observation = {**self.env.observe(), "observation_id": observation_id,
                       "observed_at_utc": utc(), "wall_elapsed_s": now - self.epoch,
                       "simulation_lag_s": max(0, now - self.epoch - self.env.data.time)}
        self.observations[observation_id] = {"observation": observation, "monotonic": now}
        return observation

    def submit(self, command, request_id):
        now = time.monotonic()
        event = {"request_id": request_id, "command": command, "status": "planning",
                 "received_at_utc": utc(), "received_at_sim_s": float(self.env.data.time),
                 "error": None, "actual_start_s": None, "actual_end_s": None}
        self.env.events.append(event)
        try:
            if set(command) != {"cube_id", "observation_id", "start_at_s", "expires_at_s", "primitives"}:
                raise ValueError("Supply cube_id, observation_id, start_at_s, expires_at_s, primitives")
            if command["cube_id"] not in self.env.cube_body_ids:
                raise ValueError("Unknown cube ID")
            observed = self.observations[command["observation_id"]]
            event["observation"] = observed["observation"]
            event["observation_to_submission_wall_s"] = now - observed["monotonic"]
            event["observation_age_sim_s"] = float(self.env.data.time) - observed["observation"]["time_s"]
            start, expiry = float(command["start_at_s"]), float(command["expires_at_s"])
            if not all(math.isfinite(v) for v in [start, expiry]) or not 0 <= start <= expiry <= start + 0.1:
                raise ValueError("Expiry must be within 0.1 seconds after a finite nonnegative start")
            if expiry > self.env.deadline:
                raise ValueError("Command extends beyond the episode deadline")
            if self.env.data.time > expiry:
                event.update(status="expired", error="Command arrived after its latest start")
                return event
            job = {"event": event, "future": self.pool.submit(compile_motion, self.env.model,
                                                             self.env.data.qpos.copy(), command["primitives"])}
            self.jobs.append(job)
        except (ValueError, TypeError, KeyError) as error:
            event.update(status="rejected", error=str(error))
        return event

    def poll_requests(self):
        for path in sorted((self.directory / "requests").glob("*.json")):
            response = self.directory / "responses" / path.name
            if response.exists():
                continue
            try:
                request = json.loads(path.read_text())
                if request["kind"] == "observe":
                    result = {"observation": self.snapshot(path.stem)}
                elif request["kind"] == "submit":
                    result = {"receipt": self.submit(request["command"], path.stem)}
                else:
                    raise ValueError("Unknown request kind")
            except (ValueError, TypeError, KeyError) as error:
                result = {"error": str(error)}
            write_json(response, result)

    def prepare_jobs(self):
        for job in self.jobs:
            event = job["event"]
            if event["status"] != "planning" or not job["future"].done():
                continue
            try:
                job["segments"] = job["future"].result()
                duration = sum(s["steps"] for s in job["segments"]) * self.env.model.opt.timestep
                event["planned_motion_s"] = duration
                start = event["command"]["start_at_s"]
                if self.env.data.time > event["command"]["expires_at_s"]:
                    event.update(status="expired", error="Preflight finished after latest start")
                    continue
                conflict = any(other is not job and other["event"]["status"] in {"queued", "running"}
                               and start < other["event"]["command"]["start_at_s"] + other["event"]["planned_motion_s"]
                               and other["event"]["command"]["start_at_s"] < start + duration
                               for other in self.jobs)
                if conflict:
                    event.update(status="rejected", error="Motion overlaps another reserved robot cycle")
                else:
                    event["status"] = "queued"
            except (ValueError, TypeError, KeyError) as error:
                event.update(status="rejected", error=str(error))

    def control_before_step(self):
        if self.running is None:
            for job in sorted(self.jobs, key=lambda j: j["event"]["command"].get("start_at_s", 0)):
                event = job["event"]
                if event["status"] != "queued":
                    continue
                if self.env.data.time > event["command"]["expires_at_s"]:
                    event.update(status="expired", error="Robot unavailable before latest start")
                elif self.env.data.time + 1e-9 >= event["command"]["start_at_s"]:
                    self.running = job
                    job.update(segment=0, step=0, initial=self.env.data.ctrl.copy(), action_start=float(self.env.data.time))
                    event.update(status="running", actual_start_s=float(self.env.data.time))
                    event["queue_wait_sim_s"] = event["actual_start_s"] - event["received_at_sim_s"]
                    self.env.active_target = event["command"]["cube_id"]
                    break
        if self.running:
            job = self.running
            segment = job["segments"][job["segment"]]
            self.env.data.ctrl[:] = job["initial"] + (segment["ctrl"] - job["initial"]) * ((job["step"] + 1) / segment["steps"])

    def control_after_step(self):
        if not self.running:
            return
        job = self.running
        segment = job["segments"][job["segment"]]
        job["step"] += 1
        if job["step"] < segment["steps"]:
            return
        if segment["endpoint"] is not None:
            self.env._sample()
            error = float(np.linalg.norm(self.env.data.site_xpos[self.env.tool_id] - segment["endpoint"]))
            self.env.max_tracking_error = max(self.env.max_tracking_error, error)
            self.env.actions.append({"action": segment["label"], "target_xyz_m": segment["endpoint"],
                                     "start_s": job["action_start"], "end_s": float(self.env.data.time),
                                     "position_error_m": error})
            job["action_start"] = float(self.env.data.time)
        job.update(segment=job["segment"] + 1, step=0, initial=self.env.data.ctrl.copy())
        if job["segment"] == len(job["segments"]):
            job["event"].update(status="completed", actual_end_s=float(self.env.data.time),
                                after=self.env.observe())
            self.env.active_target = None
            self.running = None

    def report(self):
        report = PushTrial.report(self.env)
        selected = [e["command"].get("cube_id") for e in self.env.events if isinstance(e["command"], dict)]
        selection_correct = set(selected) == set(self.env.target_ids)
        timing_failures = sum(e["status"] in {"expired", "rejected", "unfinished"} for e in self.env.events)
        healthy = self.max_lag <= self.MAX_LAG_S and not self.interrupted
        report.update(phase=4, actor=self.env.config.actor, time_mode="continuous_wall_clock",
                      selected_cube_ids=selected, selection_correct=selection_correct,
                      sorting_success=bool(report["push_success"] and selection_correct and healthy and not timing_failures),
                      realtime_healthy=healthy, max_simulation_lag_s=self.max_lag,
                      allowed_lag_s=self.MAX_LAG_S, wall_started_utc=self.wall_started,
                      wall_finished_utc=self.wall_finished, timing_failures=timing_failures,
                      events=self.env.events, observations=[o["observation"] for o in self.observations.values()],
                      note="Codex selects IDs and explicitly schedules primitive sequences. Physics continues "
                           "during observation, reasoning, queuing, preflight, and motion. Measured response "
                           "gaps include orchestration; isolated inference latency and token usage unavailable.")
        for name in ["conveyor_sim/interactive.py", "conveyor_sim/realtime.py", "conveyor_sim/live.py",
                     "conveyor_sim/live_experiment.py",
                     "experiments/conveyor-color-sorting/phase4/PROTOCOL.md",
                     "experiments/conveyor-color-sorting/phase4/cases.json"]:
            path = ROOT / name
            if path.exists():
                report["source_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return report

    def run(self):
        self.env.wait(0.5)
        self.epoch = time.monotonic() - self.env.data.time
        self.wall_started = utc()
        write_json(self.directory / "ready.json", {"started_at_utc": self.wall_started, "config": asdict(self.env.config)})
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
                               "wall_elapsed_s": time.monotonic() - self.epoch, "max_lag_s": self.max_lag,
                               "jobs": self.env.events, "scoring": self.env.scorer.summary()})
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
            self.env._sample()
            self.env.scorer.finish()
            self.env.completed = True
            write_json(self.directory / "report.json", self.report())
            np.savez_compressed(self.directory / "episode.npz", phase=4, config=json.dumps(asdict(self.env.config)),
                                frames=np.asarray(self.env.frames), times=np.asarray(self.env.frame_times),
                                score_frames=json.dumps(self.env.score_frames))
        return self.report()
