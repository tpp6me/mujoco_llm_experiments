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

from humanoid_sim.codex_policy import (
    CodexPolicy, CodexPolicyError, child_environment, check_install, public_input,
    SUPPORTED_VERSION, DISABLED_CODE_MODE_NOTICE, main,
    C2_INSTRUCTION, CONDITIONS, DEFAULT_CONDITION, MODEL, serialize_geometry_evidence,
    nominal_open_hand_geometry, verify_nominal_bounds_enclosure, generate_geometry_evidence,
    run_preflight, PROTOCOL_PATHS, PROTOCOL_IDS, ROOT,
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
            public_input(payload(), condition='c3')
        with self.assertRaises(ValueError):
            CodexPolicy(self.root, condition='invalid')

        # CLI rejects invalid condition
        with patch.object(sys, 'argv', ['codex_policy', '--output', str(self.root / 'invalid_cond'), '--condition', 'c3']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main()

        # CLI rejects altered model and max-calls for C2
        for extra in (['--model', 'different-model'], ['--max-calls', '1']):
            with patch.object(sys, 'argv', ['codex_policy', '--condition', 'c2', '--output', str(self.root / 'new_c2'), *extra]), patch('humanoid_sim.codex_policy.check_install') as check, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
                check.assert_not_called()
                self.assertFalse((self.root / 'new_c2').exists())

        # run_visual_episode rejects mismatched condition and protocol_id
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=1)
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

        # run_visual_episode rejects conflicting condition and condition_id
        with self.assertRaisesRegex(ValueError, 'Conflicting condition'):
            run_visual_episode(self.root / 'ep_conflict', session, policy, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c2', 'condition_id': 'c1',
                                                   'protocol_id': 'humanoid-codex-c2-development'})

        # run_visual_episode rejects mismatch between policy condition and metadata condition
        policy_c2 = CodexPolicy(self.root / 'codex_c2', condition='c2')
        with self.assertRaisesRegex(ValueError, 'Mismatched model callable condition'):
            run_visual_episode(self.root / 'ep3', session, policy_c2, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c1',
                                                   'protocol_id': 'humanoid-codex-c1-development'})

        # Protocol with no condition field rejects callable with mismatched condition
        with self.assertRaisesRegex(ValueError, 'Mismatched model callable condition'):
            run_visual_episode(self.root / 'ep_proto_only', session, policy_c2, max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True,
                                                   'protocol_id': 'humanoid-codex-c1-development'})

        # Model and timeout mismatches rejected before capture
        class MismatchedStub:
            condition = 'c2'
            model = 'other-model'
            timeout = 180.0
            def __call__(self, p):
                raise AssertionError('Callable reached despite setting mismatch')

        with self.assertRaisesRegex(ValueError, 'Mismatched model callable model'):
            run_visual_episode(self.root / 'ep_model_mismatch', session, MismatchedStub(), max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c2', 'condition_id': 'c2',
                                                   'protocol_id': 'humanoid-codex-c2-development',
                                                   'model_requested': 'gpt-5.6-sol'})

        class TimeoutStub:
            condition = 'c2'
            model = 'gpt-5.6-sol'
            timeout = 180.0
            def __call__(self, p):
                raise AssertionError('Callable reached despite timeout mismatch')

        with self.assertRaisesRegex(ValueError, 'Mismatched model callable timeout'):
            run_visual_episode(self.root / 'ep_timeout_mismatch', session, TimeoutStub(), max_calls=1, seed=820,
                               controller_name='mock_codex',
                               execution_metadata={'offline_only': True, 'condition': 'c2', 'condition_id': 'c2',
                                                   'protocol_id': 'humanoid-codex-c2-development',
                                                   'model_requested': 'gpt-5.6-sol'})

        # CLI probe path rejects altered model for both c1 and c2
        dummy_probe = self.root / 'dummy_probe.json'
        dummy_probe.write_text('{}')
        for cond in ('c1', 'c2'):
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

        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=2)
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

    def test_c1_artifacts_and_frozen_protocol_unchanged(self):
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
        }
        for rel_path, expected_hash in expected_hashes.items():
            path = ROOT / rel_path
            self.assertTrue(path.is_file(), f'C1 artifact not found: {rel_path}')
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual_hash, expected_hash, f'C1 artifact modified: {rel_path}')


if __name__ == '__main__':
    unittest.main()
