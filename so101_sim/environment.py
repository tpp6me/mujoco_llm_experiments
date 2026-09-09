"""Physics-backed SO101 actions; all distances are metres and angles radians."""

import json
import math
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "scenes" / "so101_pick.xml"
STATE_SPEC = mujoco.mjtState.mjSTATE_INTEGRATION
# Tool-frame X points down, with the jaws closing along world Y.
DOWNWARD = np.array([[0.0, -1, 0], [0, 0, 1], [-1, 0, 0]])


class Environment:
    def __init__(self):
        self.model = mujoco.MjModel.from_xml_path(str(SCENE))
        # Use a gentle gripper torque limit; keep the upstream arm limits.
        self.model.actuator_forcerange[5] = [-0.35, 0.35]
        self.data = mujoco.MjData(self.model)
        self.tool_id = self.model.site("gripperframe").id
        self.cube_id = self.model.geom("red_cube").id
        self.frames = []
        self.frame_times = []
        self.events = []
        self.on_frame = None
        mujoco.mj_forward(self.model, self.data)

    def reset(self, x=0.22, y=0.0):
        if not np.isfinite([x, y]).all() or not (0.15 <= x <= 0.28 and abs(y) <= 0.08):
            raise ValueError("Cube reset requires x in [0.15, 0.28] and y in [-0.08, 0.08]")
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[6:8] = [x, y]
        self.frames.clear()
        self.frame_times.clear()
        self.events.clear()
        self._frame()
        self._advance(self.data.ctrl.copy(), 0.3)
        return self._event("reset", {"x": x, "y": y})

    def _frame(self):
        self.frames.append(self.data.qpos.copy())
        self.frame_times.append(float(self.data.time))
        if self.on_frame is not None:
            self.on_frame()

    def _advance(self, target, seconds):
        if not math.isfinite(seconds) or not 0.1 <= seconds <= 10:
            raise ValueError("Action duration must be between 0.1 and 10 seconds")
        initial = self.data.ctrl.copy()
        steps = math.ceil(seconds / self.model.opt.timestep)
        every = max(1, round(1 / (30 * self.model.opt.timestep)))
        for i in range(steps):
            t = min(1.0, (i + 1) / (steps * 0.8))
            blend = t * t * (3 - 2 * t)
            self.data.ctrl[:] = initial + blend * (target - initial)
            mujoco.mj_step(self.model, self.data)
            if not np.isfinite(self.data.qpos).all():
                raise RuntimeError("Simulation produced nonfinite joint positions")
            if (i + 1) % every == 0 or i == steps - 1:
                self._frame()
        mujoco.mj_forward(self.model, self.data)

    def observe(self):
        mujoco.mj_forward(self.model, self.data)
        cube = self.data.body("red_cube").xpos.copy()
        bodies = set()
        for contact in self.data.contact:
            if contact.dist > 0:
                continue
            if contact.geom1 == self.cube_id:
                other = contact.geom2
            elif contact.geom2 == self.cube_id:
                other = contact.geom1
            else:
                continue
            bodies.add(self.model.body(int(self.model.geom_bodyid[other])).name)
        both_jaws = {"gripper", "moving_jaw_so101_v1"}.issubset(bodies)
        # Bounding height also accounts for a rotated cube.
        rotation = self.data.body("red_cube").xmat.reshape(3, 3)
        bottom = float(cube[2] - 0.015 * np.abs(rotation[2]).sum())
        return {
            "time_s": round(float(self.data.time), 4),
            "cube_xyz_m": cube.tolist(),
            "cube_bottom_m": bottom,
            "tool_xyz_m": self.data.site_xpos[self.tool_id].tolist(),
            "joint_positions_rad": dict(zip(
                [self.model.joint(i).name for i in range(6)],
                self.data.qpos[:6].tolist(), strict=True)),
            "cube_contact_bodies": sorted(bodies),
            "both_jaws_contact": both_jaws,
            "lifted_and_held": bool(both_jaws and bottom > 0.04 and "world" not in bodies),
        }

    def _event(self, action, arguments, **extra):
        event = {"action": action, "arguments": arguments, **extra, "observation": self.observe()}
        self.events.append(event)
        return event

    def solve_downward(self, xyz):
        """Damped least squares on a scratch state; never move the live robot here."""
        xyz = np.asarray(xyz, dtype=float)
        if xyz.shape != (3,) or not np.isfinite(xyz).all():
            raise ValueError("Target must contain three finite coordinates")
        if not (0.10 <= xyz[0] <= 0.35 and abs(xyz[1]) <= 0.15 and 0.018 <= xyz[2] <= 0.20):
            raise ValueError("Target is outside the supported tabletop workspace")
        scratch = mujoco.MjData(self.model)
        jp = np.zeros((3, self.model.nv))
        jr = np.zeros_like(jp)
        best = float("inf")
        seeds = [self.data.qpos[:5].copy(), np.array([0, 0, 0.47, 1.17, 1.58])]
        for seed in seeds:
            scratch.qpos[:5] = seed
            for _ in range(250):
                mujoco.mj_forward(self.model, scratch)
                current = scratch.site_xmat[self.tool_id].reshape(3, 3)
                rotation_error = DOWNWARD @ current.T
                quat = np.zeros(4)
                mujoco.mju_mat2Quat(quat, rotation_error.ravel())
                angular_error = np.zeros(3)
                mujoco.mju_quat2Vel(angular_error, quat, 1.0)
                position_error = xyz - scratch.site_xpos[self.tool_id]
                best = min(best, float(np.linalg.norm(position_error)))
                if np.linalg.norm(position_error) < 0.0001 and np.linalg.norm(angular_error) < 0.002:
                    return scratch.qpos[:5].copy()
                error = np.r_[position_error, 0.1 * angular_error]
                mujoco.mj_jacSite(self.model, scratch, jp, jr, self.tool_id)
                jac = np.vstack([jp[:, :5], 0.1 * jr[:, :5]])
                delta = jac.T @ np.linalg.solve(jac @ jac.T + 1e-5 * np.eye(6), error)
                scratch.qpos[:5] = np.clip(
                    scratch.qpos[:5] + np.clip(delta, -0.15, 0.15),
                    self.model.jnt_range[:5, 0], self.model.jnt_range[:5, 1])
        raise ValueError(f"No downward pose within joint limits for {xyz.tolist()} (best position error {best:.4f}m)")

    def move(self, xyz, seconds=2.0):
        target = self.data.ctrl.copy()
        target[:5] = self.solve_downward(xyz)
        self._advance(target, seconds)
        return self._event("move", {"xyz_m": list(xyz), "seconds": seconds},
                           position_error_m=float(np.linalg.norm(np.asarray(xyz) - self.data.site_xpos[self.tool_id])))

    def gripper(self, opening, seconds=3.0):
        if not math.isfinite(opening) or not 0 <= opening <= 1:
            raise ValueError("Gripper opening must be in [0, 1]")
        target = self.data.ctrl.copy()
        target[5] = opening  # 0 to 1 radians, within the upstream joint limits.
        self._advance(target, seconds)
        return self._event("gripper", {"opening": opening, "seconds": seconds})

    def hold(self, seconds=3.0):
        start = self.data.body("red_cube").xpos.copy()
        samples = []
        previous = self.on_frame

        def sample():
            samples.append(self.observe())
            if previous:
                previous()

        self.on_frame = sample
        try:
            self._advance(self.data.ctrl.copy(), seconds)
        finally:
            self.on_frame = previous
        return self._event("hold", {"seconds": seconds},
                           held_throughout=bool(samples and all(s["lifted_and_held"] for s in samples)),
                           cube_drift_m=float(np.linalg.norm(self.data.body("red_cube").xpos - start)))

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = np.empty(mujoco.mj_stateSize(self.model, STATE_SPEC))
        mujoco.mj_getState(self.model, self.data, state, STATE_SPEC)
        temporary = path.with_suffix(".tmp")
        with temporary.open("wb") as file:
            np.savez_compressed(file, state=state, frames=np.array(self.frames),
                                times=np.array(self.frame_times), events=json.dumps(self.events))
        temporary.replace(path)
        path.with_suffix(".json").write_text(json.dumps(self.events, indent=2) + "\n")

    def load(self, path):
        with np.load(path, allow_pickle=False) as saved:
            mujoco.mj_setState(self.model, self.data, saved["state"], STATE_SPEC)
            self.frames = list(saved["frames"])
            self.frame_times = list(saved["times"])
            self.events = json.loads(str(saved["events"]))
        mujoco.mj_forward(self.model, self.data)

    def snapshot(self, path):
        from PIL import Image

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        camera = mujoco.MjvCamera()
        configure_camera(camera)
        mujoco.mj_forward(self.model, self.data)
        with mujoco.Renderer(self.model, height=720, width=960) as renderer:
            renderer.update_scene(self.data, camera=camera)
            Image.fromarray(renderer.render()).save(path)
        return str(path)


def configure_camera(camera):
    camera.lookat[:] = [0.16, 0, 0.12]
    camera.distance = 0.65
    camera.azimuth = 135
    camera.elevation = -25
