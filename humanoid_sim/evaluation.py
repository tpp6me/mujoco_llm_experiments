"""Sequential reproducible mechanical development trials, with all failures retained."""
import hashlib
import json
import platform
from pathlib import Path
import time

import mujoco
import numpy as np

from .baseline import run_baseline
from .environment import Environment
from .scene import ROOT, SCENE, COMMIT


def provenance():
    paths = [SCENE, *sorted((ROOT/'humanoid_sim').glob('*.py'))]
    return {'model_commit': COMMIT, 'mujoco': mujoco.__version__, 'numpy': np.__version__,
            'python': platform.python_version(), 'platform': platform.platform(),
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def run_trial(output, seed=0, randomize=False):
    output = Path(output)
    if (output/'report.json').exists():
        raise ValueError(f'Trial already exists: {output}')
    env = Environment()
    env.reset(seed, randomize)
    initial = env.observe()
    started = time.monotonic()
    error = None
    try:
        error = run_baseline(env)
    except (RuntimeError, ValueError) as exc:
        error = f'{type(exc).__name__}: {exc}'
    report = {**env.scorer.report(), 'seed': seed, 'randomized': randomize,
              'controller': 'conventional_exact_state', 'error': error,
              'initial': initial, 'final': env.observe(), 'wall_seconds': time.monotonic()-started,
              'provenance': provenance()}
    report['physics_quality_pass'] = report['max_object_penetration_m'] <= .002
    report['gate_success'] = bool(report['success'] and report['physics_quality_pass'] and error is None)
    env.save(output)
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def validate(output, seeds=100, first_seed=0):
    if seeds < 1:
        raise ValueError('At least one seed is required')
    output = Path(output)
    if output.exists():
        raise ValueError(f'Validation output already exists: {output}')
    output.mkdir(parents=True)
    reports = []
    for seed in range(first_seed, first_seed+seeds):
        report = run_trial(output/f'seed-{seed:04}', seed, True)
        reports.append(report)
        summary = {'status': 'running', 'requested_trials': seeds, 'completed_trials': len(reports),
                   'physical_successes': sum(r['success'] for r in reports),
                   'gate_successes': sum(r['gate_success'] for r in reports),
                   'max_object_penetration_m': max(r['max_object_penetration_m'] for r in reports),
                   'reports': reports}
        if len(reports) == seeds:
            summary['status'] = 'complete'
            summary['gate_passed'] = seeds >= 100 and summary['gate_successes']/seeds >= .95
        (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print(json.dumps({'seed': seed, 'success': report['success'], 'gate_success': report['gate_success'], 'error': report['error']}), flush=True)
    return summary
