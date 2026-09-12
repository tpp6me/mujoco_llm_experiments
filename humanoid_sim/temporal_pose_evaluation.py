"""Private P4 temporal-model audit; exact-state driver, no image-driven actions."""
import argparse
import base64
import copy
import io
import json
import hashlib
from collections import Counter
from pathlib import Path
import time

import numpy as np
from PIL import Image

from .perception_evaluation import audit, write_json
from .temporal_pose import TemporalPose, quaternion_matrix

PROTOCOL = Path('experiments/humanoid-pick-place/protocols/P4.md')
STAGES = {'lift', 'lift_hold', 'transport', 'lower', 'release', 'retract'}


def evaluate(output, seeds):
    output.mkdir(parents=True, exist_ok=False)
    captured = audit(output/'capture', seeds, protocol=PROTOCOL, protocol_id='P4_capture')
    summary = {'protocol': 'P4', 'development_only': True, 'status': 'running',
               'source_sha256': captured['source_sha256'], 'seeds': list(seeds),
               'driver': 'conventional_exact_state_G2', 'records': [],
               'capture_episodes': [{'seed': e['seed'], 'failure': e['failure'],
                                     'frame_count': len(e['frames'])} for e in captured['episodes']]}
    write_json(output/'summary.json', summary)
    for episode in captured['episodes']:
        folder = output/'capture'/f"seed-{episode['seed']}"
        frames = []
        for index, frame in enumerate(episode['frames']):
            if frame['stage'] in STAGES:
                observation = json.loads((folder/f'{index:02d}-observation.json').read_text())
                frames.append((frame, observation))
        for variant in ['original', 'black_transport', 'frozen_transport_rgb']:
            tracker = TemporalPose()
            previous_image = None
            offsets = {}
            for frame, original in frames:
                for name, digest in summary['source_sha256'].items():
                    if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                        raise RuntimeError(f'Frozen source changed: {name}')
                observation = copy.deepcopy(original)
                if frame['stage'] == 'transport':
                    if variant == 'black_transport':
                        buffer = io.BytesIO()
                        Image.new('RGB', (observation['camera']['width'], observation['camera']['height'])).save(buffer, format='PNG')
                        observation['rgb_png_base64'] = base64.b64encode(buffer.getvalue()).decode()
                    elif variant == 'frozen_transport_rgb' and previous_image is not None:
                        observation['rgb_png_base64'] = previous_image
                start = time.perf_counter()
                estimate = tracker.observe(observation)
                elapsed = time.perf_counter()-start
                previous_image = original['rgb_png_base64']
                # Private accuracy and slip measurements only after estimation.
                hand = original['robot_state']['robot']
                offset = quaternion_matrix(hand['hand_quaternion_wxyz']).T@(
                    np.array(frame['private_true_xyz_m'])-hand['hand_xyz_m'])
                offsets[frame['time_s']] = offset
                window = [offsets[t] for t in estimate.get('window_times_s', [])]
                drift = max((float(np.linalg.norm(v-window[0])) for v in window), default=0.)
                error = (float(np.linalg.norm(np.array(estimate['object_center_xyz_m'])-frame['private_true_xyz_m']))
                         if estimate['detected'] else None)
                summary['records'].append({'seed': episode['seed'], 'stage': frame['stage'],
                                           'variant': variant, 'estimate': estimate,
                                           'error_3d_m': error, 'within_20mm': error is not None and error <= .02,
                                           'elapsed_s': elapsed, 'private_true_xyz_m': frame['private_true_xyz_m'],
                                           'private_object_to_hand_offset_m': offset.tolist(),
                                           'private_window_center_drift_m': drift})
                write_json(output/'summary.json', summary)
            print(json.dumps({'seed': episode['seed'], 'variant': variant,
                              'responses': len(summary['records'])}), flush=True)
    aggregate = {}
    for variant in ['original', 'black_transport', 'frozen_transport_rgb']:
        records = [r for r in summary['records'] if r['variant'] == variant]
        errors = [r['error_3d_m'] for r in records if r['error_3d_m'] is not None]
        aggregate[variant] = {'responses': len(records), 'accepted': len(errors),
                              'within_20mm': sum(r['within_20mm'] for r in records),
                              'accepted_over_20mm': sum(e > .02 for e in errors),
                              'accepted_mean_error_m': float(np.mean(errors)) if errors else None,
                              'accepted_max_error_m': max(errors) if errors else None,
                              'release_or_retract_accepted': sum(r['estimate']['detected'] for r in records
                                                                if r['stage'] in ('release', 'retract')),
                              'refusals': dict(Counter(r['estimate']['reason'] for r in records
                                                       if not r['estimate']['detected']))}
    summary.update(status='complete', aggregate=aggregate)
    write_json(output/'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start-seed', type=int, default=820)
    parser.add_argument('--count', type=int, default=10)
    args = parser.parse_args()
    if args.count < 1:
        parser.error('--count must be positive')
    evaluate(args.output, range(args.start_seed, args.start_seed+args.count))


if __name__ == '__main__':
    main()
