"""Independent Task010 prompt/schema preservation check; no model or physics."""
import argparse
import hashlib,json,re,sys,zipfile
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--worktree', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
base = args.worktree.resolve()
sys.path.insert(0,str(base))
import humanoid_sim.codex_policy as cp
expected=cp.static_instruction('c3')
# Independently constructed from the unmodified C2 instruction and C3 proposal.
assert hashlib.sha256(expected.encode()).hexdigest() == 'de0525e07f9470be60f9e01c4d720ad4f65260fd54b08065708e4096ce6313d0', 'C3 proposal text changed'
checks=[]
for condition in ('c1','c2'):
    arc=base/f'experiments/humanoid-pick-place/results/codex_{condition.upper()}_episode.zip'
    with zipfile.ZipFile(arc) as z:
        for f in z.namelist():
            if re.fullmatch(r'seed-820/call_\d{3}\.json',f):
                call=json.loads(z.read(f));n=call['call'];d=f'seed-820/codex/decision-{n:03}'
                png,prompt=cp.public_input(call['request'],condition=condition)
                assert png==z.read(d+'/observation.png')
                assert prompt==z.read(d+'/prompt.txt').decode(),(condition,n)
                if condition=='c2':
                    c3png,c3prompt=cp.public_input(call['request'],condition='c3')
                    assert c3png==png
                    assert c3prompt==expected+prompt[len(cp.static_instruction('c2')):]
                checks.append({'condition':condition,'call':n})
schema=json.loads((base/'experiments/humanoid-pick-place/schemas/llm-response-c3.schema.json').read_text())
assert schema['additionalProperties'] is False
assert set(schema['properties'])==set(schema['required'])=={'visual_assessment','command'}
a=schema['properties']['visual_assessment'];assert a['additionalProperties'] is False
assert set(a['properties'])==set(a['required'])=={'block_visibility','block_relative_to_fingers'}
assert set(a['properties']['block_visibility']['enum'])=={'visible','partly_visible','not_visible','uncertain'}
assert set(a['properties']['block_relative_to_fingers']['enum'])=={'between','separate','uncertain'}
assert schema['properties']['command']==cp.action_schema()['properties']['command']
result={'status':'passed','c3_static_instruction_sha256':hashlib.sha256(expected.encode()).hexdigest(),'preserved_archived_decisions':checks,'c3_public_suffix_matches_c2':True,'c3_schema_matches_proposal':True,'model_invocations':0,'physics_steps':0}
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
