"""Phase 2 conventional pushing baseline using exact target IDs and positions."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np

from so101_sim.environment import Environment
from .environment import COLORS, Config, Conveyor, ROOT


@dataclass(frozen=True)
class PushConfig:
    seed: int = 0
    belt_speed: float = 0.01
    target_color: str = "red"
    scenario: str = "isolated"
    spacing: float = 0.12

    @property
    def count(self):
        return 1 if self.scenario == "isolated" else 3

    def __post_init__(self):
        if self.scenario not in {"isolated", "neighbors", "stream"}:
            raise ValueError("Scenario must be isolated, neighbors, or stream")
        if not math.isfinite(self.belt_speed) or not 0 <= self.belt_speed <= 0.03:
            raise ValueError("Push trials support belt speeds from 0 to 0.03 m/s")
        if self.scenario != "isolated" and self.belt_speed == 0:
            raise ValueError("Multi-cube trials require a moving belt")
        if not math.isfinite(self.spacing) or not 0.06 <= self.spacing <= 0.12:
            raise ValueError("Spacing must be between 0.06 and 0.12 m")
        if self.seed < 0 or self.target_color not in COLORS:
            raise ValueError("Invalid seed or target color")


class PushTrial(Conveyor):
    def __init__(self, config=PushConfig(), capture=True):
        self.actions = []
        self.contact_cubes = set()
        self.unintended_contacts = set()
        self.fixture_contacts = set()
        self.neighbor_contacts = set()
        self.active_target = None
        self.step_count = 0
        self.max_tracking_error = 0.0
        self.rejections = []
        self.controller_error = None
        super().__init__(config, capture)
        self.tool_id = self.model.site("gripperframe").id
        self.target_ids = (["cube_001"] if config.scenario == "neighbors" else
                           [cube.id for cube in self.cubes])

    def _colors(self, rng):
        if self.config.scenario == "neighbors":
            others = [c for c in COLORS if c != self.config.target_color]
            rng.shuffle(others)
            return [others[0], self.config.target_color, others[1]]
        return [self.config.target_color] * self.config.count

    def _initial_position(self, i, rng):
        if self.config.belt_speed == 0:
            y = rng.uniform(-0.012, 0.012)
        elif self.config.scenario == "isolated":
            y = -0.10 + rng.uniform(-0.004, 0.004)
        else:
            y = -0.06 - (2 - i) * self.config.spacing + rng.uniform(-0.004, 0.004)
        return [0.22 + rng.uniform(-0.006, 0.006), y, 0.016]

    def _sample(self):
        # The Phase 1 transport metrics do not apply while the robot is pushing.
        mujoco.mj_forward(self.model, self.data)
        self.scorer.update(float(self.data.time), self.observations())
        if self.capture:
            self.frames.append(self.data.qpos.copy())
            self.frame_times.append(float(self.data.time))
            self.score_frames.append({"time_s": float(self.data.time),
                                      "collected": sum(r["destination"] == "pass" for r in self.scorer.results.values()),
                                      "outcomes": self.scorer.summary()["outcomes"]})
        if self.on_frame:
            self.on_frame()

    def _step(self):
        mujoco.mj_step(self.model, self.data)
        if not np.isfinite(self.data.qpos).all():
            raise RuntimeError("Nonfinite simulation state")
        self.step_count += 1
        for contact in self.data.contact:
            if contact.dist > 0 or contact.efc_address < 0:
                continue
            a, b = int(contact.geom1), int(contact.geom2)
            if a in self.cube_geom_ids and b in self.cube_geom_ids:
                # Collection piles are expected; contacts in the belt's working area are not.
                if max(self.data.geom_xpos[a, 2], self.data.geom_xpos[b, 2]) > -0.03:
                    self.neighbor_contacts.add(tuple(sorted((self.cube_geom_ids[a], self.cube_geom_ids[b]))))
            for arm, other in ((int(contact.geom1), int(contact.geom2)),
                               (int(contact.geom2), int(contact.geom1))):
                if arm not in self.arm_geoms or other in self.arm_geoms:
                    continue
                name = self.model.geom(other).name
                if other in self.cube_geom_ids:
                    self.contact_cubes.add(name)
                    if name != self.active_target:
                        self.unintended_contacts.add(name)
                else:
                    self.fixture_contacts.add(name)
        if self.step_count % 17 == 0:
            self._sample()

    def wait(self, seconds):
        if not math.isfinite(seconds) or not 0 <= seconds <= 150:
            raise ValueError("Wait must be finite and between 0 and 150 seconds")
        for _ in range(math.ceil(seconds / self.model.opt.timestep)):
            self._step()
        self._sample()

    def move(self, xyz, seconds, cartesian=True, label="move"):
        """Preflight IK for the full motion, then interpolate position actuator targets."""
        if not math.isfinite(seconds) or not 0.1 <= seconds <= 5:
            raise ValueError("Motion duration must be in [0.1, 5] seconds")
        xyz = np.asarray(xyz, dtype=float)
        if xyz.shape != (3,) or not np.isfinite(xyz).all():
            raise ValueError("Motion target must contain three finite coordinates")
        start_pos = self.data.site_xpos[self.tool_id].copy()
        count = max(1, math.ceil(np.linalg.norm(xyz - start_pos) / 0.005)) if cartesian else 1
        scratch = mujoco.MjData(self.model)
        scratch.qpos[:] = self.data.qpos
        adapter = SimpleNamespace(model=self.model, data=scratch, tool_id=self.tool_id)
        waypoints = []
        for fraction in np.linspace(0, 1, count + 1)[1:]:
            point = start_pos + fraction * (xyz - start_pos)
            joints = Environment.solve_downward(adapter, point)
            scratch.qpos[:5] = joints
            waypoints.append(np.r_[joints, 0.0])
        started = float(self.data.time)
        for target in waypoints:
            initial = self.data.ctrl.copy()
            steps = max(1, math.ceil(seconds / count / self.model.opt.timestep))
            for i in range(steps):
                self.data.ctrl[:] = initial + (target - initial) * ((i + 1) / steps)
                self._step()
        self._sample()
        error = float(np.linalg.norm(self.data.site_xpos[self.tool_id] - xyz))
        self.max_tracking_error = max(self.max_tracking_error, error)
        self.actions.append({"action": label, "target_xyz_m": xyz.tolist(),
                             "start_s": started, "end_s": float(self.data.time), "position_error_m": error})

    def push(self, target_id):
        if target_id not in self.cube_body_ids:
            raise ValueError("Unknown target cube")
        observation = self.observations()[target_id]
        if "belt" not in observation.contacts:
            raise ValueError("Target is not on the belt")
        self.active_target = target_id
        speed = self.config.belt_speed
        started = float(self.data.time)
        # Setup high above the near side of the belt, clear of passing cubes.
        self.move([0.18, 0.005, 0.065], 2.0, cartesian=False, label="approach")
        observation = self.observations()[target_id]
        if speed:
            wait = (-0.015 - observation.position[1]) / speed
            if wait < -0.5:
                raise ValueError("Target passed the interception entry point")
            self.wait(max(0, wait))
        # Lead the cube through descent, then follow belt motion during the sweep.
        observation = self.observations()[target_id]
        y = observation.position[1] + speed * 1.0 + 0.005
        self.move([0.18, y, 0.020], 1.0, label="descend")
        sweep_started = float(self.data.time)
        self.move([0.30, y + speed * 2.0, 0.020], 2.0, label="sweep")
        self.move([0.22, 0.005, 0.075], 1.5, label="retract")
        self.rejections.append({"cube_id": target_id, "cycle_start_s": started,
                                "sweep_start_s": sweep_started, "ready_s": float(self.data.time),
                                "cycle_seconds_including_wait": float(self.data.time) - started,
                                "observation_after_retract": list(self.data.body(target_id).xpos)})
        self.active_target = None

    def run(self, seconds=None):
        if self.completed:
            raise ValueError("Episode is already complete")
        self.wait(0.5)
        try:
            for target in sorted(self.target_ids,
                                 key=lambda id: self.data.body(id).xpos[1], reverse=True):
                self.push(target)
        except ValueError as error:
            self.controller_error = str(error)
            self.active_target = None
        # Let every cube reach an outcome even when the controller fails.
        deadline = ((0.45 - min(c["position_m"][1] for c in self.initial)) / self.config.belt_speed + 6
                    if self.config.belt_speed else self.data.time + 4)
        self.wait(4.0)
        if len(self.scorer.results) < self.config.count:
            self.wait(max(0.0, deadline - self.data.time))
        self.completed = True
        self.scorer.finish()
        return self.report()

    def report(self):
        scoring = self.scorer.summary()
        by_id = {r["id"]: r for r in scoring["cubes"]}
        success = bool(self.completed and not self.controller_error and not self.unintended_contacts and
                       not self.fixture_contacts and not self.neighbor_contacts and
                       set(self.target_ids).issubset(self.contact_cubes) and self.max_tracking_error <= 0.005 and all(
                           by_id.get(cube.id, {}).get("destination") == ("reject" if cube.id in self.target_ids else "pass")
                           for cube in self.cubes))
        paths = [ROOT / "scenes" / "conveyor.xml", ROOT / "conveyor_sim" / "environment.py",
                 Path(__file__), ROOT / "conveyor_sim" / "scoring.py", ROOT / "so101_sim" / "environment.py",
                 ROOT / "models" / "so101" / "so101.xml"]
        return {"phase": 2, "config": asdict(self.config), "initial_cubes": self.initial,
                "target_ids": self.target_ids, "completed": self.completed, "push_success": success,
                "controller_error": self.controller_error, "simulation_duration_s": float(self.data.time),
                "touched_cube_ids": sorted(self.contact_cubes),
                "unintended_cube_contacts": sorted(self.unintended_contacts),
                "cube_neighbor_contacts_on_belt": sorted(self.neighbor_contacts),
                "fixture_contacts": sorted(self.fixture_contacts), "max_tracking_error_m": self.max_tracking_error,
                "actions": self.actions, "rejections": self.rejections, "scoring": scoring,
                "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                "versions": {"mujoco": mujoco.__version__, "numpy": np.__version__},
                "note": "Conventional controller with supplied target IDs and exact state; no LLM decisions."}

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "report.json").write_text(json.dumps(self.report(), indent=2) + "\n")
        if self.capture:
            np.savez_compressed(directory / "episode.npz", phase=2, config=json.dumps(asdict(self.config)),
                                frames=np.array(self.frames), times=np.array(self.frame_times),
                                score_frames=json.dumps(self.score_frames))
