"""Signed-in CLI boundary tests; subprocess decisions are injected, never live."""
import json
import os
from pathlib import Path
import subprocess
import contextlib
import io
import sys
import tempfile
import unittest
from unittest.mock import patch

from humanoid_sim.codex_policy import (
    CodexPolicy, CodexPolicyError, child_environment, check_install, public_input,
    SUPPORTED_VERSION, DISABLED_CODE_MODE_NOTICE, main,
)
from tests.test_visual_provider_adapter import (
    make_test_png, make_test_observation, make_test_public_payload, MockRenderer,
)
from humanoid_sim.environment import Environment
from humanoid_sim.visual import VisualSession
from humanoid_sim.visual_policy_runner import VisualPolicySession, run_visual_episode


DECISION = {'command': {'action': 'hold', 'arguments': {'seconds': 0.1}}}


def payload():
    return make_test_public_payload(make_test_observation(make_test_png(960, 720)))


def write_result(directory, record_dir, decision=DECISION, extra=None):
    raw = json.dumps(decision)
    (directory / 'decision.json').write_text(raw)
    events = [{'type': 'thread.started', 'thread_id': 'test'}, {'type': 'turn.started'}]
    if extra:
        events.append(extra)
    events += [{'type': 'item.completed', 'item': {
        'type': 'agent_message', 'text': raw}}, {'type': 'turn.completed', 'usage': {}}]
    (record_dir / 'events.jsonl').write_text('\n'.join(map(json.dumps, events)) + '\n')
    return 0


class CodexPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_fresh_public_only_sessions_and_tool_configuration(self):
        scratch = []

        def run(argv, prompt, cwd, env, timeout, record_dir):
            scratch.append(cwd)
            self.assertEqual(set(p.name for p in cwd.iterdir()), {'schema.json', 'observation.png'})
            for flag in ('--ignore-user-config', '--ignore-rules', '--ephemeral', '--strict-config'):
                self.assertIn(flag, argv)
            self.assertIn('forced_login_method="chatgpt"', argv)
            self.assertIn('web_search="disabled"', argv)
            self.assertIn('shell_tool', argv)
            self.assertIn('plugins', argv)
            self.assertIn('multi_agent', argv)
            self.assertNotIn('OPENAI_API_KEY', env)
            self.assertNotIn('PRIVATE_SENTINEL', prompt)
            return write_result(cwd, record_dir)

        p = payload()
        p['instruction'] = 'PRIVATE_SENTINEL'
        p['observation']['ground_truth'] = 'PRIVATE_SENTINEL'
        policy = CodexPolicy(self.root, process_runner=run)
        for _ in range(2):
            self.assertEqual(policy(p), DECISION)
        self.assertNotEqual(*scratch)
        self.assertTrue(all(not d.exists() for d in scratch))
        record = json.loads((self.root / 'decision-002/record.json').read_text())
        self.assertEqual(record['mode'], 'mock_codex')
        self.assertEqual(record['status'], 'completed')
        self.assertEqual(record['tool_items'], 0)

    def test_tool_events_failed_turns_and_output_disagreement_stop(self):
        for kind in ('command_execution', 'mcp_tool_call', 'web_search', 'turn.failed', 'disagreement'):
            with self.subTest(kind=kind):
                def run(argv, prompt, cwd, env, timeout, record_dir):
                    extra = {'type': 'item.completed', 'item': {'type': kind}}
                    if kind == 'turn.failed':
                        extra = {'type': kind}
                    if kind == 'disagreement':
                        write_result(cwd, record_dir)
                        (cwd / 'decision.json').write_text(json.dumps({'command': {'action': 'hold', 'arguments': {'seconds': 0.2}}}))
                        return 0
                    return write_result(cwd, record_dir, extra=extra)
                policy = CodexPolicy(self.root / kind, process_runner=run)
                with self.assertRaises(CodexPolicyError):
                    policy(payload())
                self.assertEqual(policy.calls, 1)
                self.assertEqual(json.loads((self.root / kind / 'decision-001/record.json').read_text())['status'], 'failed')

    def test_timeout_nonzero_missing_and_invalid_output_retain_failure(self):
        for mode in ('timeout', 'nonzero', 'missing', 'invalid', 'interrupt'):
            with self.subTest(mode=mode):
                def run(argv, prompt, cwd, env, timeout, record_dir):
                    if mode == 'timeout':
                        raise subprocess.TimeoutExpired(argv, timeout)
                    if mode == 'interrupt':
                        raise KeyboardInterrupt()
                    if mode == 'nonzero':
                        return 1
                    if mode == 'missing':
                        return 0
                    return write_result(cwd, record_dir, {'command': {'action': 'hold', 'arguments': {'seconds': 99}}})
                policy = CodexPolicy(self.root / mode, process_runner=run)
                with self.assertRaises((Exception, KeyboardInterrupt)):
                    policy(payload())
                status = json.loads((self.root / mode / 'decision-001/record.json').read_text())['status']
                self.assertEqual(status, {'timeout': 'timeout', 'interrupt': 'interrupted'}.get(mode, 'failed'))
                self.assertEqual(policy.calls, 1)

    def test_only_exact_disabled_host_notice_before_turn_is_allowed(self):
        for before in (True, False):
            def run(argv, prompt, cwd, env, timeout, record_dir):
                write_result(cwd, record_dir)
                path = record_dir / 'events.jsonl'
                events = path.read_text().splitlines()
                events.insert(1 if before else 2, json.dumps({'type': 'item.completed', 'item': {
                    'type': 'error', 'message': DISABLED_CODE_MODE_NOTICE}}))
                path.write_text('\n'.join(events))
                return 0
            policy = CodexPolicy(self.root / str(before), process_runner=run)
            if before:
                self.assertEqual(policy(payload()), DECISION)
            else:
                with self.assertRaises(CodexPolicyError):
                    policy(payload())

    def test_corrupt_image_and_identity_mismatch_never_launch(self):
        for mode in ('dimensions', 'hash', 'corrupt'):
            p = payload()
            if mode == 'dimensions':
                p['observation']['camera']['width'] = 12
            elif mode == 'hash':
                p['observation']['rgb_sha256'] = '0' * 64
            else:
                p['observation']['rgb_png_base64'] = 'broken'
            with self.subTest(mode=mode), patch('humanoid_sim.codex_policy.run_process') as run:
                policy = CodexPolicy(self.root / mode, process_runner=run)
                with self.assertRaises(Exception):
                    policy(p)
                run.assert_not_called()

    def test_api_environment_not_forwarded(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'secret', 'OPENAI_BASE_URL': 'secret', 'GEMINI_API_KEY': 'secret'}):
            self.assertFalse(any('secret' == v for v in child_environment().values()))

    def test_requires_reviewed_cli_and_chatgpt_login(self):
        def result(stdout='', stderr='', returncode=0):
            return subprocess.CompletedProcess([], returncode, stdout, stderr)
        for responses in ([result('old-cli')], [result(SUPPORTED_VERSION), result('Logged in using an API key')]):
            with patch('humanoid_sim.codex_policy.subprocess.run', side_effect=responses):
                with self.assertRaises(CodexPolicyError):
                    check_install()
        with patch('humanoid_sim.codex_policy.subprocess.run', side_effect=[result(SUPPORTED_VERSION), result(stderr='Logged in using ChatGPT')]):
            self.assertEqual(check_install()['login_method'], 'chatgpt')

    def test_budget_and_call_cap(self):
        for remaining in (0, 21, True):
            p = payload()
            p['remaining_actions'] = remaining
            with self.assertRaises(ValueError):
                public_input(p)
        policy = CodexPolicy(self.root)
        policy.calls = 20
        with self.assertRaises(CodexPolicyError):
            policy(payload())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_guarded_runner_records_condition_and_preserves_mock_identity(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=1)
        def run(argv, prompt, cwd, environment, timeout, record_dir):
            return write_result(cwd, record_dir)
        folder = self.root / 'episode'
        policy = CodexPolicy(folder / 'codex', process_runner=run)
        report = run_visual_episode(folder, session, policy, max_calls=1, seed=820,
            controller_name='mock_codex', execution_metadata={
                'offline_only': True, 'protocol_id': 'codex-boundary-unit-test'})
        self.assertEqual(report['provenance']['protocol_id'], 'codex-boundary-unit-test')
        self.assertEqual(report['provenance']['task'], 'codex-boundary-unit-test')
        self.assertTrue(report['provenance']['offline_only'])
        self.assertIn('humanoid_sim/codex_policy.py', report['provenance']['source_sha256'])
        self.assertEqual(policy.calls, 1)
        self.assertAlmostEqual(env.data.time, 0.6, places=5)

    def test_c1_rejects_changed_condition_before_login_or_execution(self):
        for extra in (['--model', 'different-model'], ['--max-calls', '1']):
            with patch.object(sys, 'argv', ['codex_policy', '--execute', '--output', str(self.root / 'new'), *extra]), patch('humanoid_sim.codex_policy.check_install') as check, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
                check.assert_not_called()
                self.assertFalse((self.root / 'new').exists())


if __name__ == '__main__':
    unittest.main()
