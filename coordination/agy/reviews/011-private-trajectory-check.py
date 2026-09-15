"""Post-hoc C3 endpoint comparison, after blind labels; no physics stepping."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
import mujoco
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('--episode', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
a = parser.parse_args()
root = Path(__file__).resolve().parents[3]
assert Path(__file__).with_name('011-blind-labels.json').is_file()
freeze = json.loads((root/'experiments/humanoid-pick-place/protocols/C3_FREEZE.json').read_text())
for name, digest in freeze['file_sha256'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest, name
pinned = root/'experiments/humanoid-pick-place/results/codex_C3_episode.zip'
assert hashlib.sha256(pinned.read_bytes()).hexdigest() == '08202990a01ecd22adc2c860ff2260b126bfae57579963285bba6595e7198972'
with zipfile.ZipFile(pinned) as saved:
    member_hashes = json.loads(saved.read('sha256.json'))
for name in ['episode.npz', *[f'call_{n:03}.json' for n in (4,5,13,14,17,18)]]:
    assert hashlib.sha256((a.episode/name).read_bytes()).hexdigest() == member_hashes['seed-820/'+name]
model = mujoco.MjModel.from_xml_path(str(root / 'scenes/g1_pick_place.xml'))
adr = int(model.jnt_qposadr[model.joint('object_free').id])
with np.load(a.episode / 'episode.npz', allow_pickle=False) as archive:
    times, q = archive['time'].copy(), archive['qpos'].copy()
assert np.isfinite(times).all() and np.isfinite(q).all()
assert np.all(np.diff(times) > 0)
rows = []
for n in (4, 5, 13, 14, 17, 18):
    call = json.loads((a.episode / f'call_{n:03}.json').read_text())
    response = call['interface_response']
    start, end = float(response['start_time_s']), float(response['end_time_s'])
    i, j = int(np.argmin(abs(times-start))), int(np.argmin(abs(times-end)))
    assert abs(times[i]-start) < .034 and abs(times[j]-end) < .034
    before, after = q[i, adr:adr+7], q[j, adr:adr+7]
    delta = after[:3]-before[:3]
    qb, qa = before[3:7]/np.linalg.norm(before[3:7]), after[3:7]/np.linalg.norm(after[3:7])
    angle = 0. if np.array_equal(qb, qa) else float(2*np.arccos(np.clip(abs(np.dot(qb,qa)),0,1))*180/np.pi)
    rot = np.zeros(9)
    mujoco.mju_quat2Mat(rot, qa)
    rows.append({'call':n, 'action':call['command']['action'], 'status':call['status'],
                 'requested_interval_s':[start,end], 'sampled_interval_s':[float(times[i]),float(times[j])],
                 'before_xyz_m':before[:3].tolist(), 'after_xyz_m':after[:3].tolist(),
                 'displacement_xyz_m':delta.tolist(), 'xy_displacement_m':float(np.linalg.norm(delta[:2])),
                 'rotation_deg':angle, 'final_object_local_z_world_z':float(rot.reshape(3,3)[2,2])})
result = {'scope':'Private post-hoc endpoint pass after blind labels; saved qpos, no dynamics rerun',
          'physics_steps':0, 'model_invocations':0, 'sample_count':len(times),
          'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'trajectory_sha256':hashlib.sha256((a.episode/'episode.npz').read_bytes()).hexdigest(),
          'limits':'Sampled endpoint geometry, not force reconstruction or proof of enclosure. Negligible rotations/displacements can reflect numerical roundoff.',
          'rows':rows}
a.output.write_text(json.dumps(result,indent=2)+'\n')
print('Verified selected C3 trajectory endpoints without physics or model calls')
