"""Post-hoc C1 geometry audit. Loads saved states; never steps physics or a model.

Run from the repo root with PYTHONPATH=. .venv/bin/python scripts/audit_codex_c1.py
--episode runtime/humanoid/codex-C1/seed-820 --output <new directory>.
Private diagnostics only: none of this output is a controller observation.
"""
import argparse
import hashlib
import itertools
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np

from humanoid_sim.environment import Environment, ARM_NAMES, HAND_NAMES
from humanoid_sim.interface import PolicyInterface, rotation_from_quaternion
from humanoid_sim.scene import ROOT, SCENE
from humanoid_sim.visual import integration_state


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def context():
    # Avoid Environment.__init__/reset, which would advance a new simulation.
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    joints = np.array([model.joint(name).id for name in ARM_NAMES])
    return SimpleNamespace(model=model, data=mujoco.MjData(model),
        arm_joints=joints, arm_q=model.jnt_qposadr[joints], arm_v=model.jnt_dofadr[joints],
        arm_a=np.array([model.actuator(name).id for name in ARM_NAMES]),
        site=model.site('right_grasp').id, object_id=model.body('red_block').id,
        object_geom=model.geom('object').id)


def contact_record(env, c):
    return {'geom_ids': [int(c.geom1), int(c.geom2)],
            'geom_names': [env.model.geom(g).name for g in (c.geom1, c.geom2)],
            'body_names': [env.model.body(int(env.model.geom_bodyid[g])).name
                           for g in (c.geom1, c.geom2)],
            'distance_m': float(c.dist), 'position_world_m': c.pos.tolist()}


def hand_bounds(env, data):
    """Actual collision mesh vertices/box corners, expressed about the grasp site.

    Bounds describe occupied geometry, not a free grasp cavity or safe trajectory.
    No object state contributes to these bounds.
    """
    result = []
    for g in range(env.model.ngeom):
        body = env.model.body(int(env.model.geom_bodyid[g])).name
        if not body.startswith('right_hand_') or not (env.model.geom_contype[g] or env.model.geom_conaffinity[g]):
            continue
        kind = env.model.geom_type[g]
        if kind == mujoco.mjtGeom.mjGEOM_MESH:
            mesh = env.model.geom_dataid[g]
            start, count = env.model.mesh_vertadr[mesh], env.model.mesh_vertnum[mesh]
            vertices = env.model.mesh_vert[start:start+count]
        elif kind == mujoco.mjtGeom.mjGEOM_BOX:
            vertices = np.array(list(itertools.product((-1, 1), repeat=3))) * env.model.geom_size[g]
        else:
            raise ValueError(f'Unsupported collision geometry: {g}, {kind}')
        world = vertices @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g]
        relative = world - data.site_xpos[env.site]
        local = relative @ data.site_xmat[env.site].reshape(3, 3)
        result.append({'geom_id': g, 'body': body,
            'world_offset_min_m': relative.min(axis=0).tolist(),
            'world_offset_max_m': relative.max(axis=0).tolist(),
            'site_local_min_m': local.min(axis=0).tolist(),
            'site_local_max_m': local.max(axis=0).tolist()})
    return result


def audit(episode, output):
    episode, output = Path(episode).resolve(), Path(output).resolve()
    if output == episode or output.is_relative_to(episode) or episode.is_relative_to(output):
        raise ValueError('Source and output directories must not overlap')
    if output.exists():
        raise ValueError('Output directory must be new')
    source_hashes = {str(p.relative_to(episode)): digest(p)
                     for p in sorted(episode.rglob('*')) if p.is_file()}
    archive = ROOT / 'experiments/humanoid-pick-place/results/codex_C1_episode.zip'
    with zipfile.ZipFile(archive) as saved:
        archived = json.loads(saved.read('sha256.json'))
    expected_inputs = {name.removeprefix('seed-820/'): value for name, value in archived.items()
                       if name.startswith('seed-820/')}
    if source_hashes != expected_inputs:
        raise ValueError('Episode files differ from the retained C1 archive manifest')
    report = json.loads((episode / 'report.json').read_text())
    if report['seed'] != 820 or report['provenance']['protocol_id'] != 'humanoid-codex-c1-development':
        raise ValueError('This audit is restricted to the saved C1 seed-820 episode')
    if report['provenance']['mujoco'] != mujoco.__version__:
        raise ValueError('Use the recorded MuJoCo version for this audit')
    required_sources = ('humanoid_sim/environment.py', 'humanoid_sim/interface.py',
                        'humanoid_sim/scoring.py', 'humanoid_sim/scene.py',
                        'humanoid_sim/visual.py', 'scenes/g1_pick_place.xml')
    for path in required_sources:
        expected = report['provenance']['source_sha256'][path]
        if digest(ROOT / path) != expected:
            raise ValueError(f'Execution source changed: {path}')
    metadata = json.loads((episode / 'metadata.json').read_text())
    if digest(SCENE) != metadata['scene_sha256']:
        raise ValueError('Scene changed')
    calls = [json.loads((episode / f'call_{i:03}.json').read_text()) for i in (1, 2, 3)]
    env = context()
    api = PolicyInterface(env, 'robot_state')
    with np.load(episode / 'episode.npz', allow_pickle=False) as z:
        positions, times, final = z['qpos'].copy(), z['time'].copy(), z['state'].copy()
    if positions.shape != (len(times), env.model.nq) or not np.isfinite(positions).all() or not np.all(np.diff(times) > 0):
        raise ValueError('Invalid trajectory')
    rows = []
    for qpos, time_s in zip(positions, times):
        env.data.qpos[:] = qpos
        env.data.time = time_s
        mujoco.mj_forward(env.model, env.data)
        contacts = [contact_record(env, c) for c in env.data.contact
                    if env.object_geom in (c.geom1, c.geom2) and c.dist < 0
                    and any(int(env.model.geom_bodyid[g]) in api.moving_bodies for g in (c.geom1, c.geom2))]
        extent = np.abs(env.data.xmat[env.object_id].reshape(3, 3)) @ env.model.geom_size[env.object_geom]
        rows.append({'time_s': float(time_s), 'hand_xyz_m': env.data.site_xpos[env.site].tolist(),
            'object_xyz_m': env.data.xpos[env.object_id].tolist(),
            'object_vertical_extent_m': float(extent[2]),
            'object_upright_axis_z_abs': abs(float(env.data.xmat[env.object_id].reshape(3, 3)[2, 2])),
            'object_hand_contacts': contacts})
    def at(time_s):
        index = int(np.argmin(abs(times-time_s)))
        if abs(times[index]-time_s) > 1e-8:
            raise ValueError('Requested endpoint is not saved exactly')
        return index
    start = at(calls[1]['time_s'])
    env.data.qpos[:] = positions[start]
    mujoco.mj_forward(env.model, env.data)
    bounds = hand_bounds(env, env.data)
    # Full saved integration state exists only at the final endpoint. Reproduce the
    # rejected production IK/preflight there; no dynamic replay or force claims.
    mujoco.mj_setState(env.model, env.data, final, mujoco.mjtState.mjSTATE_INTEGRATION)
    mujoco.mj_forward(env.model, env.data)
    before = integration_state(env).copy()
    command = calls[2]['command']['arguments']
    target = env.data.ctrl.copy()
    target[env.arm_a] = Environment.solve(env, command['xyz_m'], rotation_from_quaternion(command['quaternion_wxyz']))
    error = None
    try:
        api.preflight(target)
    except ValueError as exc:
        error = str(exc)
    if error != calls[2]['error']:
        raise ValueError('Production guard did not reproduce the archived rejection')
    scratch = mujoco.MjData(env.model)
    scratch.qpos[:] = env.data.qpos
    actual = env.data.qpos[env.arm_q].copy()
    path = []
    for i, fraction in enumerate(np.linspace(0, 1, 101)):
        scratch.qpos[env.arm_q] = actual + (target[env.arm_a]-actual)*fraction*fraction*(3-2*fraction)
        mujoco.mj_forward(env.model, scratch)
        violations = [contact_record(env, c) for c in scratch.contact
                      if env.object_geom not in (c.geom1, c.geom2) and c.dist < -.002
                      and {int(env.model.geom_bodyid[g]) for g in (c.geom1, c.geom2)} & api.moving_bodies]
        path.append({'sample_index': i, 'path_fraction': float(fraction),
                     'hand_xyz_m': scratch.site_xpos[env.site].tolist(), 'violations': violations})
    first = next(p for p in path if p['violations'])
    if not np.array_equal(before, integration_state(env)):
        raise ValueError('Audit changed loaded integration state')
    initial, final_row = rows[start], rows[-1]
    displacement = np.array(final_row['object_xyz_m']) - initial['object_xyz_m']
    contact_rows = [r for r in rows[start:] if r['object_hand_contacts']]
    max_sample = max(((-c['distance_m'], r['time_s'], c) for r in rows for c in r['object_hand_contacts']), key=lambda item: item[0])
    # Independent robot-only calibration, not derived from the failed object's pose.
    nominal = context()
    hand_joints = np.array([nominal.model.joint(name).id for name in HAND_NAMES])
    nominal.data.qpos[nominal.model.jnt_qposadr[hand_joints]] = Environment.hand_targets(nominal, 0)
    nominal.data.qpos[nominal.arm_q] = Environment.solve(nominal, [.24, -.18, .94])
    mujoco.mj_forward(nominal.model, nominal.data)
    nominal_bounds = hand_bounds(nominal, nominal.data)
    result = {'status': 'complete', 'mode': 'private_posthoc_qpos_geometry_and_final_state_preflight',
        'physics_steps': 0, 'model_invocations': 0,
        'source_episode': str(episode), 'source_files_sha256': source_hashes,
        'source_archive_sha256': digest(archive),
        'physical_source_sha256': {p: report['provenance']['source_sha256'][p] for p in required_sources},
        'audit_source_sha256': digest(Path(__file__)), 'mujoco_version': mujoco.__version__,
        'approach_start': initial, 'approach_end': final_row,
        'object_displacement_m': displacement.tolist(),
        'object_xy_displacement_m': float(np.linalg.norm(displacement[:2])),
        'requested_approach_minus_initial_object_xyz_m': (np.array(calls[1]['command']['arguments']['xyz_m'])-initial['object_xyz_m']).tolist(),
        'requested_descent_minus_displaced_object_xyz_m': (np.array(command['xyz_m'])-final_row['object_xyz_m']).tolist(),
        'first_sampled_hand_contact': contact_rows[0],
        'max_sampled_object_hand_penetration': {'penetration_m': max_sample[0], 'time_s': max_sample[1], 'contact': max_sample[2]},
        'authoritative_private_score': json.loads((episode / 'evaluator_report.json').read_text()),
        'pre_approach_hand_collision_bounds': bounds,
        'nominal_open_hand_geometry': {
            'source': 'robot model, closure=0 joint targets, downward IK at nominal site [.24,-.18,.94]; no episode state',
            'world_offset_min_m': np.min([v['world_offset_min_m'] for v in nominal_bounds], axis=0).tolist(),
            'world_offset_max_m': np.max([v['world_offset_max_m'] for v in nominal_bounds], axis=0).tolist(),
            'per_geom': nominal_bounds},
        'rejected_path': {'production_error': error, 'first_violation': first,
                         'max_penetration_m': max(-c['distance_m'] for p in path for c in p['violations']),
                         'samples': path, 'final_integration_state_unchanged': True},
        'trajectory_samples': rows,
        'limitations': ['Saved trajectory is qpos at approximately 30 Hz, not full dynamic state at every step.',
            'Recomputed geometric contacts cannot reproduce peak forces or necessarily the 1 kHz scorer maximum.',
            'Guard path fraction is joint interpolation fraction, not simulated time or a newly executed action.',
            'Requested action coordinates do not reveal the model\'s internal object estimate.',
            'Collision bounds enclose solid geometry, not a validated grasp cavity or collision-free path.']}
    if source_hashes != {str(p.relative_to(episode)): digest(p) for p in sorted(episode.rglob('*')) if p.is_file()}:
        raise ValueError('Source episode changed during audit')
    output.mkdir(parents=True)
    (output / 'audit.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.episode, args.output)
    print(json.dumps({'status': result['status'], 'first_guard_violation': result['rejected_path']['first_violation'],
                      'object_displacement_m': result['object_displacement_m']}, indent=2))
