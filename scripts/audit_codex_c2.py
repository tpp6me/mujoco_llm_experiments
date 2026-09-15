"""Post-hoc C2 failure audit. Loads saved states; never steps physics or a model.

Run from the repo root with:
PYTHONPATH=. .venv/bin/python scripts/audit_codex_c2.py \\
    --episode runtime/humanoid/codex-C2/seed-820 \\
    --output experiments/humanoid-pick-place/results/codex_C2_audit
Private diagnostics only: none of this output is a controller observation.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
from types import SimpleNamespace
import zipfile

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from humanoid_sim.environment import Environment, ARM_NAMES, HAND_NAMES
from humanoid_sim.interface import PolicyInterface, rotation_from_quaternion, quaternion
from humanoid_sim.scene import ROOT, SCENE
from humanoid_sim.visual import integration_state

PINNED_C2_ARCHIVE_SHA256 = '940f3ef71518a15f9f171adb877c108596060142b9f1e08276146ad876bd95f8'

# Audit runtime dependencies: only the simulation, kinematic, interface, and scene assets
# required by this post-hoc audit to reconstruct and evaluate saved physical states.
# Historical execution provenance recorded in report['provenance']['source_sha256'] includes
# controller/runner files (e.g. codex_policy.py) that were active during trial execution but
# are not imported, executed, or depended upon by this post-hoc diagnostic audit.
AUDIT_RUNTIME_DEPENDENCIES = (
    'humanoid_sim/environment.py',
    'humanoid_sim/interface.py',
    'humanoid_sim/scene.py',
    'humanoid_sim/visual.py',
    'scenes/g1_pick_place.xml',
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def context():
    # Avoid Environment.__init__/reset, which would advance a new simulation.
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    joints = np.array([model.joint(name).id for name in ARM_NAMES])
    return SimpleNamespace(
        model=model,
        data=mujoco.MjData(model),
        arm_joints=joints,
        arm_q=model.jnt_qposadr[joints],
        arm_v=model.jnt_dofadr[joints],
        arm_a=np.array([model.actuator(name).id for name in ARM_NAMES]),
        site=model.site('right_grasp').id,
        object_id=model.body('red_block').id,
        object_geom=model.geom('object').id,
    )


def contact_record(env, c):
    return {
        'geom_ids': [int(c.geom1), int(c.geom2)],
        'geom_names': [env.model.geom(g).name for g in (c.geom1, c.geom2)],
        'body_names': [
            env.model.body(int(env.model.geom_bodyid[g])).name
            for g in (c.geom1, c.geom2)
        ],
        'distance_m': float(c.dist),
        'position_world_m': c.pos.tolist(),
    }


def hand_bounds(env, data):
    """Actual collision mesh vertices/box corners, expressed about the grasp site.

    Bounds describe occupied solid geometry, not a free grasp cavity or safe trajectory.
    No object state contributes to these bounds.
    """
    result = []
    for g in range(env.model.ngeom):
        body = env.model.body(int(env.model.geom_bodyid[g])).name
        if not body.startswith('right_hand_') or not (
            env.model.geom_contype[g] or env.model.geom_conaffinity[g]
        ):
            continue
        kind = env.model.geom_type[g]
        if kind == mujoco.mjtGeom.mjGEOM_MESH:
            mesh = env.model.geom_dataid[g]
            start, count = env.model.mesh_vertadr[mesh], env.model.mesh_vertnum[mesh]
            vertices = env.model.mesh_vert[start:start + count]
        elif kind == mujoco.mjtGeom.mjGEOM_BOX:
            vertices = (
                np.array(list(itertools.product((-1, 1), repeat=3)))
                * env.model.geom_size[g]
            )
        else:
            raise ValueError(f'Unsupported collision geometry: {g}, {kind}')
        world = vertices @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g]
        relative = world - data.site_xpos[env.site]
        local = relative @ data.site_xmat[env.site].reshape(3, 3)
        result.append({
            'geom_id': g,
            'body': body,
            'world_offset_min_m': relative.min(axis=0).tolist(),
            'world_offset_max_m': relative.max(axis=0).tolist(),
            'site_local_min_m': local.min(axis=0).tolist(),
            'site_local_max_m': local.max(axis=0).tolist(),
        })
    return result


def generate_contact_sheet(episode, calls, output_path):
    """Produce an ordered contact sheet from original saved public images for decisions 3-9.

    Labels are strictly factual (decision index, timestamp, and following command).
    No interpretive summary claims are embedded in the visual artifact.
    """
    panel_w, panel_h = 480, 360
    header_h = 50
    cell_w = panel_w
    cell_h = panel_h + header_h
    cols, rows = 4, 2
    sheet_w = cols * cell_w
    sheet_h = rows * cell_h

    sheet = Image.new('RGB', (sheet_w, sheet_h), color=(30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=14)
    font_title = ImageFont.load_default(size=16)

    for idx, call in enumerate(calls):
        col = idx % cols
        row = idx // cols
        x0 = col * cell_w
        y0 = row * cell_h

        draw.rectangle([x0, y0, x0 + cell_w, y0 + header_h], fill=(45, 52, 54))

        c_num = call['call']
        t_s = call['time_s']
        cmd = call.get('command', {})
        act = cmd.get('action', 'none')
        args = cmd.get('arguments', {})
        if act == 'move':
            cmd_str = f"move xyz={args.get('xyz_m')} sec={args.get('seconds')}"
        elif act == 'hand':
            cmd_str = f"hand closure={args.get('closure')} sec={args.get('seconds')}"
        else:
            cmd_str = f'{act} {args}'

        status_str = call.get('status', 'unknown')
        if status_str == 'rejected':
            cmd_str += ' (interface status: rejected)'

        draw.text(
            (x0 + 10, y0 + 6),
            f'Decision {c_num} (t = {t_s:.2f} s)',
            fill=(255, 255, 255),
            font=font_title,
        )
        draw.text(
            (x0 + 10, y0 + 26),
            f'Command: {cmd_str}',
            fill=(223, 230, 233),
            font=font,
        )

        img_path = episode / 'codex' / f'decision-{c_num:03}' / 'observation.png'
        orig = Image.open(img_path).resize((panel_w, panel_h), Image.Resampling.LANCZOS)
        sheet.paste(orig, (x0, y0 + header_h))

    # Cell 8: Purely factual reference metadata (no interpretive claims)
    x0 = 3 * cell_w
    y0 = 1 * cell_h
    draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], fill=(20, 20, 25))
    draw.rectangle([x0, y0, x0 + cell_w, y0 + header_h], fill=(45, 52, 54))
    draw.text(
        (x0 + 10, y0 + 6),
        'Audit Reference & Artifact Index',
        fill=(255, 255, 255),
        font=font_title,
    )
    info_lines = [
        'Condition: c2, development seed 820',
        'Panels: public RGB camera inputs (960x720)',
        'Decision sequence: 3 through 9',
        'Labels: observation time and following command',
        '',
        'Public telemetry artifact:',
        '  public_proprioception_history.json',
        'Private geometry artifact:',
        '  private_trajectory_annotations.json',
        'Audit numeric report:',
        '  audit.json',
    ]
    for li, line in enumerate(info_lines):
        draw.text(
            (x0 + 15, y0 + header_h + 15 + li * 24),
            line,
            fill=(200, 200, 200),
            font=font,
        )

    sheet.save(output_path)


def audit(episode, output):
    episode, output = Path(episode).resolve(), Path(output).resolve()
    if output == episode or output.is_relative_to(episode) or episode.is_relative_to(output):
        raise ValueError('Source and output directories must not overlap')
    if output.exists():
        raise ValueError('Output directory must be new')

    # Verify committed C2 archive SHA-256 and complete member manifest
    archive = ROOT / 'experiments/humanoid-pick-place/results/codex_C2_episode.zip'
    archive_digest = digest(archive)
    if archive_digest != PINNED_C2_ARCHIVE_SHA256:
        raise ValueError(
            f'Archive SHA-256 {archive_digest} does not match pinned C2 archive digest {PINNED_C2_ARCHIVE_SHA256}'
        )

    with zipfile.ZipFile(archive) as saved:
        namelist = saved.namelist()
        if len(namelist) != len(set(namelist)):
            raise ValueError('Archive contains duplicate member names')
        if 'sha256.json' not in namelist:
            raise ValueError('Archive missing sha256.json manifest')
        archived = json.loads(saved.read('sha256.json'))
        expected_members = set(archived.keys()) | {'sha256.json'}
        if set(namelist) != expected_members:
            raise ValueError('Archive namelist does not match sha256.json member set')
        for member_name, expected_hash in archived.items():
            member_bytes = saved.read(member_name)
            actual_hash = hashlib.sha256(member_bytes).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError(f'Archive member {member_name} byte hash mismatch')

    source_hashes = {
        str(p.relative_to(episode)): digest(p)
        for p in sorted(episode.rglob('*'))
        if p.is_file()
    }
    expected_inputs = {
        name.removeprefix('seed-820/'): value
        for name, value in archived.items()
        if name.startswith('seed-820/')
    }
    if source_hashes != expected_inputs:
        raise ValueError('Episode files differ from the verified C2 archive member manifest')

    report = json.loads((episode / 'report.json').read_text())
    if (
        report['seed'] != 820
        or report['provenance']['protocol_id'] != 'humanoid-codex-c2-development'
    ):
        raise ValueError('This audit is restricted to the saved C2 seed-820 episode')
    if report['provenance']['mujoco'] != mujoco.__version__:
        raise ValueError('Use the recorded MuJoCo version for this audit')

    metadata = json.loads((episode / 'metadata.json').read_text())
    if digest(SCENE) != metadata['scene_sha256']:
        raise ValueError('Scene changed')

    # Verify local runtime dependencies against execution provenance.
    # Note: historical execution provenance recorded in report['provenance']['source_sha256']
    # spans 30 files used during the trial run (including controller/policy definitions).
    # The post-hoc audit does not execute the controller policy, but reconstructs and evaluates
    # saved physical states using only physical simulation/scene runtime dependencies.
    # We verify that these actual runtime dependencies match historical execution provenance.
    for path in AUDIT_RUNTIME_DEPENDENCIES:
        if path not in report['provenance']['source_sha256']:
            raise ValueError(f'Required audit runtime dependency missing from provenance: {path}')
        expected = report['provenance']['source_sha256'][path]
        if digest(ROOT / path) != expected:
            raise ValueError(f'Execution source changed: {path}')

    all_calls = [json.loads((episode / f'call_{i:03}.json').read_text()) for i in range(1, 10)]
    evaluator_report = json.loads((episode / 'evaluator_report.json').read_text())

    env = context()
    api = PolicyInterface(env, 'robot_state')

    with np.load(episode / 'episode.npz', allow_pickle=False) as z:
        positions, times, final = z['qpos'].copy(), z['time'].copy(), z['state'].copy()

    if (
        positions.shape != (len(times), env.model.nq)
        or not np.isfinite(positions).all()
        or not np.all(np.diff(times) > 0)
    ):
        raise ValueError('Invalid trajectory')

    # Reconstruct forward kinematics across all sampled states
    rows = []
    hand_geoms = {
        g
        for g in range(env.model.ngeom)
        if env.model.body(int(env.model.geom_bodyid[g])).name.startswith('right_hand_')
    }

    for qpos, time_s in zip(positions, times):
        env.data.qpos[:] = qpos
        env.data.time = time_s
        mujoco.mj_forward(env.model, env.data)
        contacts = [
            contact_record(env, c)
            for c in env.data.contact
            if (c.geom1 == env.object_geom and c.geom2 in hand_geoms)
            or (c.geom2 == env.object_geom and c.geom1 in hand_geoms)
        ]
        extent = np.abs(env.data.xmat[env.object_id].reshape(3, 3)) @ env.model.geom_size[env.object_geom]
        rows.append({
            'time_s': float(time_s),
            'hand_xyz_m': env.data.site_xpos[env.site].tolist(),
            'object_xyz_m': env.data.xpos[env.object_id].tolist(),
            'object_vertical_extent_m': float(extent[2]),
            'object_upright_axis_z_abs': abs(float(env.data.xmat[env.object_id].reshape(3, 3)[2, 2])),
            'object_hand_contacts': contacts,
        })

    def at(time_s):
        index = int(np.argmin(abs(times - time_s)))
        if abs(times[index] - time_s) > 1e-8:
            raise ValueError('Requested endpoint is not saved exactly')
        return index

    # --- Action 4 Analysis ---
    act4_start_idx = at(all_calls[3]['time_s'])
    act4_end_idx = at(all_calls[4]['time_s'])
    act4_rows = rows[act4_start_idx:act4_end_idx + 1]

    initial_act4 = act4_rows[0]
    final_act4 = act4_rows[-1]
    act4_disp = np.array(final_act4['object_xyz_m']) - initial_act4['object_xyz_m']
    act4_xy_disp = float(np.linalg.norm(act4_disp[:2]))
    act4_total_disp = float(np.linalg.norm(act4_disp))

    # Compute rotation angle over Action 4
    env.data.qpos[:] = positions[act4_start_idx]
    mujoco.mj_forward(env.model, env.data)
    mat_start = env.data.xmat[env.object_id].reshape(3, 3).copy()

    env.data.qpos[:] = positions[act4_end_idx]
    mujoco.mj_forward(env.model, env.data)
    mat_end = env.data.xmat[env.object_id].reshape(3, 3).copy()

    r_rel = mat_end @ mat_start.T
    tr = np.clip((np.trace(r_rel) - 1) / 2.0, -1.0, 1.0)
    act4_rotation_deg = float(np.degrees(np.arccos(tr)))

    # Derive first contact in Action 4 dynamically
    first_contact_sample_idx = None
    first_sampled_contact = None
    first_contact_penetration_m = 0.0
    for idx_offset, r in enumerate(act4_rows):
        if r['object_hand_contacts']:
            first_contact_sample_idx = act4_start_idx + idx_offset
            first_sampled_contact = r
            first_contact_penetration_m = max(-c['distance_m'] for c in r['object_hand_contacts'])
            break

    # Derive dynamically the sample with maximum penetration across trajectory
    max_penetration_sample_idx = None
    max_penetration_m = 0.0
    for idx, r in enumerate(rows):
        if r['object_hand_contacts']:
            p = max(-c['distance_m'] for c in r['object_hand_contacts'])
            if p > max_penetration_m:
                max_penetration_m = p
                max_penetration_sample_idx = idx

    # Derive dynamically the nearest sample to authoritative scorer peak time
    scorer_peak_time_s = float(evaluator_report['peak_object_contact']['time_s'])
    nearest_sample_idx = int(np.argmin(np.abs(times - scorer_peak_time_s)))
    nearest_sample_row = rows[nearest_sample_idx]
    nearest_sample_time_s = float(times[nearest_sample_idx])
    nearest_sample_penetration_m = (
        max(-c['distance_m'] for c in nearest_sample_row['object_hand_contacts'])
        if nearest_sample_row['object_hand_contacts']
        else 0.0
    )

    # Action 5 end (floor height)
    act5_end_idx = at(all_calls[5]['time_s'])
    final_act5 = rows[act5_end_idx]
    total_disp_to_floor = np.array(final_act5['object_xyz_m']) - initial_act4['object_xyz_m']

    # --- Per-sample Hand Geometry across Action 4 vs Nominal Bounds ---
    nominal_prompt_bounds = {
        'x': [-0.074, 0.058],
        'y': [-0.042, 0.042],
        'z': [-0.077, 0.085],
    }
    nominal_downward_quat = np.array([0.5, -0.5, 0.5, 0.5])
    hand_joints = [env.model.joint(name).id for name in HAND_NAMES]
    hand_q_adrs = [env.model.jnt_qposadr[j] for j in hand_joints]

    act4_bounds_per_sample = []
    for idx in range(act4_start_idx, act4_end_idx + 1):
        env.data.qpos[:] = positions[idx]
        env.data.time = times[idx]
        mujoco.mj_forward(env.model, env.data)
        b_list = hand_bounds(env, env.data)
        b_min = np.min([b['world_offset_min_m'] for b in b_list], axis=0).tolist()
        b_max = np.max([b['world_offset_max_m'] for b in b_list], axis=0).tolist()
        q_site = np.array(quaternion(env.data.site_xmat[env.site]))
        f_joints = env.data.qpos[hand_q_adrs].tolist()
        act4_bounds_per_sample.append({
            'sample_index': idx,
            'time_s': float(times[idx]),
            'hand_quaternion_wxyz': q_site.tolist(),
            'quaternion_diff_from_nominal': float(np.linalg.norm(q_site - nominal_downward_quat)),
            'finger_joints_rad': f_joints,
            'world_offset_min_m': b_min,
            'world_offset_max_m': b_max,
            'departure_min_m': [
                b_min[0] - nominal_prompt_bounds['x'][0],
                b_min[1] - nominal_prompt_bounds['y'][0],
                b_min[2] - nominal_prompt_bounds['z'][0],
            ],
            'departure_max_m': [
                b_max[0] - nominal_prompt_bounds['x'][1],
                b_max[1] - nominal_prompt_bounds['y'][1],
                b_max[2] - nominal_prompt_bounds['z'][1],
            ],
        })

    # Overall bounds and departure across Action 4
    overall_min_bounds = np.min([s['world_offset_min_m'] for s in act4_bounds_per_sample], axis=0).tolist()
    overall_max_bounds = np.max([s['world_offset_max_m'] for s in act4_bounds_per_sample], axis=0).tolist()
    overall_departure_min = [
        overall_min_bounds[0] - nominal_prompt_bounds['x'][0],
        overall_min_bounds[1] - nominal_prompt_bounds['y'][0],
        overall_min_bounds[2] - nominal_prompt_bounds['z'][0],
    ]
    overall_departure_max = [
        overall_max_bounds[0] - nominal_prompt_bounds['x'][1],
        overall_max_bounds[1] - nominal_prompt_bounds['y'][1],
        overall_max_bounds[2] - nominal_prompt_bounds['z'][1],
    ]

    # Independent robot calibration
    nominal = context()
    nominal_hand_joints = np.array([nominal.model.joint(name).id for name in HAND_NAMES])
    nominal.data.qpos[nominal.model.jnt_qposadr[nominal_hand_joints]] = Environment.hand_targets(nominal, 0)
    nominal.data.qpos[nominal.arm_q] = Environment.solve(nominal, [.24, -.18, .94])
    mujoco.mj_forward(nominal.model, nominal.data)
    nominal_bounds = hand_bounds(nominal, nominal.data)

    # --- Action 9 IK Rejection Reproduction ---
    # Final integration state is saved at t=7.70 s. Reproduce the rejected IK on scratch data.
    mujoco.mj_setState(env.model, env.data, final, mujoco.mjtState.mjSTATE_INTEGRATION)
    mujoco.mj_forward(env.model, env.data)
    before_integration = integration_state(env).copy()

    call_9_cmd = all_calls[8]['command']['arguments']
    rot_9 = rotation_from_quaternion(call_9_cmd['quaternion_wxyz'])
    reproduced_ik_error = None
    try:
        Environment.solve(env, call_9_cmd['xyz_m'], rot_9)
    except ValueError as exc:
        reproduced_ik_error = str(exc)

    if reproduced_ik_error != all_calls[8]['error']:
        raise ValueError('IK solver on scratch data did not reproduce the archived rejection error')

    # Derive reported IK residual and label four-decimal precision
    residual_match = re.search(r'residual\s+([\d.]+)\s*m', reproduced_ik_error)
    if not residual_match:
        raise ValueError(f'Could not parse residual from error message: {reproduced_ik_error}')
    reproduced_ik_residual_m = float(residual_match.group(1))

    after_integration = integration_state(env)
    if not np.array_equal(before_integration, after_integration):
        raise ValueError('Audit changed loaded integration state')

    # --- Load C1 Evidence Dynamically for Consistent Comparison ---
    c1_audit_path = ROOT / 'experiments/humanoid-pick-place/results/codex_C1_audit/audit.json'
    c1_zip_path = ROOT / 'experiments/humanoid-pick-place/results/codex_C1_episode.zip'
    with zipfile.ZipFile(c1_zip_path) as z_c1:
        c1_archived = json.loads(z_c1.read('sha256.json'))
    c1_audit = json.loads(c1_audit_path.read_text())
    c1_disp_vec = np.array(c1_audit['object_displacement_m'])
    c1_act2_xy_disp_m = float(c1_audit['object_xy_displacement_m'])
    c1_act2_3d_disp_m = float(np.linalg.norm(c1_disp_vec))

    # Verify source episode did not change during analysis
    current_source_hashes = {
        str(p.relative_to(episode)): digest(p)
        for p in sorted(episode.rglob('*'))
        if p.is_file()
    }
    if source_hashes != current_source_hashes:
        raise ValueError('Source episode changed during audit')

    # Prepare outputs
    output.mkdir(parents=True)

    # 1. Contact sheet for decisions 3-9
    calls_3_to_9 = all_calls[2:9]
    contact_sheet_file = output / 'contact_sheet.png'
    generate_contact_sheet(episode, calls_3_to_9, contact_sheet_file)

    # 2. Public proprioception & history artifact (explicitly validates robot_state)
    public_proprio_history = []
    for call in calls_3_to_9:
        req = call.get('request')
        if not isinstance(req, dict):
            raise ValueError(f"Call {call['call']} request is not a JSON object")
        obs = req.get('observation')
        if not isinstance(obs, dict):
            raise ValueError(f"Call {call['call']} request observation is not a JSON object")

        # Explicitly validate public robot_state
        if 'robot_state' not in obs or not isinstance(obs['robot_state'], dict):
            raise ValueError(f"Call {call['call']} missing public robot_state in request observation")
        rs = obs['robot_state']
        if 'robot' not in rs or not isinstance(rs['robot'], dict):
            raise ValueError(f"Call {call['call']} missing robot object in robot_state")
        robot = rs['robot']
        required_robot_fields = ('hand_xyz_m', 'hand_quaternion_wxyz', 'joint_names', 'joint_position_rad', 'joint_velocity_rad_s', 'contact_links')
        for rf in required_robot_fields:
            if rf not in robot or robot[rf] is None:
                raise ValueError(f"Call {call['call']} missing or null robot field: {rf}")
        if len(robot['joint_names']) != 43 or len(robot['joint_position_rad']) != 43:
            raise ValueError(f"Call {call['call']} invalid joint array length in robot_state")

        # Verify image identity matches archived request and saved PNG
        img_bytes = (episode / 'codex' / f"decision-{call['call']:03}" / 'observation.png').read_bytes()
        computed_img_hash = hashlib.sha256(img_bytes).hexdigest()
        if call['image_sha256'] != computed_img_hash:
            raise ValueError(f"Call {call['call']} image SHA-256 does not match observation.png")

        public_proprio_history.append({
            'call': call['call'],
            'input_preceding_decision': {
                'observation_time_s': call['time_s'],
                'observation_id': call.get('observation_id'),
                'image_sha256': call['image_sha256'],
                'public_robot_state': rs,
                'public_history': req.get('history'),
                'remaining_actions': req.get('remaining_actions'),
                'remaining_time_s': req.get('remaining_time_s'),
            },
            'subsequent_command_and_execution': {
                'command': call.get('command'),
                'execution_status': call.get('status'),
                'execution_start_time_s': call.get('interface_response', {}).get('start_time_s'),
                'execution_end_time_s': call.get('interface_response', {}).get('end_time_s'),
                'error': call.get('interface_response', {}).get('error'),
            },
        })
    (output / 'public_proprioception_history.json').write_text(
        json.dumps(public_proprio_history, indent=2, allow_nan=False) + '\n'
    )

    # 3. Private trajectory annotations artifact (evaluator ground truth)
    private_annotations = {
        'artifact': 'private_trajectory_annotations',
        'classification': 'evaluator_internal_ground_truth',
        'disclaimer': 'Private evaluator data; none of this was accessible to the policy controller.',
        'decisions_3_to_9_ground_truth': [
            {
                'call': call['call'],
                'observation_time_s': call['time_s'],
                'hand_xyz_m': rows[at(call['time_s'])]['hand_xyz_m'],
                'object_xyz_m': rows[at(call['time_s'])]['object_xyz_m'],
                'object_displacement_from_initial_m': (
                    np.array(rows[at(call['time_s'])]['object_xyz_m'])
                    - np.array(rows[0]['object_xyz_m'])
                ).tolist(),
                'distance_hand_to_object_m': float(
                    np.linalg.norm(
                        np.array(rows[at(call['time_s'])]['hand_xyz_m'])
                        - np.array(rows[at(call['time_s'])]['object_xyz_m'])
                    )
                ),
                'object_upright_axis_z_abs': rows[at(call['time_s'])][
                    'object_upright_axis_z_abs'
                ],
                'object_vertical_extent_m': rows[at(call['time_s'])][
                    'object_vertical_extent_m'
                ],
            }
            for call in calls_3_to_9
        ],
        'action_4_trajectory_samples': act4_rows,
        'action_4_summary': {
            'interval_label': 'Action 4 (approach move)',
            'time_interval_s': [initial_act4['time_s'], final_act4['time_s']],
            'object_initial_xyz_m': initial_act4['object_xyz_m'],
            'object_final_xyz_m': final_act4['object_xyz_m'],
            'object_displacement_vector_m': act4_disp.tolist(),
            'object_xy_displacement_m': act4_xy_disp,
            'object_3d_displacement_m': act4_total_disp,
            'object_rotation_deg': act4_rotation_deg,
            'object_upright_axis_z_final': final_act4['object_upright_axis_z_abs'],
            'first_sampled_hand_contact': {
                'sample_index': first_contact_sample_idx,
                'time_s': first_sampled_contact['time_s'] if first_sampled_contact else None,
                'penetration_m': first_contact_penetration_m,
                'contacts': first_sampled_contact['object_hand_contacts'] if first_sampled_contact else [],
            },
            'max_sampled_penetration': {
                'sample_index': max_penetration_sample_idx,
                'time_s': float(times[max_penetration_sample_idx]) if max_penetration_sample_idx is not None else None,
                'penetration_m': max_penetration_m,
                'contacts': rows[max_penetration_sample_idx]['object_hand_contacts'] if max_penetration_sample_idx is not None else [],
            },
        },
        'action_4_to_5_floor_summary': {
            'interval_label': 'Action 4 start (t=3.200 s) to Action 5 end (t=5.000 s)',
            'time_interval_s': [initial_act4['time_s'], final_act5['time_s']],
            'object_floor_xyz_m': final_act5['object_xyz_m'],
            'displacement_vector_m': total_disp_to_floor.tolist(),
            'xy_displacement_m': float(np.linalg.norm(total_disp_to_floor[:2])),
            '3d_displacement_m': float(np.linalg.norm(total_disp_to_floor)),
        },
        'authoritative_scorer_telemetry': evaluator_report['peak_object_contact'],
    }
    (output / 'private_trajectory_annotations.json').write_text(
        json.dumps(private_annotations, indent=2, allow_nan=False) + '\n'
    )

    # 4. Master reproducible audit JSON
    result = {
        'status': 'complete',
        'mode': 'private_posthoc_qpos_geometry_and_final_state_preflight',
        'physics_steps': 0,
        'model_invocations': 0,
        'source_episode': str(episode),
        'source_files_sha256': source_hashes,
        'archive_verification': {
            'pinned_archive_sha256': PINNED_C2_ARCHIVE_SHA256,
            'archive_sha256_verified': True,
            'member_count': len(archived),
            'members_verified': True,
        },
        'source_archive_sha256': archive_digest,
        'physical_source_sha256': {
            p: report['provenance']['source_sha256'][p]
            for p in report['provenance']['source_sha256']
        },
        'audit_source_sha256': digest(Path(__file__)),
        'mujoco_version': mujoco.__version__,
        'action_4_analysis': {
            'call_index': 4,
            'interval_s': [initial_act4['time_s'], final_act4['time_s']],
            'command': all_calls[3]['command']['arguments'],
            'approach_start': initial_act4,
            'approach_end': final_act4,
            'object_displacement_m': act4_disp.tolist(),
            'object_xy_displacement_m': act4_xy_disp,
            'object_3d_displacement_m': act4_total_disp,
            'object_rotation_deg': act4_rotation_deg,
            'object_upright_axis_z_final': final_act4['object_upright_axis_z_abs'],
            'requested_approach_minus_initial_object_xyz_m': (
                np.array(all_calls[3]['command']['arguments']['xyz_m'])
                - np.array(initial_act4['object_xyz_m'])
            ).tolist(),
            'first_sampled_hand_contact': {
                'sample_index': first_contact_sample_idx,
                'time_s': first_sampled_contact['time_s'] if first_sampled_contact else None,
                'penetration_m': first_contact_penetration_m,
                'contacts': first_sampled_contact['object_hand_contacts'] if first_sampled_contact else [],
            },
            'max_sampled_penetration': {
                'sample_index': max_penetration_sample_idx,
                'time_s': float(times[max_penetration_sample_idx]) if max_penetration_sample_idx is not None else None,
                'penetration_m': max_penetration_m,
                'contacts': rows[max_penetration_sample_idx]['object_hand_contacts'] if max_penetration_sample_idx is not None else [],
            },
        },
        'telemetry_vs_sampled_geometry': {
            'full_rate_scorer_telemetry': {
                'rate_hz': 1000,
                'peak_time_s': evaluator_report['peak_object_contact']['time_s'],
                'other_body': evaluator_report['peak_object_contact']['other_body'],
                'other_geom_id': evaluator_report['peak_object_contact']['other_geom_id'],
                'penetration_m': evaluator_report['peak_object_contact']['penetration_m'],
                'normal_force_at_peak_penetration_n': evaluator_report['peak_object_contact']['normal_force_n'],
                'note': (
                    'Recorded by private scorer during live physics integration at 1 kHz (dt=0.001 s). '
                    'Normal force 25.51 N was measured at peak penetration (t=3.795 s), not a separately '
                    'maximized force.'
                ),
            },
            'sampled_qpos_geometry': {
                'rate_hz': 30,
                'nearest_to_scorer_peak_sample_index': nearest_sample_idx,
                'nearest_sample_time_s': nearest_sample_time_s,
                'nearest_sample_penetration_m': nearest_sample_penetration_m,
                'first_sampled_contact_sample_index': first_contact_sample_idx,
                'first_sampled_contact_time_s': first_sampled_contact['time_s'] if first_sampled_contact else None,
                'first_sampled_contact_penetration_m': first_contact_penetration_m,
                'first_contact_sample_index': first_contact_sample_idx,
                'first_contact_time_s': first_sampled_contact['time_s'] if first_sampled_contact else None,
                'first_contact_penetration_m': first_contact_penetration_m,
                'max_contact_sample_index': max_penetration_sample_idx,
                'max_sampled_penetration_m': max_penetration_m,
                'note': (
                    'Qpos trajectory analysis is post-hoc geometric reconstruction only (dt ~ 0.033 s). '
                    '30 Hz snapshots cannot identify exact collision onset or continuous contact forces.'
                ),
            },
        },
        'finger_geometry_vs_nominal_bounds': {
            'prompt_bounds_world_offset_m': nominal_prompt_bounds,
            'per_sample_action_4_bounds': act4_bounds_per_sample,
            'action_4_envelope': {
                'overall_min_m': overall_min_bounds,
                'overall_max_m': overall_max_bounds,
                'min_departure_from_prompt_m': overall_departure_min,
                'max_departure_from_prompt_m': overall_departure_max,
            },
            'nominal_open_hand_calibration': {
                'source': 'robot model, closure=0 joint targets, downward IK at nominal site [.24,-.18,.94]; no episode state',
                'world_offset_min_m': np.min(
                    [v['world_offset_min_m'] for v in nominal_bounds], axis=0
                ).tolist(),
                'world_offset_max_m': np.max(
                    [v['world_offset_max_m'] for v in nominal_bounds], axis=0
                ).tolist(),
                'per_geom': nominal_bounds,
            },
            'geometric_applicability_finding': (
                'The prompt supplied approximate posture-specific bounds. Measured pre-approach lower Z bounds '
                'extended to -0.0778 m, slightly beyond the prompt lower bound of -0.077 m, and finger articulation '
                'under dynamic contact further altered geometry. Furthermore, bounding boxes enclose solid geometry '
                'rather than certifying a safe swept volume or free cavity. Along the actual recorded trajectory, '
                'first sampled contact occurred at sample 117 (t=3.761 s) between right_hand_middle_0_link and the object '
                '(30 Hz snapshots cannot identify exact collision onset), reaching 5.185 mm penetration at sample 118. '
                'The empirical contact pairs and path, not box overlap alone, establish physical collision.'
            ),
        },
        'action_9_rejection': {
            'call_index': 9,
            'time_s': all_calls[8]['time_s'],
            'command': call_9_cmd,
            'production_error': all_calls[8]['error'],
            'reproduced_error': reproduced_ik_error,
            'ik_residual_m': reproduced_ik_residual_m,
            'ik_residual_precision': 'four_decimals',
            'final_integration_state_unchanged': bool(
                np.array_equal(before_integration, after_integration)
            ),
            'note': (
                'Rejected before execution by interface IK reachability check on scratch data. '
                'Zero physics advance or state mutation occurred.'
            ),
        },
        'descriptive_c1_c2_comparison': {
            'evidence_sources': {
                'c1_archive_sha256': digest(c1_zip_path),
                'c1_audit_sha256': digest(c1_audit_path),
                'c2_archive_sha256': archive_digest,
            },
            'c1': {
                'protocol_id': 'humanoid-codex-c1-development',
                'first_damaging_action': 'Action 2 (move to [0.250, -0.184, 0.820])',
                'first_damaging_action_interval_s': [1.0, 2.5],
                'first_damaging_action_xy_displacement_mm': c1_act2_xy_disp_m * 1000.0,
                'first_damaging_action_3d_displacement_mm': c1_act2_3d_disp_m * 1000.0,
                'subsequent_displacement_to_floor_mm': None,
                'object_toppled': True,
                'sustained_lift': False,
                'placement_success': False,
                'peak_object_penetration_mm': float(c1_audit['authoritative_private_score']['max_object_penetration_m']) * 1000.0,
                'scorer_normal_force_at_peak_n': float(c1_audit['authoritative_private_score']['peak_object_contact']['normal_force_n']),
                'stop_reason': 'Action 3 rejected by preflight collision guard (fingertips vs table > 2 mm)',
                'simulated_time_s': 2.50,
                'completed_actions': 2,
            },
            'c2': {
                'protocol_id': 'humanoid-codex-c2-development',
                'first_damaging_action': 'Action 4 (move to [0.251, -0.173, 0.800])',
                'first_damaging_action_interval_s': [initial_act4['time_s'], final_act4['time_s']],
                'first_damaging_action_xy_displacement_mm': act4_xy_disp * 1000.0,
                'first_damaging_action_3d_displacement_mm': act4_total_disp * 1000.0,
                'action_4_start_to_action_5_end_interval_s': [initial_act4['time_s'], final_act5['time_s']],
                'action_4_start_to_action_5_end_xy_displacement_mm': float(np.linalg.norm(total_disp_to_floor[:2])) * 1000.0,
                'action_4_start_to_action_5_end_3d_displacement_mm': float(np.linalg.norm(total_disp_to_floor)) * 1000.0,
                'object_toppled': True,
                'sustained_lift': False,
                'placement_success': False,
                'peak_object_penetration_mm': float(evaluator_report['peak_object_contact']['penetration_m']) * 1000.0,
                'scorer_normal_force_at_peak_n': float(evaluator_report['peak_object_contact']['normal_force_n']),
                'stop_reason': 'Action 9 rejected by interface IK reachability check (residual 0.0542 m)',
                'simulated_time_s': 7.70,
                'completed_actions': 8,
            },
            'efficacy_disclaimer': (
                'C1 and C2 share a single development seed (820). Differences in action count or sequence are '
                'descriptive observations, not proof of controller efficacy or systematic task progress. '
                'Subsequent commands returning to the prior region are observed in command JSON; they do not '
                'establish open-loop intent or recovery strategy.'
            ),
        },
        'authoritative_private_score': evaluator_report,
        'artifacts_generated': {
            'audit_json': 'audit.json',
            'contact_sheet_png': 'contact_sheet.png',
            'public_proprioception_history_json': 'public_proprioception_history.json',
            'private_trajectory_annotations_json': 'private_trajectory_annotations.json',
        },
        'limitations': [
            'Saved trajectory is qpos at approximately 30 Hz, not full dynamic state at every millisecond.',
            'Recomputed geometric contacts from qpos cannot reconstruct contact forces or continuous dynamics; '
            'scorer normal force (25.51 N at peak penetration) and peak timing (t=3.795 s) are from authoritative '
            '1 kHz scorer telemetry.',
            'Requested action coordinates reflect model output, not the model\'s internal belief or visual estimate.',
            'Collision bounds describe occupied solid geometry, not an open grasp cavity or certified collision-free path.',
            'Descriptive comparisons between C1 and C2 on a single development seed do not support performance or qualification claims.',
        ],
    }

    (output / 'audit.json').write_text(
        json.dumps(result, indent=2, allow_nan=False) + '\n'
    )
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    res = audit(args.episode, args.output)
    print(
        json.dumps(
            {
                'status': res['status'],
                'action_4_xy_disp_mm': res['action_4_analysis']['object_xy_displacement_m'] * 1000,
                'action_9_reproduced_error': res['action_9_rejection']['reproduced_error'],
                'state_unchanged': res['action_9_rejection']['final_integration_state_unchanged'],
            },
            indent=2,
        )
    )
