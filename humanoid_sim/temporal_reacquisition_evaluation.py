"""Development evaluation comparing baseline P4 and reacquisition candidate.

Evaluates offline on development captures (seeds 820-829).
All ground-truth poses and private drift measurements are computed post-hoc
after the estimator returns and are never provided to either tracker.

Maintains explicit grid accounting: expected, observed, evaluated, and missing counts.
Nominal post-warmup denominator is fixed at 2 per requested seed.
"""
import argparse
import base64
import copy
import io
import json
from collections import Counter
from pathlib import Path
import time

import numpy as np
from PIL import Image

from .perception_evaluation import write_json
from .temporal_pose import (
    TemporalPose, TemporalReacquisitionPose, quaternion_matrix
)

EXPECTED_STAGES = ['lift', 'lift_hold', 'transport', 'lower', 'release', 'retract']
NOMINAL_POST_WARMUP_STAGES = {'transport', 'lower'}
EXPECTED_VARIANTS = ['original', 'black_transport', 'frozen_transport_rgb']


def evaluate_stream(tracker_factory, seed, stage_observations, variant):
    tracker = tracker_factory()
    previous_image = None
    records = []
    offsets = {}

    for stage in EXPECTED_STAGES:
        stage_data = stage_observations.get(stage)
        if stage_data is None:
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'missing_stage',
                'estimate': None,
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': None,
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        frame_info, original = stage_data
        if original is None:
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'missing_observation_file',
                'estimate': None,
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': frame_info.get('private_true_xyz_m'),
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        observation = copy.deepcopy(original)
        if stage == 'transport':
            if variant == 'black_transport':
                buffer = io.BytesIO()
                Image.new('RGB', (observation['camera']['width'], observation['camera']['height'])).save(buffer, format='PNG')
                observation['rgb_png_base64'] = base64.b64encode(buffer.getvalue()).decode()
            elif variant == 'frozen_transport_rgb' and previous_image is not None:
                observation['rgb_png_base64'] = previous_image

        try:
            start = time.perf_counter()
            estimate = tracker.observe(observation)
            elapsed = time.perf_counter() - start
        except Exception as err:
            records.append({
                'seed': seed,
                'stage': stage,
                'variant': variant,
                'status': 'estimator_error',
                'error_message': str(err),
                'estimate': None,
                'error_3d_m': None,
                'within_20mm': False,
                'elapsed_s': 0.0,
                'private_true_xyz_m': frame_info.get('private_true_xyz_m'),
                'private_object_to_hand_offset_m': None,
                'private_window_center_drift_m': 0.0,
            })
            continue

        previous_image = original['rgb_png_base64']

        # Post-hoc evaluation using private ground truth
        if frame_info.get('private_true_xyz_m') is not None and 'robot_state' in original:
            hand = original['robot_state']['robot']
            offset = quaternion_matrix(hand['hand_quaternion_wxyz']).T @ (
                np.array(frame_info['private_true_xyz_m']) - hand['hand_xyz_m'])
            offsets[float(original['time_s'])] = offset
            window = [offsets[t] for t in estimate.get('window_times_s', []) if t in offsets]
            drift = max((float(np.linalg.norm(v - window[0])) for v in window), default=0.0)
            error = (float(np.linalg.norm(np.array(estimate['object_center_xyz_m']) - frame_info['private_true_xyz_m']))
                     if estimate['detected'] else None)
            offset_list = offset.tolist()
        else:
            offset_list = None
            drift = 0.0
            error = None

        records.append({
            'seed': seed,
            'stage': stage,
            'variant': variant,
            'status': 'evaluated',
            'estimate': estimate,
            'error_3d_m': error,
            'within_20mm': error is not None and error <= 0.02,
            'elapsed_s': elapsed,
            'private_true_xyz_m': frame_info['private_true_xyz_m'],
            'private_object_to_hand_offset_m': offset_list,
            'private_window_center_drift_m': drift,
        })
    return records


def compute_aggregate(records, seeds):
    aggregate = {}
    num_seeds = len(seeds)
    expected_per_stream = num_seeds * len(EXPECTED_STAGES)
    expected_post_warmup = num_seeds * len(NOMINAL_POST_WARMUP_STAGES)

    for variant in EXPECTED_VARIANTS:
        v_records = [r for r in records if r['variant'] == variant]
        evaluated = [r for r in v_records if r['status'] == 'evaluated']
        missing = [r for r in v_records if r['status'] != 'evaluated']
        errors = [r['error_3d_m'] for r in evaluated if r['error_3d_m'] is not None]

        post_warmup_records = [r for r in evaluated if r['stage'] in NOMINAL_POST_WARMUP_STAGES]
        post_warmup_errors = [r['error_3d_m'] for r in post_warmup_records if r['error_3d_m'] is not None]

        aggregate[variant] = {
            'expected_responses': expected_per_stream,
            'evaluated_responses': len(evaluated),
            'missing_responses': len(missing),
            'missing_or_error_details': [{'seed': r['seed'], 'stage': r['stage'], 'status': r['status']}
                                         for r in missing],
            'accepted': len(errors),
            'within_20mm': sum(r['within_20mm'] for r in evaluated),
            'accepted_over_20mm': sum(e > 0.02 for e in errors),
            'accepted_mean_error_m': float(np.mean(errors)) if errors else None,
            'accepted_max_error_m': max(errors) if errors else None,
            'post_warmup_targets': expected_post_warmup,
            'post_warmup_accepted': len(post_warmup_errors),
            'post_warmup_within_20mm': sum(r['within_20mm'] for r in post_warmup_records),
            'post_warmup_missing_or_refused': expected_post_warmup - len(post_warmup_errors),
            'release_or_retract_accepted': sum(r['estimate']['detected'] for r in evaluated
                                              if r['stage'] in ('release', 'retract')),
            'refusals': dict(Counter(r['estimate']['reason'] for r in evaluated
                                     if not r['estimate']['detected'])),
        }
    return aggregate


def evaluate_dataset(capture_dir, seeds, output_file=None):
    seeds = list(seeds)
    if not seeds or any(not isinstance(s, int) or s < 0 for s in seeds):
        raise ValueError('Seeds must be a non-empty list of non-negative integers')

    capture_dir = Path(capture_dir)
    results = {
        'status': 'complete',
        'development_only': True,
        'dataset': 'temporal-P4-capture',
        'seeds': seeds,
        'expected_episodes': len(seeds),
        'expected_stages_per_episode': EXPECTED_STAGES,
        'candidates': {},
    }

    # Load captured observations for each seed
    seed_data = {}
    for seed in seeds:
        folder = capture_dir / f"seed-{seed}"
        if not folder.is_dir():
            seed_data[seed] = {s: None for s in EXPECTED_STAGES}
            continue

        records_file = folder / "private_records.json"
        if not records_file.is_file():
            seed_data[seed] = {s: None for s in EXPECTED_STAGES}
            continue

        try:
            private_records = json.loads(records_file.read_text())
        except Exception:
            seed_data[seed] = {s: None for s in EXPECTED_STAGES}
            continue

        stage_obs = {}
        for stage in EXPECTED_STAGES:
            rec = next((r for r in private_records if r.get('stage') == stage), None)
            if rec is None:
                stage_obs[stage] = None
                continue
            idx = private_records.index(rec)
            obs_file = folder / f"{idx:02d}-observation.json"
            if not obs_file.is_file():
                stage_obs[stage] = (rec, None)
                continue
            try:
                obs = json.loads(obs_file.read_text())
                stage_obs[stage] = (rec, obs)
            except Exception:
                stage_obs[stage] = (rec, None)
        seed_data[seed] = stage_obs

    configurations = [
        ('baseline_p4', lambda: TemporalPose(reacquisition=False)),
        ('reacquisition_candidate', lambda: TemporalReacquisitionPose()),
    ]

    has_missing = False
    for candidate_name, factory in configurations:
        candidate_records = []
        for seed in seeds:
            for variant in EXPECTED_VARIANTS:
                stream_records = evaluate_stream(factory, seed, seed_data[seed], variant)
                candidate_records.extend(stream_records)

        aggregate = compute_aggregate(candidate_records, seeds)
        if any(agg['missing_responses'] > 0 for agg in aggregate.values()):
            has_missing = True

        results['candidates'][candidate_name] = {
            'aggregate': aggregate,
            'records': candidate_records,
        }

    if has_missing:
        results['status'] = 'incomplete'

    if output_file is not None:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        write_json(output_file, results)

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-dir', type=Path,
                        default=Path('/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture'))
    parser.add_argument('--output', type=Path,
                        default=Path('experiments/humanoid-pick-place/results/temporal_reacquisition_development.json'))
    parser.add_argument('--start-seed', type=int, default=820)
    parser.add_argument('--count', type=int, default=10)
    args = parser.parse_args()

    if args.count < 1:
        parser.error('--count must be positive')

    seeds = range(args.start_seed, args.start_seed + args.count)
    results = evaluate_dataset(args.capture_dir, seeds, args.output)

    print(f"Evaluation finished with status: {results['status']}.")
    for name, data in results['candidates'].items():
        print(f"\n--- {name} ---")
        print(json.dumps(data['aggregate'], indent=2))


if __name__ == '__main__':
    main()
