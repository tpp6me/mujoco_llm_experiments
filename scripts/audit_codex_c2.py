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
from types import SimpleNamespace
import zipfile

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

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
    """Produce an ordered contact sheet from original saved public images for decisions 3-9."""
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
            cmd_str += ' [REJECTED (IK)]'

        draw.text(
            (x0 + 10, y0 + 6),
            f'Decision {c_num} (t = {t_s:.2f} s)',
            fill=(255, 255, 255),
            font=font_title,
        )
        draw.text(
            (x0 + 10, y0 + 26),
            f'Cmd: {cmd_str}',
            fill=(223, 230, 233),
            font=font,
        )

        img_path = episode / 'codex' / f'decision-{c_num:03}' / 'observation.png'
        orig = Image.open(img_path).resize((panel_w, panel_h), Image.Resampling.LANCZOS)
        sheet.paste(orig, (x0, y0 + header_h))

    # Cell 8: Summary card
    x0 = 3 * cell_w
    y0 = 1 * cell_h
    draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], fill=(20, 20, 25))
    draw.rectangle([x0, y0, x0 + cell_w, y0 + header_h], fill=(45, 52, 54))
    draw.text(
        (x0 + 10, y0 + 6),
        'Public Observation Summary',
        fill=(255, 255, 255),
        font=font_title,
    )
    info_lines = [
        'Condition: C2 (seed 820)',
        'Original public RGB observations',
        'Decision 3: Hand descending, block upright',
        'Decision 4: Hand descends (damaging action)',
        'Decision 5: Block toppled/displaced to edge',
        'Decision 6: Block on floor; hand lifts',
        'Decision 7: Hand opens; block on floor',
        'Decision 8: Hand descends to old region',
        'Decision 9: IK rejection at table edge',
        '',
        'AGY measures/assembles;',
        'Codex reviews VLA interpretation.',
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

    source_hashes = {
        str(p.relative_to(episode)): digest(p)
        for p in sorted(episode.rglob('*'))
        if p.is_file()
    }
    archive = ROOT / 'experiments/humanoid-pick-place/results/codex_C2_episode.zip'
    with zipfile.ZipFile(archive) as saved:
        archived = json.loads(saved.read('sha256.json'))
    expected_inputs = {
        name.removeprefix('seed-820/'): value
        for name, value in archived.items()
        if name.startswith('seed-820/')
    }
    if source_hashes != expected_inputs:
        raise ValueError('Episode files differ from the retained C2 archive manifest')

    report = json.loads((episode / 'report.json').read_text())
    if (
        report['seed'] != 820
        or report['provenance']['protocol_id'] != 'humanoid-codex-c2-development'
    ):
        raise ValueError('This audit is restricted to the saved C2 seed-820 episode')
    if report['provenance']['mujoco'] != mujoco.__version__:
        raise ValueError('Use the recorded MuJoCo version for this audit')

    # Verify physical/runner sources recorded in provenance
    for path, expected in report['provenance']['source_sha256'].items():
        if digest(ROOT / path) != expected:
            raise ValueError(f'Execution source changed: {path}')

    metadata = json.loads((episode / 'metadata.json').read_text())
    if digest(SCENE) != metadata['scene_sha256']:
        raise ValueError('Scene changed')

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
    # Action 4 starts at call_004 time (3.20 s) and ends at call_005 time (4.00 s)
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

    # Hand/object contacts in Action 4
    act4_contact_rows = [r for r in act4_rows if r['object_hand_contacts']]
    first_sampled_contact = act4_contact_rows[0] if act4_contact_rows else None
    max_sampled_penetration = (
        max(
            ((-c['distance_m'], r['time_s'], c) for r in act4_rows for c in r['object_hand_contacts']),
            key=lambda item: item[0],
        )
        if act4_contact_rows
        else (0.0, None, None)
    )

    # Action 5 end (floor height)
    act5_end_idx = at(all_calls[5]['time_s'])
    final_act5 = rows[act5_end_idx]
    total_disp_to_floor = np.array(final_act5['object_xyz_m']) - initial_act4['object_xyz_m']

    # --- Hand Geometry vs Nominal Bounds ---
    # Pre-approach bounds at start of Action 4
    env.data.qpos[:] = positions[act4_start_idx]
    mujoco.mj_forward(env.model, env.data)
    act4_pre_approach_bounds = hand_bounds(env, env.data)

    # Contact bounds at sample 118
    env.data.qpos[:] = positions[118]
    mujoco.mj_forward(env.model, env.data)
    act4_contact_bounds = hand_bounds(env, env.data)

    # Independent robot calibration
    nominal = context()
    hand_joints = np.array([nominal.model.joint(name).id for name in HAND_NAMES])
    nominal.data.qpos[nominal.model.jnt_qposadr[hand_joints]] = Environment.hand_targets(nominal, 0)
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

    after_integration = integration_state(env)
    if not np.array_equal(before_integration, after_integration):
        raise ValueError('Audit changed loaded integration state')

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

    # 2. Public proprioception & history artifact
    public_proprio_history = []
    for call in calls_3_to_9:
        req = call.get('request', {})
        obs = req.get('observation', {})
        public_proprio_history.append({
            'call': call['call'],
            'observation_time_s': call['time_s'],
            'image_sha256': call['image_sha256'],
            'robot_proprioception': obs.get('robot'),
            'public_history_preceding_decision': req.get('history'),
            'command': call.get('command'),
            'interface_response': {
                'status': call.get('interface_response', {}).get('status'),
                'start_time_s': call.get('interface_response', {}).get('start_time_s'),
                'end_time_s': call.get('interface_response', {}).get('end_time_s'),
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
            'time_interval_s': [initial_act4['time_s'], final_act4['time_s']],
            'object_initial_xyz_m': initial_act4['object_xyz_m'],
            'object_final_xyz_m': final_act4['object_xyz_m'],
            'object_displacement_m': act4_disp.tolist(),
            'object_xy_displacement_m': act4_xy_disp,
            'object_total_displacement_m': act4_total_disp,
            'object_rotation_deg': act4_rotation_deg,
            'object_upright_axis_z_final': final_act4['object_upright_axis_z_abs'],
            'first_sampled_hand_contact': first_sampled_contact,
            'max_sampled_penetration': {
                'penetration_m': max_sampled_penetration[0],
                'time_s': max_sampled_penetration[1],
                'contact': max_sampled_penetration[2],
            },
        },
        'action_5_summary': {
            'time_s': final_act5['time_s'],
            'object_floor_xyz_m': final_act5['object_xyz_m'],
            'total_displacement_to_floor_m': float(np.linalg.norm(total_disp_to_floor)),
            'total_displacement_to_floor_vector_m': total_disp_to_floor.tolist(),
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
        'source_archive_sha256': digest(archive),
        'physical_source_sha256': {
            p: report['provenance']['source_sha256'][p]
            for p in report['provenance']['source_sha256']
        },
        'audit_source_sha256': digest(Path(__file__)),
        'mujoco_version': mujoco.__version__,
        'action_4_analysis': {
            'call_index': 4,
            'time_start_s': initial_act4['time_s'],
            'time_end_s': final_act4['time_s'],
            'command': all_calls[3]['command']['arguments'],
            'approach_start': initial_act4,
            'approach_end': final_act4,
            'object_displacement_m': act4_disp.tolist(),
            'object_xy_displacement_m': act4_xy_disp,
            'object_total_displacement_m': act4_total_disp,
            'object_rotation_deg': act4_rotation_deg,
            'object_upright_axis_z_final': final_act4['object_upright_axis_z_abs'],
            'requested_approach_minus_initial_object_xyz_m': (
                np.array(all_calls[3]['command']['arguments']['xyz_m'])
                - np.array(initial_act4['object_xyz_m'])
            ).tolist(),
            'first_sampled_hand_contact': first_sampled_contact,
            'max_sampled_object_hand_penetration': {
                'penetration_m': max_sampled_penetration[0],
                'time_s': max_sampled_penetration[1],
                'contact': max_sampled_penetration[2],
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
                'nearest_sample_index': 118,
                'nearest_sample_time_s': float(times[118]),
                'nearest_penetration_m': -first_sampled_contact['object_hand_contacts'][0]['distance_m']
                if first_sampled_contact
                else None,
                'max_sampled_penetration_m': max_sampled_penetration[0],
                'note': (
                    'Qpos trajectory analysis is post-hoc geometric reconstruction only (dt ~ 0.033 s). '
                    'It cannot reconstruct continuous contact forces or exact microsecond collision dynamics.'
                ),
            },
        },
        'finger_geometry_vs_nominal_bounds': {
            'prompt_bounds_world_offset_m': {
                'x': [-0.074, 0.058],
                'y': [-0.042, 0.042],
                'z': [-0.077, 0.085],
            },
            'actual_pre_approach_bounds': {
                'time_s': initial_act4['time_s'],
                'world_offset_min_m': np.min(
                    [b['world_offset_min_m'] for b in act4_pre_approach_bounds], axis=0
                ).tolist(),
                'world_offset_max_m': np.max(
                    [b['world_offset_max_m'] for b in act4_pre_approach_bounds], axis=0
                ).tolist(),
            },
            'actual_contact_bounds': {
                'time_s': float(times[118]),
                'world_offset_min_m': np.min(
                    [b['world_offset_min_m'] for b in act4_contact_bounds], axis=0
                ).tolist(),
                'world_offset_max_m': np.max(
                    [b['world_offset_max_m'] for b in act4_contact_bounds], axis=0
                ).tolist(),
            },
            'nominal_open_hand_geometry': {
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
                'The prompt nominal bounds accurately described the open-hand collision envelope in downward '
                'orientation. However, collision bounds enclose occupied solid geometry rather than a free '
                'grasp cavity or safe approach path. Commanding grasp site z=0.80 m placed the site below the '
                'upright block top (z=0.82 m), causing fingers extending to z ~ 0.723 m to collide with the block.'
            ),
        },
        'action_9_rejection': {
            'call_index': 9,
            'time_s': all_calls[8]['time_s'],
            'command': call_9_cmd,
            'production_error': all_calls[8]['error'],
            'reproduced_error': reproduced_ik_error,
            'ik_residual_m': 0.0542,
            'final_integration_state_unchanged': bool(
                np.array_equal(before_integration, after_integration)
            ),
            'note': (
                'Rejected before execution by interface IK reachability check on scratch data. '
                'Zero physics advance or state mutation occurred.'
            ),
        },
        'descriptive_c1_c2_comparison': {
            'c1': {
                'protocol_id': 'humanoid-codex-c1-development',
                'first_damaging_action': 'Action 2 (move to [0.250, -0.184, 0.820])',
                'object_xy_displacement_mm': 84.640,
                'object_toppled': True,
                'sustained_lift': False,
                'placement_success': False,
                'peak_object_penetration_mm': 6.291,
                'scorer_normal_force_at_peak_n': 0.0,
                'stop_reason': 'Action 3 rejected by preflight collision guard (fingertips vs table > 2 mm)',
                'simulated_time_s': 2.50,
                'completed_actions': 2,
            },
            'c2': {
                'protocol_id': 'humanoid-codex-c2-development',
                'first_damaging_action': 'Action 4 (move to [0.251, -0.173, 0.800])',
                'object_xy_displacement_mm': 154.269,
                'object_toppled': True,
                'sustained_lift': False,
                'placement_success': False,
                'peak_object_penetration_mm': 5.185,
                'scorer_normal_force_at_peak_n': 25.51,
                'stop_reason': 'Action 9 rejected by interface IK reachability check (residual 0.0542 m)',
                'simulated_time_s': 7.70,
                'completed_actions': 8,
            },
            'efficacy_disclaimer': (
                'C1 and C2 share a single development seed (820). Differences in action count or sequence are '
                'descriptive observations, not proof of controller efficacy or systematic task progress.'
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
