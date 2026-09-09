"""Friction-driven conveyor with a parked SO101 and reproducible cube batches."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from .scoring import Cube, Observation, Scorer

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "scenes" / "conveyor.xml"
COLORS = {"red": (0.9, 0.035, 0.025, 1), "blue": (0.025, 0.25, 0.9, 1),
          "green": (0.03, 0.7, 0.16, 1)}


@dataclass(frozen=True)
class Config:
    seed: int = 0
    count: int = 6
    belt_speed: float = 0.03
    target_color: str = "red"

    def __post_init__(self):
        if not 1 <= self.count <= 6:
            raise ValueError("Phase 1 supports one to six widely spaced cubes")
        if not math.isfinite(self.belt_speed) or not 0.005 <= self.belt_speed <= 0.06:
            raise ValueError("Belt speed must be between 0.005 and 0.06 m/s")
        if self.target_color not in COLORS:
            raise ValueError("Target color must be red, blue, or green")
        if self.seed < 0:
            raise ValueError("Seed must be nonnegative")


class Conveyor:
    def __init__(self, config=Config(), capture=True):
        self.config = config
        self.capture = capture
        rng = np.random.default_rng(config.seed)
        assigned = self._colors(rng)
        self.cubes = [Cube(f"cube_{i:03d}", color) for i, color in enumerate(assigned)]
        root = ET.parse(SCENE).getroot()
        root.find("include").set("file", str(ROOT / "models" / "so101" / "so101.xml"))
        root.find("compiler").set("meshdir", str(ROOT / "models" / "so101" / "assets"))
        world = root.find("worldbody")
        world.find("geom[@name='belt']").set("surfacevel", f"0 {config.belt_speed} 0 0 0 0")
        self.initial = []
        for i, cube in enumerate(self.cubes):
            position = self._initial_position(i, rng)
            yaw = rng.uniform(-0.15, 0.15)
            self.initial.append({**asdict(cube), "position_m": position, "yaw_rad": yaw})
            body = ET.SubElement(world, "body", name=cube.id, pos=" ".join(map(str, position)),
                                 euler=f"0 0 {yaw}")
            ET.SubElement(body, "freejoint", name=f"{cube.id}_joint")
            ET.SubElement(body, "geom", name=cube.id, type="box", size="0.015 0.015 0.015",
                          mass="0.02", rgba=" ".join(map(str, COLORS[cube.color])),
                          friction="0.8 0.005 0.0001", condim="4")
        self.model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))
        self.data = mujoco.MjData(self.model)
        self.cube_body_ids = {cube.id: self.model.body(cube.id).id for cube in self.cubes}
        self.cube_geom_ids = {self.model.geom(cube.id).id: cube.id for cube in self.cubes}
        cube_bodies = set(self.cube_body_ids.values())
        self.arm_geoms = {i for i in range(self.model.ngeom)
                          if self.model.geom_bodyid[i] != 0 and self.model.geom_bodyid[i] not in cube_bodies}
        self.scorer = Scorer(self.cubes, config.target_color)
        self.frames, self.frame_times, self.score_frames = [], [], []
        self.arm_contact_steps = 0
        self.max_arm_deviation = 0.0
        self.speed_errors = []
        self.max_lateral_drift = 0.0
        self.premature_departures = set()
        self.on_frame = None
        self.completed = False
        mujoco.mj_forward(self.model, self.data)
        self._sample()

    def _colors(self, rng):
        colors = list(COLORS)
        assigned = [colors[i % len(colors)] for i in range(self.config.count)]
        rng.shuffle(assigned)
        return assigned

    def _initial_position(self, i, rng):
        return [0.22 + rng.uniform(-0.006, 0.006),
                -0.36 + i * 0.12 + rng.uniform(-0.004, 0.004), 0.016]

    @property
    def deadline(self):
        return (0.45 - min(c["position_m"][1] for c in self.initial)) / self.config.belt_speed + 6.0

    def observations(self):
        contacts = {cube.id: set() for cube in self.cubes}
        for contact in self.data.contact:
            if contact.dist > 0 or contact.efc_address < 0:
                continue
            for this, other in ((contact.geom1, contact.geom2), (contact.geom2, contact.geom1)):
                if this in self.cube_geom_ids:
                    contacts[self.cube_geom_ids[this]].add(self.model.geom(int(other)).name)
        observations = {}
        for cube in self.cubes:
            body = self.cube_body_ids[cube.id]
            joint = self.model.joint(f"{cube.id}_joint").id
            dof = self.model.jnt_dofadr[joint]
            extent = 0.015 * np.abs(self.data.xmat[body].reshape(3, 3)).sum(axis=1)
            observations[cube.id] = Observation(tuple(self.data.xpos[body]), tuple(extent),
                                                tuple(self.data.qvel[dof:dof + 3]),
                                                tuple(sorted(contacts[cube.id])))
        return observations

    def _sample(self):
        mujoco.mj_forward(self.model, self.data)
        observations = self.observations()
        self.scorer.update(float(self.data.time), observations)
        if self.data.time >= 0.5:
            for initial in self.initial:
                obs = observations[initial["id"]]
                if obs.position[1] <= 0.40 and "belt" not in obs.contacts:
                    self.premature_departures.add(initial["id"])
                if "belt" in obs.contacts and -0.40 <= obs.position[1] <= 0.40:
                    self.speed_errors.append(abs(obs.velocity[1] - self.config.belt_speed))
                    self.max_lateral_drift = max(self.max_lateral_drift,
                                                abs(obs.position[0] - initial["position_m"][0]))
        if self.capture:
            self.frames.append(self.data.qpos.copy())
            self.frame_times.append(float(self.data.time))
            self.score_frames.append({"time_s": float(self.data.time),
                                      "collected": sum(r["destination"] == "pass" for r in self.scorer.results.values()),
                                      "outcomes": self.scorer.summary()["outcomes"]})
        if self.on_frame:
            self.on_frame()

    def run(self, seconds=None):
        if self.completed:
            raise ValueError("This episode is already complete; create another for a new trial")
        duration = self.deadline if seconds is None else seconds
        if not math.isfinite(duration) or not 0 < duration <= 300:
            raise ValueError("Episode duration must be positive and no more than 300 seconds")
        steps = math.ceil(duration / self.model.opt.timestep)
        every = max(1, round(1 / (30 * self.model.opt.timestep)))
        for i in range(steps):
            # Controls stay at the initial zero-angle parked pose throughout Phase 1.
            mujoco.mj_step(self.model, self.data)
            if not np.isfinite(self.data.qpos).all():
                raise RuntimeError("Nonfinite simulation state")
            self.max_arm_deviation = max(self.max_arm_deviation, float(np.abs(self.data.qpos[:6]).max()))
            if any((c.geom1 in self.cube_geom_ids and c.geom2 in self.arm_geoms) or
                   (c.geom2 in self.cube_geom_ids and c.geom1 in self.arm_geoms)
                   for c in self.data.contact if c.dist <= 0 and c.efc_address >= 0):
                self.arm_contact_steps += 1
            if (i + 1) % every == 0 or i == steps - 1:
                self._sample()
        self.completed = True
        self.scorer.finish()
        return self.report()

    def report(self):
        scoring = self.scorer.summary()
        collected = sum(c["destination"] == "pass" for c in scoring["cubes"])
        errors = np.asarray(self.speed_errors)
        max_error = float(errors.max()) if errors.size else None
        settled = len(scoring["cubes"]) == self.config.count
        success = bool(self.completed and settled and collected == self.config.count and
                       self.arm_contact_steps == 0 and self.max_arm_deviation < 0.01 and
                       not self.premature_departures and
                       max_error is not None and max_error <= 0.002 and self.max_lateral_drift <= 0.005)
        hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in [SCENE, Path(__file__), ROOT / "conveyor_sim" / "scoring.py",
                               ROOT / "models" / "so101" / "so101.xml"]}
        return {"phase": 1, "config": asdict(self.config), "initial_cubes": self.initial,
                "simulation_duration_s": round(float(self.data.time), 6),
                "completed": self.completed, "transport_success": success,
                "collected_cubes": collected, "arm_cube_contact_steps": self.arm_contact_steps,
                "max_arm_deviation_rad": self.max_arm_deviation,
                "max_belt_speed_error_m_s": max_error,
                "mean_belt_speed_error_m_s": float(errors.mean()) if errors.size else None,
                "max_lateral_drift_m": self.max_lateral_drift,
                "premature_belt_departures": sorted(self.premature_departures),
                "scoring": scoring, "versions": {"mujoco": mujoco.__version__, "numpy": np.__version__,
                                                   "python": platform.python_version()},
                "source_sha256": hashes,
                "note": "Transport baseline: arm parked. Target misses are expected sorting outcomes."}

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "report.json").write_text(json.dumps(self.report(), indent=2) + "\n")
        if self.capture:
            np.savez_compressed(directory / "episode.npz", config=json.dumps(asdict(self.config)),
                                frames=np.array(self.frames), times=np.array(self.frame_times),
                                score_frames=json.dumps(self.score_frames))


def configure_camera(camera):
    camera.lookat[:] = [0.22, 0.12, -0.05]
    camera.distance = 1.35
    camera.azimuth = 145
    camera.elevation = -35
