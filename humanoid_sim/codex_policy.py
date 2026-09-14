"""Image-to-primitive decisions through the user's signed-in Codex CLI.

No SDK, provider HTTP client, API-key lookup or AGY delegation. Each decision uses
a new CLI session in a temporary public-input directory, with tools disabled.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

import copy
import itertools
from types import SimpleNamespace

import mujoco
import numpy as np
from PIL import Image

from .environment import Environment, ARM_NAMES, HAND_NAMES
from .scene import ROOT, SCENE
from .visual_policy_runner import (
    VISUAL_PROMPT, MalformedResponseError, VisualPolicyError, action_schema,
    allowlist_observation, sanitize_action_for_history, sanitize_response_for_history,
    parse_and_validate_response, strict_json, write_json, _validate_budget,
)

MODEL = 'gpt-5.6-sol'
SUPPORTED_VERSION = 'codex-cli 0.154.0'
CONDITIONS = ('c1', 'c2')
DEFAULT_CONDITION = 'c1'

PROTOCOL_PATHS = {
    'c1': ROOT / 'experiments/humanoid-pick-place/protocols/C1.md',
    'c2': ROOT / 'experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md',
}

PROTOCOL_IDS = {
    'c1': 'humanoid-codex-c1-development',
    'c2': 'humanoid-codex-c2-development',
}

C2_NOMINAL_BOUNDS_ENCLOSURE = {
    'x': (-0.074, 0.058),
    'y': (-0.042, 0.042),
    'z': (-0.077, 0.085),
}
DISABLED_FEATURES = (
    'shell_tool', 'unified_exec', 'shell_snapshot', 'apps', 'plugins',
    'remote_plugin', 'hooks', 'memories', 'multi_agent', 'multi_agent_v2',
    'browser_use', 'browser_use_external', 'computer_use', 'image_generation',
    'view_image', 'skill_search', 'workspace_dependencies', 'code_mode',
    'code_mode_host', 'goals', 'sleep_tool', 'tool_suggest',
    'unbounded_connection_retries',
)
CONFIG = {
    'forced_login_method': 'chatgpt', 'web_search': 'disabled',
    'approval_policy': 'never', 'project_doc_max_bytes': 0,
    'model_reasoning_effort': 'low', 'mcp_servers': {},
    'tools.update_plan.enabled': False,
    'tools.experimental_request_user_input.enabled': False,
    'features.skip_host_skill_discovery': True,
    'suppress_unstable_features_warning': True,
}
DISABLED_CODE_MODE_NOTICE = (
    'Code Mode is unavailable because code-mode host is disabled. Code mode will '
    'fail closed; enable `features.code_mode_host` and install `codex-code-mode-host`.'
)
DECISION_INSTRUCTION = (
    '\nYou are the decision component, not a coding assistant. The attached image '
    'and the following JSON are the entire task observation. Do not call tools, '
    'read files, search, ask questions or edit anything. Return exactly one JSON '
    'command matching the supplied output schema. Do not provide commentary.\n'
)
C2_INSTRUCTION = (
    'Additional robot geometry and feedback contract:\n'
    'The right_grasp site is a reference embedded within the hand geometry. It is not\n'
    'the lowest fingertip, an empty grasp cavity, or the desired object centre.\n'
    'With fully open fingers and the declared downward orientation, nominal collision\n'
    'geometry occupies approximately these world-axis offsets relative to the site:\n'
    'X [-0.074, +0.058] m, Y [-0.042, +0.042] m, Z [-0.077, +0.085] m.\n'
    'These are rounded bounds on solid robot geometry from its description. Actual\n'
    'extents change with finger articulation, orientation and tracking error. They do\n'
    'not specify where to place an object within the hand or certify a safe path.\n'
    'A grasp-site target above the table can still put fingertips through the table.\n'
    'Likewise, putting the site at an object\'s visible top does not guarantee clearance\n'
    'between the open hand and the object. Plan clearance for the entire hand and its\n'
    'path, not only the reference point. The guard does not certify object contacts.\n'
    'After every completed motion, use the current image to reassess the object\'s\n'
    'position and orientation. If it moved or toppled, do not keep descending toward\n'
    'its former position or assume that it remains upright. A completed motion is not\n'
    'evidence of a grasp. Replan using the new visual observation and public hand state.\n'
)


class CodexPolicyError(VisualPolicyError):
    pass


def hand_collision_bounds(model, data, site_id):
    """Actual collision mesh vertices/box corners, expressed about the grasp site.

    Bounds describe occupied geometry, not a free grasp cavity or safe trajectory.
    No object state contributes to these bounds.
    """
    result = []
    for g in range(model.ngeom):
        body = model.body(int(model.geom_bodyid[g])).name
        if not body.startswith('right_hand_') or not (model.geom_contype[g] or model.geom_conaffinity[g]):
            continue
        kind = model.geom_type[g]
        if kind == mujoco.mjtGeom.mjGEOM_MESH:
            mesh = model.geom_dataid[g]
            start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
            vertices = model.mesh_vert[start:start+count]
        elif kind == mujoco.mjtGeom.mjGEOM_BOX:
            vertices = np.array(list(itertools.product((-1, 1), repeat=3))) * model.geom_size[g]
        else:
            raise ValueError(f'Unsupported collision geometry: {g}, {kind}')
        world = vertices @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g]
        relative = world - data.site_xpos[site_id]
        local = relative @ data.site_xmat[site_id].reshape(3, 3)
        result.append({
            'geom_id': g,
            'geom_name': model.geom(g).name,
            'body': body,
            'world_offset_min_m': relative.min(axis=0).tolist(),
            'world_offset_max_m': relative.max(axis=0).tolist(),
            'site_local_min_m': local.min(axis=0).tolist(),
            'site_local_max_m': local.max(axis=0).tolist(),
        })
    return result


def nominal_open_hand_geometry(scene_xml=SCENE):
    """Reproduce nominal open-hand collision bounds from robot description and IK.

    Robot-only calculation at downward ready posture with closure=0.
    Does not load C1 audit, episode trajectory, or object state.
    """
    model = mujoco.MjModel.from_xml_path(str(scene_xml))
    joints = np.array([model.joint(name).id for name in ARM_NAMES])
    env = SimpleNamespace(
        model=model,
        data=mujoco.MjData(model),
        arm_joints=joints,
        arm_q=model.jnt_qposadr[joints],
        arm_v=model.jnt_dofadr[joints],
        arm_a=np.array([model.actuator(name).id for name in ARM_NAMES]),
        site=model.site('right_grasp').id,
    )
    hand_joints = np.array([model.joint(name).id for name in HAND_NAMES])
    env.data.qpos[model.jnt_qposadr[hand_joints]] = Environment.hand_targets(env, 0)
    env.data.qpos[env.arm_q] = Environment.solve(env, [.24, -.18, .94])
    mujoco.mj_forward(model, env.data)
    bounds = hand_collision_bounds(model, env.data, env.site)
    world_min = np.min([b['world_offset_min_m'] for b in bounds], axis=0).tolist()
    world_max = np.max([b['world_offset_max_m'] for b in bounds], axis=0).tolist()
    return {
        'source': 'robot model, closure=0 joint targets, downward IK at nominal site [.24,-.18,.94]; no episode state',
        'world_offset_min_m': world_min,
        'world_offset_max_m': world_max,
        'per_geom': bounds,
    }


def verify_nominal_bounds_enclosure(geometry=None):
    """Verify that declared C2 rounded bounds strictly enclose nominal open-hand bounds."""
    if geometry is None:
        geometry = nominal_open_hand_geometry()
    min_m = geometry['world_offset_min_m']
    max_m = geometry['world_offset_max_m']
    declared = C2_NOMINAL_BOUNDS_ENCLOSURE
    axes = ('x', 'y', 'z')
    enclosed = {}
    for i, axis in enumerate(axes):
        decl_min, decl_max = declared[axis]
        if not (decl_min <= min_m[i] and max_m[i] <= decl_max):
            raise ValueError(
                f'Nominal bounds on axis {axis} [{min_m[i]}, {max_m[i]}] '
                f'not enclosed by declared bounds [{decl_min}, {decl_max}]'
            )
        enclosed[axis] = {
            'nominal_min_m': min_m[i],
            'nominal_max_m': max_m[i],
            'declared_min_m': decl_min,
            'declared_max_m': decl_max,
            'min_margin_m': min_m[i] - decl_min,
            'max_margin_m': decl_max - max_m[i],
            'enclosed': True,
        }
    return {
        'status': 'verified_enclosed',
        'nominal_geometry': geometry,
        'declared_bounds': declared,
        'axes': enclosed,
        'posture_specific': True,
        'site': 'right_grasp',
        'orientation': 'downward',
        'hand_closure': 0.0,
    }


def generate_geometry_evidence(geometry=None):
    """Produce static robot-only geometry evidence document."""
    if geometry is None:
        geometry = nominal_open_hand_geometry()
    verification = verify_nominal_bounds_enclosure(geometry)
    return {
        'status': 'verified',
        'contract_type': 'static_robot_only_nominal_open_hand_geometry',
        'posture': {
            'site': 'right_grasp',
            'nominal_waypoint_xyz_m': [0.24, -0.18, 0.94],
            'orientation': 'downward',
            'quaternion_wxyz': [0.5, -0.5, 0.5, 0.5],
            'hand_closure': 0.0,
            'posture_specific': True,
        },
        'nominal_geometry': {
            'source': geometry['source'],
            'world_offset_min_m': geometry['world_offset_min_m'],
            'world_offset_max_m': geometry['world_offset_max_m'],
            'geom_count': len(geometry['per_geom']),
        },
        'declared_rounded_bounds': {
            'x_m': [-0.074, 0.058],
            'y_m': [-0.042, 0.042],
            'z_m': [-0.077, 0.085],
        },
        'enclosure_verification': verification['axes'],
        'contract_notes': [
            'Bounds describe solid robot collision geometry around the right_grasp site.',
            'Bounds do not represent a free grasp cavity, desired object location, or certified safe path.',
            'Actual geometry changes with finger articulation, orientation, and tracking error.',
            'No object state or task outcomes contribute to this computation.',
        ],
    }


def git_source_commit():
    """Return current git commit hash of the worktree or repository."""
    try:
        res = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True,
                             capture_output=True, timeout=5, check=True)
        return res.stdout.strip()
    except Exception:
        return 'unknown'


def child_environment():
    """Allow normal login discovery, never forward API keys or custom endpoints."""
    return {key: os.environ[key] for key in (
        'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR', 'CODEX_HOME'
    ) if key in os.environ}


def public_input(payload, condition=DEFAULT_CONDITION):
    if condition not in CONDITIONS:
        raise ValueError(f'Unsupported condition: {condition}')
    obs = allowlist_observation(payload['observation'])
    png = base64.b64decode(obs.pop('rgb_png_base64'), validate=True)
    with Image.open(io.BytesIO(png)) as img:
        if img.format != 'PNG':
            raise ValueError('Expected PNG image')
        img.verify()
    with Image.open(io.BytesIO(png)) as img:
        img.load()
        if img.size != (obs['camera']['width'], obs['camera']['height']):
            raise ValueError('Image dimensions differ from calibration')
    if payload['observation'].get('rgb_sha256', obs['rgb_sha256']) != obs['rgb_sha256']:
        raise ValueError('Image identity mismatch')
    history = payload.get('history', [])
    if not isinstance(history, list):
        raise ValueError('History must be a list')
    clean_history = []
    for h in history[-20:]:
        response = sanitize_response_for_history(h['response'])
        # Runner history is already sanitized; preserve its public robot state.
        if 'robot_state' in h['response']:
            from .visual_policy_runner import allowlist_robot_state
            response['robot_state'] = allowlist_robot_state(h['response']['robot_state'])
        clean_history.append({'action': sanitize_action_for_history(h['action']), 'response': response})
    remaining = payload['remaining_actions']
    seconds = payload['remaining_time_s']
    _validate_budget(remaining, seconds)
    text = {'observation': obs, 'history': clean_history,
            'remaining_actions': remaining, 'remaining_time_s': seconds}
    if condition == 'c1':
        prompt = VISUAL_PROMPT + DECISION_INSTRUCTION + json.dumps(text, sort_keys=True, allow_nan=False)
    elif condition == 'c2':
        prompt = VISUAL_PROMPT + DECISION_INSTRUCTION + C2_INSTRUCTION + json.dumps(text, sort_keys=True, allow_nan=False)
    else:
        raise ValueError(f'Unsupported condition: {condition}')
    return png, prompt


def cli_command(executable, directory, model):
    argv = [executable, 'exec', '--ignore-user-config', '--ignore-rules',
            '--strict-config', '--ephemeral', '--skip-git-repo-check',
            '--sandbox', 'read-only', '--color', 'never', '--json',
            '--model', model, '--cd', str(directory),
            '--image', str(directory / 'observation.png'),
            '--output-schema', str(directory / 'schema.json'),
            '--output-last-message', str(directory / 'decision.json')]
    for key, value in CONFIG.items():
        # Empty map uses TOML syntax; other configured scalar values are JSON/TOML compatible.
        argv += ['--config', key + '=' + ('{}' if value == {} else json.dumps(value))]
    for feature in DISABLED_FEATURES:
        argv += ['--disable', feature]
    return argv + ['-']


def run_process(argv, prompt, cwd, env, timeout, record_dir):
    """Retain CLI events; kill this process group on timeout/interruption."""
    with (record_dir / 'events.jsonl').open('wb') as out, (record_dir / 'stderr.txt').open('wb') as err:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                cwd=cwd, env=env, start_new_session=True)
        try:
            proc.communicate(prompt.encode(), timeout=timeout)
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            raise
        return proc.returncode


def validate_events(path, final_text):
    if path.stat().st_size > 2_000_000:
        raise CodexPolicyError('CLI event log exceeds audit limit')
    messages, completions, starts = [], 0, 0
    for line in path.read_text().splitlines():
        event = strict_json(line)
        kind = event.get('type')
        if kind == 'turn.started':
            starts += 1
        elif kind == 'turn.completed':
            completions += 1
        elif kind in ('item.started', 'item.updated', 'item.completed'):
            item = event.get('item', {})
            if (kind == 'item.completed' and starts == 0 and item.get('type') == 'error'
                    and item.get('message') == DISABLED_CODE_MODE_NOTICE):
                # CLI 0.154.0 emits this expected startup notice when its tool host is disabled.
                continue
            if item.get('type') not in ('agent_message', 'reasoning'):
                raise CodexPolicyError('Tool use or unexpected CLI item: ' + str(item.get('type')))
            if kind == 'item.completed' and item.get('type') == 'agent_message':
                messages.append(item.get('text'))
        elif kind != 'thread.started':
            raise CodexPolicyError('Failed or unexpected CLI event: ' + str(kind))
    if starts != 1 or completions != 1 or len(messages) != 1:
        raise CodexPolicyError('Expected one fresh completed decision without retries or extra messages')
    if strict_json(messages[0]) != strict_json(final_text):
        raise CodexPolicyError('CLI final file disagrees with event log')


class CodexPolicy:
    def __init__(self, record_dir, *, model=MODEL, timeout=120., executable='codex',
                 process_runner=run_process, condition=DEFAULT_CONDITION):
        if condition not in CONDITIONS:
            raise ValueError(f'Unsupported condition: {condition}')
        if not isinstance(model, str) or not model or model.startswith('-'):
            raise ValueError('Explicit model identifier required')
        if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not 0 < timeout <= 180:
            raise ValueError('Timeout must be in (0, 180] seconds')
        self.condition = condition
        self.model, self.timeout, self.executable = model, timeout, executable
        self.record_dir = Path(record_dir)
        self.process_runner, self.calls = process_runner, 0

    def __call__(self, payload):
        if self.calls >= 20:
            raise CodexPolicyError('Codex invocation limit reached')
        self.calls += 1
        folder = self.record_dir / f'decision-{self.calls:03}'
        folder.mkdir(parents=True, exist_ok=False)
        record = {'status': 'preparing', 'invocation': self.calls,
                  'condition': self.condition,
                  'mode': 'codex_chatgpt' if self.process_runner is run_process else 'mock_codex',
                  'model_requested': self.model, 'timeout_s': self.timeout,
                  'process_started': False}
        write_json(folder / 'record.json', record)
        started = time.monotonic()
        try:
            png, prompt = public_input(payload, condition=self.condition)
            record.update(image_sha256=hashlib.sha256(png).hexdigest(),
                          prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
            (folder / 'prompt.txt').write_text(prompt)
            (folder / 'observation.png').write_bytes(png)
            with tempfile.TemporaryDirectory(prefix='humanoid-codex-public-') as scratch:
                directory = Path(scratch)
                (directory / 'observation.png').write_bytes(png)
                write_json(directory / 'schema.json', action_schema())
                argv = cli_command(self.executable, directory, self.model)
                record.update(argv=argv, status='pending', process_started=None)
                write_json(folder / 'record.json', record)
                code = self.process_runner(argv, prompt, directory, child_environment(), self.timeout, folder)
                record.update(returncode=code, process_started=True)
                if code != 0:
                    raise CodexPolicyError(f'Codex exited with status {code}; see retained stderr')
                result = directory / 'decision.json'
                if not result.is_file() or result.stat().st_size > 64_000:
                    raise MalformedResponseError('Missing or oversized Codex decision')
                raw = result.read_text()
                (folder / 'decision.json').write_text(raw)
                validate_events(folder / 'events.jsonl', raw)
                parsed = strict_json(raw)
                if not isinstance(parsed, dict) or set(parsed) != {'command'}:
                    raise MalformedResponseError('Expected exactly one command wrapper')
                command = parse_and_validate_response(parsed)
                record.update(status='completed', command=command, tool_items=0)
                return {'command': command}
        except (KeyboardInterrupt, SystemExit):
            record['status'] = 'interrupted'
            raise
        except subprocess.TimeoutExpired:
            record['status'] = 'timeout'
            raise CodexPolicyError('Codex decision timed out; no retry')
        except Exception as exc:
            record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            record['wall_latency_s'] = time.monotonic() - started
            write_json(folder / 'record.json', record)


def check_install(executable='codex'):
    """Local CLI checks only; auth secrets remain owned by Codex."""
    env = child_environment()
    version = subprocess.run([executable, '--version'], env=env, text=True,
                             capture_output=True, timeout=10, check=True).stdout.strip()
    if version != SUPPORTED_VERSION:
        raise CodexPolicyError(f'Unreviewed CLI version: {version}')
    auth = subprocess.run([executable, 'login', 'status'], env=env, text=True,
                          capture_output=True, timeout=10)
    if auth.returncode or 'Logged in using ChatGPT' not in auth.stdout + auth.stderr:
        raise CodexPolicyError('Sign in to Codex with ChatGPT; API-key login is not supported here')
    return {'cli_version': version, 'login_method': 'chatgpt',
            'executable': shutil.which(executable), 'config': CONFIG,
            'disabled_features': DISABLED_FEATURES}


def run_preflight(output_dir, *, condition=DEFAULT_CONDITION, model=MODEL, max_calls=20,
                  executable='codex', info=None):
    """Run offline preflight: verify installation, condition, geometry, payload, budgets, isolation.

    Zero model invocations and zero physics steps.
    """
    output = Path(output_dir).resolve()
    if output.exists():
        raise ValueError('Output directory must be new')
    if condition not in CONDITIONS:
        raise ValueError(f'Unsupported condition: {condition}')
    if model != MODEL or max_calls != 20:
        raise ValueError(f'{condition.upper()} fixes the requested model and 20-call cap; declare a successor before changing them')
    _validate_budget(max_calls, 25.0)

    if info is None:
        info = check_install(executable=executable)

    protocol_path = PROTOCOL_PATHS[condition]
    protocol_id = PROTOCOL_IDS[condition]
    protocol_sha256 = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    source_commit = git_source_commit()

    # 1. Geometry evidence & enclosure verification
    geom_evidence = generate_geometry_evidence()
    geom_evidence_bytes = json.dumps(geom_evidence, indent=2, sort_keys=True).encode('utf-8') + b'\n'
    geom_evidence_sha256 = hashlib.sha256(geom_evidence_bytes).hexdigest()

    # 2. Public payload construction & isolation verification
    # Generate initial observation with static kinematics and zero physics steps
    import math
    import uuid
    from .interface import PolicyInterface
    from .visual import RGBRenderer
    from .visual_policy_runner import build_public_payload

    mj_model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(mj_model)
    for side in ['left', 'right']:
        for name, val in [('shoulder_pitch', .2), ('shoulder_roll', .2 if side == 'left' else -.2), ('elbow', 1.28)]:
            data.qpos[mj_model.joint(f'{side}_{name}_joint').qposadr] = val
    joints = np.array([mj_model.joint(name).id for name in ARM_NAMES])
    arm_q = mj_model.jnt_qposadr[joints]
    arm_v = mj_model.jnt_dofadr[joints]
    hand_joints = np.array([mj_model.joint(name).id for name in HAND_NAMES])
    env = SimpleNamespace(model=mj_model, data=data, arm_joints=joints, arm_q=arm_q, arm_v=arm_v,
                          arm_a=np.array([mj_model.actuator(name).id for name in ARM_NAMES]),
                          site=mj_model.site('right_grasp').id)
    data.qpos[mj_model.jnt_qposadr[hand_joints]] = Environment.hand_targets(env, 0)
    data.qpos[arm_q] = Environment.solve(env, [.24, -.18, .94])
    rng = np.random.default_rng(820)
    q = mj_model.joint('object_free').qposadr[0]
    data.qpos[q:q+2] += rng.uniform(-.015, .015, 2)
    angle = rng.uniform(-.15, .15)
    data.qpos[q+3:q+7] = [math.cos(angle/2), 0, 0, math.sin(angle/2)]
    mujoco.mj_forward(mj_model, data)

    renderer = RGBRenderer(env, camera='fixed')
    try:
        png, camera = renderer.capture()
    finally:
        renderer.close()

    api = PolicyInterface(env, 'robot_state')
    robot_state = api.observe()
    raw_obs = {
        'schema_version': 1,
        'observation_id': uuid.uuid4().hex,
        'time_s': 0.0,
        'camera': camera,
        'robot_state': robot_state,
        'rgb_png_base64': base64.b64encode(png).decode('ascii'),
        'rgb_sha256': hashlib.sha256(png).hexdigest(),
    }

    # Test payload construction with private fields injected to verify exclusion
    payload = build_public_payload(raw_obs, history=[], deadline=25.0, max_calls=max_calls, calls=0)
    test_payload = copy.deepcopy(payload)
    test_payload['observation']['ground_truth_object_pos'] = [0.25, -0.18, 0.76]
    test_payload['private_oracle_score'] = {'penetration': 0.005}

    png, prompt = public_input(test_payload, condition=condition)

    # Verify isolation
    if 'ground_truth_object_pos' in prompt or 'private_oracle_score' in prompt:
        raise RuntimeError('Private fields leaked into public prompt')

    child_env = child_environment()
    for secret_key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'GEMINI_API_KEY'):
        if secret_key in child_env:
            raise RuntimeError(f'Secret key {secret_key} present in child environment')

    prompt_sha256 = hashlib.sha256(prompt.encode('utf-8')).hexdigest()

    output.mkdir(parents=True)
    (output / 'geometry_evidence.json').write_bytes(geom_evidence_bytes)
    write_json(output / 'public_payload.json', payload)
    (output / 'prompt.txt').write_text(prompt)
    (output / 'observation.png').write_bytes(png)

    preflight_record = {
        'status': 'complete',
        'condition': condition,
        'condition_id': condition,
        'protocol_id': protocol_id,
        'protocol_path': str(protocol_path.relative_to(ROOT)),
        'protocol_sha256': protocol_sha256,
        'source_commit': source_commit,
        'cli_version': info['cli_version'],
        'login_method': info['login_method'],
        'executable': info['executable'],
        'model_requested': model,
        'max_actions': max_calls,
        'deadline_s': 25.0,
        'decision_timeout_s': 120.0,
        'demonstration_prompt_sha256': prompt_sha256,
        'geometry_evidence_sha256': geom_evidence_sha256,
        'isolation_verified': True,
        'model_invocations': 0,
        'physics_steps': 0,
        'config': info.get('config', CONFIG),
        'disabled_features': list(info.get('disabled_features', DISABLED_FEATURES)),
    }
    write_json(output / 'preflight.json', preflight_record)
    return preflight_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--condition', choices=['c1', 'c2'], default=DEFAULT_CONDITION,
                        help='Experiment condition: c1 (default) or c2')
    parser.add_argument('--execute', action='store_true', help='Run the seed-820 development episode')
    parser.add_argument('--probe', type=Path, help='One signed-in decision on an archived public payload; no action')
    parser.add_argument('--model', default=MODEL)
    parser.add_argument('--max-calls', type=int, default=20)
    parser.add_argument('--executable', default='codex', help='Path to codex executable')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory')
    if args.execute and args.probe:
        parser.error('Choose episode or archived-image probe')
    if (args.execute or not args.probe) and (args.model != MODEL or args.max_calls != 20):
        parser.error(f'{args.condition.upper()} fixes the requested model and 20-call cap; declare a successor before changing them')
    _validate_budget(args.max_calls, 25.)
    info = check_install(executable=args.executable)

    if not args.execute and not args.probe:
        preflight_record = run_preflight(args.output, condition=args.condition,
                                         model=args.model, max_calls=args.max_calls,
                                         executable=args.executable, info=info)
        print(json.dumps(preflight_record, indent=2))
        return

    policy = CodexPolicy(args.output / 'codex', model=args.model, executable=args.executable,
                         condition=args.condition)
    if args.probe:
        args.output.mkdir(parents=True)
        write_json(args.output / 'preflight.json', info)
        if args.condition == 'c2':
            geom_ev = generate_geometry_evidence()
            write_json(args.output / 'geometry_evidence.json', geom_ev)
        decision = policy(strict_json(args.probe.read_text()))
        write_json(args.output / 'probe.json', {'decision': decision, 'actions_executed': 0, 'condition': args.condition})
        print(json.dumps(decision))
        return

    from .environment import Environment
    from .visual import VisualSession, RGBRenderer
    from .visual_policy_runner import VisualPolicySession, run_visual_episode
    protocol = PROTOCOL_PATHS[args.condition]
    protocol_sha256 = hashlib.sha256(protocol.read_bytes()).hexdigest()
    source_commit = git_source_commit()
    geom_evidence = generate_geometry_evidence()
    geom_evidence_bytes = json.dumps(geom_evidence, indent=2, sort_keys=True).encode('utf-8') + b'\n'
    geom_evidence_sha256 = hashlib.sha256(geom_evidence_bytes).hexdigest()

    env = Environment()
    env.reset(820, randomize=True)
    renderer = RGBRenderer(env, camera='fixed')
    session = VisualPolicySession(VisualSession(env, renderer), max_calls=args.max_calls)
    try:
        report = run_visual_episode(args.output, session, policy, max_calls=args.max_calls,
                                    seed=820, controller_name='codex_chatgpt',
                                    execution_metadata={'mode': 'codex_chatgpt', 'offline_only': False,
                                                        'condition': args.condition,
                                                        'condition_id': args.condition,
                                                        'protocol_id': PROTOCOL_IDS[args.condition],
                                                        'protocol_sha256': protocol_sha256,
                                                        'source_commit': source_commit,
                                                        'geometry_evidence_sha256': geom_evidence_sha256,
                                                        'model_requested': args.model, **info})
        write_json(args.output / 'geometry_evidence.json', geom_evidence)
        print(json.dumps(report, indent=2))
    finally:
        renderer.close()


if __name__ == '__main__':
    main()
