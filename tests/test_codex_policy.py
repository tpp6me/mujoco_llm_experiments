import copy
import hashlib
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
import zipfile

import mujoco
from types import SimpleNamespace

from humanoid_sim.codex_policy import (
    CodexPolicy, CodexPolicyError, child_environment, check_install, public_input,
    SUPPORTED_VERSION, DISABLED_CODE_MODE_NOTICE, main,
    C2_INSTRUCTION, C3_INSTRUCTION, C3_VISUAL_PROMPT, C3_DECISION_INSTRUCTION,
    CONDITIONS, DEFAULT_CONDITION, MODEL, serialize_geometry_evidence,
    output_schema, serialize_schema, static_instruction,
    nominal_open_hand_geometry, verify_nominal_bounds_enclosure, generate_geometry_evidence,
    run_preflight, PROTOCOL_PATHS, PROTOCOL_IDS, ROOT,
)
from tests.test_visual_provider_adapter import (
    make_test_png, make_test_observation, make_test_public_payload, MockRenderer,
)
from humanoid_sim.environment import Environment
from humanoid_sim.visual import VisualSession
from humanoid_sim.visual_policy_runner import (
    VisualPolicySession, run_visual_episode,
    c3_response_schema, parse_and_validate_c3_response, validate_visual_assessment,
    parse_and_validate_response, MalformedResponseError,
)

ARCHIVE_PATH = ROOT / 'experiments/humanoid-pick-place/results/codex_C2_episode.zip'


class FakeSession:
    """Injected test double backed by archived public observations from C2 episode.

    Guarantees zero Environment instantiation, zero simulator resets, and zero physics steps.
    """
    def __init__(self, sim_time=0.5):
        with zipfile.ZipFile(ARCHIVE_PATH) as z:
            self.obs = json.loads(z.read('seed-820/call_001.json'))['request']['observation']
        self.obs['time_s'] = float(sim_time)
        self.env = SimpleNamespace(data=SimpleNamespace(time=float(sim_time)))
        self.executed_requests = []

    def capture(self):
        return copy.deepcopy(self.obs)

    def execute(self, oid, req):
        self.executed_requests.append(copy.deepcopy(req))
        duration = req.get('arguments', {}).get('seconds', 0.1) if isinstance(req, dict) and 'arguments' in req else 0.1
        start_t = self.obs['time_s']
        end_t = start_t + duration
        self.obs['time_s'] = end_t
        self.env.data.time = end_t
        return {
            'status': 'completed',
            'start_time_s': start_t,
            'end_time_s': end_t,
            'request_id': req.get('request_id', f'req-{len(self.executed_requests):03d}') if isinstance(req, dict) else 'req-001',
        }


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

        p_init = patch('humanoid_sim.environment.Environment.__init__', side_effect=AssertionError('No Environment.__init__ allowed in offline tests'))
        p_reset = patch('humanoid_sim.environment.Environment.reset', side_effect=AssertionError('No Environment.reset allowed in offline tests'))
        p_step = patch('mujoco.mj_step', side_effect=AssertionError('No mujoco.mj_step allowed in offline tests'))
        p_step1 = patch('mujoco.mj_step1', side_effect=AssertionError('No mujoco.mj_step1 allowed in offline tests'))
        p_step2 = patch('mujoco.mj_step2', side_effect=AssertionError('No mujoco.mj_step2 allowed in offline tests'))
        p_init.start()
        p_reset.start()
        p_step.start()
        p_step1.start()
        p_step2.start()
        self.addCleanup(p_init.stop)
        self.addCleanup(p_reset.stop)
        self.addCleanup(p_step.stop)
        self.addCleanup(p_step1.stop)
        self.addCleanup(p_step2.stop)

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
        session = FakeSession(sim_time=0.5)
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
        self.assertAlmostEqual(session.env.data.time, 0.6, places=5)

    def test_default_runner_operation_and_report_retention(self):
        # R1: Default execution_metadata=None must not raise UnboundLocalError and must write report.json
        folder = self.root / 'default_run'
        session = FakeSession(sim_time=0.5)
        policy = lambda p: {'command': {'action': 'hold', 'arguments': {'seconds': 0.1}}}
        report = run_visual_episode(folder, session, policy, max_calls=1)

        self.assertTrue((folder / 'report.json').is_file())
        self.assertEqual(report['termination_reason'], 'action_limit')
        self.assertEqual(report['model_calls'], 1)
        self.assertEqual(report['completed_actions'], 1)
        self.assertEqual(report['errors'], 0)
        self.assertIn('provenance', report)
        self.assertNotIn('visual_assessments', report)

    def test_default_runner_failure_and_interruption_retains_report(self):
        # R1: Failure or interruption under execution_metadata=None must retain report.json
        folder_fail = self.root / 'default_fail'
        session_fail = FakeSession(sim_time=0.5)
        def failing_policy(p):
            raise MalformedResponseError('Invalid command syntax')

        report_fail = run_visual_episode(folder_fail, session_fail, failing_policy, max_calls=1)
        self.assertTrue((folder_fail / 'report.json').is_file())
        self.assertEqual(report_fail['termination_reason'], 'malformed_response')
        self.assertEqual(report_fail['errors'], 1)
        self.assertEqual(report_fail['completed_actions'], 0)

        folder_intr = self.root / 'default_intr'
        session_intr = FakeSession(sim_time=0.5)
        def interrupting_policy(p):
            raise KeyboardInterrupt('User interruption')

        with self.assertRaises(KeyboardInterrupt):
            run_visual_episode(folder_intr, session_intr, interrupting_policy, max_calls=1)
        self.assertTrue((folder_intr / 'report.json').is_file())
        report_intr = json.loads((folder_intr / 'report.json').read_text())
        self.assertEqual(report_intr['termination_reason'], 'interrupted')
        self.assertEqual(report_intr['errors'], 1)

    def test_c1_rejects_changed_condition_before_login_or_execution(self):
        for extra in (['--model', 'different-model'], ['--max-calls', '1']):
            with patch.object(sys, 'argv', ['codex_policy', '--execute', '--output', str(self.root / 'new'), *extra]), patch('humanoid_sim.codex_policy.check_install') as check, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
                check.assert_not_called()
                self.assertFalse((self.root / 'new').exists())

    def test_c1_prompt_preservation_and_c2_paragraph_inclusion(self):
        p = payload()
        p['history'] = [{'action': {'action': 'hold', 'arguments': {'seconds': 0.1}},
                         'response': {'status': 'completed', 'robot_state': p['observation']['robot_state']}}]
        p['remaining_actions'] = 19
        p['remaining_time_s'] = 24.0

        # C1 prompt (explicit and default)
        _, c1_prompt_default = public_input(p)
        _, c1_prompt_explicit = public_input(p, condition='c1')
        self.assertEqual(c1_prompt_default, c1_prompt_explicit)
        self.assertNotIn('Additional robot geometry and feedback contract:', c1_prompt_default)
        self.assertNotIn('nominal collision', c1_prompt_default)

        # C2 prompt
        _, c2_prompt = public_input(p, condition='c2')
        self.assertIn('Additional robot geometry and feedback contract:', c2_prompt)
        self.assertIn(C2_INSTRUCTION, c2_prompt)

        # C2 text is inserted right before the JSON observation string
        json_prefix = '{"history":'
        self.assertIn(json_prefix, c2_prompt)
        c2_idx = c2_prompt.index(C2_INSTRUCTION)
        json_idx = c2_prompt.index(json_prefix)
        self.assertEqual(c2_idx + len(C2_INSTRUCTION), json_idx)

        # Removing C2_INSTRUCTION yields exact C1 prompt bytes
        reconstructed_c1 = c2_prompt[:c2_idx] + c2_prompt[json_idx:]
        self.assertEqual(reconstructed_c1, c1_prompt_explicit)

        # Verify C2_INSTRUCTION matches exact code block in C2_PROPOSAL.md
        c2_proposal = (ROOT / 'experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md').read_text()
        lines = c2_proposal.splitlines()
        cb = [i for i, l in enumerate(lines) if l.startswith('```')]
        expected_c2 = '\n'.join(lines[cb[0]+1:cb[1]]) + '\n'
        self.assertEqual(C2_INSTRUCTION, expected_c2)

        # Verify C1 prompt against archived C1 episode prompt prefix
        with zipfile.ZipFile(ROOT / 'experiments/humanoid-pick-place/results/codex_C1_episode.zip') as z:
            archived = z.read('seed-820/codex/decision-001/prompt.txt').decode()
        archived_inst_end = archived.index('{"history":')
        c1_inst_end = c1_prompt_default.index('{"history":')
        self.assertEqual(c1_prompt_default[:c1_inst_end], archived[:archived_inst_end])

    def test_private_field_exclusion_and_payload_isolation(self):
        p = payload()
        p['instruction'] = 'PRIVATE_INSTRUCTION'
        p['observation']['ground_truth'] = {'object_xyz': [0.24, -0.18, 0.76]}
        p['observation']['oracle_pose'] = [0.24, -0.18, 0.76, 1, 0, 0, 0]
        p['oracle_score'] = {'penetration_m': 0.005}
        p['evaluator_report'] = {'placement': False}
        p['history'] = [{'action': {'action': 'hold', 'arguments': {'seconds': 0.1}},
                         'response': {'status': 'completed', 'ground_truth_contacts': [1, 2, 3],
                                      'robot_state': p['observation']['robot_state']}}]

        for cond in CONDITIONS:
            _, prompt = public_input(p, condition=cond)
            self.assertNotIn('PRIVATE_INSTRUCTION', prompt)
            self.assertNotIn('ground_truth', prompt)
            self.assertNotIn('oracle_pose', prompt)
            self.assertNotIn('oracle_score', prompt)
            self.assertNotIn('evaluator_report', prompt)
            self.assertNotIn('ground_truth_contacts', prompt)

        # Child environment excludes credentials
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'secret-openai',
            'OPENAI_BASE_URL': 'https://custom.endpoint',
            'GEMINI_API_KEY': 'secret-gemini',
            'ANTHROPIC_API_KEY': 'secret-anthropic',
        }):
            env = child_environment()
            for key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'GEMINI_API_KEY', 'ANTHROPIC_API_KEY'):
                self.assertNotIn(key, env)

    def test_condition_and_settings_mismatches_rejected(self):
        # Invalid condition in public_input and CodexPolicy
        with self.assertRaises(ValueError):
            public_input(payload(), condition='c4')
        with self.assertRaises(ValueError):
            CodexPolicy(self.root, condition='invalid')

        # CLI rejects invalid condition
        with patch.object(sys, 'argv', ['codex_policy', '--output', str(self.root / 'invalid_cond'), '--condition', 'c4']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main()

        # CLI rejects altered model and max-calls for C2 and C3
        for cond in ('c2', 'c3'):
            for extra in (['--model', 'different-model'], ['--max-calls', '1']):
                with patch.object(sys, 'argv', ['codex_policy', '--condition', cond, '--output', str(self.root / f'new_{cond}'), *extra]), patch('humanoid_sim.codex_policy.check_install') as check, contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        main()
                    check.assert_not_called()
                    self.assertFalse((self.root / f'new_{cond}').exists())

        # run_visual_episode rejects mismatched condition and protocol_id
        session = FakeSession()
        policy = CodexPolicy(self.root / 'codex', condition='c1')

        with self.assertRaisesRegex(ValueError, 'Mismatched condition and protocol_id'):
            run_visual_episode(self.root / 'ep1', session, policy, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c1',
                                                   'protocol_id': 'humanoid-codex-c2-development'})

        with self.assertRaisesRegex(ValueError, 'Mismatched condition and protocol_id'):
            run_visual_episode(self.root / 'ep2', session, policy, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c2',
                                                   'protocol_id': 'humanoid-codex-c1-development'})

        with self.assertRaisesRegex(ValueError, 'Mismatched condition and protocol_id'):
            run_visual_episode(self.root / 'ep_c3_proto_mismatch', session, policy, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c3',
                                                   'protocol_id': 'humanoid-codex-c2-development'})

        # run_visual_episode rejects conflicting condition and condition_id
        with self.assertRaisesRegex(ValueError, 'Conflicting condition'):
            run_visual_episode(self.root / 'ep_conflict', session, policy, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c2', 'condition_id': 'c1',
                                                   'protocol_id': 'humanoid-codex-c2-development'})

        with self.assertRaisesRegex(ValueError, 'Conflicting condition'):
            run_visual_episode(self.root / 'ep_conflict_c3', session, policy, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c3', 'condition_id': 'c2',
                                                   'protocol_id': 'humanoid-codex-c3-development'})

        # run_visual_episode rejects mismatch between policy condition and metadata condition
        policy_c2 = CodexPolicy(self.root / 'codex_c2', condition='c2')
        with self.assertRaisesRegex(ValueError, 'Mismatched model callable condition'):
            run_visual_episode(self.root / 'ep3', session, policy_c2, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c1',
                                                   'protocol_id': 'humanoid-codex-c1-development'})

        policy_c3 = CodexPolicy(self.root / 'codex_c3', condition='c3')
        with self.assertRaisesRegex(ValueError, 'Mismatched model callable condition'):
            run_visual_episode(self.root / 'ep3_c3', session, policy_c3, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c2',
                                                   'protocol_id': 'humanoid-codex-c2-development'})

        # Protocol with no condition field rejects callable with mismatched condition
        with self.assertRaisesRegex(ValueError, 'Mismatched model callable condition'):
            run_visual_episode(self.root / 'ep_proto_only', session, policy_c2, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True,
                                                   'protocol_id': 'humanoid-codex-c1-development'})

        # Model and timeout mismatches rejected before capture
        class MismatchedStub:
            condition = 'c3'
            model = 'other-model'
            timeout = 180.0
            def __call__(self, p):
                raise AssertionError('Callable reached despite setting mismatch')

        with self.assertRaisesRegex(ValueError, 'Mismatched model callable model'):
            run_visual_episode(self.root / 'ep_model_mismatch', session, MismatchedStub(), max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c3', 'condition_id': 'c3',
                                                   'protocol_id': 'humanoid-codex-c3-development',
                                                   'model_requested': 'gpt-5.6-sol'})

        class TimeoutStub:
            condition = 'c3'
            model = 'gpt-5.6-sol'
            timeout = 180.0
            def __call__(self, p):
                raise AssertionError('Callable reached despite timeout mismatch')

        with self.assertRaisesRegex(ValueError, 'Mismatched model callable timeout'):
            run_visual_episode(self.root / 'ep_timeout_mismatch', session, TimeoutStub(), max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c3', 'condition_id': 'c3',
                                                   'protocol_id': 'humanoid-codex-c3-development',
                                                   'model_requested': 'gpt-5.6-sol'})

        # CLI probe path rejects altered model for both c1 and c2
        dummy_probe = self.root / 'dummy_probe.json'
        dummy_probe.write_text('{}')
        for cond in ('c1', 'c2', 'c3'):
            with patch.object(sys, 'argv', ['codex_policy', '--probe', str(dummy_probe),
                                            '--condition', cond, '--output', str(self.root / f'probe_{cond}'),
                                            '--model', 'different-model']), \
                 patch('humanoid_sim.codex_policy.check_install') as check, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
                check.assert_not_called()
                self.assertFalse((self.root / f'probe_{cond}').exists())

    def test_geometry_nominal_bounds_and_enclosure_verification(self):
        geom = nominal_open_hand_geometry()
        self.assertIn('nominal site [.24,-.18,.94]', geom['source'])
        self.assertEqual(len(geom['world_offset_min_m']), 3)
        self.assertEqual(len(geom['world_offset_max_m']), 3)

        # Enclosure verification
        verification = verify_nominal_bounds_enclosure(geom)
        self.assertEqual(verification['status'], 'verified_enclosed')
        self.assertTrue(verification['posture_specific'])
        self.assertEqual(verification['site'], 'right_grasp')
        self.assertEqual(verification['orientation'], 'downward')
        self.assertEqual(verification['hand_closure'], 0.0)

        # All axes strictly enclosed with positive margins
        for axis in ('x', 'y', 'z'):
            self.assertTrue(verification['axes'][axis]['enclosed'])
            self.assertGreater(verification['axes'][axis]['min_margin_m'], 0)
            self.assertGreater(verification['axes'][axis]['max_margin_m'], 0)

        # Failure when bounds are violated
        bad_geom = {'world_offset_min_m': [-0.080, -0.040, -0.070],
                    'world_offset_max_m': [0.050, 0.040, 0.080]}
        with self.assertRaises(ValueError):
            verify_nominal_bounds_enclosure(bad_geom)

        evidence = generate_geometry_evidence()
        self.assertEqual(evidence['status'], 'verified')
        self.assertEqual(evidence['contract_type'], 'static_robot_only_nominal_open_hand_geometry')
        self.assertTrue(evidence['posture']['posture_specific'])

    def test_geometry_altered_object_truth_cannot_affect_contract(self):
        geom_baseline = nominal_open_hand_geometry()
        evidence_baseline = generate_geometry_evidence()

        # Modify scene XML by moving object far away and changing its size
        import xml.etree.ElementTree as ET
        tree = ET.parse(ROOT / 'scenes/g1_pick_place.xml')
        root = tree.getroot()
        root.find('compiler').set('meshdir', str(ROOT / 'models/g1/assets'))
        obj = root.find(".//body[@name='red_block']")
        obj.set('pos', '10.0 -20.0 30.0')
        geom = obj.find('geom')
        geom.set('size', '0.5 0.5 0.5')
        geom.set('mass', '50.0')

        tmp_scene = self.root / 'modified_scene.xml'
        tree.write(tmp_scene)

        geom_modified = nominal_open_hand_geometry(scene_xml=tmp_scene)
        evidence_modified = generate_geometry_evidence(geom_modified)

        # Geometry and evidence are bit-for-bit identical despite altered object truth
        self.assertEqual(geom_baseline['world_offset_min_m'], geom_modified['world_offset_min_m'])
        self.assertEqual(geom_baseline['world_offset_max_m'], geom_modified['world_offset_max_m'])
        self.assertEqual(evidence_baseline, evidence_modified)

    def test_geometry_distinguishes_occupied_bounds_from_grasp_cavity_and_safe_path(self):
        import mujoco
        import numpy as np
        from humanoid_sim.environment import ARM_NAMES
        from humanoid_sim.scene import SCENE
        from types import SimpleNamespace
        from humanoid_sim.codex_policy import hand_collision_bounds
        model = mujoco.MjModel.from_xml_path(str(SCENE))
        data = mujoco.MjData(model)

        # 1. Occupied bounds enclose solid geometry, not an empty grasp cavity:
        # Placing an object inside the open hand's occupied bounds produces physical contact
        # with right_hand geoms.
        hand_joints = [model.joint(name).id for name in ('right_hand_thumb_0_joint', 'right_hand_thumb_1_joint',
                       'right_hand_thumb_2_joint', 'right_hand_middle_0_joint', 'right_hand_middle_1_joint',
                       'right_hand_index_0_joint', 'right_hand_index_1_joint')]
        for j in hand_joints:
            data.qpos[model.jnt_qposadr[j]] = 0.0

        # Position arm downward ready
        joints = np.array([model.joint(name).id for name in ARM_NAMES])
        env = SimpleNamespace(model=model, data=data, arm_joints=joints,
                              arm_q=model.jnt_qposadr[joints], arm_v=model.jnt_dofadr[joints],
                              arm_a=np.array([model.actuator(name).id for name in ARM_NAMES]),
                              site=model.site('right_grasp').id)
        data.qpos[env.arm_q] = Environment.solve(env, [.24, -.18, .94])
        mujoco.mj_forward(model, data)

        hand_geom_ids = [g for g in range(model.ngeom)
                         if model.body(int(model.geom_bodyid[g])).name.startswith('right_hand_')
                         and (model.geom_contype[g] or model.geom_conaffinity[g])]
        target_geom = hand_geom_ids[0]
        target_pos = data.geom_xpos[target_geom]
        qadr = model.jnt_qposadr[model.joint('object_free').id]
        data.qpos[qadr:qadr+3] = target_pos
        data.qpos[qadr+3:qadr+7] = [1, 0, 0, 0]
        mujoco.mj_forward(model, data)

        object_geom_id = model.geom('object').id
        penetrations = [c for c in data.contact if {c.geom1, c.geom2} & set(hand_geom_ids) and object_geom_id in (c.geom1, c.geom2)]
        self.assertGreater(len(penetrations), 0, 'Object placed inside occupied bounds must collide with hand links')

        # 2. Grasp site target above table is not a safe path:
        # At grasp site Z=0.755 m (above table Z=0.700 m), lowest finger vertices extend below table Z=0.700 m
        data.qpos[env.arm_q] = Environment.solve(env, [.25, -.18, .755])
        mujoco.mj_forward(model, data)
        bounds = hand_collision_bounds(model, data, env.site)
        lowest_z = min(b['world_offset_min_m'][2] for b in bounds) + data.site_xpos[env.site][2]
        self.assertLess(lowest_z, 0.700, 'Fingertip vertices extend below table surface when site Z=0.755 m')

    def test_offline_preflight_zero_model_invocations_and_artifacts(self):
        orig_popen = subprocess.Popen

        def safe_popen(cmd, *args, **kwargs):
            if any(arg == 'exec' for arg in cmd):
                raise AssertionError('Codex exec decision must not be invoked in preflight')
            return orig_popen(cmd, *args, **kwargs)

        preflight_dir = self.root / 'c2_preflight'
        # Offline preflight must succeed even when Codex CLI login is unavailable and without graphics
        with patch('humanoid_sim.codex_policy.CodexPolicy.__call__', side_effect=AssertionError('No model invocation allowed')), \
             patch('humanoid_sim.codex_policy.run_process', side_effect=AssertionError('No process execution allowed')), \
             patch('humanoid_sim.codex_policy.check_install', side_effect=RuntimeError('Codex CLI login unavailable')), \
             patch('humanoid_sim.visual.RGBRenderer', side_effect=AssertionError('No renderer invocation allowed')), \
             patch('subprocess.Popen', side_effect=safe_popen), \
             patch('mujoco.mj_step', side_effect=AssertionError('No physics step allowed')):
            record = run_preflight(preflight_dir, condition='c2')

        self.assertEqual(record['status'], 'complete')
        self.assertEqual(record['condition'], 'c2')
        self.assertEqual(record['condition_id'], 'c2')
        self.assertEqual(record['protocol_id'], 'humanoid-codex-c2-development')
        self.assertEqual(record['model_invocations'], 0)
        self.assertEqual(record['physics_steps'], 0)
        self.assertTrue(record['isolation_verified'])

        # Verify artifact files exist and have non-zero size
        for fname in ('preflight.json', 'geometry_evidence.json', 'public_payload.json', 'prompt.txt', 'observation.png'):
            p = preflight_dir / fname
            self.assertTrue(p.is_file(), f'Missing preflight artifact: {fname}')
            self.assertGreater(p.stat().st_size, 0)

        # Verify geometry evidence file hash matches record hash
        written_geom_hash = hashlib.sha256((preflight_dir / 'geometry_evidence.json').read_bytes()).hexdigest()
        self.assertEqual(written_geom_hash, record['geometry_evidence_sha256'])

        # Verify prompt contains C2 instruction and excludes private fields
        prompt_text = (preflight_dir / 'prompt.txt').read_text()
        self.assertIn(C2_INSTRUCTION, prompt_text)
        self.assertNotIn('ground_truth', prompt_text)

        # Refusal on existing directory
        with self.assertRaisesRegex(ValueError, 'must be new'):
            run_preflight(preflight_dir, condition='c2')

    def test_default_c1_local_check_preserves_graphics_free_behavior(self):
        fake_info = {'cli_version': SUPPORTED_VERSION, 'login_method': 'chatgpt',
                     'executable': 'mock-codex', 'config': {}, 'disabled_features': []}
        c1_dir = self.root / 'c1_check'
        with patch.object(sys, 'argv', ['codex_policy', '--condition', 'c1', '--output', str(c1_dir)]), \
             patch('humanoid_sim.codex_policy.check_install', return_value=fake_info), \
             patch('humanoid_sim.visual.RGBRenderer', side_effect=AssertionError('No graphics permitted in local check')), \
             patch('humanoid_sim.codex_policy.run_preflight', side_effect=AssertionError('C1 must not run synthesized preflight')), \
             contextlib.redirect_stdout(io.StringIO()):
            main()

        self.assertTrue((c1_dir / 'preflight.json').is_file())
        written = json.loads((c1_dir / 'preflight.json').read_text())
        self.assertEqual(written['cli_version'], SUPPORTED_VERSION)

    def test_geometry_evidence_written_and_retained_on_interruption(self):
        class InterruptStub:
            condition = 'c2'
            model = MODEL
            timeout = 120.0
            def __call__(self, p):
                raise KeyboardInterrupt('Simulated user interruption during episode')

        session = FakeSession()
        ep_dir = self.root / 'interrupted_ep'
        geom_ev = generate_geometry_evidence()
        geom_bytes = serialize_geometry_evidence(geom_ev)
        geom_hash = hashlib.sha256(geom_bytes).hexdigest()

        with self.assertRaises(KeyboardInterrupt):
            run_visual_episode(ep_dir, session, InterruptStub(), max_calls=2, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={
                                   'offline_only': True, 'condition': 'c2', 'condition_id': 'c2',
                                   'protocol_id': 'humanoid-codex-c2-development',
                                   'protocol_path': 'experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md',
                                   'model_requested': MODEL,
                                   'decision_timeout_s': 120.0,
                                   'geometry_evidence_sha256': geom_hash,
                                   'static_files': {'geometry_evidence.json': geom_bytes},
                               })

        # geometry_evidence.json must exist despite interruption and match hash
        self.assertTrue((ep_dir / 'geometry_evidence.json').is_file())
        file_hash = hashlib.sha256((ep_dir / 'geometry_evidence.json').read_bytes()).hexdigest()
        self.assertEqual(file_hash, geom_hash)

        # report.json must be written by finally block with matching provenance
        self.assertTrue((ep_dir / 'report.json').is_file())
        report = json.loads((ep_dir / 'report.json').read_text())
        self.assertEqual(report['provenance']['geometry_evidence_sha256'], geom_hash)

    def test_c3_prompt_preservation_and_exact_proposed_replacements(self):
        p = payload()
        p['history'] = [{'action': {'action': 'hold', 'arguments': {'seconds': 0.1}},
                         'response': {'status': 'completed', 'robot_state': p['observation']['robot_state']}}]
        p['remaining_actions'] = 19
        p['remaining_time_s'] = 24.0

        # C1 prompt preservation (explicit vs default)
        _, c1_default = public_input(p)
        _, c1_explicit = public_input(p, condition='c1')
        self.assertEqual(c1_default, c1_explicit)

        # C2 prompt preservation
        _, c2_prompt = public_input(p, condition='c2')
        self.assertIn(C2_INSTRUCTION, c2_prompt)
        self.assertNotIn('C3 visual assessment contract:', c2_prompt)

        # C3 prompt construction
        _, c3_prompt = public_input(p, condition='c3')

        # Replacement 1: VISUAL_PROMPT replacement
        self.assertIn('Return only the structured C3 response specified below. Do not claim task success.', c3_prompt)
        self.assertNotIn('Return only the structured action. Do not claim success in prose.', c3_prompt)

        # Replacement 2: DECISION_INSTRUCTION replacement
        self.assertIn('Return exactly one JSON object matching the supplied C3 output schema.', c3_prompt)
        self.assertNotIn('Return exactly one JSON command matching the supplied output schema.', c3_prompt)

        # C3 instruction appended after C2 instruction, before JSON observation
        self.assertIn(C2_INSTRUCTION, c3_prompt)
        self.assertIn(C3_INSTRUCTION, c3_prompt)
        c2_pos = c3_prompt.index(C2_INSTRUCTION)
        c3_pos = c3_prompt.index(C3_INSTRUCTION)
        json_pos = c3_prompt.index('{"history":')
        self.assertEqual(c2_pos + len(C2_INSTRUCTION), c3_pos)
        self.assertEqual(c3_pos + len(C3_INSTRUCTION), json_pos)

        # Verify C3_INSTRUCTION matches exact code block in C3_PROPOSAL.md
        c3_proposal = (ROOT / 'experiments/humanoid-pick-place/protocols/C3_PROPOSAL.md').read_text()
        lines = c3_proposal.splitlines()
        cb = [i for i, l in enumerate(lines) if l.startswith('```')]
        expected_c3 = '\n'.join(lines[cb[0]+1:cb[1]]) + '\n'
        self.assertEqual(C3_INSTRUCTION, expected_c3)

        # Hashes: static instruction hash vs per-decision full prompt hash
        static_c3 = static_instruction('c3')
        static_hash = hashlib.sha256(static_c3.encode('utf-8')).hexdigest()
        full_hash = hashlib.sha256(c3_prompt.encode('utf-8')).hexdigest()
        self.assertNotEqual(static_hash, full_hash)

        # Changing dynamic observation changes prompt_sha256 but leaves static_instruction_sha256 unchanged
        p2 = payload()
        p2['remaining_actions'] = 18
        _, c3_prompt2 = public_input(p2, condition='c3')
        full_hash2 = hashlib.sha256(c3_prompt2.encode('utf-8')).hexdigest()
        self.assertNotEqual(full_hash, full_hash2)
        self.assertEqual(hashlib.sha256(static_instruction('c3').encode('utf-8')).hexdigest(), static_hash)

    def test_c3_strict_response_schema_definition(self):
        schema = c3_response_schema()
        disk_schema_path = ROOT / 'experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json'
        self.assertTrue(disk_schema_path.is_file())
        disk_schema = json.loads(disk_schema_path.read_text())
        self.assertEqual(schema, disk_schema)

        # Output schema helper matches
        self.assertEqual(output_schema('c3'), schema)

        # Strict JSON schema constraints
        self.assertEqual(schema['type'], 'object')
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['required'], ['visual_assessment', 'command'])

        va_schema = schema['properties']['visual_assessment']
        self.assertEqual(va_schema['type'], 'object')
        self.assertFalse(va_schema['additionalProperties'])
        self.assertEqual(va_schema['required'], ['block_visibility', 'block_relative_to_fingers'])

        vis = va_schema['properties']['block_visibility']
        self.assertEqual(vis['type'], 'string')
        self.assertEqual(vis['enum'], ['visible', 'partly_visible', 'not_visible', 'uncertain'])

        rel = va_schema['properties']['block_relative_to_fingers']
        self.assertEqual(rel['type'], 'string')
        self.assertEqual(rel['enum'], ['between', 'separate', 'uncertain'])

        # Deterministic serialization
        serialized = serialize_schema(schema)
        self.assertIsInstance(serialized, bytes)
        reloaded = json.loads(serialized.decode('utf-8'))
        self.assertEqual(reloaded, schema)

    def test_c3_valid_assessment_retention_and_unchanged_command_forwarding(self):
        valid_response = {
            'visual_assessment': {
                'block_visibility': 'visible',
                'block_relative_to_fingers': 'separate',
            },
            'command': {
                'action': 'hold',
                'arguments': {
                    'seconds': 0.1,
                },
            },
        }

        # Parsing directly
        parsed = parse_and_validate_c3_response(valid_response)
        self.assertEqual(parsed['visual_assessment'], valid_response['visual_assessment'])
        self.assertEqual(parsed['command'], valid_response['command'])

        # parse_and_validate_response returns only command
        cmd_only = parse_and_validate_response(valid_response, condition='c3')
        self.assertEqual(cmd_only, valid_response['command'])
        self.assertNotIn('visual_assessment', cmd_only)

        # Integration in run_visual_episode
        session = FakeSession()

        class C3MockPolicy:
            condition = 'c3'
            model = MODEL
            timeout = 120.0
            def __call__(self, p):
                return valid_response

        ep_dir = self.root / 'c3_valid_ep'
        schema_hash = hashlib.sha256(serialize_schema(c3_response_schema())).hexdigest()
        report = run_visual_episode(
            ep_dir, session, C3MockPolicy(), max_calls=1, seed=820,
            controller_name='mock_codex',
            execution_metadata={
                'offline_only': True,
                'condition': 'c3',
                'condition_id': 'c3',
                'protocol_id': 'humanoid-codex-c3-development',
                'model_requested': MODEL,
                'decision_timeout_s': 120.0,
                'schema_sha256': schema_hash,
            },
        )

        # Only command reached session.execute (no visual_assessment in action_request)
        self.assertEqual(len(session.executed_requests), 1)
        self.assertEqual(session.executed_requests[0]['action'], 'hold')
        self.assertEqual(session.executed_requests[0]['arguments'], {'seconds': 0.1})
        self.assertNotIn('visual_assessment', session.executed_requests[0])

        # Report retains visual_assessments
        self.assertIn('visual_assessments', report)
        self.assertEqual(len(report['visual_assessments']), 1)
        va_record = report['visual_assessments'][0]
        self.assertEqual(va_record['visual_assessment'], valid_response['visual_assessment'])

        # Report provenance includes schema_sha256
        self.assertEqual(report['provenance']['schema_sha256'], schema_hash)

        # Call record on disk retains both visual_assessment and command
        rec = json.loads((ep_dir / 'call_001.json').read_text())
        self.assertEqual(rec['visual_assessment'], valid_response['visual_assessment'])
        self.assertEqual(rec['command'], valid_response['command'])

    def test_c3_malformed_response_failure_accounting(self):
        valid_cmd = {'action': 'hold', 'arguments': {'seconds': 0.1}}
        valid_va = {'block_visibility': 'visible', 'block_relative_to_fingers': 'separate'}

        # Missing visual_assessment
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_c3_response({'command': valid_cmd})

        # Missing command
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_c3_response({'visual_assessment': valid_va})

        # Extra top-level property
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_c3_response({'visual_assessment': valid_va, 'command': valid_cmd, 'extra': 123})

        # Extra property inside visual_assessment
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_c3_response({
                'visual_assessment': {**valid_va, 'extra': 'field'},
                'command': valid_cmd,
            })

        # Invalid block_visibility enum
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_c3_response({
                'visual_assessment': {'block_visibility': 'occluded', 'block_relative_to_fingers': 'separate'},
                'command': valid_cmd,
            })

        # Invalid block_relative_to_fingers enum
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_c3_response({
                'visual_assessment': {'block_visibility': 'visible', 'block_relative_to_fingers': 'grasped'},
                'command': valid_cmd,
            })

        # Malformed command
        with self.assertRaises(MalformedResponseError):
            parse_and_validate_c3_response({
                'visual_assessment': valid_va,
                'command': {'action': 'fly_away', 'arguments': {}},
            })

        # In run_visual_episode: malformed response stops episode as counted failure
        class BadPolicy:
            condition = 'c3'
            model = MODEL
            timeout = 120.0
            def __call__(self, p):
                return {'command': valid_cmd}  # Missing visual_assessment

        session = FakeSession()
        ep_dir = self.root / 'c3_bad_ep'
        report = run_visual_episode(
            ep_dir, session, BadPolicy(), max_calls=2, seed=820,
            controller_name='mock_codex',
            execution_metadata={
                'offline_only': True,
                'condition': 'c3',
                'condition_id': 'c3',
                'protocol_id': 'humanoid-codex-c3-development',
                'model_requested': MODEL,
                'decision_timeout_s': 120.0,
            },
        )
        self.assertEqual(report['termination_reason'], 'malformed_response')
        self.assertEqual(report['errors'], 1)
        self.assertEqual(report['completed_actions'], 0)
        self.assertEqual(report['model_calls'], 1)
        self.assertIn('visual_assessment', report['error'])
        self.assertIn('visual_assessment', (ep_dir / 'call_001.json').read_text())

        # Output disagreement with events raises error in CodexPolicy
        def run_disagree(argv, prompt, cwd, env, timeout, record_dir):
            write_result(cwd, record_dir, decision={'visual_assessment': valid_va, 'command': valid_cmd})
            (cwd / 'decision.json').write_text(json.dumps({
                'visual_assessment': {'block_visibility': 'partly_visible', 'block_relative_to_fingers': 'uncertain'},
                'command': valid_cmd,
            }))
            return 0

        policy_disagree = CodexPolicy(self.root / 'pol_c3_disagree', condition='c3', process_runner=run_disagree)
        with self.assertRaises(CodexPolicyError):
            policy_disagree(payload())
        self.assertEqual(policy_disagree.calls, 1)
        self.assertEqual(json.loads((self.root / 'pol_c3_disagree' / 'decision-001/record.json').read_text())['status'], 'failed')

    def test_c3_interruption_evidence_and_static_file_retention(self):
        class InterruptStub:
            condition = 'c3'
            model = MODEL
            timeout = 120.0
            def __call__(self, p):
                raise KeyboardInterrupt('Simulated user interruption during C3 episode')

        session = FakeSession()
        ep_dir = self.root / 'interrupted_c3_ep'
        geom_ev = generate_geometry_evidence()
        geom_bytes = serialize_geometry_evidence(geom_ev)
        geom_hash = hashlib.sha256(geom_bytes).hexdigest()
        schema_bytes = serialize_schema(c3_response_schema())
        schema_hash = hashlib.sha256(schema_bytes).hexdigest()

        with self.assertRaises(KeyboardInterrupt):
            run_visual_episode(
                ep_dir, session, InterruptStub(), max_calls=2, seed=820,
                controller_name='mock_codex',
                execution_metadata={
                    'offline_only': True,
                    'condition': 'c3',
                    'condition_id': 'c3',
                    'protocol_id': 'humanoid-codex-c3-development',
                    'protocol_path': 'experiments/humanoid-pick-place/protocols/C3_PROPOSAL.md',
                    'model_requested': MODEL,
                    'decision_timeout_s': 120.0,
                    'geometry_evidence_sha256': geom_hash,
                    'schema_sha256': schema_hash,
                    'static_files': {
                        'geometry_evidence.json': geom_bytes,
                        'schema.json': schema_bytes,
                    },
                },
            )

        # Both schema.json and geometry_evidence.json must exist and match hashes
        self.assertTrue((ep_dir / 'schema.json').is_file())
        self.assertEqual(hashlib.sha256((ep_dir / 'schema.json').read_bytes()).hexdigest(), schema_hash)

        self.assertTrue((ep_dir / 'geometry_evidence.json').is_file())
        self.assertEqual(hashlib.sha256((ep_dir / 'geometry_evidence.json').read_bytes()).hexdigest(), geom_hash)

        # report.json must be written by finally block with matching provenance
        self.assertTrue((ep_dir / 'report.json').is_file())
        report = json.loads((ep_dir / 'report.json').read_text())
        self.assertEqual(report['provenance']['schema_sha256'], schema_hash)
        self.assertEqual(report['provenance']['geometry_evidence_sha256'], geom_hash)
        self.assertIn('visual_assessments', report)

    def test_c3_no_extra_calls_and_no_assessment_leakage_into_history(self):
        valid_response = {
            'visual_assessment': {
                'block_visibility': 'visible',
                'block_relative_to_fingers': 'separate',
            },
            'command': {
                'action': 'hold',
                'arguments': {'seconds': 0.1},
            },
        }

        call_payloads = []

        class MultiStepPolicy:
            condition = 'c3'
            model = MODEL
            timeout = 120.0
            def __call__(self, p):
                call_payloads.append(p)
                return valid_response

        session = FakeSession()
        ep_dir = self.root / 'c3_multistep_ep'
        report = run_visual_episode(
            ep_dir, session, MultiStepPolicy(), max_calls=2, seed=820,
            controller_name='mock_codex',
            execution_metadata={
                'offline_only': True,
                'condition': 'c3',
                'condition_id': 'c3',
                'protocol_id': 'humanoid-codex-c3-development',
                'model_requested': MODEL,
                'decision_timeout_s': 120.0,
            },
        )

        # Exactly 2 calls made for 2 steps (no extra critic, no retry)
        self.assertEqual(len(call_payloads), 2)
        self.assertEqual(report['model_calls'], 2)
        self.assertEqual(report['completed_actions'], 2)
        self.assertEqual(report['errors'], 0)

        # Step 2 payload history contains action and response, but ZERO visual_assessment
        second_payload = call_payloads[1]
        self.assertEqual(len(second_payload['history']), 1)
        hist_entry = second_payload['history'][0]
        self.assertIn('action', hist_entry)
        self.assertIn('response', hist_entry)
        self.assertNotIn('visual_assessment', hist_entry)
        self.assertNotIn('visual_assessment', hist_entry['action'])
        self.assertNotIn('visual_assessment', hist_entry['response'])

        # Check prompt constructed from second_payload: contains no visual assessment text in history
        _, prompt2 = public_input(second_payload, condition='c3')
        json_start = prompt2.index('{"history":')
        history_json_segment = prompt2[json_start:]
        self.assertNotIn('visual_assessment', history_json_segment)
        self.assertNotIn('block_visibility', history_json_segment)
        self.assertNotIn('block_relative_to_fingers', history_json_segment)

    def test_c3_valid_then_malformed_response_accounting(self):
        # R3: Independent fake-interface reproduction: call 1 valid, call 2 MalformedResponseError.
        # Report visual_assessments must contain both attempted calls with explicit status.
        valid = {
            'visual_assessment': {
                'block_visibility': 'visible',
                'block_relative_to_fingers': 'separate',
            },
            'command': {'action': 'hold', 'arguments': {'seconds': 0.1}},
        }

        class Policy:
            def __init__(self):
                self.n = 0
            def __call__(self, p):
                self.n += 1
                if self.n == 1:
                    return copy.deepcopy(valid)
                raise MalformedResponseError('Missing visual_assessment')

        ep_dir = self.root / 'c3_valid_then_malformed'
        session = FakeSession()
        report = run_visual_episode(
            ep_dir, session, Policy(), max_calls=2,
            execution_metadata={
                'offline_only': True,
                'protocol_id': 'humanoid-codex-c3-development',
                'condition': 'c3',
            },
        )

        self.assertEqual(report['model_calls'], 2)
        self.assertEqual(report['completed_actions'], 1)
        self.assertEqual(report['termination_reason'], 'malformed_response')
        self.assertEqual(len(report['visual_assessments']), 2)

        call1 = report['visual_assessments'][0]
        self.assertEqual(call1['call'], 1)
        self.assertEqual(call1['status'], 'completed')
        self.assertEqual(call1['visual_assessment_state'], 'valid')
        self.assertEqual(call1['visual_assessment'], valid['visual_assessment'])
        self.assertIsNotNone(call1['prompt_sha256'])
        self.assertIsNotNone(call1['static_instruction_sha256'])
        self.assertIsNotNone(call1['schema_sha256'])
        self.assertIsNone(call1['error'])

        call2 = report['visual_assessments'][1]
        self.assertEqual(call2['call'], 2)
        self.assertEqual(call2['status'], 'malformed_response')
        self.assertEqual(call2['visual_assessment_state'], 'missing')
        self.assertIsNone(call2['visual_assessment'])
        self.assertEqual(call2['error'], 'Missing visual_assessment')
        self.assertIsNotNone(call2['prompt_sha256'])
        self.assertIsNotNone(call2['static_instruction_sha256'])
        self.assertIsNotNone(call2['schema_sha256'])

    def test_c3_string_response_parsing(self):
        # R3: Valid JSON-string response must be parsed, completed, and visual_assessment must NOT be null.
        valid = {
            'visual_assessment': {
                'block_visibility': 'visible',
                'block_relative_to_fingers': 'separate',
            },
            'command': {'action': 'hold', 'arguments': {'seconds': 0.1}},
        }
        ep_dir = self.root / 'c3_string_resp'
        session = FakeSession()
        report = run_visual_episode(
            ep_dir, session, lambda p: json.dumps(valid), max_calls=1,
            execution_metadata={
                'offline_only': True,
                'protocol_id': 'humanoid-codex-c3-development',
                'condition': 'c3',
            },
        )
        self.assertEqual(report['model_calls'], 1)
        self.assertEqual(report['completed_actions'], 1)
        self.assertEqual(len(report['visual_assessments']), 1)
        va = report['visual_assessments'][0]
        self.assertEqual(va['status'], 'completed')
        self.assertEqual(va['visual_assessment_state'], 'valid')
        self.assertEqual(va['visual_assessment'], valid['visual_assessment'])

    def test_c3_timeout_and_interruption_accounting(self):
        # R3: Call failure from timeout or interruption retains unreached/interrupted assessment state
        # and never borrows stale assessment from previous call.
        valid = {
            'visual_assessment': {
                'block_visibility': 'visible',
                'block_relative_to_fingers': 'separate',
            },
            'command': {'action': 'hold', 'arguments': {'seconds': 0.1}},
        }

        class TimeoutPolicy:
            def __init__(self):
                self.n = 0
            def __call__(self, p):
                self.n += 1
                if self.n == 1:
                    return copy.deepcopy(valid)
                raise TimeoutError('Decision timed out after 120s')

        ep_dir = self.root / 'c3_timeout'
        session = FakeSession()
        report = run_visual_episode(
            ep_dir, session, TimeoutPolicy(), max_calls=2,
            execution_metadata={
                'offline_only': True,
                'protocol_id': 'humanoid-codex-c3-development',
                'condition': 'c3',
            },
        )
        self.assertEqual(report['model_calls'], 2)
        self.assertEqual(report['completed_actions'], 1)
        self.assertEqual(report['termination_reason'], 'exception')
        self.assertEqual(len(report['visual_assessments']), 2)
        va2 = report['visual_assessments'][1]
        self.assertEqual(va2['visual_assessment_state'], 'unreached')
        self.assertIsNone(va2['visual_assessment'])

    def test_c3_offline_preflight_synthetic_software_check(self):
        orig_popen = subprocess.Popen

        def safe_popen(cmd, *args, **kwargs):
            if any(arg == 'exec' for arg in cmd):
                raise AssertionError('Codex exec decision must not be invoked in preflight')
            return orig_popen(cmd, *args, **kwargs)

        preflight_dir = self.root / 'c3_preflight'
        with patch('humanoid_sim.codex_policy.run_process', side_effect=AssertionError('No live process execution allowed')), \
             patch('humanoid_sim.codex_policy.check_install', side_effect=RuntimeError('Codex CLI login unavailable')), \
             patch('humanoid_sim.visual.RGBRenderer', side_effect=AssertionError('No renderer invocation allowed')), \
             patch('subprocess.Popen', side_effect=safe_popen), \
             patch('subprocess.run', side_effect=AssertionError('No subprocess.run allowed')), \
             patch('mujoco.mj_step', side_effect=AssertionError('No physics step allowed')):
            record = run_preflight(preflight_dir, condition='c3')

        self.assertEqual(record['status'], 'complete')
        self.assertEqual(record['condition'], 'c3')
        self.assertEqual(record['condition_id'], 'c3')
        self.assertEqual(record['protocol_id'], 'humanoid-codex-c3-development')
        self.assertEqual(record['model_invocations'], 0)
        self.assertEqual(record['physics_steps'], 0)
        self.assertTrue(record['isolation_verified'])
        self.assertIn('synthetic_software_check', record)
        self.assertEqual(record['synthetic_software_check']['status'], 'verified')
        self.assertEqual(record['synthetic_software_check']['type'], 'offline_synthetic_software_check')
        self.assertFalse(record['synthetic_software_check']['model_generated'])

        # Verify all 9 artifact files exist and have non-zero size
        expected_artifacts = (
            'preflight.json', 'prompt.txt', 'schema.json', 'geometry_evidence.json',
            'public_payload.json', 'observation.png', 'synthetic_decision.json',
            'synthetic_events.jsonl', 'synthetic_record.json'
        )
        for fname in expected_artifacts:
            p = preflight_dir / fname
            self.assertTrue(p.is_file(), f'Missing C3 preflight artifact: {fname}')
            self.assertGreater(p.stat().st_size, 0, f'Empty artifact: {fname}')

        # Verify geometry evidence file hash matches record hash
        written_geom_hash = hashlib.sha256((preflight_dir / 'geometry_evidence.json').read_bytes()).hexdigest()
        self.assertEqual(written_geom_hash, record['geometry_evidence_sha256'])

        # Verify schema file hash matches record hash
        written_schema_hash = hashlib.sha256((preflight_dir / 'schema.json').read_bytes()).hexdigest()
        self.assertEqual(written_schema_hash, record['schema_sha256'])

        # Verify prompt text has C3 instruction and replacements
        prompt_text = (preflight_dir / 'prompt.txt').read_text()
        self.assertIn(C3_INSTRUCTION, prompt_text)
        self.assertIn(C2_INSTRUCTION, prompt_text)
        self.assertIn('Return only the structured C3 response specified below.', prompt_text)
        self.assertNotIn('ground_truth', prompt_text)

        # Verify synthetic decision is valid C3 response
        synth_dec = json.loads((preflight_dir / 'synthetic_decision.json').read_text())
        parsed = parse_and_validate_c3_response(synth_dec)
        self.assertEqual(parsed['visual_assessment']['block_visibility'], 'visible')
        self.assertEqual(parsed['visual_assessment']['block_relative_to_fingers'], 'separate')

        # Refusal on existing directory
        with self.assertRaisesRegex(ValueError, 'must be new'):
            run_preflight(preflight_dir, condition='c3')

    def test_c1_and_c2_artifacts_and_frozen_protocols_unchanged(self):
        expected_hashes = {
            'experiments/humanoid-pick-place/protocols/C1.md':
                '401343ba76317d5f1eb8f01cabff7dcc9f79d6dddbb5325b0252204e1e9e07a4',
            'experiments/humanoid-pick-place/results/codex_C1.json':
                '556962a8cadea3608e34b2da32ef3df01a5bd551d4ad0510ceba9fd7de6868ec',
            'experiments/humanoid-pick-place/results/codex_C1_episode.zip':
                '19f3313d521ecbdd5b9181dee2717e9219d5eea1784ed346d6e1553745b9caee',
            'experiments/humanoid-pick-place/results/codex_C1_probes.zip':
                '391044b8f3f815ef7ddc35884b8c7d8893e87de6dd923e1410552be9a8e49f5f',
            'experiments/humanoid-pick-place/results/codex_C1_audit/audit.json':
                '6c3da29eb53d291d30d8e7b24195c174e95debaa76f73d0e1bd3a5d729cdf601',
            'experiments/humanoid-pick-place/results/codex_C1_audit/tests.txt':
                '6ffea0d21adbe4c712f8a13cb5e406f331ef4b5917aa06eca345540f88bc7c58',
            'experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md':
                'a1a3b982fd455c9c2e220787be74c9bbad4c1c0dd6f4e32894aac9a896ced7c0',
            'experiments/humanoid-pick-place/results/codex_C2.json':
                '72d1e5e2e4805988fecd4439aebc6d37b0ea8f8d8077766b57069fdd00308cc1',
            'experiments/humanoid-pick-place/results/codex_C2_episode.zip':
                '940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8',
            'experiments/humanoid-pick-place/results/codex_C2_audit/audit.json':
                '20d3935517e5623101f950d0551bb72b4e3c7137d2927c145aa92a94d0f0b5b1',
            'experiments/humanoid-pick-place/results/codex_C2_audit/tests.txt':
                '9f51ce5b93319d4294ca703d22bd3b7c790bf19a8b35182182cdd871a18212bd',
        }
        for rel_path, expected_hash in expected_hashes.items():
            path = ROOT / rel_path
            self.assertTrue(path.is_file(), f'Historical artifact not found: {rel_path}')
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual_hash, expected_hash, f'Historical artifact modified: {rel_path}')


if __name__ == '__main__':
    unittest.main()
