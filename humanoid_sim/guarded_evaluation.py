"""Sequential qualification of the conventional policy through the shared interface."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from .environment import Environment
from .interface import PolicyInterface
from .guarded_baseline import run_policy
from .evaluation import provenance as legacy_provenance
from .scene import ROOT

CONFIGURATIONS = {'g1': {'release_z': .90, 'release_closure': .4},
                  'g2': {'release_z': .88, 'release_closure': .4}}


def provenance(protocol='g1'):
    configuration = CONFIGURATIONS[protocol]
    protocol_path = ROOT/f'experiments/humanoid-pick-place/protocols/{protocol.upper()}.md'
    result = legacy_provenance()
    result['protocol_id'] = f'supported-g1-guarded-{protocol}'
    result['policy_configuration'] = configuration.copy()
    for path in [protocol_path, ROOT/'experiments/humanoid-pick-place/schemas/action-v2.schema.json']:
        result['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def run_trial(folder, seed, frozen=None, protocol='g1'):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    actual = provenance(protocol)
    if frozen is not None and actual != frozen:
        raise ValueError('Configuration changed during frozen evaluation')
    env = Environment(); env.reset(seed, True)
    api = PolicyInterface(env)
    initial = api.observe(); started = time.monotonic(); error = None
    try:
        error = run_policy(api, **CONFIGURATIONS[protocol])
    except (ValueError, RuntimeError) as exc:
        error = f'{type(exc).__name__}: {exc}'
    report = {**env.scorer.report(), 'seed': seed, 'randomized': True,
              'controller': 'conventional_exact_state_guarded', 'error': error,
              'initial': initial, 'final': api.observe(), 'wall_seconds': time.monotonic()-started,
              'provenance': actual, 'action_attempts': len(env.events),
              'rejected_actions': sum(e.get('interface_response', {}).get('status')=='rejected' for e in env.events)}
    report['physics_quality_pass'] = report['max_object_penetration_m'] <= .002
    report['deadline_pass'] = env.data.time <= 25.000001
    report['gate_success'] = bool(report['success'] and report['physics_quality_pass'] and report['deadline_pass'] and error is None and report['rejected_actions']==0)
    env.save(folder)
    (folder/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


def validate(folder, count=100, first_seed=500, protocol='g1'):
    if count < 1: raise ValueError('count must be positive')
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=False)
    frozen = provenance(protocol); reports = []
    (folder/'manifest.json').write_text(json.dumps({'seeds':list(range(first_seed,first_seed+count)), 'provenance':frozen}, indent=2)+'\n')
    for seed in range(first_seed, first_seed+count):
        report = run_trial(folder/f'seed-{seed:04}', seed, frozen, protocol); reports.append(report)
        summary = {'status': 'complete' if len(reports)==count else 'running',
                   'requested_trials': count, 'completed_trials': len(reports),
                   'physical_successes': sum(r['success'] for r in reports),
                   'gate_successes': sum(r['gate_success'] for r in reports),
                   'rejected_actions': sum(r['rejected_actions'] for r in reports),
                   'protocol_matched': count == 100 and first_seed == {'g1': 500, 'g2': 600}[protocol],
                   'max_object_penetration_m': max(r['max_object_penetration_m'] for r in reports),
                   'reports': reports}
        summary['gate_passed'] = len(reports)==count and summary['protocol_matched'] and summary['gate_successes']/count>=.95
        (folder/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
        print(json.dumps({'seed':seed,'success':report['success'],'gate_success':report['gate_success'],'error':report['error']}),flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--protocol', choices=sorted(CONFIGURATIONS), default='g1')
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--first-seed', type=int, default=500)
    args = parser.parse_args()
    summary = validate(args.output, args.count, args.first_seed, args.protocol)
    print(json.dumps({k:v for k,v in summary.items() if k!='reports'}, indent=2))
    return 0 if summary['gate_passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
