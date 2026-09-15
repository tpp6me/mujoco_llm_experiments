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
import zipfile

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
    c3_response_schema, parse_and_validate_c3_response, validate_visual_assessment,
    serialize_schema,
    allowlist_observation, sanitize_action_for_history, sanitize_response_for_history,
    parse_and_validate_response, strict_json, write_json, _validate_budget,
)

MODEL = 'gpt-5.6-sol'
SUPPORTED_VERSION = 'codex-cli 0.154.0'
CONDITIONS = ('c1', 'c2', 'c3')
DEFAULT_CONDITION = 'c1'

PROTOCOL_PATHS = {
    'c1': ROOT / 'experiments/humanoid-pick-place/protocols/C1.md',
    'c2': ROOT / 'experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md',
    'c3': ROOT / 'experiments/humanoid-pick-place/protocols/C3_PROPOSAL.md',
}

PROTOCOL_IDS = {
    'c1': 'humanoid-codex-c1-development',
    'c2': 'humanoid-codex-c2-development',
    'c3': 'humanoid-codex-c3-development',
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
C3_VISUAL_PROMPT = VISUAL_PROMPT.replace(
    'Return only the structured action. Do not claim success in prose.',
    'Return only the structured C3 response specified below. Do not claim task success.'
)
C3_DECISION_INSTRUCTION = DECISION_INSTRUCTION.replace(
    'Return exactly one JSON command matching the supplied output schema.',
    'Return exactly one JSON object matching the supplied C3 output schema.'
)
C3_INSTRUCTION = (
    'C3 visual assessment contract:\n'
    'Report the current visible state of the red block before selecting the next action.\n'
    'Return visual_assessment and command in the supplied JSON schema.\n'
    'For block_visibility, use visible when the block is clearly visible, partly_visible\n'
    'when part is hidden, not_visible when it cannot be seen, and uncertain when unsure.\n'
    'For block_relative_to_fingers, use between when the image clearly places the block\n'
    'between the fingers, separate when it is visibly separate from them, and uncertain\n'
    'when the image does not establish this relation. Apparent alignment in an image\n'
    'alone does not establish a physical grasp. Use the current image and public robot\n'
    'state rather than assuming the previous command achieved its purpose. Choose the\n'
    'next command consistently with this assessment. Do not report private coordinates,\n'
    'scorer values or additional explanations.\n'
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


def serialize_geometry_evidence(geom_evidence):
    """Deterministic serialization of geometry evidence with sorted keys and trailing newline."""
    return json.dumps(geom_evidence, indent=2, sort_keys=True).encode('utf-8') + b'\n'


def git_source_info():
    """Return git commit hash and dirty status of the worktree or repository."""
    info = {'commit': 'unknown', 'is_dirty': False, 'status': 'unknown'}
    try:
        res = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True,
                             capture_output=True, timeout=5, check=True)
        info['commit'] = res.stdout.strip()
        status_res = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, text=True,
                                    capture_output=True, timeout=5, check=True)
        dirty_lines = [l for l in status_res.stdout.splitlines() if not l.startswith('?? runtime/')]
        info['is_dirty'] = len(dirty_lines) > 0
        info['status'] = 'dirty' if info['is_dirty'] else 'clean'
    except Exception as exc:
        info['error'] = str(exc)
    return info


def git_source_commit():
    """Return current git commit hash of the worktree or repository."""
    return git_source_info()['commit']


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
    prompt = static_instruction(condition) + json.dumps(text, sort_keys=True, allow_nan=False)
    return png, prompt


def static_instruction(condition=DEFAULT_CONDITION):
    """Return the complete static instruction text preceding the dynamic observation JSON."""
    if condition == 'c1':
        return VISUAL_PROMPT + DECISION_INSTRUCTION
    elif condition == 'c2':
        return VISUAL_PROMPT + DECISION_INSTRUCTION + C2_INSTRUCTION
    elif condition == 'c3':
        return C3_VISUAL_PROMPT + C3_DECISION_INSTRUCTION + C2_INSTRUCTION + C3_INSTRUCTION
    raise ValueError(f'Unsupported condition: {condition}')


def output_schema(condition=DEFAULT_CONDITION):
    """Return JSON schema dict for the requested condition."""
    if condition in ('c1', 'c2'):
        return action_schema()
    elif condition == 'c3':
        return c3_response_schema()
    raise ValueError(f'Unsupported condition: {condition}')


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
        self.assessments = []
        self.last_assessment = None

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
            static_inst = static_instruction(self.condition)
            static_instruction_sha256 = hashlib.sha256(static_inst.encode('utf-8')).hexdigest()
            prompt_sha256 = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            schema = output_schema(self.condition)
            schema_bytes = serialize_schema(schema)
            schema_sha256 = hashlib.sha256(schema_bytes).hexdigest()
            source_info = git_source_info()

            obs_info = payload.get('observation', {})
            obs_id = obs_info.get('observation_id')
            time_s = obs_info.get('time_s')

            record.update(
                image_sha256=hashlib.sha256(png).hexdigest(),
                prompt_sha256=prompt_sha256,
                static_instruction_sha256=static_instruction_sha256,
                schema_sha256=schema_sha256,
                source_commit=source_info['commit'],
                observation_id=obs_id,
                time_s=time_s,
            )
            (folder / 'prompt.txt').write_text(prompt)
            (folder / 'observation.png').write_bytes(png)
            with tempfile.TemporaryDirectory(prefix='humanoid-codex-public-') as scratch:
                directory = Path(scratch)
                (directory / 'observation.png').write_bytes(png)
                (directory / 'schema.json').write_bytes(schema_bytes)
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

                if self.condition == 'c3':
                    c3_result = parse_and_validate_c3_response(raw)
                    visual_assessment = c3_result['visual_assessment']
                    command = c3_result['command']
                    self.last_assessment = visual_assessment
                    assessment_record = {
                        'call': self.calls,
                        'observation_id': obs_id,
                        'time_s': time_s,
                        'image_sha256': record['image_sha256'],
                        'prompt_sha256': prompt_sha256,
                        'static_instruction_sha256': static_instruction_sha256,
                        'schema_sha256': schema_sha256,
                        'model_requested': self.model,
                        'source_commit': source_info['commit'],
                        'visual_assessment': visual_assessment,
                        'command': command,
                    }
                    self.assessments.append(assessment_record)
                    record.update(status='completed', visual_assessment=visual_assessment, command=command, tool_items=0)
                    return {'visual_assessment': visual_assessment, 'command': command}
                else:
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

    cli_info = None
    if info is not None:
        cli_info = info
    else:
        try:
            cli_info = check_install(executable=executable)
        except Exception as exc:
            cli_info = {
                'cli_version': 'unverified (offline preflight)',
                'login_method': 'unverified',
                'executable': shutil.which(executable) or executable,
                'status': f'offline_unverified: {exc}',
                'config': CONFIG,
                'disabled_features': DISABLED_FEATURES,
            }

    protocol_path = PROTOCOL_PATHS[condition]
    protocol_id = PROTOCOL_IDS[condition]
    protocol_sha256 = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    git_info = git_source_info()

    # 1. Geometry evidence & enclosure verification
    geom_evidence = None
    geom_evidence_bytes = None
    geom_evidence_sha256 = None
    if condition in ('c2', 'c3'):
        geom_evidence = generate_geometry_evidence()
        geom_evidence_bytes = serialize_geometry_evidence(geom_evidence)
        geom_evidence_sha256 = hashlib.sha256(geom_evidence_bytes).hexdigest()

    # 2. Output schema
    schema = output_schema(condition)
    schema_bytes = serialize_schema(schema)
    schema_sha256 = hashlib.sha256(schema_bytes).hexdigest()

    # 3. Public payload from committed archive & isolation verification
    archive_path = ROOT / 'experiments/humanoid-pick-place/results/codex_C1_episode.zip'
    input_provenance = 'experiments/humanoid-pick-place/results/codex_C1_episode.zip:seed-820/call_001.json'
    with zipfile.ZipFile(archive_path) as z:
        c1_call1 = json.loads(z.read('seed-820/call_001.json'))
    payload = c1_call1['request']

    # Test payload construction with private fields injected to verify exclusion
    test_payload = copy.deepcopy(payload)
    test_payload['observation']['ground_truth_object_pos'] = [0.25, -0.18, 0.76]
    test_payload['private_oracle_score'] = {'penetration': 0.005}
    test_payload['history'] = [{'action': {'action': 'hold', 'arguments': {'seconds': 0.1}},
                                'response': {'status': 'completed',
                                             'visual_assessment': {'block_visibility': 'visible'},
                                             'robot_state': test_payload['observation']['robot_state']}}]

    _, test_prompt = public_input(test_payload, condition=condition)

    # Verify isolation
    if 'ground_truth_object_pos' in test_prompt or 'private_oracle_score' in test_prompt:
        raise RuntimeError('Private fields leaked into public prompt')
    if '"visual_assessment"' in test_prompt:
        raise RuntimeError('Visual assessment leaked into public prompt history')

    child_env = child_environment()
    for secret_key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'GEMINI_API_KEY'):
        if secret_key in child_env:
            raise RuntimeError(f'Secret key {secret_key} present in child environment')

    png_clean, prompt_clean = public_input(payload, condition=condition)
    prompt_sha256 = hashlib.sha256(prompt_clean.encode('utf-8')).hexdigest()
    static_inst = static_instruction(condition)
    static_instruction_sha256 = hashlib.sha256(static_inst.encode('utf-8')).hexdigest()

    output.mkdir(parents=True)
    if geom_evidence_bytes is not None:
        (output / 'geometry_evidence.json').write_bytes(geom_evidence_bytes)
    (output / 'schema.json').write_bytes(schema_bytes)
    write_json(output / 'public_payload.json', payload)
    (output / 'prompt.txt').write_text(prompt_clean)
    (output / 'observation.png').write_bytes(png_clean)

    synthetic_check_meta = None
    if condition == 'c3':
        synthetic_decision = {
            'visual_assessment': {
                'block_visibility': 'visible',
                'block_relative_to_fingers': 'separate'
            },
            'command': {
                'action': 'hold',
                'arguments': {
                    'seconds': 0.1
                }
            }
        }
        synthetic_raw = json.dumps(synthetic_decision, indent=2) + '\n'
        (output / 'synthetic_decision.json').write_text(synthetic_raw)
        synthetic_events = [
            {'type': 'thread.started', 'thread_id': 'preflight-synthetic-check'},
            {'type': 'turn.started'},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': synthetic_raw.strip()}},
            {'type': 'turn.completed', 'usage': {}}
        ]
        (output / 'synthetic_events.jsonl').write_text('\n'.join(json.dumps(ev) for ev in synthetic_events) + '\n')

        def mock_synthetic_runner(argv, pr, cwd, env, to, rec_dir):
            (cwd / 'decision.json').write_text(synthetic_raw)
            (rec_dir / 'events.jsonl').write_text((output / 'synthetic_events.jsonl').read_text())
            return 0

        with tempfile.TemporaryDirectory(prefix='c3-synthetic-check-') as scratch:
            check_policy = CodexPolicy(scratch, condition='c3', process_runner=mock_synthetic_runner)
            res = check_policy(payload)
            if res != synthetic_decision:
                raise RuntimeError('Synthetic C3 software check failed output agreement')
            scratch_rec = (Path(scratch) / 'decision-001' / 'record.json').read_text()
            (output / 'synthetic_record.json').write_text(scratch_rec)

        synthetic_check_meta = {
            'status': 'verified',
            'type': 'offline_synthetic_software_check',
            'model_generated': False,
            'decision_agreement': True,
            'event_agreement': True,
            'assessment_retained': True,
        }

    impl_sources = (
        'humanoid_sim/codex_policy.py',
        'humanoid_sim/visual_policy_runner.py',
        'scripts/audit_codex_c2.py',
        'scripts/run_offline_tests.py',
        'tests/test_codex_policy.py',
        'tests/test_codex_c1_audit.py',
        'tests/test_codex_c2_audit.py',
        'experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json',
    )
    impl_source_hashes = {
        rel_p: hashlib.sha256((ROOT / rel_p).read_bytes()).hexdigest()
        for rel_p in impl_sources
        if (ROOT / rel_p).is_file()
    }

    preflight_record = {
        'status': 'complete',
        'condition': condition,
        'condition_id': condition,
        'protocol_id': protocol_id,
        'protocol_path': str(protocol_path.relative_to(ROOT)),
        'protocol_sha256': protocol_sha256,
        'source_base_commit': '9445fbef35e2944165314d306b4b214ef7d4bd9c',
        'source_commit': git_info['commit'],
        'git_status': git_info['status'],
        'is_dirty': git_info['is_dirty'],
        'implementation_source_sha256': impl_source_hashes,
        'cli_version': cli_info.get('cli_version'),
        'login_method': cli_info.get('login_method'),
        'executable': cli_info.get('executable'),
        'cli_status': cli_info.get('status', 'verified'),
        'model_requested': model,
        'max_actions': max_calls,
        'deadline_s': 25.0,
        'decision_timeout_s': 120.0,
        'demonstration_prompt_sha256': prompt_sha256,
        'static_instruction_sha256': static_instruction_sha256,
        'schema_sha256': schema_sha256,
        'geometry_evidence_sha256': geom_evidence_sha256,
        'input_provenance': input_provenance,
        'isolation_verified': True,
        'model_invocations': 0,
        'physics_steps': 0,
        'config': cli_info.get('config', CONFIG),
        'disabled_features': list(cli_info.get('disabled_features', DISABLED_FEATURES)),
    }
    if synthetic_check_meta is not None:
        preflight_record['synthetic_software_check'] = synthetic_check_meta
    write_json(output / 'preflight.json', preflight_record)

    file_descriptions = {
        'geometry_evidence.json': 'Nominal robot-only hand geometry offsets and bounds serialized with sort_keys=True',
        'observation.png': 'Archived initial observation PNG byte-for-byte identical to C1 seed-820 call 1',
        'preflight.json': 'Preflight execution metadata with base source commit, CLI/config status, implementation hashes, and verification metrics',
        'prompt.txt': 'Full demonstration prompt containing static instructions, C2 geometry paragraph, C3 visual assessment contract, and public observation JSON',
        'public_payload.json': 'Public observation payload extracted from archived seed-820 call 1 excluding private simulator state',
        'schema.json': 'Deterministic C3 structured response schema defining required visual_assessment and command properties',
        'synthetic_decision.json': 'Offline synthetic decision fixture adhering to C3 schema for zero-model verification',
        'synthetic_events.jsonl': 'Offline synthetic Codex CLI events stream fixture corresponding to synthetic_decision',
        'synthetic_record.json': 'Offline synthetic decision record verifying output agreement and assessment retention',
    }
    manifest_files = {}
    for p in sorted(output.iterdir()):
        if p.name == 'manifest.json' or not p.is_file():
            continue
        manifest_files[p.name] = {
            'description': file_descriptions.get(p.name, f'Preflight artifact {p.name}'),
            'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'size_bytes': p.stat().st_size,
        }

    rel_output = str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output)
    manifest_record = {
        'condition': condition,
        'condition_id': condition,
        'protocol_id': protocol_id,
        'protocol_path': str(protocol_path.relative_to(ROOT)),
        'protocol_sha256': protocol_sha256,
        'source_base_commit': '9445fbef35e2944165314d306b4b214ef7d4bd9c',
        'source_commit': git_info['commit'],
        'git_status': git_info['status'],
        'is_dirty': git_info['is_dirty'],
        'implementation_source_sha256': impl_source_hashes,
        'generator_command': f'python -m humanoid_sim.codex_policy --condition {condition} --output {rel_output}',
        'geometry_evidence_sha256': geom_evidence_sha256,
        'schema_sha256': schema_sha256,
        'static_instruction_sha256': static_instruction_sha256,
        'input_provenance': input_provenance,
        'isolation_verified': True,
        'model_invocations': 0,
        'physics_steps': 0,
        'files': manifest_files,
    }
    write_json(output / 'manifest.json', manifest_record)
    return preflight_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--condition', choices=['c1', 'c2', 'c3'], default=DEFAULT_CONDITION,
                        help='Experiment condition: c1 (default), c2, or c3')
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
    if args.condition in ('c1', 'c2', 'c3') and (args.model != MODEL or args.max_calls != 20):
        parser.error(f'{args.condition.upper()} fixes the requested model ({MODEL}) and 20-call cap; declare a successor before changing them')
    _validate_budget(args.max_calls, 25.)

    if not args.execute and not args.probe:
        if args.condition == 'c1':
            info = check_install(executable=args.executable)
            args.output.mkdir(parents=True)
            write_json(args.output / 'preflight.json', info)
            print(json.dumps(info, indent=2))
            return
        else:
            preflight_record = run_preflight(args.output, condition=args.condition,
                                             model=args.model, max_calls=args.max_calls,
                                             executable=args.executable)
            print(json.dumps(preflight_record, indent=2))
            return

    info = check_install(executable=args.executable)
    policy = CodexPolicy(args.output / 'codex', model=args.model, executable=args.executable,
                         condition=args.condition)
    if args.probe:
        args.output.mkdir(parents=True)
        write_json(args.output / 'preflight.json', info)
        if args.condition in ('c2', 'c3'):
            geom_ev = generate_geometry_evidence()
            geom_ev_bytes = serialize_geometry_evidence(geom_ev)
            (args.output / 'geometry_evidence.json').write_bytes(geom_ev_bytes)
        schema = output_schema(args.condition)
        (args.output / 'schema.json').write_bytes(serialize_schema(schema))
        decision = policy(strict_json(args.probe.read_text()))
        write_json(args.output / 'probe.json', {'decision': decision, 'actions_executed': 0, 'condition': args.condition, 'model': args.model})
        print(json.dumps(decision))
        return

    from .environment import Environment
    from .visual import VisualSession, RGBRenderer
    from .visual_policy_runner import VisualPolicySession, run_visual_episode
    protocol = PROTOCOL_PATHS[args.condition]
    protocol_sha256 = hashlib.sha256(protocol.read_bytes()).hexdigest()
    git_info = git_source_info()
    source_commit = git_info['commit']

    geom_evidence_bytes = None
    geom_evidence_sha256 = None
    static_files = {}
    if args.condition in ('c2', 'c3'):
        geom_evidence = generate_geometry_evidence()
        geom_evidence_bytes = serialize_geometry_evidence(geom_evidence)
        geom_evidence_sha256 = hashlib.sha256(geom_evidence_bytes).hexdigest()
        static_files['geometry_evidence.json'] = geom_evidence_bytes

    schema = output_schema(args.condition)
    schema_bytes = serialize_schema(schema)
    schema_sha256 = hashlib.sha256(schema_bytes).hexdigest()
    static_files['schema.json'] = schema_bytes

    static_inst = static_instruction(args.condition)
    static_instruction_sha256 = hashlib.sha256(static_inst.encode('utf-8')).hexdigest()

    env = Environment()
    env.reset(820, randomize=True)
    renderer = RGBRenderer(env, camera='fixed')
    session = VisualPolicySession(VisualSession(env, renderer), max_calls=args.max_calls)
    execution_metadata = {
        'mode': 'codex_chatgpt',
        'offline_only': False,
        'condition': args.condition,
        'condition_id': args.condition,
        'protocol_id': PROTOCOL_IDS[args.condition],
        'protocol_path': str(protocol.relative_to(ROOT)),
        'protocol_sha256': protocol_sha256,
        'source_commit': source_commit,
        'git_status': git_info['status'],
        'is_dirty': git_info['is_dirty'],
        'model_requested': args.model,
        'max_calls': args.max_calls,
        'decision_timeout_s': 120.0,
        'static_instruction_sha256': static_instruction_sha256,
        'schema_sha256': schema_sha256,
        'geometry_evidence_sha256': geom_evidence_sha256,
        'static_files': static_files,
        **info,
    }
    try:
        report = run_visual_episode(args.output, session, policy, max_calls=args.max_calls,
                                    seed=820, controller_name='codex_chatgpt',
                                    execution_metadata=execution_metadata)
        print(json.dumps(report, indent=2))
    finally:
        renderer.close()


if __name__ == '__main__':
    main()
