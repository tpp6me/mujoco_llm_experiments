"""Development evaluation comparing baseline P4 and reacquisition candidate.

Evaluates offline on development captures (seeds 820-829).
All ground-truth poses and private drift measurements are computed post-hoc
after the estimator returns and are never provided to either tracker.
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

STAGES = ['lift', 'lift_hold', 'transport', 'lower', 'release', 'retract']


def evaluate_stream(tracker_factory, frames, variant):
    tracker = tracker_factory()
    previous_image = None
    records = []
    offsets = {}

    for frame_info, original in frames:
        observation = copy.deepcopy(original)
        stage = frame_info['stage']
        if stage == 'transport':
            if variant == 'black_transport':
                buffer = io.BytesIO()
                Image.new('RGB', (observation['camera']['width'], observation['camera']['height'])).save(buffer, format='PNG')
                observation['rgb_png_base64'] = base64.b64encode(buffer.getvalue()).decode()
            elif variant == 'frozen_transport_rgb' and previous_image is not None:
                observation['rgb_png_base64'] = previous_image

        start = time.perf_counter()
        estimate = tracker.observe(observation)
        elapsed = time.perf_counter() - start
        previous_image = original['rgb_png_base64']

        # Post-hoc evaluation using private ground truth
        hand = original['robot_state']['robot']
        offset = quaternion_matrix(hand['hand_quaternion_wxyz']).T @ (
            np.array(frame_info['private_true_xyz_m']) - hand['hand_xyz_m'])
        offsets[frame_info['time_s']] = offset
        window = [offsets[t] for t in estimate.get('window_times_s', [])]
        drift = max((float(np.linalg.norm(v - window[0])) for v in window), default=0.)
        error = (float(np.linalg.norm(np.array(estimate['object_center_xyz_m']) - frame_info['private_true_xyz_m']))
                 if estimate['detected'] else None)

        records.append({
            'stage': stage,
            'variant': variant,
            'estimate': estimate,
            'error_3d_m': error,
            'within_20mm': error is not None and error <= 0.02,
            'elapsed_s': elapsed,
            'private_true_xyz_m': frame_info['private_true_xyz_m'],
            'private_object_to_hand_offset_m': offset.tolist(),
            'private_window_center_drift_m': drift,
        })
    return records


def compute_aggregate(records):
    aggregate = {}
    for variant in ['original', 'black_transport', 'frozen_transport_rgb']:
        v_records = [r for r in records if r['variant'] == variant]
        errors = [r['error_3d_m'] for r in v_records if r['error_3d_m'] is not None]
        post_warmup_records = [r for r in v_records if r['stage'] in ('transport', 'lower')]
        post_warmup_errors = [r['error_3d_m'] for r in post_warmup_records if r['error_3d_m'] is not None]

        aggregate[variant] = {
            'responses': len(v_records),
            'accepted': len(errors),
            'within_20mm': sum(r['within_20mm'] for r in v_records),
            'accepted_over_20mm': sum(e > 0.02 for e in errors),
            'accepted_mean_error_m': float(np.mean(errors)) if errors else None,
            'accepted_max_error_m': max(errors) if errors else None,
            'post_warmup_targets': len(post_warmup_records),
            'post_warmup_accepted': len(post_warmup_errors),
            'post_warmup_within_20mm': sum(r['within_20mm'] for r in post_warmup_records),
            'release_or_retract_accepted': sum(r['estimate']['detected'] for r in v_records
                                              if r['stage'] in ('release', 'retract')),
            'refusals': dict(Counter(r['estimate']['reason'] for r in v_records
                                     if not r['estimate']['detected'])),
        }
    return aggregate


def evaluate_dataset(capture_dir, seeds, output_file=None):
    capture_dir = Path(capture_dir)
    results = {
        'status': 'complete',
        'development_only': True,
        'dataset': 'temporal-P4-capture',
        'seeds': list(seeds),
        'candidates': {},
    }

    configurations = [
        ('baseline_p4', lambda: TemporalPose(reacquisition=False)),
        ('reacquisition_candidate', lambda: TemporalReacquisitionPose()),
    ]

    for candidate_name, factory in configurations:
        candidate_records = []
        for seed in seeds:
            folder = capture_dir / f"seed-{seed}"
            private_records = json.loads((folder / "private_records.json").read_text())
            frames = []
            for idx, r in enumerate(private_records):
                if r['stage'] in STAGES:
                    obs = json.loads((folder / f"{idx:02d}-observation.json").read_text())
                    frames.append((r, obs))

            for variant in ['original', 'black_transport', 'frozen_transport_rgb']:
                stream_records = evaluate_stream(factory, frames, variant)
                for rec in stream_records:
                    rec['seed'] = seed
                candidate_records.extend(stream_records)

        aggregate = compute_aggregate(candidate_records)
        results['candidates'][candidate_name] = {
            'aggregate': aggregate,
            'records': candidate_records,
        }

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

    seeds = range(args.start_seed, args.start_seed + args.count)
    results = evaluate_dataset(args.capture_dir, seeds, args.output)

    print("Evaluation complete.")
    for name, data in results['candidates'].items():
        print(f"\n--- {name} ---")
        print(json.dumps(data['aggregate'], indent=2))


if __name__ == '__main__':
    main()
