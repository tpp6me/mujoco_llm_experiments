"""Development evaluation comparing baseline P4, 2-frame, and 3-frame reacquisition candidates.

Evaluates offline on development captures (seeds 820-829).
All ground-truth poses and private drift measurements are computed post-hoc
after the estimator returns and are never provided to any tracker.

Maintains explicit grid accounting: expected, observed, evaluated, and missing counts.
Nominal post-warmup denominator is fixed at 2 per requested seed (transport and lower).
"""
import argparse
import base64
import copy
import io
import json
import shutil
from collections import Counter
from pathlib import Path
import time

import numpy as np
from PIL import Image

from .perception_evaluation import write_json
from .temporal_pose import (
    TemporalPose, TemporalReacquisitionPose, TemporalThreeFrameReacquisitionPose,
    quaternion_matrix
)

EXPECTED_STAGES = ['lift', 'lift_hold', 'transport', 'lower', 'release', 'retract']
AUGMENTED_STAGES = ['lift', 'lift_hold', 'transport', 'lower_mid', 'lower', 'release', 'retract']
NOMINAL_POST_WARMUP_STAGES = {'transport', 'lower'}
EXPECTED_VARIANTS = ['original', 'black_transport', 'frozen_transport_rgb']


def is_valid_truth_xyz(xyz):
    """Validate ground truth coordinates on the evaluator side only."""
    if xyz is None or not isinstance(xyz, (list, tuple, np.ndarray)):
        return False
    if len(xyz) != 3:
        return False
    try:
        arr = np.asarray(xyz, dtype=float)
        return arr.shape == (3,) and np.isfinite(arr).all()
    except (ValueError, TypeError):
        return False


def evaluate_stream(tracker_factory, seed, stage_observations, variant, stages=None):
    if stages is None:
        stages = EXPECTED_STAGES
    tracker = tracker_factory()
    records = []
    offsets = {}

    for stage in stages:
        stage_data = stage_observations.get(stage) if isinstance(stage_observations, dict) else None
        if stage_data is None:
            if hasattr(tracker, 'invalidate'):
                tracker.invalidate()
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'missing_stage',
                'error_message': f'Stage {stage} not present in capture data',
                'estimate': None,
                'scoring_status': 'missing_truth',
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': None,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        if not isinstance(stage_data, (tuple, list)) or len(stage_data) != 2:
            if hasattr(tracker, 'invalidate'):
                tracker.invalidate()
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'malformed_record_structure',
                'error_message': 'Stage entry must be a (frame_info, observation) tuple',
                'estimate': None,
                'scoring_status': 'missing_truth',
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': None,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        frame_info, original = stage_data
        if not isinstance(frame_info, dict):
            if hasattr(tracker, 'invalidate'):
                tracker.invalidate()
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'malformed_record_structure',
                'error_message': 'Frame info must be a dict',
                'estimate': None,
                'scoring_status': 'missing_truth',
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': None,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        private_true_xyz = frame_info.get('private_true_xyz_m')

        if original is None:
            if hasattr(tracker, 'invalidate'):
                tracker.invalidate()
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'missing_observation_file',
                'error_message': f'Observation file for stage {stage} is missing or could not be loaded',
                'estimate': None,
                'scoring_status': 'missing_truth' if not is_valid_truth_xyz(private_true_xyz) else 'valid_truth_unobserved',
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': private_true_xyz,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        if not isinstance(original, dict):
            if hasattr(tracker, 'invalidate'):
                tracker.invalidate()
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'malformed_observation_structure',
                'error_message': 'Observation JSON must be a dict',
                'estimate': None,
                'scoring_status': 'missing_truth' if not is_valid_truth_xyz(private_true_xyz) else 'valid_truth_unobserved',
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': private_true_xyz,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        # Prepare stimulus
        try:
            observation = copy.deepcopy(original)
            if stage == 'transport':
                if variant == 'black_transport':
                    camera = observation.get('camera')
                    if not isinstance(camera, dict) or 'width' not in camera or 'height' not in camera:
                        raise ValueError("Missing 'camera' with 'width' and 'height' for black transport")
                    try:
                        width, height = int(camera['width']), int(camera['height'])
                    except (ValueError, TypeError):
                        raise ValueError("Invalid camera dimensions type")
                    if width <= 0 or height <= 0:
                        raise ValueError(f"Invalid non-positive camera dimensions: {width}x{height}")
                    buffer = io.BytesIO()
                    Image.new('RGB', (width, height)).save(buffer, format='PNG')
                    observation['rgb_png_base64'] = base64.b64encode(buffer.getvalue()).decode()
                elif variant == 'frozen_transport_rgb':
                    # Require declared lift-hold source image
                    lift_hold_entry = stage_observations.get('lift_hold') if isinstance(stage_observations, dict) else None
                    if (not isinstance(lift_hold_entry, (tuple, list)) or
                        len(lift_hold_entry) != 2 or
                        not isinstance(lift_hold_entry[1], dict)):
                        raise ValueError("Lift-hold source observation unavailable for frozen transport stimulus")
                    lift_hold_obs = lift_hold_entry[1]
                    lift_hold_img = lift_hold_obs.get('rgb_png_base64')
                    if not isinstance(lift_hold_img, str) or not lift_hold_img:
                        raise ValueError("Lift-hold source image missing or empty for frozen transport stimulus")
                    observation['rgb_png_base64'] = lift_hold_img
        except Exception as prep_err:
            if hasattr(tracker, 'invalidate'):
                tracker.invalidate()
            status = 'stimulus_unavailable' if variant == 'frozen_transport_rgb' else 'preparation_error'
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': status,
                'error_message': str(prep_err),
                'estimate': None,
                'scoring_status': 'missing_truth' if not is_valid_truth_xyz(private_true_xyz) else 'unscored_preparation_error',
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': private_true_xyz,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        # Execute observation on tracker
        try:
            start = time.perf_counter()
            estimate = tracker.observe(observation)
            elapsed = time.perf_counter() - start
        except Exception as err:
            if hasattr(tracker, 'invalidate'):
                tracker.invalidate()
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'estimator_error',
                'error_message': str(err),
                'estimate': None,
                'scoring_status': 'missing_truth' if not is_valid_truth_xyz(private_true_xyz) else 'unscored_estimator_error',
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': private_true_xyz,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        if not isinstance(estimate, dict):
            if hasattr(tracker, 'invalidate'):
                tracker.invalidate()
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'estimator_error',
                'error_message': 'Estimator returned non-dict output',
                'estimate': None,
                'scoring_status': 'missing_truth' if not is_valid_truth_xyz(private_true_xyz) else 'unscored_estimator_error',
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': elapsed,
                'private_true_xyz_m': private_true_xyz,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        # Post-hoc evaluation using private ground truth (never seen by tracker)
        offset_list = None
        drift = 0.0
        try:
            if is_valid_truth_xyz(private_true_xyz) and 'robot_state' in original:
                robot = original['robot_state'].get('robot', {})
                quat = robot.get('hand_quaternion_wxyz')
                hand_xyz = robot.get('hand_xyz_m')
                if quat is not None and hand_xyz is not None:
                    hand_xyz_arr = np.asarray(hand_xyz, dtype=float)
                    truth_xyz_arr = np.asarray(private_true_xyz, dtype=float)
                    if hand_xyz_arr.shape == (3,) and np.isfinite(hand_xyz_arr).all():
                        R = quaternion_matrix(quat)
                        offset = R.T @ (truth_xyz_arr - hand_xyz_arr)
                        timestamp = float(original.get('time_s', 0.0))
                        offsets[timestamp] = offset
                        window = [offsets[t] for t in estimate.get('window_times_s', []) if t in offsets]
                        drift = max((float(np.linalg.norm(v - window[0])) for v in window), default=0.0)
                        offset_list = offset.tolist()
        except Exception:
            offset_list = None
            drift = 0.0

        # Scoring of emitted pose vs ground truth
        error = None
        within_20mm = False
        if estimate.get('detected'):
            if is_valid_truth_xyz(private_true_xyz):
                try:
                    center_arr = np.asarray(estimate['object_center_xyz_m'], dtype=float)
                    truth_arr = np.asarray(private_true_xyz, dtype=float)
                    error = float(np.linalg.norm(center_arr - truth_arr))
                    within_20mm = (error <= 0.02)
                    scoring_status = 'scored'
                except Exception:
                    error = None
                    within_20mm = False
                    scoring_status = 'scoring_error'
            else:
                if private_true_xyz is None or 'private_true_xyz_m' not in frame_info:
                    scoring_status = 'unscored_missing_truth'
                else:
                    scoring_status = 'unscored_invalid_truth'
        else:
            if not is_valid_truth_xyz(private_true_xyz):
                scoring_status = 'missing_or_invalid_truth'
            else:
                scoring_status = 'not_detected'

        records.append({
            'seed': seed,
            'stage': stage,
            'variant': variant,
            'status': 'evaluated',
            'estimate': estimate,
            'scoring_status': scoring_status,
            'error_3d_m': error,
            'within_20mm': within_20mm,
            'elapsed_s': elapsed,
            'private_true_xyz_m': private_true_xyz,
            'private_object_to_hand_offset_m': offset_list,
            'private_window_center_drift_m': drift,
        })
    return records


def compute_aggregate(records, seeds, stages=None, post_warmup_stages=None):
    if stages is None:
        stages = EXPECTED_STAGES
    if post_warmup_stages is None:
        post_warmup_stages = NOMINAL_POST_WARMUP_STAGES
    aggregate = {}
    num_seeds = len(seeds)
    expected_per_stream = num_seeds * len(stages)
    expected_post_warmup = num_seeds * len(post_warmup_stages)

    for variant in EXPECTED_VARIANTS:
        v_records = [r for r in records if r['variant'] == variant]
        evaluated = [r for r in v_records if r['status'] == 'evaluated']
        missing = [r for r in v_records if r['status'] != 'evaluated']

        # Accepted poses: count of emitted poses where estimate['detected'] is True
        accepted_records = [r for r in evaluated if r.get('estimate') and r['estimate'].get('detected')]
        accepted = len(accepted_records)

        # Scored responses: where 3D error was successfully computed
        scored_records = [r for r in evaluated if r.get('error_3d_m') is not None]
        errors = [r['error_3d_m'] for r in scored_records]

        # Emitted poses that could not be scored due to missing/invalid ground truth
        unscored_accepted = [r for r in accepted_records if r.get('error_3d_m') is None]

        # Missing or invalid truth count across evaluated responses
        missing_or_invalid_truth = sum(
            1 for r in evaluated
            if r.get('scoring_status') in ('unscored_missing_truth', 'unscored_invalid_truth',
                                          'missing_or_invalid_truth', 'scoring_error')
            or not is_valid_truth_xyz(r.get('private_true_xyz_m'))
        )

        post_warmup_records = [r for r in evaluated if r['stage'] in post_warmup_stages]
        post_warmup_accepted = sum(1 for r in post_warmup_records
                                   if r.get('estimate') and r['estimate'].get('detected'))
        post_warmup_scored = [r for r in post_warmup_records if r.get('error_3d_m') is not None]
        post_warmup_errors = [r['error_3d_m'] for r in post_warmup_scored]

        aggregate[variant] = {
            'expected_responses': expected_per_stream,
            'evaluated_responses': len(evaluated),
            'missing_responses': len(missing),
            'missing_or_error_details': [
                {
                    'seed': r['seed'],
                    'stage': r['stage'],
                    'status': r['status'],
                    'error_message': r.get('error_message'),
                }
                for r in missing
            ],
            'accepted': accepted,
            'scored_responses': len(scored_records),
            'unscored_accepted': len(unscored_accepted),
            'missing_or_invalid_truth': missing_or_invalid_truth,
            'within_20mm': sum(r.get('within_20mm', False) for r in evaluated),
            'accepted_over_20mm': sum(e > 0.02 for e in errors),
            'accepted_mean_error_m': float(np.mean(errors)) if errors else None,
            'accepted_max_error_m': max(errors) if errors else None,
            'post_warmup_targets': expected_post_warmup,
            'post_warmup_accepted': post_warmup_accepted,
            'post_warmup_scored': len(post_warmup_scored),
            'post_warmup_within_20mm': sum(r.get('within_20mm', False) for r in post_warmup_records),
            'post_warmup_missing_or_refused': expected_post_warmup - post_warmup_accepted,
            'release_or_retract_accepted': sum(
                1 for r in evaluated
                if r['stage'] in ('release', 'retract')
                and r.get('estimate') and r['estimate'].get('detected')
            ),
            'refusals': dict(Counter(
                r['estimate']['reason'] for r in evaluated
                if r.get('estimate') and not r['estimate'].get('detected')
            )),
        }
    return aggregate


def evaluate_dataset(capture_dir, seeds, output_file=None, stages=None,
                     post_warmup_stages=None, dataset_label='temporal-P4-capture'):
    if stages is None:
        stages = EXPECTED_STAGES
    if post_warmup_stages is None:
        post_warmup_stages = NOMINAL_POST_WARMUP_STAGES
    seeds = list(seeds)
    if not seeds or any(not isinstance(s, int) or s < 0 for s in seeds):
        raise ValueError('Seeds must be a non-empty list of non-negative integers')

    capture_dir = Path(capture_dir)
    results = {
        'status': 'complete',
        'development_only': True,
        'dataset': dataset_label,
        'seeds': seeds,
        'expected_episodes': len(seeds),
        'expected_stages_per_episode': stages,
        'nominal_post_warmup_stages': sorted(list(post_warmup_stages)),
        'candidates': {},
    }

    # Load captured observations for each seed
    seed_data = {}
    for seed in seeds:
        folder = capture_dir / f"seed-{seed}"
        if not folder.is_dir():
            seed_data[seed] = {s: None for s in stages}
            continue

        records_file = folder / "private_records.json"
        if not records_file.is_file():
            seed_data[seed] = {s: None for s in stages}
            continue

        try:
            private_records = json.loads(records_file.read_text())
        except Exception:
            seed_data[seed] = {s: None for s in stages}
            continue

        if not isinstance(private_records, list):
            seed_data[seed] = {s: None for s in stages}
            continue

        stage_obs = {}
        for stage in stages:
            rec = next((r for r in private_records if isinstance(r, dict) and r.get('stage') == stage), None)
            if rec is None:
                stage_obs[stage] = None
                continue
            obs_file = None
            if isinstance(rec, dict) and 'image' in rec and isinstance(rec['image'], str):
                prefix = rec['image'].split('-')[0]
                cand_file = folder / f"{prefix}-observation.json"
                if cand_file.is_file():
                    obs_file = cand_file
            if obs_file is None and stage == 'lower_mid':
                cand_mid = folder / "06b-observation.json"
                if cand_mid.is_file():
                    obs_file = cand_mid
            if obs_file is None:
                idx = private_records.index(rec)
                cand_idx = folder / f"{idx:02d}-observation.json"
                if cand_idx.is_file():
                    obs_file = cand_idx
            if obs_file is None or not obs_file.is_file():
                stage_obs[stage] = (rec, None)
                continue
            try:
                obs = json.loads(obs_file.read_text())
                if not isinstance(obs, dict):
                    obs = None
                stage_obs[stage] = (rec, obs)
            except Exception:
                stage_obs[stage] = (rec, None)
        seed_data[seed] = stage_obs

    configurations = [
        ('baseline_p4', lambda: TemporalPose(reacquisition=False)),
        ('reacquisition_2frame', lambda: TemporalReacquisitionPose(min_reacquisition_frames=2)),
        ('reacquisition_3frame', lambda: TemporalThreeFrameReacquisitionPose()),
        ('reacquisition_candidate', lambda: TemporalReacquisitionPose(min_reacquisition_frames=2)),
    ]

    has_incomplete = False
    for candidate_name, factory in configurations:
        candidate_records = []
        for seed in seeds:
            for variant in EXPECTED_VARIANTS:
                stream_records = evaluate_stream(factory, seed, seed_data[seed], variant, stages=stages)
                candidate_records.extend(stream_records)

        aggregate = compute_aggregate(candidate_records, seeds, stages=stages, post_warmup_stages=post_warmup_stages)
        if any(agg['missing_responses'] > 0 or agg.get('missing_or_invalid_truth', 0) > 0 for agg in aggregate.values()):
            has_incomplete = True

        results['candidates'][candidate_name] = {
            'aggregate': aggregate,
            'records': candidate_records,
        }

    if has_incomplete:
        results['status'] = 'incomplete'

    if output_file is not None:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        write_json(output_file, results)

    return results


def render_augmented_dataset(source_capture_dir, output_capture_dir, seeds):
    """Render deterministic lowering midpoint observations from saved P4 trajectories.

    Lowering midpoint schedule: t_mid = (t_transport + t_lower) / 2 = 12.0s.
    Renders exact physical states from episode/episode.npz without modifying the read-only
    source capture directory.
    """
    import mujoco
    from .environment import Environment
    from .visual import RGBRenderer, VisualSession

    source_capture_dir = Path(source_capture_dir)
    output_capture_dir = Path(output_capture_dir)
    output_capture_dir.mkdir(parents=True, exist_ok=True)

    env = Environment()
    renderer = RGBRenderer(env)
    session = VisualSession(env, renderer)

    try:
        for seed in seeds:
            src_seed = source_capture_dir / f"seed-{seed}"
            out_seed = output_capture_dir / f"seed-{seed}"
            out_seed.mkdir(parents=True, exist_ok=True)

            # Copy all files from src_seed into out_seed if not already present
            for item in src_seed.iterdir():
                dest = out_seed / item.name
                if not dest.exists():
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)

            # Read private_records.json
            records_file = out_seed / "private_records.json"
            records = json.loads(records_file.read_text())

            # Check if lower_mid already exists in records
            if any(r.get('stage') == 'lower_mid' for r in records):
                continue

            # Load saved episode
            episode_folder = out_seed / "episode"
            env.load(episode_folder)
            npz = np.load(episode_folder / "episode.npz")
            qpos_arr = npz['qpos']
            time_arr = npz['time']

            # Deterministic midpoint: t_mid = 12.0s
            t_mid_target = 12.0
            idx_mid = int(np.argmin(np.abs(time_arr - t_mid_target)))

            # Set exact physical state
            env.data.qpos[:] = qpos_arr[idx_mid]
            env.data.time = float(time_arr[idx_mid])
            mujoco.mj_forward(env.model, env.data)

            # Capture visual observation
            obs = session.capture()
            png_bytes = base64.b64decode(obs['rgb_png_base64'])

            # Ground truth object pose
            truth_xyz = env.data.xpos[env.object_id].copy().tolist()
            truth_rot = env.data.xmat[env.object_id].reshape(3, 3).copy().tolist()

            # Save observation files
            mid_obs_file = out_seed / "06b-observation.json"
            mid_img_file = out_seed / "06b-lower_mid.png"
            write_json(mid_obs_file, obs)
            mid_img_file.write_bytes(png_bytes)

            # Build record
            mid_record = {
                'stage': 'lower_mid',
                'time_s': obs['time_s'],
                'image': '06b-lower_mid.png',
                'request': None,
                'action_status': 'midpoint_observation',
                'perception': {
                    'observation_id': obs['observation_id'],
                    'time_s': obs['time_s'],
                },
                'state_preserved': True,
                'private_true_xyz_m': truth_xyz,
                'private_true_rotation': truth_rot,
            }

            # Insert mid_record right before 'lower' stage
            lower_idx = next(i for i, r in enumerate(records) if r.get('stage') == 'lower')
            records.insert(lower_idx, mid_record)
            write_json(records_file, records)
    finally:
        renderer.close()


def evaluate_evidence(source_capture_dir, augmented_capture_dir, seeds,
                      output_file=None, render_if_missing=True):
    """Run comparative evaluation of Task 002: original vs augmented lowering streams."""
    source_capture_dir = Path(source_capture_dir)
    augmented_capture_dir = Path(augmented_capture_dir)
    seeds = list(seeds)

    if render_if_missing:
        # Check if all seeds exist in augmented dir
        needs_render = any(not (augmented_capture_dir / f"seed-{s}" / "06b-observation.json").is_file()
                           for s in seeds)
        if needs_render:
            print(f"Rendering lowering midpoints for seeds {seeds} into {augmented_capture_dir}...")
            render_augmented_dataset(source_capture_dir, augmented_capture_dir, seeds)

    print("Evaluating original endpoint-only stream...")
    orig_results = evaluate_dataset(source_capture_dir, seeds, stages=EXPECTED_STAGES,
                                    dataset_label='temporal-P4-capture-original')

    print("Evaluating augmented stream (with lowering midpoint)...")
    aug_results = evaluate_dataset(augmented_capture_dir, seeds, stages=AUGMENTED_STAGES,
                                   dataset_label='temporal-P4-capture-augmented')

    evidence = {
        'status': 'complete' if orig_results['status'] == 'complete' and aug_results['status'] == 'complete' else 'incomplete',
        'development_only': True,
        'seeds': seeds,
        'lowering_schedule': 'midpoint at t=12.0s',
        'source_provenance': str(source_capture_dir),
        'augmented_provenance': str(augmented_capture_dir),
        'original_stream': orig_results,
        'augmented_stream': aug_results,
    }

    if output_file is not None:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        write_json(output_file, evidence)

    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_capture_dir = Path('runtime/humanoid/temporal-P4/capture')
    if not default_capture_dir.is_dir():
        default_capture_dir = Path('/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture')
    parser.add_argument('--capture-dir', type=Path,
                        default=default_capture_dir)
    parser.add_argument('--augmented-dir', type=Path,
                        default=Path('runtime/humanoid/temporal-P4-augmented/capture'))
    parser.add_argument('--output', type=Path,
                        default=Path('experiments/humanoid-pick-place/results/temporal_reacquisition_development.json'))
    parser.add_argument('--output-evidence', type=Path,
                        default=Path('experiments/humanoid-pick-place/results/temporal_reacquisition_evidence_development.json'))
    parser.add_argument('--start-seed', type=int, default=820)
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--compare', action='store_true', default=True)
    args = parser.parse_args()

    if args.count < 1:
        parser.error('--count must be positive')

    seeds = list(range(args.start_seed, args.start_seed + args.count))

    if args.compare:
        evidence = evaluate_evidence(args.capture_dir, args.augmented_dir, seeds,
                                     output_file=args.output_evidence)
        # Also write the original results to --output for backwards compatibility
        write_json(args.output, evidence['original_stream'])
        print(f"\nTask 002 Evidence Evaluation finished with status: {evidence['status']}.")
        for stream_name, res in [('Original Stream (Endpoint-Only)', evidence['original_stream']),
                                 ('Augmented Stream (With Lowering Midpoint)', evidence['augmented_stream'])]:
            print(f"\n==================== {stream_name} ====================")
            for cand in ['baseline_p4', 'reacquisition_2frame', 'reacquisition_3frame']:
                print(f"\n--- {cand} (nominal original) ---")
                agg = res['candidates'][cand]['aggregate']['original']
                print(f"Accepted: {agg['accepted']}/{agg['expected_responses']}")
                print(f"Post-warmup targets: {agg['post_warmup_accepted']}/{agg['post_warmup_targets']}")
                print(f"Within 20mm: {agg['within_20mm']}")
                print(f"Accepted over 20mm: {agg['accepted_over_20mm']}")
                print(f"Mean error: {agg['accepted_mean_error_m']}")
                print(f"Max error: {agg['accepted_max_error_m']}")
                print(f"Release/retract accepted: {agg['release_or_retract_accepted']}")
    else:
        results = evaluate_dataset(args.capture_dir, seeds, args.output)
        print(f"Evaluation finished with status: {results['status']}.")


if __name__ == '__main__':
    main()
