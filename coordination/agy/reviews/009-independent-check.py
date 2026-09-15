import argparse,hashlib,json,sys,tempfile,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
parser=argparse.ArgumentParser(description='Reproduce the retained C2 offline audit with physics/process calls forbidden.')
parser.add_argument('--worktree',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
base=args.worktree.resolve()
sys.path.insert(0,str(base))
from scripts.audit_codex_c2 import audit
from humanoid_sim.environment import HAND_NAMES
arc=base/'experiments/humanoid-pick-place/results/codex_C2_episode.zip'
with tempfile.TemporaryDirectory(prefix='codex-c2-review-') as tmp:
    tmp=Path(tmp)
    with zipfile.ZipFile(arc) as z:
        for name in z.namelist():
            if name.startswith('seed-820/'):
                assert not Path(name).is_absolute() and '..' not in Path(name).parts
                z.extract(name,tmp)
    ep=tmp/'seed-820'
    with patch('mujoco.mj_step',side_effect=AssertionError('physics forbidden')), patch('humanoid_sim.environment.Environment.reset',side_effect=AssertionError('reset forbidden')), patch('subprocess.Popen',side_effect=AssertionError('process/model forbidden')), patch('subprocess.run',side_effect=AssertionError('process/model forbidden')):
        actual=audit(ep,tmp/'audit')
    saved=base/'experiments/humanoid-pick-place/results/codex_C2_audit'
    matches=[]
    hash_mismatches=[]
    for name in ('audit.json','private_trajectory_annotations.json','public_proprioception_history.json'):
        a=json.loads((tmp/'audit'/name).read_text()); b=json.loads((saved/name).read_text())
        if name=='audit.json':
            a.pop('source_episode');b.pop('source_episode')
            ah=a.pop('audit_source_sha256');bh=b.pop('audit_source_sha256')
            if ah!=bh: hash_mismatches.append({'actual':ah,'embedded':bh})
        if a!=b:
            print('MISMATCH',name,[k for k in a if a[k]!=b.get(k)])
            for k in a:
                if a[k]!=b.get(k) and k not in ('source_files_sha256','physical_source_sha256'):
                    print(k, str(a[k])[:300], str(b.get(k))[:300])
        assert a==b,name
        matches.append(name)
    assert (tmp/'audit/contact_sheet.png').read_bytes()==(saved/'contact_sheet.png').read_bytes()
    sheet=Image.open(saved/'contact_sheet.png')
    pub=json.loads((saved/'public_proprioception_history.json').read_text())
    for n,item in enumerate(pub):
        i=item['call']; call=json.loads((ep/f'call_{i:03}.json').read_text()); req=call['request']; inp=item['input_preceding_decision']
        assert inp['public_robot_state']==req['observation']['robot_state']
        assert inp['public_history']==req['history']
        assert inp['observation_id']==req['observation']['observation_id']
        assert inp['image_sha256']==req['observation']['rgb_sha256']
        original=Image.open(ep/f'codex/decision-{i:03}/observation.png').resize((480,360),Image.Resampling.LANCZOS)
        x=(n%4)*480; y=(n//4)*410+50
        assert np.array_equal(np.asarray(sheet.crop((x,y,x+480,y+360))),np.asarray(original))
    result={'status':'requires_correction' if hash_mismatches else 'passed','code_hash_mismatches':hash_mismatches,'reproduced_json_artifacts':matches,'contact_sheet_byte_exact':True,'original_image_panels_verified':7,'public_state_history_identity_rows_verified':7,'physics_steps':0,'model_invocations':0,'audit_code_sha256':hashlib.sha256((base/'scripts/audit_codex_c2.py').read_bytes()).hexdigest(),'geometry':actual['finger_geometry_vs_nominal_bounds']['action_4_envelope'],'first_contact':actual['telemetry_vs_sampled_geometry']['sampled_qpos_geometry'],'finger_joint_order':HAND_NAMES,'ik_error':actual['action_9_rejection']['reproduced_error']}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

raise SystemExit(1 if hash_mismatches else 0)
