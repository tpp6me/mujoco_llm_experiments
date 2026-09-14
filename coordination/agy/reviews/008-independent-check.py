"""Independent post-run C2 evidence audit; no decisions, reset or physics steps."""
import argparse,json,hashlib,sys,zipfile,statistics
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worktree',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
sys.path.insert(0,str(args.worktree.resolve()))
from humanoid_sim.codex_policy import public_input,validate_events,static_instruction
base=args.worktree.resolve()
episode=base/'runtime/humanoid/codex-C2/seed-820'
report=json.loads((episode/'report.json').read_text())
score=json.loads((episode/'evaluator_report.json').read_text())
prov=report['provenance']
assert prov['condition']==prov['condition_id']=='c2'
assert prov['protocol_id']=='humanoid-codex-c2-development'
assert prov['source_commit']=='a675e5223a7966926744624561d2e4542883d17a'
assert prov['git_status']=='clean' and prov['is_dirty'] is False
assert prov['static_instruction_sha256']==hashlib.sha256(static_instruction('c2').encode()).hexdigest()
assert prov['geometry_evidence_sha256']==hashlib.sha256((episode/'geometry_evidence.json').read_bytes()).hexdigest()
for f,h in prov['source_sha256'].items():
    assert hashlib.sha256((base/f).read_bytes()).hexdigest()==h,f
calls=sorted(episode.glob('call_*.json'))
assert len(calls)==report['model_calls']<=20
records=[]
for f in calls:
    call=json.loads(f.read_text())
    folder=episode/'codex'/f"decision-{call['call']:03}"
    decision=json.loads((folder/'record.json').read_text())
    png,prompt=public_input(call['request'],condition='c2')
    assert png==(folder/'observation.png').read_bytes()
    assert prompt==(folder/'prompt.txt').read_text()
    assert hashlib.sha256(png).hexdigest()==decision['image_sha256']==call['image_sha256']
    assert hashlib.sha256(prompt.encode()).hexdigest()==decision['prompt_sha256']
    assert decision['mode']=='codex_chatgpt' and decision['condition']=='c2'
    if decision['status']=='completed':
        raw=(folder/'decision.json').read_text()
        validate_events(folder/'events.jsonl',raw)
        assert json.loads(raw)['command']==call['command']
    response=call.get('interface_response',{})
    if response.get('status')=='rejected':
        assert response['start_time_s']==response['end_time_s']
    records.append({'call':call['call'],'status':call['status'],'decision_status':decision['status'],
                    'command':call.get('command'),'cli_latency_s':decision['wall_latency_s']})
assert sum(x['status']=='completed' for x in records)==report['completed_actions']
rejected=sum(x['status']=='rejected' for x in records)
normal_end=report['termination_reason'] in ('deadline','action_limit')
strict=bool(score['success'] and score['max_object_penetration_m']<=.002 and report['simulated_time_s']<=25.000001 and rejected==0 and report['errors']==0 and report['refusals']==0 and report['execution_outcomes_unknown']==0 and normal_end)
result={'reviewed_source_commit':prov['source_commit'],'status':'verified','model_calls':len(calls),
        'completed_actions':report['completed_actions'],'rejected_actions':rejected,
        'termination_reason':report['termination_reason'],'physical_success':score['success'],
        'sustained_lift':score['lifted'],'strict_success':strict,
        'max_object_penetration_m':score['max_object_penetration_m'],
        'final_simulated_time_s':report['simulated_time_s'],
        'mean_cli_latency_s':statistics.mean(x['cli_latency_s'] for x in records) if records else None,
        'records':records}
archive=base/'experiments/humanoid-pick-place/results/codex_C2_episode.zip'
with zipfile.ZipFile(archive) as z:
    manifest=json.loads(z.read('sha256.json'))
    assert len(z.namelist())==len(set(z.namelist()))
    assert set(z.namelist())==set(manifest)|{'sha256.json'}
    for f,h in manifest.items():
        assert hashlib.sha256(z.read(f)).hexdigest()==h,f
        assert (episode.parent/f).read_bytes()==z.read(f),f
    assert {str(f.relative_to(episode.parent)) for f in episode.parent.rglob('*') if f.is_file()}==set(manifest)
result['archive_members_verified']=len(manifest)
result['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
