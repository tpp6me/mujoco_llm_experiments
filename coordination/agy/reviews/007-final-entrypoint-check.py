import sys, json, hashlib, zipfile, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import contextlib, io
sys.path.insert(0,'/private/tmp/mujoco-llms-agy-007')
from humanoid_sim import codex_policy as c
from humanoid_sim.visual_policy_runner import run_visual_episode
from humanoid_sim import visual_policy_runner as runner
with zipfile.ZipFile(c.ROOT/'experiments/humanoid-pick-place/results/codex_C1_episode.zip') as z:
    obs=json.loads(z.read('seed-820/call_001.json'))['request']['observation']
    for i in (1,2,3):
        call=json.loads(z.read(f'seed-820/call_{i:03}.json'))
        assert c.public_input(call['request'])[1].encode()==z.read(f'seed-820/codex/decision-{i:03}/prompt.txt')
proposal=c.PROTOCOL_PATHS['c2'].read_text().split('```text\n')[1].split('```')[0]
assert c.C2_INSTRUCTION==proposal
bundle=c.ROOT/'coordination/agy/reports/007-c2-preflight'
manifest=json.loads((bundle/'manifest.json').read_text())
for f,m in manifest['files'].items():
    assert hashlib.sha256((bundle/f).read_bytes()).hexdigest()==m['sha256'],f
assert c.public_input(json.loads((bundle/'public_payload.json').read_text()),condition='c2')[1]==(bundle/'prompt.txt').read_text()
assert hashlib.sha256(c.serialize_geometry_evidence(c.generate_geometry_evidence())).hexdigest()==manifest['files']['geometry_evidence.json']['sha256']
class DummyEnvironment:
    def __init__(self): self.data=SimpleNamespace(time=.5)
    def reset(self,*a,**k): pass
class DummyRenderer:
    def __init__(self,*a,**k): pass
    def close(self): pass
original=c.CodexPolicy
with tempfile.TemporaryDirectory() as d:
    out=Path(d)/'episode'
    def interrupted(argv,prompt,cwd,env,timeout,record_dir):
        assert (out/'geometry_evidence.json').exists()
        assert c.C2_INSTRUCTION in prompt
        raise KeyboardInterrupt('review-only interruption, no CLI invoked')
    def factory(*a,**k): return original(*a,process_runner=interrupted,**k)
    def fake_session(*a,**k): return SimpleNamespace(capture=lambda:obs)
    info={'cli_version':c.SUPPORTED_VERSION,'login_method':'chatgpt','executable':'mock-codex'}
    with patch.object(sys,'argv',['codex_policy','--execute','--condition','c2','--output',str(out)]),patch.object(c,'check_install',return_value=info),patch.object(c,'CodexPolicy',side_effect=factory),patch('humanoid_sim.environment.Environment',DummyEnvironment),patch('humanoid_sim.visual.RGBRenderer',DummyRenderer),patch('humanoid_sim.visual.VisualSession',return_value=None),patch.object(runner,'VisualPolicySession',side_effect=fake_session),contextlib.redirect_stdout(io.StringIO()):
        try: c.main()
        except KeyboardInterrupt: pass
        else: raise AssertionError('Expected interruption')
    report=json.loads((out/'report.json').read_text())
    assert report['termination_reason']=='interrupted'
    assert report['provenance']['geometry_evidence_sha256']==hashlib.sha256((out/'geometry_evidence.json').read_bytes()).hexdigest()
    assert report['provenance']['static_instruction_sha256']==hashlib.sha256(c.static_instruction('c2').encode()).hexdigest()
    record=json.loads((out/'codex/decision-001/record.json').read_text())
    assert record['mode']=='mock_codex' and record['status']=='interrupted'
    assert record['prompt_sha256']==hashlib.sha256((out/'codex/decision-001/prompt.txt').read_bytes()).hexdigest()
print('PASS: archived C1 prompts; exact C2 text; all preflight file hashes and payload; actual main path retains geometry and truthful static/full prompt hashes on injected interruption. No real CLI, renderer or physics used.')
