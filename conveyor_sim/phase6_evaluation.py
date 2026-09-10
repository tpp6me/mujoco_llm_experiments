"""Complete-accounting Phase 6 paired evaluation and uncertainty summaries."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np
from .environment import ROOT


def wilson(successes, total):
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z*z/total
    center = (p + z*z/(2*total))/denominator
    radius = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))/denominator
    return [max(0, center-radius), min(1, center+radius)]


def distribution(values):
    return {"count": len(values), "min": min(values), "median": float(np.median(values)),
            "p95": float(np.percentile(values, 95)), "max": max(values)} if values else None


def summarize(reports):
    outcomes = Counter()
    for r in reports:
        outcomes.update(r['scoring']['outcomes'])
    events = [e for r in reports for e in r['events']]
    audits = [a for r in reports for a in r['perception_audits']]
    final = [a for a in audits if not a['superseded']]
    targets = sum(len(r['target_ids']) for r in reports)
    success = sum(r['sorting_success'] for r in reports)
    return {"episodes": len(reports), "successful_episodes": success,
            "physically_successful_episodes": sum(r['push_success'] for r in reports),
            "episode_success_wilson_95": wilson(success, len(reports)),
            "selection_correct_episodes": sum(r['selection_correct'] for r in reports),
            "realtime_healthy_episodes": sum(r['realtime_healthy'] for r in reports),
            "target_cubes": targets, "non_target_cubes": 3*len(reports)-targets,
            "outcomes": dict(outcomes), "target_rejection_rate": outcomes['correct_reject']/targets,
            "command_statuses": dict(Counter(e['status'] for e in events)),
            "estimates": len(audits), "correct_colors": sum(a['color_correct'] for a in audits),
            "final_rule_estimates": len(final), "correct_final_targets": sum(a['is_target'] for a in final),
            "position_error_m": distribution([a['position_error_m'] for a in audits]),
            "response_wall_s": distribution([e['observation_to_submission_wall_s'] for e in events
                                             if 'observation_to_submission_wall_s' in e]),
            "adaptation_delay_s": distribution([r['adaptation_delay_s'] for r in reports if r['adaptation_delay_s'] is not None]),
            "max_simulation_lag_s": max(r['max_simulation_lag_s'] for r in reports),
            "unintended_contact_episodes": sum(bool(r['unintended_cube_contacts'] or r['fixture_contacts'] or
                                                    r['cube_neighbor_contacts_on_belt']) for r in reports)}


def evaluate(root, output, case_file=None, inputs_relative='phase6/inputs'):
    folder = ROOT / 'experiments/conveyor-color-sorting'
    case_file = (case_file or folder/'phase6/cases.json').resolve()
    cases = json.loads(case_file.read_text())
    groups, images, paired = {}, [], []
    public_keys = {'observation_id','instruction','time_s','observed_at_utc','time_mode','belt_velocity_m_s',
                   'calibration','image_path','rule_version','next_rule_change_at_s',
                   'capture_to_image_ready_wall_s','image_ready_at_utc'}
    for actor in ['codex_session','conventional']:
        reports=[]
        for case in cases:
            directory = root/actor/case['id']
            r=json.loads((directory/'private/report.json').read_text())
            assert r['phase']==6 and r['completed'] and r['actor']==actor, case['id']
            assert r['scoring']['classified_cubes']==3, case['id']
            for key,value in case['config'].items():
                assert r['config'][key]==value, (case['id'],key)
            for name,digest in r['source_sha256'].items():
                assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest, name
            for o in r['observations']:
                assert set(o)==public_keys, (case['id'],set(o))
                dest=folder/inputs_relative/actor/f"{case['id']}_v{o['rule_version']}.png"
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(o['image_path'],dest)
                images.append({'actor':actor,'case':case['id'],'rule_version':o['rule_version'],
                               'image':str(dest.relative_to(folder)),
                               'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'observation':o})
            r['case_id'],r['condition']=case['id'],case['condition']
            reports.append(r)
        groups[actor]={'summary':summarize(reports),'runs':reports,
                       'conditions':{condition:summarize([r for r in reports if r['condition']==condition])
                                     for condition in sorted({c['condition'] for c in cases})}}
    for a,b in zip(groups['codex_session']['runs'],groups['conventional']['runs'],strict=True):
        assert a['initial_cubes']==b['initial_cubes'] and a['target_ids']==b['target_ids'],a['case_id']
        paired.append({'case':a['case_id'],'codex_success':a['sorting_success'],'conventional_success':b['sorting_success'],
                       'targets':len(a['target_ids']),'codex_rejected':a['scoring']['outcomes'].get('correct_reject',0),
                       'conventional_rejected':b['scoring']['outcomes'].get('correct_reject',0)})
    rng=np.random.default_rng(600006)
    samples=rng.integers(0,len(paired),(10000,len(paired)))
    numerator=np.array([p['codex_rejected']-p['conventional_rejected'] for p in paired])
    denominator=np.array([p['targets'] for p in paired])
    bootstrap=numerator[samples].sum(axis=1)/denominator[samples].sum(axis=1)
    robustness=[]
    for case in cases:
        if 'paired_reference' in case:
            for actor,g in groups.items():
                a=next(r for r in g['runs'] if r['case_id']==case['paired_reference'])
                b=next(r for r in g['runs'] if r['case_id']==case['id'])
                robustness.append({'actor':actor,'reference':case['paired_reference'],'variant':case['id'],
                                   'reference_success':a['sorting_success'],'variant_success':b['sorting_success']})
    healthy=all(r['realtime_healthy'] for g in groups.values() for r in g['runs'])
    healthy_indices=[i for i,(a,b) in enumerate(zip(groups['codex_session']['runs'],groups['conventional']['runs'],strict=True))
                     if a['realtime_healthy'] and b['realtime_healthy']]
    health_failures=[{'actor':actor,'case':r['case_id'],'max_lag_s':r['max_simulation_lag_s'],
                     'physical_success':r['push_success']}
                    for actor,g in groups.items() for r in g['runs'] if not r['realtime_healthy']]
    result={'phase':6,'development_measurement_complete':True,'all_runtimes_healthy':healthy,
            'formal_benchmark_complete':False,'matched_initial_states':True,'source_hashes_verified':True,
            'public_schema_verified':True,'cases':cases,'groups':groups,'images':images,'paired_comparisons':paired,
            'runtime_health_failures':health_failures,
            'healthy_pair_sensitivity':{actor:summarize([g['runs'][i] for i in healthy_indices]) for actor,g in groups.items()},
            'robustness_pairs':robustness,
            'target_rate_difference_codex_minus_conventional':float(numerator.sum()/denominator.sum()),
            'episode_paired_bootstrap_95':np.percentile(bootstrap,[2.5,97.5]).tolist() if len(paired)>=10 else None,
            'bootstrap':{'samples':10000,'seed':600006,'unit':'matched episode pair',
                         'note':'Interval omitted below ten pairs; tiny diagnostic cohorts can give degenerate intervals'},
            'study_artifact_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in [case_file,case_file.parent/'PROTOCOL.md']},
            'limitations':['Development manifest, not the planned 30 x 20-cube benchmark',
                           'Small per-condition samples and shared scene/development context',
                           'Camera rotation is about vertical axis, with supplied calibration',
                           'Conventional parser supports exactly the declared tested grammar',
                           'Response gaps include orchestration and image delivery, not isolated inference']}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'cases','images','groups','paired_comparisons','robustness_pairs'}} |
                     {'groups':{k:v['summary'] for k,v in groups.items()}},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'runtime/conveyor/phase6')
    parser.add_argument('--output',type=Path,default=ROOT/'experiments/conveyor-color-sorting/results/phase6_comparison.json')
    parser.add_argument('--cases',type=Path)
    parser.add_argument('--inputs-relative',default='phase6/inputs')
    args=parser.parse_args()
    evaluate(args.root,args.output,args.cases,args.inputs_relative)
