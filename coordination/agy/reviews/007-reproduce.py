"""Review reproductions against AGY 007. No model decisions or physics steps."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import zipfile

sys.path.insert(0, '/private/tmp/mujoco-llms-agy-007')
from humanoid_sim import codex_policy as c
from humanoid_sim.visual_policy_runner import run_visual_episode, write_json
from tests.test_visual_provider_adapter import MockRenderer

result = {}
with zipfile.ZipFile(c.ROOT / 'experiments/humanoid-pick-place/results/codex_C1_episode.zip') as z:
    call = json.loads(z.read('seed-820/call_001.json'))
    obs = call['request']['observation']
    comparisons = []
    for i in (1, 2, 3):
        saved = json.loads(z.read(f'seed-820/call_{i:03}.json'))
        _, prompt = c.public_input(saved['request'])
        comparisons.append(prompt.encode() == z.read(f'seed-820/codex/decision-{i:03}/prompt.txt'))
    result['all_three_c1_prompts_match_archives'] = all(comparisons)
proposal = (c.ROOT / 'experiments/humanoid-pick-place/protocols/C2_PROPOSAL.md').read_text()
result['c2_text_matches_proposal'] = c.C2_INSTRUCTION == proposal.split('```text\n', 1)[1].split('```', 1)[0]
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    geometry = c.generate_geometry_evidence()
    expected = hashlib.sha256((json.dumps(geometry, indent=2, sort_keys=True)+'\n').encode()).hexdigest()
    write_json(root / 'geometry_evidence.json', geometry)
    actual = hashlib.sha256((root / 'geometry_evidence.json').read_bytes()).hexdigest()
    result['geometry_digest'] = {'recorded_by_execute': expected, 'actual_written_file': actual, 'matches': expected == actual}
    result['actual_geometry'] = geometry['nominal_geometry']
    result['metadata_cases'] = []
    for index, metadata in enumerate([
        {'condition': 'c2', 'condition_id': 'c1', 'protocol_id': c.PROTOCOL_IDS['c2']},
        {'protocol_id': c.PROTOCOL_IDS['c1']},
        {'condition': 'c2', 'condition_id': 'c2', 'protocol_id': c.PROTOCOL_IDS['c2'], 'model_requested': c.MODEL},
    ]):
        reached = []
        class Stub:
            condition = 'c2'
            model = 'other-model'
            timeout = 180.
            def __call__(self, payload):
                reached.append(True)
                raise RuntimeError('review sentinel; no decision or action executed')
        try:
            report = run_visual_episode(root / f'case-{index}', SimpleNamespace(capture=lambda: obs), Stub(),
                seed=820, execution_metadata={'offline_only': True, **metadata})
            result['metadata_cases'].append({'metadata': metadata, 'callable_reached': bool(reached),
                                            'rejected_before_capture': False, 'termination': report['termination_reason']})
        except ValueError as exc:
            result['metadata_cases'].append({'metadata': metadata, 'callable_reached': bool(reached),
                                            'rejected_before_capture': True, 'error': str(exc)})
    fake_info = {'cli_version': c.SUPPORTED_VERSION, 'login_method': 'chatgpt', 'executable': 'mock-codex'}
    with patch.object(c, 'check_install', return_value=fake_info), patch('humanoid_sim.visual.RGBRenderer', MockRenderer), patch('mujoco.mj_step', side_effect=AssertionError('No physics permitted')):
        # MockRenderer's constructor takes no arguments; adapt the factory.
        with patch('humanoid_sim.visual.RGBRenderer', side_effect=lambda *a, **k: MockRenderer()):
            preflight = c.run_preflight(root / 'preflight', condition='c2')
            result['mocked_preflight'] = {k: preflight[k] for k in ('status', 'source_commit', 'model_invocations', 'physics_steps')}
    with patch.object(c, 'check_install', side_effect=RuntimeError('Codex CLI/login unavailable')):
        try:
            c.run_preflight(root / 'without-login', condition='c2')
        except RuntimeError as exc:
            result['offline_preflight_requires_real_login_by_default'] = str(exc)

Path('/private/tmp/agy-007-review/reproduction.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
# Import tests before patching so its direct auth unit retains the production function.
suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_codex_policy')
# Run with platform/auth boundaries injected. No rendering or real CLI.
with patch.object(c, 'check_install', return_value=fake_info), patch('humanoid_sim.visual.RGBRenderer', side_effect=lambda *a, **k: MockRenderer()):
    with open('/private/tmp/agy-007-review/policy-tests.txt', 'w') as log:
        test_result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
print('Policy tests with injected auth/renderer:', test_result.testsRun, 'success:', test_result.wasSuccessful())
