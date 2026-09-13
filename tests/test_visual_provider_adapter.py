"""Tests for Responses API visual provider adapter with injected offline transport."""
import base64
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
import urllib.request

import numpy as np
from PIL import Image

from humanoid_sim.environment import Environment
from humanoid_sim.interface import PolicyInterface, VERSION, INSTRUCTION_VERSION
from humanoid_sim.visual import VisualSession, calibration
from humanoid_sim.visual_policy_runner import (
    VISUAL_PROMPT,
    VisualPolicyError,
    ModelRefusalError,
    MalformedResponseError,
    VisualPolicySession,
    run_visual_episode,
    action_schema
)
from humanoid_sim.visual_provider_adapter import (
    DEFAULT_DETAIL,
    DEFAULT_MAX_OUTPUT,
    VisualProviderAdapter,
    VisualAdapterError,
    MalformedEnvelopeError,
    ProviderRefusalError,
    validate_png_base64,
    build_responses_request,
    validate_response_envelope,
    export_request,
    provenance
)


def make_test_png(w=40, h=30):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[5:15, 5:25, 0] = 220
    img[15:25, 10:30, 1] = 180
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format='PNG')
    return buf.getvalue()


def make_test_camera(w=960, h=720):
    return calibration(SimpleNamespace(
        forward=[0, 0, -1], up=[0, 1, 0], pos=[0.24, -0.8, 2.0],
        frustum_near=0.1, frustum_top=0.05, frustum_bottom=-0.05, frustum_center=0
    ))


def make_test_observation(png_bytes=None, obs_id='obs-test-001', time_s=0.5):
    if png_bytes is None:
        png_bytes = make_test_png()
    b64 = base64.b64encode(png_bytes).decode('ascii')
    sha256_hex = hashlib.sha256(png_bytes).hexdigest()
    cam = make_test_camera()
    robot_state = {
        'schema_version': 'humanoid-actions-v2',
        'instruction_version': 1,
        'mode': 'robot_state',
        'time_s': time_s,
        'frame': 'world',
        'supported_body': True,
        'robot': {
            'joint_names': ['j1', 'j2'],
            'joint_position_rad': [0.1, -0.2],
            'joint_velocity_rad_s': [0.0, 0.0],
            'hand_xyz_m': [0.24, -0.18, 0.95],
            'hand_quaternion_wxyz': [0.5, -0.5, 0.5, 0.5],
            'contact_links': []
        }
    }
    return {
        'schema_version': 'humanoid-visual-v1',
        'observation_id': obs_id,
        'time_s': time_s,
        'camera': cam,
        'robot_state': robot_state,
        'rgb_png_base64': b64,
        'rgb_sha256': sha256_hex
    }


def make_test_public_payload(obs=None, remaining_time=24.5, remaining_actions=20, history=None):
    if obs is None:
        obs = make_test_observation()
    return {
        'instruction': VISUAL_PROMPT,
        'instruction_version': 1,
        'action_schema': action_schema(),
        'remaining_time_s': remaining_time,
        'remaining_actions': remaining_actions,
        'observation': obs,
        'history': history or []
    }


def make_mock_responses_envelope(command_dict, status='completed', model='gpt-5.6-sol', usage='__DEFAULT__'):
    if usage == '__DEFAULT__':
        usage = {'input_tokens': 1200, 'output_tokens': 25, 'total_tokens': 1225}
    return {
        'id': 'resp-test-001',
        'object': 'response',
        'status': status,
        'model': model,
        'output': [
            {
                'type': 'message',
                'id': 'msg-test-001',
                'role': 'assistant',
                'content': [
                    {
                        'type': 'output_text',
                        'text': json.dumps({'command': command_dict})
                    }
                ]
            }
        ],
        'usage': usage
    }


class MockRenderer:
    def __init__(self):
        self.png_bytes = make_test_png(960, 720)
        self.camera_dict = make_test_camera(960, 720)

    def capture(self):
        return self.png_bytes, copy.deepcopy(self.camera_dict)

    def close(self):
        pass


class VisualProviderAdapterTests(unittest.TestCase):

    def test_request_builder_image_item_hash_and_single_image(self):
        png_bytes = make_test_png(960, 720)
        expected_sha = hashlib.sha256(png_bytes).hexdigest()
        obs = make_test_observation(png_bytes=png_bytes)
        payload = make_test_public_payload(obs=obs)

        req = build_responses_request(payload, model='gpt-5.6-sol', detail='high', max_output_tokens=2048)

        # Check top-level keys
        self.assertEqual(req['model'], 'gpt-5.6-sol')
        self.assertFalse(req['store'])
        self.assertEqual(req['max_output_tokens'], 2048)
        self.assertEqual(req['instructions'], VISUAL_PROMPT)
        self.assertEqual(req['reasoning'], {'effort': 'low'})

        # Check structured outputs format
        self.assertIn('text', req)
        self.assertEqual(req['text']['format']['type'], 'json_schema')
        self.assertEqual(req['text']['format']['name'], 'humanoid_primitive')
        self.assertTrue(req['text']['format']['strict'])
        self.assertEqual(req['text']['format']['schema'], action_schema())

        # Check input structure
        self.assertIn('input', req)
        self.assertEqual(len(req['input']), 1)
        msg = req['input'][0]
        self.assertEqual(msg['role'], 'user')
        self.assertEqual(len(msg['content']), 2)

        # Content part 0: input_text
        text_part = msg['content'][0]
        self.assertEqual(text_part['type'], 'input_text')
        text_public = json.loads(text_part['text'])

        # Critical requirement: base64 image MUST NOT be duplicated in text JSON
        self.assertNotIn('rgb_png_base64', text_public['observation'])
        self.assertEqual(text_public['observation']['rgb_sha256'], expected_sha)
        self.assertEqual(text_public['observation']['observation_id'], 'obs-test-001')
        self.assertEqual(text_public['observation']['time_s'], 0.5)
        self.assertIn('camera', text_public['observation'])
        self.assertIn('robot_state', text_public['observation'])
        self.assertEqual(text_public['remaining_actions'], 20)
        self.assertEqual(text_public['remaining_time_s'], 24.5)

        # Content part 1: input_image
        img_part = msg['content'][1]
        self.assertEqual(img_part['type'], 'input_image')
        self.assertEqual(img_part['detail'], 'high')
        data_url = img_part['image_url']
        self.assertTrue(data_url.startswith('data:image/png;base64,'))
        decoded_b64 = data_url.split('base64,', 1)[1]
        decoded_bytes = base64.b64decode(decoded_b64)
        self.assertEqual(hashlib.sha256(decoded_bytes).hexdigest(), expected_sha)
        with Image.open(io.BytesIO(decoded_bytes)) as img:
            self.assertEqual((img.width, img.height), (960, 720))
            self.assertEqual(img.format, 'PNG')

    def test_request_builder_excludes_planted_private_fields(self):
        obs = make_test_observation()
        # Plant private fields at every possible level
        obs['secret_object_truth'] = [0.24, -0.18, 0.76]
        obs['task_state'] = {'object_pose': [0.24, -0.18, 0.76]}
        obs['score'] = {'placement_success': True, 'max_penetration': 0.001}
        obs['private_scorer_report'] = {'eval': True}
        obs['robot_state']['task_state'] = {'object': 'block'}
        obs['camera']['private_calibration'] = 'plant'

        history = [
            {
                'action': {'action': 'hold', 'arguments': {'seconds': 0.5}, 'secret': 99},
                'response': {'status': 'completed', 'start_time_s': 0.0, 'end_time_s': 0.5, 'private_oracle': True}
            }
        ]
        payload = make_test_public_payload(obs=obs, history=history)
        payload['private_root_field'] = 'secret'

        req = build_responses_request(payload, model='gpt-5.6-sol')
        req_json_str = json.dumps(req)

        forbidden_keys = [
            'secret_object_truth',
            'private_scorer_report',
            'private_root_field',
            'private_calibration',
            'private_oracle'
        ]
        for key in forbidden_keys:
            self.assertNotIn(key, req_json_str)

        # Parse the embedded input_text JSON and assert no private keys survive
        text_part = req['input'][0]['content'][0]['text']
        parsed_text = json.loads(text_part)
        self.assertNotIn('secret_object_truth', parsed_text['observation'])
        self.assertNotIn('task_state', parsed_text['observation'])
        self.assertNotIn('score', parsed_text['observation'])
        self.assertNotIn('task_state', parsed_text['observation']['robot_state'])
        self.assertNotIn('secret', parsed_text['history'][0]['action'])
        self.assertNotIn('private_oracle', parsed_text['history'][0]['response'])

    def test_request_builder_bounds_history_to_20(self):
        long_history = [
            {
                'action': {'action': 'hold', 'arguments': {'seconds': 0.1}, 'request_id': f'act-{i}'},
                'response': {'status': 'completed', 'start_time_s': float(i), 'end_time_s': float(i + 0.1)}
            }
            for i in range(25)
        ]
        payload = make_test_public_payload(history=long_history)
        req = build_responses_request(payload, model='gpt-5.6-sol')
        text_part = req['input'][0]['content'][0]['text']
        parsed_text = json.loads(text_part)
        self.assertEqual(len(parsed_text['history']), 20)
        self.assertEqual(parsed_text['history'][-1]['action']['request_id'], 'act-24')

    def test_request_builder_validates_malformed_png_and_base64(self):
        obs = make_test_observation()
        # Malformed base64
        obs['rgb_png_base64'] = 'not-valid-base64!!@@##'
        with self.assertRaises(ValueError):
            build_responses_request(make_test_public_payload(obs=obs), model='gpt-5.6-sol')

        # Valid base64 but not PNG (e.g. plain text)
        obs['rgb_png_base64'] = base64.b64encode(b'Hello world plain text').decode('ascii')
        with self.assertRaises(ValueError):
            build_responses_request(make_test_public_payload(obs=obs), model='gpt-5.6-sol')

        # Hash mismatch
        good_png = make_test_png()
        obs['rgb_png_base64'] = base64.b64encode(good_png).decode('ascii')
        obs['rgb_sha256'] = '0000000000000000000000000000000000000000000000000000000000000000'
        with self.assertRaises(ValueError):
            build_responses_request(make_test_public_payload(obs=obs), model='gpt-5.6-sol')

        # Empty model
        obs = make_test_observation()
        with self.assertRaises(ValueError):
            build_responses_request(make_test_public_payload(obs=obs), model='')

        # Invalid detail
        with self.assertRaises(ValueError):
            build_responses_request(make_test_public_payload(obs=obs), model='gpt-5.6-sol', detail='ultra_hd')

        # Invalid max output tokens
        with self.assertRaises(ValueError):
            build_responses_request(make_test_public_payload(obs=obs), model='gpt-5.6-sol', max_output_tokens=0)

    def test_adapter_omitting_transport_fails_without_credentials_or_network(self):
        for bad_transport in (None, 'not_callable', 12345):
            with self.assertRaises(ValueError):
                VisualProviderAdapter(transport=bad_transport, model='gpt-5.6-sol')

    def test_adapter_injected_transport_success(self):
        hold_cmd = {'action': 'hold', 'arguments': {'seconds': 0.5}}
        raw_env = make_mock_responses_envelope(hold_cmd, status='completed')

        def mock_transport(req):
            self.assertIn('model', req)
            self.assertEqual(req['input'][0]['content'][1]['type'], 'input_image')
            return raw_env, 'req-id-123'

        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = VisualProviderAdapter(transport=mock_transport, model='gpt-5.6-sol', record_dir=tmpdir)
            payload = make_test_public_payload()
            result = adapter(payload)

            self.assertEqual(result, {'command': hold_cmd})
            record_path = Path(tmpdir) / 'provider_call_001.json'
            self.assertTrue(record_path.exists())
            record = json.loads(record_path.read_text())
            self.assertEqual(record['call'], 1)
            self.assertTrue(record['offline_evidence'])
            self.assertTrue(record['injected_transport'])
            self.assertEqual(record['status'], 'completed')
            self.assertEqual(record['provider_status'], 'completed')
            self.assertEqual(record['request_id'], 'req-id-123')
            self.assertEqual(record['command'], hold_cmd)
            self.assertGreaterEqual(record['wall_latency_s'], 0.0)
            self.assertEqual(record['usage']['total_tokens'], 1225)

    def test_adapter_handles_reasoning_metadata(self):
        hold_cmd = {'action': 'hold', 'arguments': {'seconds': 0.5}}
        raw_env = {
            'id': 'resp-reasoning-01',
            'status': 'completed',
            'model': 'gpt-5.6-sol',
            'output': [
                {
                    'type': 'reasoning',
                    'content': [{'type': 'reasoning_text', 'text': 'Evaluating next movement...'}]
                },
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': json.dumps({'command': hold_cmd})}]
                }
            ],
            'usage': {'input_tokens': 1000, 'output_tokens': 50, 'total_tokens': 1050}
        }
        adapter = VisualProviderAdapter(transport=lambda _: raw_env, model='gpt-5.6-sol')
        result = adapter(make_test_public_payload())
        self.assertEqual(result, {'command': hold_cmd})

    def test_adapter_refusal_at_root_and_message_level(self):
        # 1. Refusal at root status
        env1 = {'status': 'refusal', 'error': 'Refused by safety filter'}
        adapter1 = VisualProviderAdapter(transport=lambda _: env1, model='gpt-5.6-sol')
        with self.assertRaises(ModelRefusalError):
            adapter1(make_test_public_payload())

        # 2. Refusal in message content
        env2 = {
            'status': 'completed',
            'output': [
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'refusal', 'refusal': 'I cannot interact with physical objects'}]
                }
            ]
        }
        adapter2 = VisualProviderAdapter(transport=lambda _: env2, model='gpt-5.6-sol')
        with self.assertRaises(ModelRefusalError):
            adapter2(make_test_public_payload())

    def test_adapter_incomplete_or_failed_status_never_executes_action(self):
        valid_cmd = {'action': 'hold', 'arguments': {'seconds': 0.5}}
        # Status 'incomplete' with valid embedded action inside output
        env_incomplete = make_mock_responses_envelope(valid_cmd, status='incomplete')
        adapter_inc = VisualProviderAdapter(transport=lambda _: env_incomplete, model='gpt-5.6-sol')
        with self.assertRaises(MalformedResponseError):
            adapter_inc(make_test_public_payload())

        # Status 'failed' with valid embedded action inside output
        env_failed = make_mock_responses_envelope(valid_cmd, status='failed')
        adapter_fail = VisualProviderAdapter(transport=lambda _: env_failed, model='gpt-5.6-sol')
        with self.assertRaises(MalformedResponseError):
            adapter_fail(make_test_public_payload())

        # Missing or None status
        env_nostatus = make_mock_responses_envelope(valid_cmd, status=None)
        adapter_nostatus = VisualProviderAdapter(transport=lambda _: env_nostatus, model='gpt-5.6-sol')
        with self.assertRaises(MalformedResponseError):
            adapter_nostatus(make_test_public_payload())

    def test_adapter_rejects_unexpected_tool_output(self):
        valid_cmd = {'action': 'hold', 'arguments': {'seconds': 0.5}}
        # Output with tool call item
        env_tool = {
            'status': 'completed',
            'output': [
                {'type': 'tool_call', 'id': 'call_123', 'name': 'read_file'},
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': json.dumps({'command': valid_cmd})}]
                }
            ]
        }
        adapter = VisualProviderAdapter(transport=lambda _: env_tool, model='gpt-5.6-sol')
        with self.assertRaises(MalformedResponseError):
            adapter(make_test_public_payload())

    def test_adapter_rejects_multiple_action_messages_or_output_text(self):
        valid_cmd = {'action': 'hold', 'arguments': {'seconds': 0.5}}
        # Multiple message items
        env_multi_msg = {
            'status': 'completed',
            'output': [
                {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps({'command': valid_cmd})}]},
                {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': json.dumps({'command': valid_cmd})}]}
            ]
        }
        adapter1 = VisualProviderAdapter(transport=lambda _: env_multi_msg, model='gpt-5.6-sol')
        with self.assertRaises(MalformedResponseError):
            adapter1(make_test_public_payload())

        # Multiple output_text items in single message
        env_multi_text = {
            'status': 'completed',
            'output': [
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [
                        {'type': 'output_text', 'text': json.dumps({'command': valid_cmd})},
                        {'type': 'output_text', 'text': json.dumps({'command': valid_cmd})}
                    ]
                }
            ]
        }
        adapter2 = VisualProviderAdapter(transport=lambda _: env_multi_text, model='gpt-5.6-sol')
        with self.assertRaises(MalformedResponseError):
            adapter2(make_test_public_payload())

    def test_adapter_rejects_malformed_json_and_invalid_commands(self):
        bad_outputs = [
            'not-valid-json',
            '{"command": {"action": "fly"}}',
            '{"command": {"action": "hold", "arguments": {"seconds": True}}}',
            '{"command": {"action": "move", "arguments": {"xyz_m": [99, 99, 99], "quaternion_wxyz": [1, 0, 0, 0], "seconds": 1.0}}}',
            '{"command": {"action": "move", "arguments": {"xyz_m": [0.24, -0.18, 0.95], "quaternion_wxyz": [1.0, 1.0, 0.0, 0.0], "seconds": 1.0}}}',  # norm != 1
            '{"command": {"action": "hand", "arguments": {"closure": 1.5, "seconds": 0.5}}}',
            '{"command": {"action": "hold", "arguments": {"seconds": 0.001}}}'  # seconds < 0.02
        ]
        for bad in bad_outputs:
            env = {
                'status': 'completed',
                'output': [
                    {
                        'type': 'message',
                        'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': bad}]
                    }
                ]
            }
            adapter = VisualProviderAdapter(transport=lambda _: env, model='gpt-5.6-sol')
            with self.assertRaises(MalformedResponseError):
                adapter(make_test_public_payload())

    def test_adapter_transport_exception_retained_and_reraised(self):
        def crashing_transport(req):
            raise ConnectionResetError('Simulated transport disconnection')

        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = VisualProviderAdapter(transport=crashing_transport, model='gpt-5.6-sol', record_dir=tmpdir)
            with self.assertRaises(ConnectionResetError):
                adapter(make_test_public_payload())

            record_file = Path(tmpdir) / 'provider_call_001.json'
            self.assertTrue(record_file.exists())
            rec = json.loads(record_file.read_text())
            self.assertEqual(rec['status'], 'transport_exception')
            self.assertIn('ConnectionResetError', rec['error'])
            self.assertIsNone(rec['raw_response'])

    def test_adapter_unknown_usage_labeled_without_cost_fabrication(self):
        valid_cmd = {'action': 'hold', 'arguments': {'seconds': 0.5}}
        env = make_mock_responses_envelope(valid_cmd, usage=None)
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = VisualProviderAdapter(transport=lambda _: env, model='gpt-5.6-sol', record_dir=tmpdir)
            result = adapter(make_test_public_payload())
            self.assertEqual(result, {'command': valid_cmd})
            rec = json.loads((Path(tmpdir) / 'provider_call_001.json').read_text())
            self.assertEqual(rec['usage'], {'status': 'unknown'})
            self.assertNotIn('estimated_cost_usd', rec)
            self.assertNotIn('charged_estimate_usd', rec)

    def test_adapter_honest_call_counts_and_no_record_overwrite(self):
        valid_cmd = {'action': 'hold', 'arguments': {'seconds': 0.5}}
        env = make_mock_responses_envelope(valid_cmd)
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = VisualProviderAdapter(transport=lambda _: env, model='gpt-5.6-sol', record_dir=tmpdir)
            payload = make_test_public_payload()
            adapter(payload)
            adapter(payload)
            adapter(payload)

            self.assertEqual(adapter.call_count, 3)
            p1 = Path(tmpdir) / 'provider_call_001.json'
            p2 = Path(tmpdir) / 'provider_call_002.json'
            p3 = Path(tmpdir) / 'provider_call_003.json'
            self.assertTrue(p1.exists())
            self.assertTrue(p2.exists())
            self.assertTrue(p3.exists())
            self.assertEqual(json.loads(p1.read_text())['call'], 1)
            self.assertEqual(json.loads(p2.read_text())['call'], 2)
            self.assertEqual(json.loads(p3.read_text())['call'], 3)

            # Manually reset invocation counter and verify overwrite attempt raises ValueError
            adapter.invocation_count = 0
            with self.assertRaises(ValueError):
                adapter(payload)

    def test_end_to_end_run_visual_episode_with_adapter(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=2, deadline=2.0)

        step_commands = [
            {'action': 'hold', 'arguments': {'seconds': 0.5}},
            {'action': 'hold', 'arguments': {'seconds': 0.5}}
        ]
        calls_made = []

        def mock_transport(req):
            idx = len(calls_made)
            calls_made.append(req)
            cmd = step_commands[idx] if idx < len(step_commands) else step_commands[-1]
            return make_mock_responses_envelope(cmd)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_folder = Path(tmpdir) / 'test_episode'
            adapter_dir = out_folder / 'adapter'
            adapter = VisualProviderAdapter(transport=mock_transport, model='gpt-5.6-sol', record_dir=adapter_dir)

            report = run_visual_episode(
                folder=out_folder,
                session=session,
                model_callable=adapter,
                max_calls=2,
                deadline=2.0,
                seed=820,
                controller_name='visual_provider_adapter'
            )

            self.assertEqual(report['termination_reason'], 'action_limit')
            self.assertEqual(report['model_calls'], 2)
            self.assertEqual(report['completed_actions'], 2)
            self.assertEqual(report['refusals'], 0)
            self.assertEqual(report['errors'], 0)
            self.assertFalse(report['placement_success_claimed'])

            # Verify adapter recorded attempt logs
            self.assertTrue((adapter_dir / 'provider_call_001.json').exists())
            self.assertTrue((adapter_dir / 'provider_call_002.json').exists())
            rec1 = json.loads((adapter_dir / 'provider_call_001.json').read_text())
            self.assertEqual(rec1['command'], step_commands[0])
            self.assertEqual(rec1['status'], 'completed')

            # Verify runner recorded step logs
            self.assertTrue((out_folder / 'call_001.json').exists())
            self.assertTrue((out_folder / 'call_002.json').exists())
            self.assertTrue((out_folder / 'report.json').exists())

    def test_end_to_end_failure_termination_before_execution(self):
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=2, deadline=2.0)

        # Mock transport returns incomplete status despite embedded hold action
        def incomplete_transport(req):
            return make_mock_responses_envelope({'action': 'hold', 'arguments': {'seconds': 0.5}}, status='incomplete')

        with tempfile.TemporaryDirectory() as tmpdir:
            out_folder = Path(tmpdir) / 'fail_episode'
            adapter_dir = out_folder / 'adapter'
            adapter = VisualProviderAdapter(transport=incomplete_transport, model='gpt-5.6-sol', record_dir=adapter_dir)

            report = run_visual_episode(
                folder=out_folder,
                session=session,
                model_callable=adapter,
                max_calls=2,
                deadline=2.0,
                seed=820,
                controller_name='visual_provider_adapter'
            )

            self.assertEqual(report['termination_reason'], 'malformed_response')
            self.assertEqual(report['model_calls'], 1)
            self.assertEqual(report['completed_actions'], 0)
            self.assertEqual(report['action_attempts'], 0)  # Never attempted execution!
            self.assertEqual(report['errors'], 1)

    def test_dry_export_request_and_manifest(self):
        obs = make_test_observation()
        with tempfile.TemporaryDirectory() as tmpdir:
            obs_file = Path(tmpdir) / 'input_obs.json'
            obs_file.write_text(json.dumps(obs))

            export_file = Path(tmpdir) / 'exported_request.json'
            manifest_file = Path(tmpdir) / 'manifest.json'

            manifest = export_request(
                source_path=obs_file,
                output_path=export_file,
                model='gpt-5.6-sol',
                manifest_path=manifest_file,
                detail='high'
            )

            self.assertTrue(export_file.exists())
            self.assertTrue(manifest_file.exists())

            exported = json.loads(export_file.read_text())
            self.assertEqual(exported['model'], 'gpt-5.6-sol')
            self.assertEqual(exported['input'][0]['content'][1]['detail'], 'high')

            self.assertEqual(manifest['model'], 'gpt-5.6-sol')
            self.assertEqual(manifest['image_size'], [40, 30])
            self.assertIn('top_level_keys', manifest['field_layout'])

            # Verify refusal to overwrite
            with self.assertRaises(FileExistsError):
                export_request(
                    source_path=obs_file,
                    output_path=export_file,
                    model='gpt-5.6-sol'
                )

    def test_zero_network_and_credential_access_boundary(self):
        from unittest.mock import patch
        class NoCredentials(dict):
            def __getitem__(self, key):
                if key == 'OPENAI_API_KEY':
                    raise AssertionError('Credential read attempted')
                return super().__getitem__(key)
            def get(self, key, default=None):
                if key == 'OPENAI_API_KEY':
                    raise AssertionError('Credential read attempted')
                return super().get(key, default)

        with patch('os.environ', NoCredentials()), patch(
            'socket.socket.connect', side_effect=AssertionError('Network attempted')
        ), patch('urllib.request.urlopen', side_effect=AssertionError('Network attempted')):
            with self.assertRaises(ValueError):
                VisualProviderAdapter(transport=None, model='offline-fixture')
            payload = make_test_public_payload()
            self.assertIn('input', build_responses_request(payload, model='offline-fixture'))
            with tempfile.TemporaryDirectory() as tmpdir:
                source = Path(tmpdir) / 'obs.json'
                source.write_text(json.dumps(make_test_observation()))
                target = Path(tmpdir) / 'request.json'
                export_request(source, target, model='offline-fixture')
                self.assertTrue(target.exists())
            envelope = make_mock_responses_envelope({'action': 'hold', 'arguments': {'seconds': 0.1}})
            adapter = VisualProviderAdapter(lambda _: envelope, model='offline-fixture')
            self.assertEqual(adapter(payload)['command']['action'], 'hold')

    def test_ambiguous_transport_containers_never_execute(self):
        envelope = make_mock_responses_envelope({'action': 'hold', 'arguments': {'seconds': 0.1}})
        for raw in ([envelope, envelope], (envelope, envelope), (envelope, 'id', envelope)):
            with self.subTest(raw_type=type(raw).__name__), tempfile.TemporaryDirectory() as tmp:
                adapter = VisualProviderAdapter(lambda _: raw, model='offline-fixture', record_dir=tmp)
                with self.assertRaises(MalformedResponseError):
                    adapter(make_test_public_payload())
                record = json.loads((Path(tmp) / 'provider_call_001.json').read_text())
                self.assertEqual(record['status'], 'malformed_envelope')
                self.assertEqual(adapter.call_count, 1)
        with tempfile.TemporaryDirectory() as tmp:
            adapter = VisualProviderAdapter(lambda _: (envelope, 'request-1'), model='offline-fixture', record_dir=tmp)
            self.assertEqual(adapter(make_test_public_payload())['command']['action'], 'hold')
            record = json.loads((Path(tmp) / 'provider_call_001.json').read_text())
            self.assertEqual(record['request_id'], 'request-1')

    def test_interrupt_preserves_adapter_and_episode_outcomes(self):
        def interrupt(_):
            raise KeyboardInterrupt('interrupted after dispatch')
        env = Environment()
        env.reset(820, randomize=True)
        session = VisualPolicySession(VisualSession(env, MockRenderer()), max_calls=1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = VisualProviderAdapter(interrupt, model='offline-fixture', record_dir=root / 'adapter')
            with self.assertRaises(KeyboardInterrupt):
                run_visual_episode(root / 'episode', session, adapter, max_calls=1)
            record = json.loads((root / 'adapter/provider_call_001.json').read_text())
            self.assertEqual(record['status'], 'interrupted')
            self.assertTrue(record['transport_invoked'])
            self.assertEqual(adapter.call_count, 1)
            report = json.loads((root / 'episode/report.json').read_text())
            self.assertEqual(report['termination_reason'], 'interrupted')
            self.assertEqual(report['completed_actions'], 0)
            self.assertEqual(report['action_attempts'], 0)

    def test_pending_record_persisted_before_transport(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rec_dir = Path(tmpdir)
            saw_pending = []

            def transport(body):
                pending_file = rec_dir / 'provider_call_001.json'
                if pending_file.exists():
                    data = json.loads(pending_file.read_text())
                    saw_pending.append(data)
                return make_mock_responses_envelope({'action': 'hold', 'arguments': {'seconds': 0.5}})

            adapter = VisualProviderAdapter(transport=transport, model='gpt-5.6-sol', record_dir=rec_dir)
            adapter(make_test_public_payload())

            self.assertEqual(len(saw_pending), 1)
            self.assertEqual(saw_pending[0]['status'], 'pending')
            self.assertIsNone(saw_pending[0]['transport_invoked'])
            self.assertEqual(saw_pending[0]['model'], 'gpt-5.6-sol')
            self.assertIn('input', saw_pending[0]['request'])

            # After transport completes, record is updated to completed
            final_data = json.loads((rec_dir / 'provider_call_001.json').read_text())
            self.assertEqual(final_data['status'], 'completed')
            self.assertTrue(final_data['transport_invoked'])

    def test_preflight_error_has_zero_transport_calls_and_retains_evidence(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            rec_dir = Path(tmpdir)
            adapter = VisualProviderAdapter(
                transport=lambda b: calls.append(b),
                model='gpt-5.6-sol',
                record_dir=rec_dir
            )
            bad_payload = make_test_public_payload()
            bad_payload['observation']['rgb_png_base64'] = 'not-valid-base64!'

            with self.assertRaises(ValueError):
                adapter(bad_payload)

            self.assertEqual(adapter.call_count, 0)
            self.assertEqual(len(calls), 0)
            self.assertEqual(adapter.invocation_count, 1)

            rec_file = rec_dir / 'provider_call_001.json'
            self.assertTrue(rec_file.exists())
            rec = json.loads(rec_file.read_text())
            self.assertEqual(rec['status'], 'preparation_error')
            self.assertEqual(rec['call'], 0)
            self.assertFalse(rec['transport_invoked'])
            self.assertIn('ValueError', rec['error'])

    def test_pre_transport_filesystem_error_prevents_callback(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            blocked_file = Path(tmpdir) / 'blocked_file'
            blocked_file.write_text('I am a file, not a directory')

            adapter = VisualProviderAdapter(
                transport=lambda b: calls.append(b),
                model='gpt-5.6-sol',
                record_dir=blocked_file
            )
            with self.assertRaises((OSError, NotADirectoryError, FileExistsError)):
                adapter(make_test_public_payload())

            self.assertEqual(adapter.call_count, 0)
            self.assertEqual(len(calls), 0)

    def test_malformed_tuple_list_scalar_results_retain_evidence(self):
        cases = [
            ((), 'empty tuple'),
            ([], 'empty list'),
            ('non-json-string-scalar', 'scalar string'),
            (12345, 'integer scalar'),
        ]
        for bad_result, label in cases:
            with tempfile.TemporaryDirectory() as tmpdir:
                rec_dir = Path(tmpdir)
                adapter = VisualProviderAdapter(
                    transport=lambda _: bad_result,
                    model='gpt-5.6-sol',
                    record_dir=rec_dir
                )
                with self.assertRaises(MalformedResponseError, msg=f'Failed for {label}'):
                    adapter(make_test_public_payload())

                self.assertEqual(adapter.call_count, 1)
                rec_file = rec_dir / 'provider_call_001.json'
                self.assertTrue(rec_file.exists(), msg=f'Record missing for {label}')
                rec = json.loads(rec_file.read_text())
                self.assertEqual(rec['status'], 'malformed_envelope')
                self.assertIsNotNone(rec['error'])

    def test_truncated_png_raster_data_rejected(self):
        good_png = make_test_png(960, 720)
        truncated_png = good_png[:100]  # Valid header, truncated IDAT raster
        truncated_sha = hashlib.sha256(truncated_png).hexdigest()
        truncated_b64 = base64.b64encode(truncated_png).decode('ascii')

        obs = make_test_observation()
        obs['rgb_png_base64'] = truncated_b64
        obs['rgb_sha256'] = truncated_sha
        payload = make_test_public_payload(obs=obs)

        with self.assertRaises(ValueError) as ctx:
            build_responses_request(payload, model='gpt-5.6-sol')
        self.assertIn('truncated', str(ctx.exception).lower())

    def test_export_request_rejects_same_output_and_manifest_path(self):
        obs = make_test_observation()
        with tempfile.TemporaryDirectory() as tmpdir:
            obs_file = Path(tmpdir) / 'input_obs.json'
            obs_file.write_text(json.dumps(obs))
            target_path = Path(tmpdir) / 'same_target.json'

            # 1. Exactly identical path
            with self.assertRaises(ValueError):
                export_request(
                    source_path=obs_file,
                    output_path=target_path,
                    manifest_path=target_path,
                    model='gpt-5.6-sol'
                )
            self.assertFalse(target_path.exists())

            # 2. Resolved alias / relative path pointing to same file
            rel_alias = Path(tmpdir) / '.' / 'same_target.json'
            with self.assertRaises(ValueError):
                export_request(
                    source_path=obs_file,
                    output_path=target_path,
                    manifest_path=rel_alias,
                    model='gpt-5.6-sol'
                )
            self.assertFalse(target_path.exists())

    def test_explicit_model_required_at_all_entrypoints(self):
        payload = make_test_public_payload()

        # build_responses_request requires model
        with self.assertRaises(TypeError):
            build_responses_request(payload)  # omitted
        with self.assertRaises(ValueError):
            build_responses_request(payload, model='')
        with self.assertRaises(ValueError):
            build_responses_request(payload, model='   ')

        # VisualProviderAdapter requires model
        with self.assertRaises(TypeError):
            VisualProviderAdapter(transport=lambda _: {})  # omitted
        with self.assertRaises(ValueError):
            VisualProviderAdapter(transport=lambda _: {}, model='')
        with self.assertRaises(ValueError):
            VisualProviderAdapter(transport=lambda _: {}, model='   ')

        # export_request requires model
        with tempfile.TemporaryDirectory() as tmpdir:
            obs_file = Path(tmpdir) / 'obs.json'
            obs_file.write_text(json.dumps(make_test_observation()))
            out_file = Path(tmpdir) / 'out.json'
            with self.assertRaises(TypeError):
                export_request(obs_file, out_file)  # omitted
            with self.assertRaises(ValueError):
                export_request(obs_file, out_file, model='')
            with self.assertRaises(ValueError):
                export_request(obs_file, out_file, model='  ')


if __name__ == '__main__':
    unittest.main()
