"""Private P3 candidate audit on fresh exact-state-driven RGB trajectories."""
import argparse
import base64
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image

from .carried_pose import estimate_carried_block
from .perception_evaluation import audit, write_json

PROTOCOL = Path('experiments/humanoid-pick-place/protocols/P3.md')
CARRIED_STAGES = {'lift', 'lift_hold', 'transport', 'lower'}


def variants(png):
    """Declared sensor corruption from pixels only; never object-truth bounds."""
    rgb = np.array(Image.open(io.BytesIO(png)).convert('RGB'))
    r, g, b = rgb.astype(float).transpose(2, 0, 1)
    red = (r > 65) & (r > 1.8*g) & (r > 1.8*b)
    columns = np.argwhere(red)[:, 1]
    cut = int(np.median(columns)) if len(columns) else rgb.shape[1]//2
    partial = rgb.copy()
    partial[:, :cut+1] = 0
    result = {'original': png}
    for name, array in [('half_occluded', partial), ('blank', np.zeros_like(rgb))]:
        buffer = io.BytesIO()
        Image.fromarray(array).save(buffer, format='PNG')
        result[name] = buffer.getvalue()
    return result


def evaluate(output, seeds):
    output.mkdir(parents=True, exist_ok=False)
    captured = audit(output/'capture', seeds, protocol=PROTOCOL, protocol_id='P3_capture')
    summary = {'protocol': 'P3', 'development_only': True, 'status': 'running',
               'source_sha256': captured['source_sha256'], 'seeds': list(seeds),
               'driver': 'conventional_exact_state_G2', 'records': [],
               'capture_episodes': [{'seed': e['seed'], 'failure': e['failure'],
                                     'frame_count': len(e['frames'])} for e in captured['episodes']]}
    write_json(output/'summary.json', summary)
    for episode in captured['episodes']:
        folder = output/'capture'/f"seed-{episode['seed']}"
        for index, frame in enumerate(episode['frames']):
            if frame['stage'] not in CARRIED_STAGES:
                continue
            observation = json.loads((folder/f'{index:02d}-observation.json').read_text())
            png = base64.b64decode(observation['rgb_png_base64'])
            for variant, image in variants(png).items():
                for name, digest in summary['source_sha256'].items():
                    if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                        raise RuntimeError(f'Frozen source changed: {name}')
                start = time.perf_counter()
                # Estimator inputs are restricted to the public observation.
                estimate = estimate_carried_block(image, observation['camera'],
                                                  observation['robot_state']['robot']['hand_xyz_m'])
                elapsed = time.perf_counter()-start
                # Private accuracy measurement happens only after estimation.
                error = (float(np.linalg.norm(np.array(estimate['object_center_xyz_m'])
                                              - frame['private_true_xyz_m']))
                         if estimate['detected'] else None)
                rotation = np.array(frame['private_true_rotation'])
                record = {'seed': episode['seed'], 'stage': frame['stage'], 'variant': variant,
                          'estimate': estimate, 'error_3d_m': error,
                          'within_20mm': error is not None and error <= .02,
                          'elapsed_s': elapsed, 'private_true_xyz_m': frame['private_true_xyz_m'],
                          'private_long_axis_tilt_deg': float(np.degrees(np.arccos(
                              np.clip(abs(rotation[2, 2]), 0, 1))))}
                summary['records'].append(record)
                write_json(output/'summary.json', summary)
            print(json.dumps({'seed': episode['seed'], 'stage': frame['stage'],
                              'cases': len(summary['records'])}), flush=True)
    aggregate = {}
    for variant in ['original', 'half_occluded', 'blank']:
        records = [r for r in summary['records'] if r['variant'] == variant]
        errors = [r['error_3d_m'] for r in records if r['error_3d_m'] is not None]
        aggregate[variant] = {'cases': len(records), 'accepted': len(errors),
                              'within_20mm': sum(r['within_20mm'] for r in records),
                              'accepted_over_20mm': sum(e > .02 for e in errors),
                              'accepted_mean_error_m': float(np.mean(errors)) if errors else None,
                              'accepted_max_error_m': max(errors) if errors else None,
                              'refusals': dict(Counter(r['estimate']['reason'] for r in records
                                                       if not r['estimate']['detected']))}
    summary['aggregate'] = aggregate
    summary['status'] = 'complete'
    write_json(output/'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start-seed', type=int, default=800)
    parser.add_argument('--count', type=int, default=10)
    args = parser.parse_args()
    if args.count < 1:
        parser.error('--count must be positive')
    evaluate(args.output, range(args.start_seed, args.start_seed+args.count))


if __name__ == '__main__':
    main()
