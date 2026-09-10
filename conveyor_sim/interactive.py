"""Persistent Phase 3 primitives. No action selects cubes by color."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import mujoco
import numpy as np

from .environment import COLORS, Conveyor, ROOT
from .pushing import PushTrial
from .scoring import Observation

STATE_SPEC = mujoco.mjtState.mjSTATE_INTEGRATION


@dataclass(frozen=True)
class InteractiveConfig:
    seed: int = 0
    target_color: str = "red"  # Grader setting; omitted from agent observations.
    instruction: str = "Reject red cubes; let the others pass."
    actor: str = "codex_session"
    belt_speed: float = 0.01
    spacing: float = 0.12
    count: int = 3

    def __post_init__(self):
        if self.seed < 0 or self.target_color not in COLORS or not self.instruction.strip():
            raise ValueError("Invalid seed, grader color, or instruction")
        if self.actor not in {"codex_session", "conventional", "test"}:
            raise ValueError("Unknown actor")
        if self.belt_speed != 0.01 or self.spacing != 0.12 or self.count != 3:
            raise ValueError("Phase 3 fixes three cubes, 1 cm/s, and 12 cm spacing")


class InteractiveTrial(PushTrial):
    def __init__(self, config=InteractiveConfig(), capture=True):
        # Initialize the shared physical controller without Phase 2's target layout.
        self.actions, self.rejections, self.events = [], [], []
        self.contact_cubes, self.unintended_contacts = set(), set()
        self.fixture_contacts, self.neighbor_contacts = set(), set()
        self.active_target, self.controller_error = None, None
        self.step_count, self.max_tracking_error = 0, 0.0
        self.last_saved_wall = None
        Conveyor.__init__(self, config, capture)
        self.tool_id = self.model.site("gripperframe").id
        # These IDs are used by the independent report, never by an action.
        self.target_ids = [c.id for c in self.cubes if c.color == config.target_color]

    def _colors(self, rng):
        return Conveyor._colors(self, rng)

    def _initial_position(self, i, rng):
        return [0.22 + rng.uniform(-0.006, 0.006),
                -0.30 + i * 0.12 + rng.uniform(-0.004, 0.004), 0.016]

    def observe(self):
        observations = self.observations()
        return {
            "instruction": self.config.instruction,
            "time_s": float(self.data.time), "time_mode": "paused_between_actions",
            "belt_velocity_m_s": [0, self.config.belt_speed, 0],
            "deadline_s": self.deadline,
            "tool_xyz_m": self.data.site_xpos[self.tool_id].tolist(),
            "joint_positions_rad": self.data.qpos[:6].tolist(),
            "joint_velocities_rad_s": self.data.qvel[:6].tolist(),
            "selected_cube_id": self.active_target,
            "completed": self.completed,
            "cubes": [{"id": c.id, "color": c.color,
                       **{key: list(value) for key, value in asdict(observations[c.id]).items()},
                       "destination": self.scorer.results.get(c.id, {}).get("destination")}
                      for c in self.cubes],
        }

    def execute(self, command):
        """Apply one explicit agent command, recording its inputs and consequences."""
        received = datetime.now(timezone.utc).isoformat()
        before = self.observe()
        error = None
        try:
            self._execute(command)
        except (ValueError, TypeError, KeyError) as exc:
            error = str(exc)
        event = {"index": len(self.events), "actor": self.config.actor,
                 "received_at_utc": received, "previous_save_at_utc": self.last_saved_wall,
                 "command": command, "before": before, "after": self.observe(), "error": error}
        self.events.append(event)
        return event

    def _execute(self, command):
        if not isinstance(command, dict):
            raise ValueError("Command must be an object")
        tool = command.get("tool")
        allowed = {"observe": {"tool"}, "wait": {"tool", "seconds"},
                   "move_to": {"tool", "xyz", "seconds", "joint", "cube_id"},
                   "sweep": {"tool", "xyz", "seconds"}, "retract": {"tool"},
                   "finish": {"tool"}}
        if tool not in allowed or set(command) - allowed[tool]:
            raise ValueError("Unknown tool or arguments")
        if tool == "observe":
            return
        if self.completed:
            raise ValueError("Episode is complete")
        if tool == "finish":
            self.scorer.finish()
            self.completed = True
            return
        if tool == "wait":
            seconds = float(command["seconds"])
            if not math.isfinite(seconds) or not 0 <= seconds <= 90:
                raise ValueError("Wait must be in [0, 90] seconds")
            self.wait(seconds)
            return
        if tool == "retract":
            self.move([0.22, 0.005, 0.075], 1.5, label="retract")
            self.active_target = None
            return
        xyz = np.asarray(command["xyz"], dtype=float)
        if xyz.shape != (3,) or not np.isfinite(xyz).all():
            raise ValueError("xyz must contain three finite coordinates")
        seconds = float(command["seconds"])
        if tool == "sweep":
            if self.active_target is None:
                raise ValueError("Select a cube with move_to before sweeping")
            if (abs(self.data.site_xpos[self.tool_id][0] - 0.18) > 0.005 or
                    abs(self.data.site_xpos[self.tool_id][2] - 0.020) > 0.005):
                raise ValueError("Sweep must start at the near belt edge at pushing height")
            if not (0.27 <= xyz[0] <= 0.30 and abs(xyz[1]) <= 0.10 and xyz[2] == 0.020
                    and 1 <= seconds <= 3):
                raise ValueError("Sweep exceeds the bounded working area or duration")
            self.move(xyz, seconds, label="sweep")
            return
        selected = command.get("cube_id", self.active_target)
        if selected is not None and selected not in self.cube_body_ids:
            raise ValueError("Unknown cube ID")
        if "cube_id" in command and self.active_target not in {None, selected}:
            raise ValueError("Retract before selecting a different cube")
        joint = command.get("joint", False)
        if not isinstance(joint, bool):
            raise ValueError("joint must be a boolean")
        if joint and xyz[2] < 0.06:
            raise ValueError("Joint interpolation requires a clearance-height endpoint")
        previous = self.active_target
        self.active_target = selected
        try:
            self.move(xyz, seconds, cartesian=not joint, label="move_to")
        except ValueError:
            self.active_target = previous
            raise

    def report(self):
        report = super().report()
        selection = [e["command"]["cube_id"] for e in self.events
                     if isinstance(e["command"], dict) and "cube_id" in e["command"] and not e["error"]]
        # Color choice errors cannot be hidden by later successful motions.
        correct_selection = set(selection) == set(self.target_ids)
        report.update(phase=3, time_mode="paused_between_actions", actor=self.config.actor,
                      selected_cube_ids=selection, selection_correct=correct_selection,
                      sorting_success=bool(report["push_success"] and correct_selection and
                                           not any(e["error"] for e in self.events)),
                      tool_calls=len(self.events), tool_errors=sum(bool(e["error"]) for e in self.events),
                      model_usage={"model": ("Codex session; exact runtime identifier not exposed"
                                             if self.config.actor == "codex_session" else None),
                                   "model_calls": None, "tokens": None, "cost": None},
                      note="Interactive development trial. Simulation pauses between explicit actions; "
                           "wall-clock gaps include orchestration and are not isolated model latency.")
        for relative in ["conveyor_sim/interactive.py", "conveyor_sim/phase3.py",
                         "experiments/conveyor-color-sorting/phase3/PROTOCOL.md",
                         "experiments/conveyor-color-sorting/phase3/cases.json"]:
            path = ROOT / relative
            if path.exists():
                report["source_sha256"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        report["events"] = self.events
        return report

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        state = np.empty(mujoco.mj_stateSize(self.model, STATE_SPEC))
        mujoco.mj_getState(self.model, self.data, state, STATE_SPEC)
        self.last_saved_wall = datetime.now(timezone.utc).isoformat()
        metadata = {key: getattr(self, key) for key in
                    ["actions", "rejections", "events", "active_target", "controller_error",
                     "step_count", "max_tracking_error", "completed", "last_saved_wall"]}
        for key in ["contact_cubes", "unintended_contacts", "fixture_contacts", "neighbor_contacts"]:
            metadata[key] = sorted(getattr(self, key))
        metadata["scorer"] = {key: getattr(self.scorer, key) for key in
                              ["candidates", "last_moving", "results", "time"]}
        metadata["scorer"]["latest"] = {key: asdict(obs) for key, obs in self.scorer.latest.items()}
        temporary = directory / "episode.tmp"
        with temporary.open("wb") as file:
            np.savez_compressed(file, phase=3, config=json.dumps(asdict(self.config)), state=state,
                                metadata=json.dumps(metadata), frames=np.asarray(self.frames),
                                times=np.asarray(self.frame_times), score_frames=json.dumps(self.score_frames))
        temporary.replace(directory / "episode.npz")
        report_tmp = directory / "report.tmp"
        report_tmp.write_text(json.dumps(self.report(), indent=2) + "\n")
        report_tmp.replace(directory / "report.json")

    @classmethod
    def load(cls, directory):
        with np.load(Path(directory) / "episode.npz", allow_pickle=False) as saved:
            env = cls(InteractiveConfig(**json.loads(str(saved["config"]))))
            mujoco.mj_setState(env.model, env.data, saved["state"], STATE_SPEC)
            env.frames, env.frame_times = list(saved["frames"]), list(saved["times"])
            env.score_frames = json.loads(str(saved["score_frames"]))
            meta = json.loads(str(saved["metadata"]))
        for key, value in meta.pop("scorer").items():
            if key == "latest":
                value = {k: Observation(**v) for k, v in value.items()}
            setattr(env.scorer, key, value)
        for key, value in meta.items():
            if key in {"contact_cubes", "unintended_contacts", "fixture_contacts"}:
                value = set(value)
            elif key == "neighbor_contacts":
                value = {tuple(pair) for pair in value}
            setattr(env, key, value)
        # mj_forward updates derived coordinates. Preserve the saved integration
        # fields (including solver warm-start state) for the next actual step.
        state = np.empty(mujoco.mj_stateSize(env.model, STATE_SPEC))
        mujoco.mj_getState(env.model, env.data, state, STATE_SPEC)
        mujoco.mj_forward(env.model, env.data)
        mujoco.mj_setState(env.model, env.data, state, STATE_SPEC)
        return env
