"""Private RGB visibility audit driven by the exact-state conventional policy.

This is not a visual controller evaluation. Never expose this evaluator or its
private records as policy observations.
"""
import argparse
import base64
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

from .environment import Environment
from .guarded_baseline import run_policy
from .interface import PolicyInterface
from .perception import PerceptionSession
from .visual import RGBRenderer, VisualSession, integration_state, project
from .vision_pose import estimate_supported_block

STAGES = ['reset', 'approach', 'descend', 'close', 'lift', 'lift_hold',
          'transport', 'lower', 'release', 'retract', 'park', 'settle']
PROTOCOL = Path('experiments/humanoid-pick-place/protocols/P2.md')


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def audit(output, seeds, protocol=PROTOCOL, protocol_id="P2"):
    output.mkdir(parents=True, exist_ok=False)
    paths = [*Path('humanoid_sim').glob('*.py'), Path('scenes/g1_pick_place.xml'),
             Path('requirements-lock.txt'), protocol]
    frozen = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    manifest = {'protocol': protocol_id, 'seeds': list(seeds), 'source_sha256': frozen,
                'controller': 'conventional_exact_state_guarded_G2',
                'development_only': True, 'observation_condition': 'fixed_camera_RGB'}
    write_json(output/'manifest.json', manifest)
    summary = {**manifest, 'status': 'running', 'episodes': []}
    write_json(output/'summary.json', summary)
    env = Environment()
    renderer = RGBRenderer(env)
    try:
        for seed in seeds:
            for name, digest in frozen.items():
                if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                    raise RuntimeError(f'Frozen source changed: {name}')
            env.reset(seed, True)
            folder = output/f'seed-{seed}'
            folder.mkdir()
            session = PerceptionSession(VisualSession(env, renderer))
            records = []
            current = None

            def capture(request=None, response=None):
                nonlocal current
                before = integration_state(env)
                observation, perception = session.capture()
                preserved = np.array_equal(before, integration_state(env))
                if not preserved:
                    raise RuntimeError('Capture changed integration state')
                current = observation['observation_id']
                png = base64.b64decode(observation['rgb_png_base64'])
                index = len(records)
                stage = STAGES[index] if index < len(STAGES) else f'action-{index}'
                image_name = f'{index:02d}-{stage}.png'
                (folder/image_name).write_bytes(png)
                # Public artifacts never contain task truth or scoring fields.
                write_json(folder/f'{index:02d}-observation.json', observation)
                write_json(folder/f'{index:02d}-perception.json', perception)
                # Everything below this line is private, post-capture diagnostics.
                truth = env.data.xpos[env.object_id].copy()
                rotation = env.data.xmat[env.object_id].reshape(3, 3)
                half_size = env.model.geom_size[env.object_geom]
                corners = [truth+rotation@(half_size*np.array(signs))
                           for signs in itertools.product([-1, 1], repeat=3)]
                projected = np.array([project(p, observation['camera']) for p in corners])
                bounds = np.r_[projected.min(axis=0), projected.max(axis=0)]
                visibility = perception['visibility']
                pixel_error = None
                within_bounds = None
                if visibility['detected']:
                    box = np.array(visibility['bbox_xyxy_px'])
                    within_bounds = bool(np.all(box[:2] >= bounds[:2]-2)
                                         and np.all(box[2:] <= bounds[2:]+2))
                    pixel_error = float(np.linalg.norm(
                        np.array(visibility['centroid_xy_px'])-project(truth, observation['camera'])))
                # Deliberately misuse the old prior as a diagnostic comparator only.
                raw = estimate_supported_block(png, observation['camera'])
                raw_error = (float(np.linalg.norm(np.array(raw['object_center_xyz_m'])-truth))
                             if raw['detected'] else None)
                pose = perception['pose']
                error = (float(np.linalg.norm(np.array(pose['object_center_xyz_m'])-truth))
                         if pose['detected'] else None)
                records.append({'stage': stage, 'time_s': observation['time_s'],
                                'image': image_name, 'request': request,
                                'action_status': response and response['status'],
                                'perception': perception, 'state_preserved': preserved,
                                'private_true_xyz_m': truth.tolist(),
                                'private_true_rotation': rotation.tolist(),
                                'private_projected_bbox_px': bounds.tolist(),
                                'red_bbox_within_object_projection': within_bounds,
                                'visible_centroid_to_projected_center_px': pixel_error,
                                'pose_error_3d_m': error,
                                'raw_P1_diagnostic': raw, 'raw_P1_error_3d_m': raw_error})
                write_json(folder/'private_records.json', records)

            class OracleDriver:
                def observe(self):
                    return PolicyInterface(env, 'exact_state').observe()

                def execute(self, request):
                    response = session.execute(current, request)
                    capture(request, response)
                    return response

            failure = None
            try:
                capture()
                failure = run_policy(OracleDriver(), release_z=.88, release_closure=.4)
            except Exception as error:
                failure = f'{type(error).__name__}: {error}'
            env.save(folder/'episode')
            result = {'seed': seed, 'failure': failure, 'frames': records,
                      'private_score': env.scorer.report()}
            summary['episodes'].append(result)
            write_json(output/'summary.json', summary)
            print(json.dumps({'seed': seed, 'frames': len(records), 'failure': failure}), flush=True)
        summary['status'] = 'complete'
        write_json(output/'summary.json', summary)
    finally:
        renderer.close()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start-seed', type=int, default=760)
    parser.add_argument('--count', type=int, default=20)
    args = parser.parse_args()
    if args.count < 1:
        parser.error('--count must be positive')
    audit(args.output, range(args.start_seed, args.start_seed+args.count))


if __name__ == '__main__':
    main()
