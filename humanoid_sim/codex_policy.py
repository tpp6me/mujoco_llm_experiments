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

from PIL import Image

from .visual_policy_runner import (
    VISUAL_PROMPT, MalformedResponseError, VisualPolicyError, action_schema,
    allowlist_observation, sanitize_action_for_history, sanitize_response_for_history,
    parse_and_validate_response, strict_json, write_json, _validate_budget,
)

MODEL = 'gpt-5.6-sol'
SUPPORTED_VERSION = 'codex-cli 0.154.0'
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


class CodexPolicyError(VisualPolicyError):
    pass


def child_environment():
    """Allow normal login discovery, never forward API keys or custom endpoints."""
    return {key: os.environ[key] for key in (
        'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR', 'CODEX_HOME'
    ) if key in os.environ}


def public_input(payload):
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
    prompt = VISUAL_PROMPT + DECISION_INSTRUCTION + json.dumps(text, sort_keys=True, allow_nan=False)
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
                 process_runner=run_process):
        if not isinstance(model, str) or not model or model.startswith('-'):
            raise ValueError('Explicit model identifier required')
        if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not 0 < timeout <= 180:
            raise ValueError('Timeout must be in (0, 180] seconds')
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
                  'mode': 'codex_chatgpt' if self.process_runner is run_process else 'mock_codex',
                  'model_requested': self.model, 'timeout_s': self.timeout,
                  'process_started': False}
        write_json(folder / 'record.json', record)
        started = time.monotonic()
        try:
            png, prompt = public_input(payload)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute', action='store_true', help='Run the seed-820 development episode')
    parser.add_argument('--probe', type=Path, help='One signed-in decision on an archived public payload; no action')
    parser.add_argument('--model', default=MODEL)
    parser.add_argument('--max-calls', type=int, default=20)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory')
    if args.execute and args.probe:
        parser.error('Choose episode or archived-image probe')
    if args.execute and (args.model != MODEL or args.max_calls != 20):
        parser.error('C1 fixes the requested model and 20-call cap; declare a successor before changing them')
    _validate_budget(args.max_calls, 25.)
    info = check_install()
    if not args.execute and not args.probe:
        args.output.mkdir(parents=True)
        write_json(args.output / 'preflight.json', info)
        print(json.dumps(info, indent=2))
        return
    policy = CodexPolicy(args.output / 'codex', model=args.model)
    if args.probe:
        args.output.mkdir(parents=True)
        write_json(args.output / 'preflight.json', info)
        decision = policy(strict_json(args.probe.read_text()))
        write_json(args.output / 'probe.json', {'decision': decision, 'actions_executed': 0})
        print(json.dumps(decision))
        return
    from .environment import Environment
    from .visual import VisualSession, RGBRenderer
    from .visual_policy_runner import VisualPolicySession, run_visual_episode
    protocol = Path(__file__).resolve().parents[1] / 'experiments/humanoid-pick-place/protocols/C1.md'
    info['protocol_sha256'] = hashlib.sha256(protocol.read_bytes()).hexdigest()
    env = Environment()
    env.reset(820, randomize=True)
    renderer = RGBRenderer(env, camera='fixed')
    session = VisualPolicySession(VisualSession(env, renderer), max_calls=args.max_calls)
    try:
        report = run_visual_episode(args.output, session, policy, max_calls=args.max_calls,
                                    seed=820, controller_name='codex_chatgpt',
                                    execution_metadata={'mode': 'codex_chatgpt', 'offline_only': False,
                                                        'protocol_id': 'humanoid-codex-c1-development',
                                                        'model_requested': args.model, **info})
        print(json.dumps(report, indent=2))
    finally:
        renderer.close()


if __name__ == '__main__':
    main()
