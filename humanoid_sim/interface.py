"""Versioned, paused-time policy interface. Run with python -m humanoid_sim.interface."""
import argparse
import copy
import json
import math
from pathlib import Path
import sys

import mujoco
import numpy as np

from .environment import Environment

VERSION = 'humanoid-actions-v2'
INSTRUCTION_VERSION = 1


def number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be a finite number in [{low}, {high}]')
    return float(value)


def vector(value, size, name):
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f'{name} must contain {size} numbers')
    return np.array([number(v, name, -1e6, 1e6) for v in value])


def rotation_from_quaternion(value):
    quat = vector(value, 4, 'quaternion_wxyz')
    if abs(np.linalg.norm(quat)-1) > 1e-6:
        raise ValueError('quaternion_wxyz must have unit norm within 1e-6')
    matrix = np.empty(9)
    mujoco.mju_quat2Mat(matrix, quat / np.linalg.norm(quat))
    return matrix.reshape(3, 3)


def quaternion(matrix):
    result = np.empty(4)
    mujoco.mju_mat2Quat(result, np.asarray(matrix).reshape(9))
    return result.tolist()


class PolicyInterface:
    def __init__(self, env, mode='exact_state'):
        if mode not in ('exact_state', 'robot_state'):
            raise ValueError('mode must be exact_state or robot_state')
        self.env, self.mode = env, mode
        model = env.model
        root = int(model.jnt_bodyid[env.arm_joints[0]])
        self.moving_bodies = set()
        for body in range(1, model.nbody):
            ancestor = body
            while ancestor and ancestor != root:
                ancestor = int(model.body_parentid[ancestor])
            if ancestor == root:
                self.moving_bodies.add(body)

    def observe(self):
        env = self.env
        mujoco.mj_forward(env.model, env.data)
        joint_ids = env.model.actuator_trnid[:, 0]
        contacts = set()
        # Binary contact readings reveal only which moving robot links touch something.
        for c in env.data.contact:
            if c.dist <= .0005:
                for geom in (c.geom1, c.geom2):
                    body = int(env.model.geom_bodyid[geom])
                    if body in self.moving_bodies:
                        contacts.add(env.model.body(body).name)
        result = {
            'schema_version': VERSION, 'instruction_version': INSTRUCTION_VERSION,
            'mode': self.mode, 'time_s': float(env.data.time),
            'frame': 'world', 'supported_body': True,
            'robot': {
                'joint_names': [env.model.joint(int(j)).name for j in joint_ids],
                'joint_position_rad': env.data.qpos[env.model.jnt_qposadr[joint_ids]].tolist(),
                'joint_velocity_rad_s': env.data.qvel[env.model.jnt_dofadr[joint_ids]].tolist(),
                'hand_xyz_m': env.data.site_xpos[env.site].tolist(),
                'hand_quaternion_wxyz': quaternion(env.data.site_xmat[env.site]),
                'contact_links': sorted(contacts),
            },
        }
        if self.mode == 'exact_state':
            result['task_state'] = env.observe()
        return result

    def preflight(self, target):
        """Sample the commanded joint path; do not advance or alter live physics.

        Fingers and all other non-arm joints stay at their measured positions.
        Object contacts are excluded. This is a kinematic safeguard, not a
        guarantee about dynamic tracking, carried objects, or between-sample motion.
        """
        env = self.env
        scratch = mujoco.MjData(env.model)
        scratch.qpos[:] = env.data.qpos
        actual = env.data.qpos[env.arm_q].copy()
        arm_target = target[env.arm_a]
        # Predict a kinematic path from measured joints. A commanded start pose
        # can differ under load and create collisions the physical robot never has.
        # This remains an approximation to actuator tracking, not a dynamic rollout.
        configurations = [actual + (arm_target-actual)*t*t*(3-2*t)
                          for t in np.linspace(0, 1, 101)]
        for pose in configurations:
            scratch.qpos[env.arm_q] = pose
            mujoco.mj_forward(env.model, scratch)
            for c in scratch.contact:
                if env.object_geom in (c.geom1, c.geom2):
                    continue
                bodies = {int(env.model.geom_bodyid[g]) for g in (c.geom1, c.geom2)}
                if bodies & self.moving_bodies and c.dist < -.002:
                    raise ValueError('Commanded joint path predicts robot/environment penetration over 2 mm')

    def execute(self, request):
        env = self.env
        start = float(env.data.time)
        response = {'schema_version': VERSION, 'request_id': None,
                    'status': 'rejected', 'start_time_s': start}
        try:
            if not isinstance(request, dict):
                raise ValueError('Request must be a JSON object')
            if set(request) != {'schema_version', 'instruction_version', 'request_id', 'action', 'arguments'}:
                raise ValueError('Request fields must match the versioned schema exactly')
            request_id = request['request_id']
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise ValueError('request_id must be a string of 1–128 characters')
            response['request_id'] = request_id
            if any(e.get('interface_response', {}).get('request_id') == request_id for e in env.events):
                raise ValueError('Duplicate request_id; actions are never implicitly retried')
            if request['schema_version'] != VERSION:
                raise ValueError('Unsupported schema_version')
            if type(request['instruction_version']) is not int or request['instruction_version'] != INSTRUCTION_VERSION:
                raise ValueError('Stale or unsupported instruction_version')
            action, args = request['action'], request['arguments']
            if not isinstance(action, str) or action not in ('move', 'hand', 'hold') or not isinstance(args, dict):
                raise ValueError('Expected move, hand, or hold and an arguments object')
            fields = {'move': {'xyz_m', 'quaternion_wxyz', 'seconds'},
                      'hand': {'closure', 'seconds'}, 'hold': {'seconds'}}[action]
            if set(args) != fields:
                raise ValueError(f'Arguments must be exactly {sorted(fields)}')
            seconds = number(args['seconds'], 'seconds', .02, 10)
            target = env.data.ctrl.copy()
            if action == 'move':
                xyz = vector(args['xyz_m'], 3, 'xyz_m')
                rotation = rotation_from_quaternion(args['quaternion_wxyz'])
                target[env.arm_a] = env.solve(xyz, rotation)
            elif action == 'hand':
                target[env.hand_a] = env.hand_targets(number(args['closure'], 'closure', 0, 1))
            self.preflight(target)
            env.advance(target, seconds)
            response['status'] = 'completed'
        except ValueError as exc:
            response['error'] = str(exc)
        except RuntimeError as exc:
            response['status'] = 'failed'
            response['error'] = str(exc)
        response['end_time_s'] = float(env.data.time)
        response['observation'] = self.observe()
        try:
            json.dumps(request, allow_nan=False)
            archived_request = copy.deepcopy(request)
        except (ValueError, TypeError):
            archived_request = {'invalid_python_request': repr(request)}
        env.events.append({'interface_request': archived_request, 'interface_response': copy.deepcopy(response),
                           'score': env.scorer.report()})
        return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', type=Path, required=True)
    parser.add_argument('--mode', choices=['exact_state', 'robot_state'], default='exact_state')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('observe')
    action = commands.add_parser('act')
    action.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    try:
        env = Environment()
        env.load(args.episode)
        interface = PolicyInterface(env, args.mode)
        if args.command == 'observe':
            result = interface.observe()
        else:
            if (args.episode/'report.json').exists():
                raise ValueError('Completed baseline trials are immutable; start a new episode with reset')
            raw = args.request.read_text()
            try:
                def invalid_constant(value):
                    raise ValueError(f'Nonfinite JSON constant: {value}')
                def unique_pairs(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError(f'Duplicate JSON field: {key}')
                        result[key] = value
                    return result
                request = json.loads(raw, parse_constant=invalid_constant, object_pairs_hook=unique_pairs)
            except ValueError as exc:
                # Preserve malformed attempts privately without advancing physics.
                env.events.append({'invalid_interface_json': raw, 'error': str(exc)})
                env.save(args.episode)
                raise
            result = interface.execute(request)
            env.save(args.episode)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result.get('status', 'completed') == 'completed' else 1
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
