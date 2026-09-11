"""Supported G1 actuated manipulation. Ground truth is for baseline development."""
import hashlib
import json
import math
from pathlib import Path

import mujoco
import numpy as np

from .scene import SCENE, TABLE_Z, BASKET
from .scoring import Scorer

# Local hand X points down; finger flexion is toward world -X.
DOWNWARD = np.array([[0., -1., 0.], [0., 0., 1.], [-1., 0., 0.]])
ARM_NAMES = [f'right_{name}_joint' for name in ('shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow', 'wrist_roll', 'wrist_pitch', 'wrist_yaw')]
HAND_NAMES = [f'right_hand_{name}_joint' for name in ('thumb_0', 'thumb_1', 'thumb_2', 'index_0', 'index_1', 'middle_0', 'middle_1')]


def configure_camera(camera):
    camera.lookat[:] = [.18, -.12, .78]
    camera.distance = 1.9
    camera.azimuth = 135
    camera.elevation = -23


class Environment:
    def __init__(self):
        self.model = mujoco.MjModel.from_xml_path(str(SCENE))
        self.data = mujoco.MjData(self.model)
        self.site = self.model.site('right_grasp').id
        self.object_id = self.model.body('red_block').id
        self.object_geom = self.model.geom('object').id
        self.arm_joints = np.array([self.model.joint(n).id for n in ARM_NAMES])
        self.arm_q = self.model.jnt_qposadr[self.arm_joints]
        self.arm_v = self.model.jnt_dofadr[self.arm_joints]
        self.arm_a = np.array([self.model.actuator(n).id for n in ARM_NAMES])
        self.hand_a = np.array([self.model.actuator(n).id for n in HAND_NAMES])
        self.act_q = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.frames, self.frame_times, self.events = [], [], []
        self.on_frame = None
        self.reset()

    def reset(self, seed=0, randomize=False):
        mujoco.mj_resetData(self.model, self.data)
        for side in ['left', 'right']:
            for name, val in [('shoulder_pitch', .2), ('shoulder_roll', .2 if side == 'left' else -.2), ('elbow', 1.28)]:
                self.data.qpos[self.model.joint(f'{side}_{name}_joint').qposadr] = val
        self.data.ctrl[:] = self.data.qpos[self.act_q]
        self.data.ctrl[self.hand_a] = self.hand_targets(0)
        self.data.qpos[self.act_q] = self.data.ctrl
        rng = np.random.default_rng(seed)
        q = self.model.joint('object_free').qposadr[0]
        if randomize:
            self.data.qpos[q:q+2] += rng.uniform(-.015, .015, 2)
            angle = rng.uniform(-.15, .15)
            self.data.qpos[q+3:q+7] = [math.cos(angle/2), 0, 0, math.sin(angle/2)]
        self.data.qpos[self.arm_q] = self.solve([.24, -.18, .94])
        self.data.ctrl[:] = self.data.qpos[self.act_q]
        self.seed, self.randomized = seed, randomize
        self.frames, self.frame_times, self.events = [], [], []
        self.scorer = Scorer(self.model)
        mujoco.mj_forward(self.model, self.data)
        self._frame()
        self.advance(self.data.ctrl.copy(), .5)
        return self.observe()

    def hand_targets(self, closure):
        return np.array([0, -.1, -.1, 0, 0, 0, 0]) * (1-closure) + np.array([0, -.7, -.8, 1.15, 1.2, 1.15, 1.2]) * closure

    def _frame(self):
        self.frames.append(self.data.qpos.copy())
        self.frame_times.append(float(self.data.time))
        if self.on_frame:
            self.on_frame()

    def advance(self, target, seconds):
        if not math.isfinite(seconds) or not .02 <= seconds <= 10:
            raise ValueError('Duration must be finite and between .02 and 10 seconds')
        if target.shape != (self.model.nu,) or not np.isfinite(target).all():
            raise ValueError('Invalid actuator target')
        if np.any(target < self.model.actuator_ctrlrange[:, 0]) or np.any(target > self.model.actuator_ctrlrange[:, 1]):
            raise ValueError('Actuator target outside limits')
        start = self.data.ctrl.copy()
        steps = math.ceil(seconds / self.model.opt.timestep)
        for i in range(steps):
            t = min(1., (i+1)/(steps*.8))
            self.data.ctrl[:] = start + (target-start)*t*t*(3-2*t)
            mujoco.mj_step(self.model, self.data)
            self.scorer.update(self.data)
            if not np.isfinite(self.data.qpos).all():
                raise RuntimeError('Nonfinite physics state')
            if (i+1) % round(1/(30*self.model.opt.timestep)) == 0 or i == steps-1:
                self._frame()
        mujoco.mj_forward(self.model, self.data)

    def solve(self, xyz, rotation=DOWNWARD):
        xyz = np.asarray(xyz, dtype=float)
        if xyz.shape != (3,) or not np.isfinite(xyz).all():
            raise ValueError('Expected finite XYZ')
        if not (.15 <= xyz[0] <= .55 and -.6 <= xyz[1] <= -.05 and .60 <= xyz[2] <= 1.15):
            raise ValueError('Pose outside supported development workspace')
        scratch = mujoco.MjData(self.model)
        scratch.qpos[:] = self.data.qpos
        scratch.qpos[self.arm_q] = [-1, -.7, 1.3, .8, .05, .16, 1.1]
        jp, jr = np.zeros((3,self.model.nv)), np.zeros((3,self.model.nv))
        for _ in range(350):
            mujoco.mj_forward(self.model, scratch)
            current = scratch.site_xmat[self.site].reshape(3,3)
            dp = xyz - scratch.site_xpos[self.site]
            dr = .5 * sum((np.cross(current[:,i], rotation[:,i]) for i in range(3)))
            if np.linalg.norm(dp) < .0005 and np.linalg.norm(dr) < .005 and np.trace(rotation.T@current) > 2.99:
                return scratch.qpos[self.arm_q].copy()
            mujoco.mj_jacSite(self.model, scratch, jp, jr, self.site)
            jac = np.vstack([jp[:,self.arm_v], .2*jr[:,self.arm_v]])
            delta = jac.T @ np.linalg.solve(jac@jac.T + .0001*np.eye(6), np.r_[dp, .2*dr])
            scratch.qpos[self.arm_q] = np.clip(scratch.qpos[self.arm_q] + np.clip(delta,-.15,.15), self.model.jnt_range[self.arm_joints,0], self.model.jnt_range[self.arm_joints,1])
        raise ValueError(f'Unreachable hand pose {xyz.tolist()}: residual {np.linalg.norm(dp):.4f} m')

    def move(self, xyz, seconds=2):
        target = self.data.ctrl.copy()
        target[self.arm_a] = self.solve(xyz)
        self.advance(target, seconds)
        return self.event('move', {'xyz':list(xyz),'seconds':seconds})

    def hand(self, closure, seconds=2):
        if not math.isfinite(closure) or not 0 <= closure <= 1:
            raise ValueError('Hand closure must be in [0,1]')
        target = self.data.ctrl.copy()
        target[self.hand_a] = self.hand_targets(closure)
        self.advance(target, seconds)
        return self.event('hand', {'closure':closure,'seconds':seconds})

    def hold(self, seconds=2):
        self.advance(self.data.ctrl.copy(), seconds)
        return self.event('hold', {'seconds':seconds})

    def observe(self):
        mujoco.mj_forward(self.model,self.data)
        contacts = set()
        for c in self.data.contact:
            if c.dist > .0005:
                continue
            if c.geom1 == self.object_geom: other=c.geom2
            elif c.geom2 == self.object_geom: other=c.geom1
            else: continue
            contacts.add(self.model.body(int(self.model.geom_bodyid[other])).name or self.model.geom(other).name or 'world')
        p = self.data.xpos[self.object_id]
        ext = np.abs(self.data.xmat[self.object_id].reshape(3,3)) @ self.model.geom_size[self.object_geom]
        return {'time_s':float(self.data.time), 'object_xyz':p.tolist(), 'object_bottom':float(p[2]-ext[2]), 'hand_xyz':self.data.site_xpos[self.site].tolist(), 'object_contacts':sorted(contacts), 'basket_xyz':[ *BASKET,TABLE_Z], 'supported_body':True}

    def event(self, action, args):
        result={'action':action,'arguments':args,'observation':self.observe()}
        self.events.append(result)
        return result

    def save(self, folder):
        folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
        spec=mujoco.mjtState.mjSTATE_INTEGRATION
        state=np.empty(mujoco.mj_stateSize(self.model,spec))
        mujoco.mj_getState(self.model,self.data,state,spec)
        np.savez_compressed(folder/'episode.npz', state=state, qpos=np.array(self.frames), time=np.array(self.frame_times))
        (folder/'events.json').write_text(json.dumps(self.events,indent=2)+'\n')
        metadata = {'scene_sha256': hashlib.sha256(SCENE.read_bytes()).hexdigest(),
                    'seed': self.seed, 'randomized': self.randomized,
                    'scorer': {k: v for k, v in vars(self.scorer).items() if k != 'model'}}
        (folder/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')

    def load(self, folder):
        metadata = json.loads((Path(folder)/'metadata.json').read_text())
        if metadata['scene_sha256'] != hashlib.sha256(SCENE.read_bytes()).hexdigest():
            raise ValueError('Saved episode scene differs from current scene; replay requires its original scene')
        self.seed, self.randomized = metadata['seed'], metadata['randomized']
        for key, value in metadata['scorer'].items():
            if key in vars(self.scorer) and key != 'model':
                setattr(self.scorer, key, value)
        with np.load(Path(folder)/'episode.npz',allow_pickle=False) as saved:
            mujoco.mj_setState(self.model,self.data,saved['state'],mujoco.mjtState.mjSTATE_INTEGRATION)
            self.frames=list(saved['qpos']); self.frame_times=list(saved['time'])
        self.events=json.loads((Path(folder)/'events.json').read_text())
        mujoco.mj_forward(self.model,self.data)
