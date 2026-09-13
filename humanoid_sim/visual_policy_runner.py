"""Bounded provider-neutral offline RGB-to-action visual policy runner.

Advance the original experiment toward an LLM choosing manipulation actions from
RGB and proprioception. This is scaffolding and offline execution with an injected
stub/callable, not a live model experiment or successful manipulation claim.
"""
import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import time

from .environment import Environment
from .interface import PolicyInterface, VERSION, INSTRUCTION_VERSION
from .visual import VisualSession, RGBRenderer, state_key, calibration
from .scene import ROOT

MAX_CALLS = 20
DEADLINE = 25.0
PROTOCOL_ID = 'humanoid-visual-policy-scaffold-v1'

VISUAL_PROMPT = """Control a supported G1 humanoid in a MuJoCo simulation using visual observations and robot proprioception.
Pick the red block from the table and place it fully inside the basket, release it, withdraw the hand at least 0.12 m from the object, and let it settle for at least 2 seconds.
Choose ONE primitive per response using the supplied action schema. No automatic pickup skill exists. You choose approach, grasp, lift, transport, release, and withdrawal.
Use current visual observations, robot proprioception, and previous public action outcomes to close the loop.
No ground-truth object coordinates, basket coordinates, or oracle score feedback are provided.
Physics pauses while you think; only action durations consume simulated time.
The entire episode must finish by simulated t=25 s including reset. At most 20 actions are allowed.
A rejected action ends the episode without retry. Do not request an action that exceeds the remaining time. Hold is an explicit action.
All poses use world metres, Z up; joint readings use radians. move targets the right grasp-site pose; orientation is a unit quaternion in w,x,y,z order mapping site-local axes into world coordinates.
The downward orientation is [0.5, -0.5, 0.5, 0.5]; local hand X then points down and finger flexion is toward world -X. The site is a hand reference, not an automatic object grasp or centering operation.
Hand closure 0 opens and 1 closes the coordinated three fingers.
Actions take 0.02 to 10 s. Motion interpolation and force-limited physical contacts control the arm; completed means execution, not exact tracking or task success.
Workspace input bounds: X [0.15, 0.55], Y [-0.60, -0.05], Z [0.60, 1.15]. Some poses inside these bounds are unreachable or rejected by the sampled collision guard.
Robot pelvis is fixed; do not walk. The arm starts in an overhead ready pose.
Static task geometry: table top z=0.70; block dimensions 0.05 x 0.07 x 0.12 m, mass 0.06 kg; basket floor top z=0.712, rim top z=0.84, interior 0.17 x 0.17 m.
The block must be lifted at least 0.04 m above the table with hand contact for 0.2 s, then fully contained, on the basket floor, without hand contact, nearly stationary for 2 s.
Keep contact gentle. The private evaluator measures maximum object penetration.
Return only the structured action. Do not claim success in prose."""


class VisualPolicyError(Exception):
    """Base exception for visual policy runner."""
    pass


class ModelRefusalError(VisualPolicyError):
    """Raised when the model callable refuses to act."""
    pass


class MalformedResponseError(VisualPolicyError):
    """Raised when the model response cannot be parsed or violates schema."""
    pass


def strict_json(text):
    """Strict JSON parser rejecting duplicates and nonfinite constants."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON field: {key}')
            result[key] = value
        return result

    def constant(val):
        raise ValueError(f'Nonfinite JSON constant: {val}')

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def write_json(path, value):
    """Atomically write formatted JSON without NaN/Infinity."""
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def action_schema():
    """Action schema formatted for structured output."""
    schema_path = ROOT / 'experiments/humanoid-pick-place/schemas/action-v2.schema.json'
    schema = json.loads(schema_path.read_text())
    variants = []
    for branch in schema['oneOf']:
        props = {
            'action': {'type': 'string', **branch['properties']['action']},
            'arguments': branch['properties']['arguments']
        }
        variants.append({
            'type': 'object',
            'properties': props,
            'required': list(props),
            'additionalProperties': False
        })
    return {
        'type': 'object',
        'properties': {'command': {'anyOf': variants}},
        'required': ['command'],
        'additionalProperties': False
    }


def _validate_finite_float(val, name):
    if not isinstance(val, (int, float)) or not math.isfinite(val):
        raise ValueError(f'{name} must be a finite float, got {val!r}')
    return float(val)


def _validate_float_list(lst, size, name):
    if not isinstance(lst, (list, tuple)) or len(lst) != size:
        raise ValueError(f'{name} must be a list of {size} numbers')
    return [_validate_finite_float(v, f'{name}[{i}]') for i, v in enumerate(lst)]


def allowlist_camera(cam):
    """Allowlist extraction for camera calibration data."""
    if not isinstance(cam, dict):
        raise ValueError('camera must be a dictionary')
    return {
        'width': int(cam['width']),
        'height': int(cam['height']),
        'projection': str(cam['projection']),
        'camera_world_xyz_m': _validate_float_list(cam['camera_world_xyz_m'], 3, 'camera_world_xyz_m'),
        'world_to_camera_rotation': [
            _validate_float_list(row, 3, f'world_to_camera_rotation[{i}]')
            for i, row in enumerate(cam['world_to_camera_rotation'])
        ],
        'focal_xy_px': _validate_float_list(cam['focal_xy_px'], 2, 'focal_xy_px'),
        'principal_xy_px': _validate_float_list(cam['principal_xy_px'], 2, 'principal_xy_px'),
        'axes': str(cam['axes'])
    }


def allowlist_robot(robot):
    """Allowlist extraction for robot joint and hand proprioception."""
    if not isinstance(robot, dict):
        raise ValueError('robot must be a dictionary')
    joint_names = [str(n) for n in robot['joint_names']]
    num_joints = len(joint_names)
    return {
        'joint_names': joint_names,
        'joint_position_rad': _validate_float_list(robot['joint_position_rad'], num_joints, 'joint_position_rad'),
        'joint_velocity_rad_s': _validate_float_list(robot['joint_velocity_rad_s'], num_joints, 'joint_velocity_rad_s'),
        'hand_xyz_m': _validate_float_list(robot['hand_xyz_m'], 3, 'hand_xyz_m'),
        'hand_quaternion_wxyz': _validate_float_list(robot['hand_quaternion_wxyz'], 4, 'hand_quaternion_wxyz'),
        'contact_links': sorted([str(c) for c in robot.get('contact_links', [])])
    }


def allowlist_robot_state(rs):
    """Allowlist extraction for public robot state."""
    if not isinstance(rs, dict):
        raise ValueError('robot_state must be a dictionary')
    return {
        'schema_version': str(rs.get('schema_version', VERSION)),
        'instruction_version': int(rs.get('instruction_version', INSTRUCTION_VERSION)),
        'mode': 'robot_state',
        'time_s': _validate_finite_float(rs['time_s'], 'time_s'),
        'frame': 'world',
        'supported_body': bool(rs.get('supported_body', True)),
        'robot': allowlist_robot(rs['robot'])
    }


def allowlist_observation(obs):
    """Strict allowlist extractor for public visual observations."""
    if not isinstance(obs, dict):
        raise ValueError('observation must be a dictionary')
    b64_png = str(obs['rgb_png_base64'])
    raw_bytes = base64.b64decode(b64_png)
    image_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return {
        'schema_version': str(obs.get('schema_version', 'humanoid-visual-v1')),
        'observation_id': str(obs['observation_id']),
        'time_s': _validate_finite_float(obs['time_s'], 'time_s'),
        'camera': allowlist_camera(obs['camera']),
        'robot_state': allowlist_robot_state(obs['robot_state']),
        'rgb_png_base64': b64_png,
        'rgb_sha256': image_sha256
    }


def sanitize_action_for_history(action_req):
    """Allowlist extraction for public action command in history."""
    if not isinstance(action_req, dict):
        return {'action': 'invalid', 'arguments': {}, 'request_id': 'unknown'}
    action = str(action_req.get('action'))
    args = action_req.get('arguments', {})
    sanitized_args = {}
    if action == 'move':
        sanitized_args = {
            'xyz_m': _validate_float_list(args.get('xyz_m', []), 3, 'xyz_m'),
            'quaternion_wxyz': _validate_float_list(args.get('quaternion_wxyz', []), 4, 'quaternion_wxyz'),
            'seconds': _validate_finite_float(args.get('seconds', 0), 'seconds')
        }
    elif action == 'hand':
        sanitized_args = {
            'closure': _validate_finite_float(args.get('closure', 0), 'closure'),
            'seconds': _validate_finite_float(args.get('seconds', 0), 'seconds')
        }
    elif action == 'hold':
        sanitized_args = {
            'seconds': _validate_finite_float(args.get('seconds', 0), 'seconds')
        }
    return {
        'action': action,
        'arguments': sanitized_args,
        'request_id': str(action_req.get('request_id', ''))
    }


def sanitize_response_for_history(response):
    """Allowlist extraction for action execution outcomes in history."""
    if not isinstance(response, dict):
        return {'status': 'invalid', 'error': 'Invalid response type'}
    sanitized = {
        'request_id': str(response.get('request_id', '')),
        'status': str(response.get('status', 'unknown')),
        'start_time_s': _validate_finite_float(response.get('start_time_s', 0.0), 'start_time_s'),
        'end_time_s': _validate_finite_float(response.get('end_time_s', 0.0), 'end_time_s')
    }
    if 'error' in response and response['error'] is not None:
        sanitized['error'] = str(response['error'])
    if 'observation' in response and isinstance(response['observation'], dict):
        sanitized['robot_state'] = allowlist_robot_state(response['observation'])
    return sanitized


def build_public_payload(observation, history, deadline=DEADLINE, max_calls=MAX_CALLS, calls=0, max_history=20):
    """Build the public request payload strictly from allowlist."""
    obs_clean = allowlist_observation(observation)
    time_s = obs_clean['time_s']
    remaining_time = max(0.0, float(deadline - time_s))
    remaining_actions = max(0, int(max_calls - calls))
    history_slice = history[-max_history:] if max_history > 0 else []
    sanitized_history = [
        {
            'action': sanitize_action_for_history(h.get('action')),
            'response': sanitize_response_for_history(h.get('response'))
        }
        for h in history_slice
    ]
    payload = {
        'instruction': VISUAL_PROMPT,
        'instruction_version': INSTRUCTION_VERSION,
        'action_schema': action_schema(),
        'remaining_time_s': remaining_time,
        'remaining_actions': remaining_actions,
        'observation': obs_clean,
        'history': sanitized_history
    }
    json.dumps(payload, allow_nan=False)
    return payload


def parse_and_validate_response(raw):
    """Parse and validate model response into a single valid primitive command."""
    if isinstance(raw, str):
        try:
            parsed = strict_json(raw)
        except ValueError as exc:
            raise MalformedResponseError(f'Invalid JSON in model response: {exc}')
    elif isinstance(raw, dict):
        parsed = raw
    else:
        raise MalformedResponseError(f'Model response must be JSON string or dict, got {type(raw).__name__}')

    # Check for refusal
    if isinstance(parsed, dict):
        if 'refusal' in parsed and parsed['refusal']:
            raise ModelRefusalError(f'Model refused: {parsed["refusal"]}')
        if parsed.get('status') == 'refusal':
            raise ModelRefusalError(f'Model status is refusal: {parsed.get("error", "refusal")}')
        for item in parsed.get('output', []):
            if isinstance(item, dict) and item.get('type') == 'message':
                for c in item.get('content', []):
                    if isinstance(c, dict) and c.get('type') == 'refusal':
                        raise ModelRefusalError(f'Model refusal: {c.get("refusal")}')

    # Extract command
    if isinstance(parsed, dict) and 'command' in parsed:
        command = parsed['command']
    elif isinstance(parsed, dict) and 'action' in parsed and 'arguments' in parsed:
        command = parsed
    elif isinstance(parsed, dict) and 'output' in parsed:
        content = [
            c for item in parsed.get('output', [])
            if isinstance(item, dict) and item.get('type') == 'message'
            for c in item.get('content', [])
            if isinstance(c, dict)
        ]
        text_parts = [c['text'] for c in content if c.get('type') == 'output_text']
        if not text_parts:
            raise MalformedResponseError('No output text in response message')
        try:
            decision = strict_json(''.join(text_parts))
            if not isinstance(decision, dict) or 'command' not in decision:
                raise MalformedResponseError('Expected command wrapper in output text')
            command = decision['command']
        except ValueError as exc:
            raise MalformedResponseError(f'Failed to parse output text JSON: {exc}')
    else:
        raise MalformedResponseError('Response did not contain a valid command structure')

    if not isinstance(command, dict):
        raise MalformedResponseError('command must be an object')
    if set(command.keys()) != {'action', 'arguments'}:
        raise MalformedResponseError(f'command fields must be exactly action and arguments, got {set(command.keys())}')

    action = command['action']
    if action not in ('move', 'hand', 'hold'):
        raise MalformedResponseError(f'Unknown action: {action!r}')

    args = command['arguments']
    if not isinstance(args, dict):
        raise MalformedResponseError('arguments must be an object')

    required_args = {
        'move': {'xyz_m', 'quaternion_wxyz', 'seconds'},
        'hand': {'closure', 'seconds'},
        'hold': {'seconds'}
    }[action]

    if set(args.keys()) != required_args:
        raise MalformedResponseError(f'Arguments for {action} must be exactly {sorted(required_args)}, got {sorted(args.keys())}')

    validated_args = {}
    try:
        seconds = _validate_finite_float(args['seconds'], 'seconds')
        if not 0.02 <= seconds <= 10.0:
            raise MalformedResponseError(f'seconds must be in [0.02, 10.0], got {seconds}')
        validated_args['seconds'] = seconds

        if action == 'move':
            xyz = _validate_float_list(args['xyz_m'], 3, 'xyz_m')
            if not (0.15 <= xyz[0] <= 0.55 and -0.60 <= xyz[1] <= -0.05 and 0.60 <= xyz[2] <= 1.15):
                raise MalformedResponseError(f'xyz_m outside workspace bounds: {xyz}')
            quat = _validate_float_list(args['quaternion_wxyz'], 4, 'quaternion_wxyz')
            norm = math.sqrt(sum(x * x for x in quat))
            if abs(norm - 1.0) > 1e-4:
                raise MalformedResponseError(f'quaternion_wxyz must have unit norm, norm={norm}')
            validated_args['xyz_m'] = xyz
            validated_args['quaternion_wxyz'] = quat
        elif action == 'hand':
            closure = _validate_finite_float(args['closure'], 'closure')
            if not 0.0 <= closure <= 1.0:
                raise MalformedResponseError(f'closure must be in [0.0, 1.0], got {closure}')
            validated_args['closure'] = closure
    except ValueError as exc:
        raise MalformedResponseError(str(exc))

    return {'action': action, 'arguments': validated_args}


class VisualPolicySession:
    """Narrow adapter around VisualSession enforcing action limits, deadline, and isolation."""
    def __init__(self, visual_session, max_calls=MAX_CALLS, deadline=DEADLINE):
        self.session = visual_session
        self.max_calls = max_calls
        self.deadline = deadline
        self.attempts = 0

    @property
    def env(self):
        return getattr(self.session, 'env', None)

    @property
    def api(self):
        return getattr(self.session, 'api', None)

    def capture(self):
        return self.session.capture()

    def execute(self, observation_id, request):
        now = float(self.session.env.data.time) if hasattr(self.session, 'env') and self.session.env is not None else 0.0
        self.attempts += 1
        arguments = request.get('arguments') if isinstance(request, dict) else None
        seconds = arguments.get('seconds') if isinstance(arguments, dict) else None
        error = None
        if self.attempts > self.max_calls:
            error = 'Action limit reached'
        elif (
            type(seconds) in (float, int)
            and math.isfinite(seconds)
            and math.ceil(seconds / 0.001) * 0.001 > self.deadline - now + 1e-6
        ):
            error = 'Action exceeds episode deadline'

        if error:
            if hasattr(self.session, 'pending'):
                self.session.pending = None
            response = {
                'schema_version': VERSION,
                'request_id': request.get('request_id') if isinstance(request, dict) else None,
                'status': 'rejected',
                'error': error,
                'start_time_s': now,
                'end_time_s': now,
                'observation': self.session.api.observe() if hasattr(self.session, 'api') and self.session.api is not None else {}
            }
            if hasattr(self.session, 'env') and self.session.env is not None:
                self.session.env.events.append({
                    'visual_observation_id': observation_id,
                    'interface_request': copy.deepcopy(request),
                    'interface_response': copy.deepcopy(response),
                    'score': self.session.env.scorer.report() if hasattr(self.session.env, 'scorer') and self.session.env.scorer is not None else None
                })
            return response

        return self.session.execute(observation_id, request)


class HoldStub:
    """Named stub that issues explicit hold primitives."""
    def __init__(self, seconds=1.0):
        self.seconds = seconds

    def __call__(self, payload):
        return {
            'command': {
                'action': 'hold',
                'arguments': {'seconds': self.seconds}
            }
        }


class ScriptedDemoStub:
    """Clearly labeled scripted sequence for plumbing smoke checks.

    NOT a trained policy, LLM, conventional comparator, or success claim.
    """
    def __init__(self):
        self.step = 0
        self.script = [
            {'action': 'hold', 'arguments': {'seconds': 0.5}},
            {
                'action': 'move',
                'arguments': {
                    'xyz_m': [0.24, -0.18, 0.95],
                    'quaternion_wxyz': [0.5, -0.5, 0.5, 0.5],
                    'seconds': 1.0
                }
            },
            {'action': 'hand', 'arguments': {'closure': 0.2, 'seconds': 0.5}},
            {'action': 'hold', 'arguments': {'seconds': 1.0}}
        ]

    def __call__(self, payload):
        if self.step < len(self.script):
            cmd = self.script[self.step]
            self.step += 1
            return {'command': copy.deepcopy(cmd)}
        return {'command': {'action': 'hold', 'arguments': {'seconds': 1.0}}}


class RefusalStub:
    """Named stub that always refuses."""
    def __init__(self, reason='Offline stub refusal test'):
        self.reason = reason

    def __call__(self, payload):
        return {'refusal': self.reason}


class MalformedStub:
    """Named stub that returns malformed responses."""
    def __init__(self, malformed_value='{"command": {"action": "fly_away"}}'):
        self.malformed_value = malformed_value

    def __call__(self, payload):
        return self.malformed_value


class ExceptionStub:
    """Named stub that raises an exception."""
    def __init__(self, message='Offline stub exception test'):
        self.message = message

    def __call__(self, payload):
        raise RuntimeError(self.message)


class CollisionStub:
    """Named stub that issues a move predicting collision through the table."""
    def __call__(self, payload):
        return {
            'command': {
                'action': 'move',
                'arguments': {
                    'xyz_m': [0.24, -0.18, 0.70],  # Solvable IK that penetrates table in preflight
                    'quaternion_wxyz': [0.5, -0.5, 0.5, 0.5],
                    'seconds': 2.0
                }
            }
        }


def get_named_stub(name):
    """Factory for named offline stubs."""
    stubs = {
        'scripted': ScriptedDemoStub,
        'hold': HoldStub,
        'refusal': RefusalStub,
        'malformed': MalformedStub,
        'exception': ExceptionStub,
        'collision': CollisionStub
    }
    if name not in stubs:
        raise ValueError(f'Unknown named stub: {name!r}. Available: {sorted(stubs.keys())}')
    return stubs[name]()


def provenance(controller_name='offline_stub'):
    """Provenance metadata recording source hashes and frozen protocol limits."""
    from .guarded_evaluation import provenance as mechanical_provenance
    result = mechanical_provenance('g2')
    runner_doc = ROOT / 'experiments/humanoid-pick-place/VISUAL_POLICY_RUNNER.md'
    if runner_doc.exists():
        result['source_sha256'][str(runner_doc.relative_to(ROOT))] = hashlib.sha256(runner_doc.read_bytes()).hexdigest()
    runner_py = ROOT / 'humanoid_sim/visual_policy_runner.py'
    if runner_py.exists():
        result['source_sha256'][str(runner_py.relative_to(ROOT))] = hashlib.sha256(runner_py.read_bytes()).hexdigest()
    visual_py = ROOT / 'humanoid_sim/visual.py'
    if visual_py.exists():
        result['source_sha256'][str(visual_py.relative_to(ROOT))] = hashlib.sha256(visual_py.read_bytes()).hexdigest()

    result.update(
        protocol_id=PROTOCOL_ID,
        task='AGY-004',
        controller=controller_name,
        instruction_version=INSTRUCTION_VERSION,
        prompt_sha256=hashlib.sha256(VISUAL_PROMPT.encode('utf-8')).hexdigest(),
        action_schema_sha256=hashlib.sha256(json.dumps(action_schema(), sort_keys=True).encode('utf-8')).hexdigest(),
        max_actions=MAX_CALLS,
        deadline_s=DEADLINE,
        offline_only=True
    )
    return result


def run_visual_episode(
    folder,
    session,
    model_callable,
    clock=time.monotonic,
    max_calls=MAX_CALLS,
    deadline=DEADLINE,
    seed=None,
    controller_name='offline_stub'
):
    """Execute the offline visual RGB-to-action policy loop.

    Never passes private object coordinates, task scoring, or non-whitelisted
    data to model_callable. Stops on refusal, malformation, exception, action rejection,
    or budget exhaustion. Does not retry or infer success.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    history = []
    image_identities = []
    calls = 0
    action_attempts = 0
    completed_actions = 0
    refusals = 0
    errors = 0
    total_wall_latency_s = 0.0
    termination_reason = 'deadline'
    terminal_error = None

    while True:
        if calls >= max_calls:
            termination_reason = 'action_limit'
            terminal_error = 'Action limit reached'
            break

        try:
            raw_obs = session.capture()
        except Exception as exc:
            termination_reason = 'capture_failure'
            terminal_error = f'{type(exc).__name__}: {exc}'
            errors += 1
            break

        sim_time = raw_obs['time_s']
        if sim_time >= deadline - 1e-6:
            termination_reason = 'deadline'
            terminal_error = 'Simulated deadline reached'
            break

        obs_id = raw_obs['observation_id']
        png_bytes = base64.b64decode(raw_obs['rgb_png_base64'])
        image_sha256 = hashlib.sha256(png_bytes).hexdigest()
        image_identities.append({
            'call': calls + 1,
            'observation_id': obs_id,
            'time_s': sim_time,
            'image_sha256': image_sha256
        })

        public_payload = build_public_payload(
            observation=raw_obs,
            history=history,
            deadline=deadline,
            max_calls=max_calls,
            calls=calls
        )

        calls += 1
        call_file = folder / f'call_{calls:03}.json'
        call_record = {
            'call': calls,
            'observation_id': obs_id,
            'time_s': sim_time,
            'image_sha256': image_sha256,
            'request': public_payload,
            'status': 'pending'
        }
        write_json(call_file, call_record)

        start_wall = clock()
        try:
            raw_response = model_callable(public_payload)
            wall_s = clock() - start_wall
            total_wall_latency_s += wall_s
            call_record['wall_latency_s'] = wall_s
            call_record['raw_response'] = raw_response
        except Exception as exc:
            wall_s = clock() - start_wall
            total_wall_latency_s += wall_s
            call_record['wall_latency_s'] = wall_s
            call_record['status'] = 'exception'
            call_record['error'] = f'{type(exc).__name__}: {exc}'
            write_json(call_file, call_record)
            termination_reason = 'exception'
            terminal_error = call_record['error']
            errors += 1
            break

        try:
            command = parse_and_validate_response(raw_response)
            call_record['command'] = command
        except ModelRefusalError as exc:
            call_record['status'] = 'refusal'
            call_record['error'] = str(exc)
            write_json(call_file, call_record)
            termination_reason = 'refusal'
            terminal_error = str(exc)
            refusals += 1
            break
        except MalformedResponseError as exc:
            call_record['status'] = 'malformed_response'
            call_record['error'] = str(exc)
            write_json(call_file, call_record)
            termination_reason = 'malformed_response'
            terminal_error = str(exc)
            errors += 1
            break

        action_request = {
            'schema_version': VERSION,
            'instruction_version': INSTRUCTION_VERSION,
            'request_id': f'visual-{calls}',
            'action': command['action'],
            'arguments': command['arguments']
        }
        action_attempts += 1
        action_response = session.execute(obs_id, action_request)
        call_record['interface_request'] = action_request
        call_record['interface_response'] = action_response

        history.append({
            'action': sanitize_action_for_history(action_request),
            'response': sanitize_response_for_history(action_response)
        })

        if action_response.get('status') == 'completed':
            call_record['status'] = 'completed'
            completed_actions += 1
            write_json(call_file, call_record)
            end_time = action_response.get('end_time_s', sim_time)
            if calls >= max_calls:
                termination_reason = 'action_limit'
                terminal_error = 'Action limit reached'
                break
            if end_time >= deadline - 1e-6:
                termination_reason = 'deadline'
                terminal_error = 'Simulated deadline reached'
                break
        else:
            call_record['status'] = action_response.get('status', 'rejected')
            call_record['error'] = action_response.get('error', 'Action rejected')
            write_json(call_file, call_record)
            termination_reason = 'rejected_action' if action_response.get('status') == 'rejected' else 'failed'
            terminal_error = call_record['error']
            break

    # Retain environment events and private evaluator report separately if environment exists
    if hasattr(session, 'env') and session.env is not None:
        try:
            session.env.save(folder)
            if hasattr(session.env, 'scorer') and session.env.scorer is not None:
                evaluator_report = session.env.scorer.report()
                write_json(folder / 'evaluator_report.json', evaluator_report)
        except Exception:
            pass

    report = {
        'controller': controller_name,
        'seed': seed,
        'termination_reason': termination_reason,
        'error': terminal_error,
        'action_attempts': action_attempts,
        'model_calls': calls,
        'completed_actions': completed_actions,
        'refusals': refusals,
        'errors': errors,
        'simulated_time_s': float(session.env.data.time) if hasattr(session, 'env') and session.env is not None else None,
        'total_wall_latency_s': total_wall_latency_s,
        'placement_success_claimed': False,
        'image_identities': image_identities,
        'provenance': provenance(controller_name)
    }
    write_json(folder / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Output directory for run logs (must not exist)')
    parser.add_argument('--seed', type=int, default=820, help='Random seed for environment reset (default: 820)')
    parser.add_argument('--stub', choices=['scripted', 'hold', 'refusal', 'malformed', 'exception', 'collision'],
                        default='scripted', help='Named offline stub to execute (default: scripted)')
    parser.add_argument('--camera', choices=['fixed', 'head'], default='fixed', help='Camera view (default: fixed)')
    parser.add_argument('--max-calls', type=int, default=MAX_CALLS, help='Maximum model calls/actions (default: 20)')
    parser.add_argument('--deadline', type=float, default=DEADLINE, help='Simulated deadline seconds (default: 25.0)')
    args = parser.parse_args()

    if args.seed in range(840, 850):
        parser.error(f'Seed {args.seed} is in held-out validation range 840-849 and strictly prohibited')

    stub = get_named_stub(args.stub)
    env = Environment()
    env.reset(args.seed, randomize=True)
    renderer = RGBRenderer(env, camera=args.camera)
    vis_session = VisualSession(env, renderer)
    session = VisualPolicySession(vis_session, max_calls=args.max_calls, deadline=args.deadline)
    try:
        report = run_visual_episode(
            folder=args.output,
            session=session,
            model_callable=stub,
            max_calls=args.max_calls,
            deadline=args.deadline,
            seed=args.seed,
            controller_name=f'stub_{args.stub}'
        )
    finally:
        renderer.close()

    print(json.dumps({
        'output': str(args.output),
        'seed': args.seed,
        'stub': args.stub,
        'termination_reason': report['termination_reason'],
        'model_calls': report['model_calls'],
        'completed_actions': report['completed_actions'],
        'error': report['error'],
        'placement_success_claimed': report['placement_success_claimed']
    }, indent=2))


if __name__ == '__main__':
    main()
