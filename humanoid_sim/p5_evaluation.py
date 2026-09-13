"""P5 preparation and evaluation wrapper for passive temporal reacquisition.

Prepares and screens the passive P5 protocol on existing development captures (seeds 820-829).
Reuses the fixed-grid evaluator and augmentation helpers from Task 002.
Held-out validation seeds (840-849) are strictly protected and cannot be executed here.
Perception remains completely disconnected from control.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from .perception_evaluation import write_json
from .temporal_pose import (
    TemporalPose, TemporalReacquisitionPose, TemporalThreeFrameReacquisitionPose
)
from .temporal_reacquisition_evaluation import (
    EXPECTED_STAGES, AUGMENTED_STAGES, NOMINAL_POST_WARMUP_STAGES,
    EXPECTED_VARIANTS, AUGMENTED_MANIFEST_VERSION, AUGMENTED_GENERATION_REVISION,
    AUGMENTED_SCHEDULE_RULE, AUGMENTED_REPLAY_MODE, AUGMENTED_CAMERA_CONFIG,
    get_scene_sha256, file_sha256, is_valid_truth_xyz,
    evaluate_dataset, evaluate_stream, compute_aggregate,
    is_augmented_cache_valid, render_augmented_dataset, evaluate_evidence
)

P5_REVISED_PROPOSAL_PATH = Path('experiments/humanoid-pick-place/protocols/P5_REVISED_PROPOSAL.md')
P5_HISTORICAL_PROPOSAL_PATH = Path('experiments/humanoid-pick-place/protocols/P5_PROPOSAL.md')
TASK_002_EVIDENCE_PATH = Path('experiments/humanoid-pick-place/results/temporal_reacquisition_evidence_development.json')

HELD_OUT_SEEDS = set(range(840, 850))
DEVELOPMENT_SEEDS = set(range(820, 830))
PRIMARY_CANDIDATE = 'reacquisition_3frame'

GATE_MIN_COVERAGE_TARGETS = 16
GATE_TOTAL_TARGETS = 20
GATE_MAX_MEAN_ERROR_M = 0.005  # 5.0 mm gate strictly preserved
GATE_MAX_NOMINAL_ERROR_M = 0.020  # 20.0 mm
GATE_MAX_RELEASE_RETRACT_ACCEPTED = 0
GATE_MAX_CORRUPTED_TRANSPORT_ACCEPTED = 0

FUTURE_CAPTURE_COMMAND_TEMPLATE = (
    "python -m humanoid_sim.perception_evaluation audit "
    "runtime/humanoid/temporal-P5/capture 840 841 842 843 844 845 846 847 848 849 "
    "--protocol experiments/humanoid-pick-place/protocols/P5_REVISED_PROPOSAL.md"
)


def validate_seeds_guard(seeds, allow_non_development=False):
    """Validate seeds, ensuring held-out seeds 840-849 are never executed in Task 003."""
    seeds_list = list(seeds)
    if not seeds_list:
        raise ValueError("Seeds list must be non-empty")
    for s in seeds_list:
        if not isinstance(s, int) or s < 0:
            raise ValueError(f"Invalid non-negative integer seed: {s}")
        if s in HELD_OUT_SEEDS:
            raise ValueError(
                f"Execution on held-out seed {s} (range 840-849) is strictly forbidden in Task 003. "
                "These seeds are reserved for future frozen validation."
            )
        if not allow_non_development and s not in DEVELOPMENT_SEEDS:
            raise ValueError(
                f"Seed {s} is outside authorized development seeds (820-829) for executable mode."
            )
    return seeds_list


def get_git_commit_hash(cwd=None):
    """Return current git commit hash if in a git repository."""
    try:
        res = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True, text=True, check=True, cwd=cwd
        )
        return res.stdout.strip()
    except Exception:
        return 'unknown'


def build_preflight_report(source_capture_dir, augmented_capture_dir,
                           seeds=None, root_dir=None):
    """Generate structured preflight report detailing configuration, inputs, and hashes."""
    if seeds is None:
        seeds = list(range(820, 830))
    validate_seeds_guard(seeds)

    root = Path(root_dir) if root_dir else Path.cwd()
    source_capture_dir = Path(source_capture_dir)
    augmented_capture_dir = Path(augmented_capture_dir)

    # Hashes
    protocol_revised = root / P5_REVISED_PROPOSAL_PATH
    protocol_hist = root / P5_HISTORICAL_PROPOSAL_PATH
    evidence_task002 = root / TASK_002_EVIDENCE_PATH

    code_hashes = {
        'temporal_pose.py': file_sha256(root / 'humanoid_sim' / 'temporal_pose.py'),
        'temporal_reacquisition_evaluation.py': file_sha256(root / 'humanoid_sim' / 'temporal_reacquisition_evaluation.py'),
        'p5_evaluation.py': file_sha256(root / 'humanoid_sim' / 'p5_evaluation.py'),
    }

    # Input availability
    src_exists = source_capture_dir.is_dir()
    src_seeds_present = []
    if src_exists:
        for s in seeds:
            s_dir = source_capture_dir / f"seed-{s}"
            if s_dir.is_dir() and (s_dir / "private_records.json").is_file():
                src_seeds_present.append(s)

    aug_exists = augmented_capture_dir.is_dir()
    aug_cache_valid = False
    aug_manifest_present = False
    if aug_exists:
        aug_manifest_present = (augmented_capture_dir / "augmented_manifest.json").is_file()
        aug_cache_valid = is_augmented_cache_valid(source_capture_dir, augmented_capture_dir, seeds)

    report = {
        'status': 'development_preparation',
        'fresh_validation_executed': False,
        'held_out_seeds_touched': False,
        'held_out_seeds_reserved': sorted(list(HELD_OUT_SEEDS)),
        'executable_development_seeds': seeds,
        'future_capture_command': FUTURE_CAPTURE_COMMAND_TEMPLATE,
        'git_commit': get_git_commit_hash(cwd=str(root)),
        'provenance_hashes': {
            'scene_sha256': get_scene_sha256(),
            'protocol_revised_sha256': file_sha256(protocol_revised),
            'protocol_historical_sha256': file_sha256(protocol_hist),
            'code_sha256': code_hashes,
        },
        'candidate_specification': {
            'primary': {
                'name': PRIMARY_CANDIDATE,
                'class': 'TemporalThreeFrameReacquisitionPose',
                'schedule': 'augmented_stream (7 stages with lowering midpoint)',
                'window_rule': 'Requires 3 frames after reacquisition seed; minimum hand baseline 80 mm',
            },
            'prespecified_comparators': [
                {
                    'name': 'reacquisition_2frame',
                    'class': 'TemporalReacquisitionPose(min_reacquisition_frames=2)',
                    'schedule': 'both original and augmented streams',
                },
                {
                    'name': 'baseline_p4',
                    'class': 'TemporalPose(reacquisition=False)',
                    'schedule': 'both original and augmented streams',
                },
            ],
            'evaluation_rule': 'All conditions and comparators prespecified; no winner selection after scoring',
        },
        'schedule_specification': {
            'original': {
                'stages': EXPECTED_STAGES,
                'stage_count': len(EXPECTED_STAGES),
                'nominal_post_warmup_targets': sorted(list(NOMINAL_POST_WARMUP_STAGES)),
            },
            'augmented': {
                'stages': AUGMENTED_STAGES,
                'stage_count': len(AUGMENTED_STAGES),
                'midpoint_rule': AUGMENTED_SCHEDULE_RULE,
                'replay_mode': AUGMENTED_REPLAY_MODE,
                'camera_config': AUGMENTED_CAMERA_CONFIG,
            },
        },
        'grid_configuration': {
            'variants': EXPECTED_VARIANTS,
            'expected_original_responses_per_candidate_10seeds': 180,
            'expected_augmented_responses_per_candidate_10seeds': 210,
            'total_expected_responses_3_candidates_10seeds': 1170,
            'nominal_post_warmup_target_denominator_10seeds': GATE_TOTAL_TARGETS,
            'midpoint_denominator_rule': 'Extra midpoint responses never enlarge original-target denominator',
        },
        'gates_specification': {
            'gate_1_nominal_coverage': f">={GATE_MIN_COVERAGE_TARGETS}/{GATE_TOTAL_TARGETS} accepted original post-warmup targets",
            'gate_2_nominal_accuracy': f"<={GATE_MAX_MEAN_ERROR_M*1000:.1f} mm mean 3D center error over accepted original targets",
            'gate_3_nominal_max_error': f"<={GATE_MAX_NOMINAL_ERROR_M*1000:.1f} mm max error across all accepted nominal stages (including midpoint)",
            'gate_4_relationship_loss_safety': "0 accepted on release or retract",
            'gate_5_disruption_robustness': "0 accepted on corrupted transport frames (black, frozen RGB)",
            'completeness_requirement': "Missing stages/truth, errors, or unscored acceptances make evidence incomplete; incomplete is never a pass",
        },
        'input_availability': {
            'source_capture_dir': str(source_capture_dir),
            'source_exists': src_exists,
            'source_seeds_present': src_seeds_present,
            'augmented_capture_dir': str(augmented_capture_dir),
            'augmented_exists': aug_exists,
            'augmented_manifest_present': aug_manifest_present,
            'augmented_cache_valid': aug_cache_valid,
            'accepted_task_002_evidence_file': str(evidence_task002),
            'accepted_task_002_evidence_present': evidence_task002.is_file(),
            'accepted_task_002_evidence_sha256': file_sha256(evidence_task002),
        },
    }
    return report


def compute_gate_report(evidence_or_results, candidate_name=PRIMARY_CANDIDATE,
                        is_rescore=False, provenance_notes=None):
    """Compute structured gate report with strict evaluation of all five P5 continuation gates."""
    # Extract augmented candidate aggregate and records
    if 'augmented_stream' in evidence_or_results:
        aug_stream = evidence_or_results['augmented_stream']
        overall_status = evidence_or_results.get('status', 'complete')
        seeds = evidence_or_results.get('seeds', [])
    else:
        aug_stream = evidence_or_results
        overall_status = aug_stream.get('status', 'complete')
        seeds = aug_stream.get('seeds', [])

    candidates_dict = aug_stream.get('candidates', {})
    if candidate_name not in candidates_dict:
        raise ValueError(f"Candidate '{candidate_name}' not found in results. Available: {list(candidates_dict.keys())}")

    candidate_data = candidates_dict[candidate_name]
    aggregate = candidate_data.get('aggregate', {})
    records = candidate_data.get('records', [])

    nominal_agg = aggregate.get('original', {})
    black_agg = aggregate.get('black_transport', {})
    frozen_agg = aggregate.get('frozen_transport_rgb', {})

    num_seeds = len(seeds)
    is_full_10_seeds = (num_seeds == 10)
    is_incomplete = (overall_status == 'incomplete') or any(
        agg.get('missing_responses', 0) > 0 or agg.get('missing_or_invalid_truth', 0) > 0 or agg.get('unscored_accepted', 0) > 0
        for agg in [nominal_agg, black_agg, frozen_agg] if agg
    )

    # Disaggregate midpoint from original targets in records
    mid_records = [r for r in records if r.get('variant') == 'original' and r.get('stage') == 'lower_mid']
    mid_accepted = [r for r in mid_records if r.get('estimate') and r['estimate'].get('detected')]
    mid_scored = [r for r in mid_accepted if r.get('error_3d_m') is not None]
    mid_errors = [r['error_3d_m'] for r in mid_scored]

    mid_mean_error_m = float(np.mean(mid_errors)) if mid_errors else None
    mid_max_error_m = max(mid_errors) if mid_errors else None

    # Corrupted transport acceptances
    corrupted_transport_accepted = 0
    for r in records:
        if r.get('stage') == 'transport' and r.get('variant') in ('black_transport', 'frozen_transport_rgb'):
            if r.get('estimate') and r['estimate'].get('detected'):
                corrupted_transport_accepted += 1

    # Gate 1: Nominal Post-Warmup Coverage
    pw_accepted = nominal_agg.get('post_warmup_accepted', 0)
    pw_targets = nominal_agg.get('post_warmup_targets', num_seeds * 2)
    pw_scored = nominal_agg.get('post_warmup_scored', 0)
    pw_unscored = nominal_agg.get('unscored_accepted', 0)

    if not is_full_10_seeds:
        gate_1_status = 'not_applicable'
        gate_1_reason = f"Subset dry run ({num_seeds} seeds; 10 seeds required for formal gate)"
    elif is_incomplete:
        gate_1_status = 'incomplete'
        gate_1_reason = f"Incomplete evidence: {nominal_agg.get('missing_responses', 0)} missing, {pw_unscored} unscored"
    elif pw_accepted >= GATE_MIN_COVERAGE_TARGETS:
        gate_1_status = 'pass'
        gate_1_reason = f"Accepted {pw_accepted}/{pw_targets} post-warmup targets (>={GATE_MIN_COVERAGE_TARGETS} required)"
    else:
        gate_1_status = 'fail'
        gate_1_reason = f"Accepted {pw_accepted}/{pw_targets} post-warmup targets (<{GATE_MIN_COVERAGE_TARGETS} required)"

    # Gate 2: Nominal Post-Warmup Accuracy (Mean Error over Accepted Original Targets)
    pw_mean_m = nominal_agg.get('post_warmup_mean_error_m')
    pw_mean_mm = (pw_mean_m * 1000.0) if pw_mean_m is not None else None

    if not is_full_10_seeds:
        gate_2_status = 'not_applicable'
        gate_2_reason = f"Subset dry run ({num_seeds} seeds; 10 seeds required for formal gate)"
    elif is_incomplete:
        gate_2_status = 'incomplete'
        gate_2_reason = "Incomplete evidence; cannot score accuracy gate"
    elif pw_mean_m is None or pw_accepted == 0:
        gate_2_status = 'fail'
        gate_2_reason = "Zero accepted post-warmup targets"
    elif pw_mean_m <= GATE_MAX_MEAN_ERROR_M:
        gate_2_status = 'pass'
        gate_2_reason = f"Accepted original-target mean {pw_mean_mm:.4f} mm <= {GATE_MAX_MEAN_ERROR_M*1000:.1f} mm threshold"
    else:
        gate_2_status = 'fail'
        gate_2_reason = (
            f"Accepted original-target mean {pw_mean_mm:.4f} mm exceeds "
            f"{GATE_MAX_MEAN_ERROR_M*1000:.1f} mm threshold (FAIL - gate strictly preserved)"
        )

    # Gate 3: Maximum Error Across Accepted Nominal Stages (including midpoint)
    nom_max_m = nominal_agg.get('accepted_max_error_m')
    nom_max_mm = (nom_max_m * 1000.0) if nom_max_m is not None else None

    if is_incomplete:
        gate_3_status = 'incomplete'
        gate_3_reason = "Incomplete evidence; cannot certify maximum error gate"
    elif nom_max_m is None or nominal_agg.get('accepted', 0) == 0:
        gate_3_status = 'fail'
        gate_3_reason = "Zero accepted nominal responses"
    elif nom_max_m <= GATE_MAX_NOMINAL_ERROR_M:
        gate_3_status = 'pass'
        mid_desc = f"{mid_max_error_m*1000.0:.4f} mm" if mid_max_error_m is not None else "none"
        gate_3_reason = (
            f"Maximum error {nom_max_mm:.4f} mm <= {GATE_MAX_NOMINAL_ERROR_M*1000:.1f} mm "
            f"(midpoint max error: {mid_desc})"
        )
    else:
        gate_3_status = 'fail'
        gate_3_reason = f"Maximum error {nom_max_mm:.4f} mm > {GATE_MAX_NOMINAL_ERROR_M*1000:.1f} mm threshold"

    # Gate 4: Relationship Loss Containment (Release / Retract)
    rel_ret_accepted = nominal_agg.get('release_or_retract_accepted', 0)
    rel_ret_denom = num_seeds * 2

    if is_incomplete:
        gate_4_status = 'incomplete'
        gate_4_reason = "Incomplete evidence; release/retract containment unverified"
    elif rel_ret_accepted == GATE_MAX_RELEASE_RETRACT_ACCEPTED:
        gate_4_status = 'pass'
        gate_4_reason = f"0/{rel_ret_denom} positions emitted on release or retract endpoints"
    else:
        gate_4_status = 'fail'
        gate_4_reason = f"{rel_ret_accepted}/{rel_ret_denom} positions emitted on release or retract endpoints (FAIL)"

    # Gate 5: Sensor Disruption Robustness (Corrupted Transport)
    black_acc = black_agg.get('accepted', 0)
    frozen_acc = frozen_agg.get('accepted', 0)

    if is_incomplete:
        gate_5_status = 'incomplete'
        gate_5_reason = "Incomplete evidence; sensor disruption containment unverified"
    elif corrupted_transport_accepted == GATE_MAX_CORRUPTED_TRANSPORT_ACCEPTED:
        gate_5_status = 'pass'
        gate_5_reason = (
            f"0/{num_seeds*2} positions emitted on corrupted transport frames "
            f"(black_transport: {black_acc} total, frozen_transport_rgb: {frozen_acc} total)"
        )
    else:
        gate_5_status = 'fail'
        gate_5_reason = f"{corrupted_transport_accepted} positions emitted on corrupted transport frames (FAIL)"

    # Overall outcome
    all_gates = [gate_1_status, gate_2_status, gate_3_status, gate_4_status, gate_5_status]
    if any(g == 'incomplete' for g in all_gates) or is_incomplete:
        overall_outcome = 'INCOMPLETE'
        overall_reason = "Evidence is incomplete; incomplete is never a pass."
    elif any(g == 'fail' for g in all_gates):
        overall_outcome = 'FAIL'
        failed_reasons = []
        if gate_1_status == 'fail':
            failed_reasons.append("coverage (<16/20)")
        if gate_2_status == 'fail':
            if pw_mean_mm is not None:
                failed_reasons.append(f"accuracy ({pw_mean_mm:.4f} mm > 5.0 mm)")
            else:
                failed_reasons.append("accuracy (zero accepted post-warmup targets)")
        if gate_3_status == 'fail':
            if nom_max_mm is not None:
                failed_reasons.append(f"max error ({nom_max_mm:.4f} mm > 20 mm)")
            else:
                failed_reasons.append("max error (zero accepted nominal responses)")
        if gate_4_status == 'fail':
            failed_reasons.append("release/retract emission")
        if gate_5_status == 'fail':
            failed_reasons.append("corrupted transport emission")
        overall_reason = f"Gate criteria failed on: {', '.join(failed_reasons)}."
    elif any(g == 'not_applicable' for g in all_gates):
        overall_outcome = 'NOT_APPLICABLE_SUBSET'
        overall_reason = f"Subset dry run on {num_seeds} seeds; formal gate evaluation requires all 10 seeds."
    else:
        overall_outcome = 'PASS'
        overall_reason = "All 5 continuation gates passed."

    report = {
        'report_type': 'gate_report_rescore' if is_rescore else 'gate_report_development',
        'is_rescore': is_rescore,
        'candidate': candidate_name,
        'schedule': 'augmented_stream',
        'seeds': seeds,
        'seed_count': num_seeds,
        'evaluation_status': overall_status,
        'is_complete': not is_incomplete,
        'provenance_notes': provenance_notes or ('Task 002 development evidence rescore' if is_rescore else 'Development dry run'),
        'gates': {
            'gate_1_coverage': {
                'description': f'>={GATE_MIN_COVERAGE_TARGETS}/{GATE_TOTAL_TARGETS} nominal post-warmup targets accepted',
                'status': gate_1_status,
                'numerator': pw_accepted,
                'denominator': pw_targets,
                'scored_count': pw_scored,
                'unscored_count': pw_unscored,
                'reason': gate_1_reason,
            },
            'gate_2_accuracy': {
                'description': f'<={GATE_MAX_MEAN_ERROR_M*1000:.1f} mm mean 3D center error over accepted original targets',
                'status': gate_2_status,
                'metric_value_m': pw_mean_m,
                'metric_value_mm': pw_mean_mm,
                'threshold_mm': GATE_MAX_MEAN_ERROR_M * 1000.0,
                'denominator_accepted_original_targets': pw_accepted,
                'reason': gate_2_reason,
            },
            'gate_3_nominal_max_error': {
                'description': f'<={GATE_MAX_NOMINAL_ERROR_M*1000:.1f} mm maximum center error across all accepted nominal stages',
                'status': gate_3_status,
                'metric_value_m': nom_max_m,
                'metric_value_mm': nom_max_mm,
                'threshold_mm': GATE_MAX_NOMINAL_ERROR_M * 1000.0,
                'midpoint_max_error_mm': (mid_max_error_m * 1000.0) if mid_max_error_m is not None else None,
                'reason': gate_3_reason,
            },
            'gate_4_relationship_loss_safety': {
                'description': 'Zero accepted poses on release or retract endpoints (0/20)',
                'status': gate_4_status,
                'accepted_count': rel_ret_accepted,
                'denominator': rel_ret_denom,
                'reason': gate_4_reason,
            },
            'gate_5_disruption_robustness': {
                'description': 'Zero accepted poses on corrupted transport frames',
                'status': gate_5_status,
                'corrupted_transport_accepted': corrupted_transport_accepted,
                'black_transport_total_accepted': black_acc,
                'frozen_transport_rgb_total_accepted': frozen_acc,
                'reason': gate_5_reason,
            },
        },
        'descriptive_metrics': {
            'midpoint_metrics': {
                'midpoint_stage': 'lower_mid',
                'midpoint_expected': num_seeds,
                'midpoint_accepted': len(mid_accepted),
                'midpoint_scored': len(mid_scored),
                'midpoint_mean_error_mm': (mid_mean_error_m * 1000.0) if mid_mean_error_m is not None else None,
                'midpoint_max_error_mm': (mid_max_error_m * 1000.0) if mid_max_error_m is not None else None,
                'denominator_separation_note': 'Midpoint estimates are reported separately and never enlarge or dilute the 20-target original post-warmup denominator.',
            },
            'all_accepted_metrics': {
                'all_accepted_count': nominal_agg.get('accepted', 0),
                'all_accepted_mean_error_mm': (nominal_agg.get('accepted_mean_error_m') * 1000.0) if nominal_agg.get('accepted_mean_error_m') is not None else None,
                'all_accepted_max_error_mm': nom_max_mm,
            },
            'refusals': nominal_agg.get('refusals', {}),
        },
        'overall_outcome': overall_outcome,
        'overall_reason': overall_reason,
    }
    return report


def print_gate_report_summary(report):
    """Print readable summary of the structured gate report."""
    print("\n" + "=" * 70)
    print(f"P5 GATE EVALUATION REPORT: {report['candidate']} ({report['report_type']})")
    print(f"Seeds: {report['seeds']} (Count: {report['seed_count']})")
    print(f"Status: {report['evaluation_status']} | Complete: {report['is_complete']}")
    print(f"Provenance: {report['provenance_notes']}")
    print("-" * 70)
    for k, g in report['gates'].items():
        tag = f"[{g['status'].upper()}]"
        print(f"  {tag:<16} {k}: {g['reason']}")
    print("-" * 70)
    print(f"OVERALL OUTCOME: [{report['overall_outcome']}]")
    print(f"Reason: {report['overall_reason']}")
    desc = report['descriptive_metrics']
    mid = desc['midpoint_metrics']
    all_m = desc['all_accepted_metrics']
    print("-" * 70)
    mid_mean_str = f"{mid['midpoint_mean_error_mm']:.4f} mm" if mid.get('midpoint_mean_error_mm') is not None else "N/A"
    mid_max_str = f"{mid['midpoint_max_error_mm']:.4f} mm" if mid.get('midpoint_max_error_mm') is not None else "N/A"
    all_mean_str = f"{all_m['all_accepted_mean_error_mm']:.4f} mm" if all_m.get('all_accepted_mean_error_mm') is not None else "N/A"
    all_max_str = f"{all_m['all_accepted_max_error_mm']:.4f} mm" if all_m.get('all_accepted_max_error_mm') is not None else "N/A"
    print(f"Midpoint (lower_mid): accepted {mid['midpoint_accepted']}/{mid['midpoint_expected']}; mean: {mid_mean_str}; max: {mid_max_str}")
    print(f"All accepted (nom): count {all_m['all_accepted_count']}; mean: {all_mean_str}; max: {all_max_str}")
    print("=" * 70 + "\n")


def run_preflight_command(args):
    """Execute preflight check and write report."""
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_preflight_report(
        source_capture_dir=args.capture_dir,
        augmented_capture_dir=args.augmented_dir,
        seeds=args.seeds,
        root_dir=args.root_dir
    )
    report_file = out_dir / "preflight_report.json"
    write_json(report_file, report)
    print(f"Preflight report written to: {report_file}")
    print(f"Status: {report['status']} | Fresh validation executed: {report['fresh_validation_executed']}")
    print(f"Git commit: {report['git_commit']}")
    print(f"Scene SHA-256: {report['provenance_hashes']['scene_sha256']}")
    print(f"Augmented cache valid: {report['input_availability']['augmented_cache_valid']}")
    return report


def run_rescore_command(args):
    """Rescore an existing evidence JSON artifact and generate structured gate report."""
    evidence_path = Path(args.rescore)
    if not evidence_path.is_file():
        raise FileNotFoundError(f"Evidence file not found: {evidence_path}")

    evidence = json.loads(evidence_path.read_text())
    report = compute_gate_report(
        evidence,
        candidate_name=args.candidate,
        is_rescore=True,
        provenance_notes=f"Artifact rescore of: {evidence_path.resolve()}"
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_name = getattr(args, 'report_name', None) or "gate_report_rescore.json"
    report_file = out_dir / report_name
    write_json(report_file, report)
    print_gate_report_summary(report)
    print(f"Gate report written to: {report_file}")
    return report


def run_dry_run_command(args):
    """Execute development dry run on existing development inputs."""
    validate_seeds_guard(args.seeds)
    source_capture_dir = Path(args.capture_dir)
    augmented_capture_dir = Path(args.augmented_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running development dry run on seeds {args.seeds}...")
    evidence = evaluate_evidence(
        source_capture_dir=source_capture_dir,
        augmented_capture_dir=augmented_capture_dir,
        seeds=args.seeds,
        output_file=out_dir / "p5_development_evidence.json",
        render_if_missing=False  # Reuses validated cache read-only
    )

    report = compute_gate_report(
        evidence,
        candidate_name=args.candidate,
        is_rescore=False,
        provenance_notes=f"Development dry run on seeds {args.seeds}; cache read-only from {augmented_capture_dir.resolve()}"
    )

    report_file = out_dir / "gate_report_development.json"
    write_json(report_file, report)
    print_gate_report_summary(report)
    print(f"Development evidence written to: {out_dir / 'p5_development_evidence.json'}")
    print(f"Development gate report written to: {report_file}")

    # Write task manifest
    manifest = {
        'manifest_version': 1,
        'generator': 'humanoid_sim.p5_evaluation.dry_run',
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'git_commit': get_git_commit_hash(),
        'seeds': args.seeds,
        'candidate': args.candidate,
        'source_capture_dir': str(source_capture_dir.resolve()),
        'augmented_capture_dir': str(augmented_capture_dir.resolve()),
        'artifacts': {
            'evidence': str((out_dir / "p5_development_evidence.json").resolve()),
            'gate_report': str(report_file.resolve()),
        },
        'overall_outcome': report['overall_outcome'],
    }
    write_json(out_dir / "manifest.json", manifest)
    print(f"Manifest written to: {out_dir / 'manifest.json'}")
    return report


def main():
    default_capture_dir = Path('runtime/humanoid/temporal-P4/capture')
    if not default_capture_dir.is_dir():
        default_capture_dir = Path('/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture')

    default_augmented_dir = Path('runtime/humanoid/temporal-P4-augmented/capture')
    if not default_augmented_dir.is_dir():
        default_augmented_dir = Path('/private/tmp/mujoco-llms-agy-002/runtime/humanoid/temporal-P4-augmented/capture')

    default_output_dir = Path('experiments/humanoid-pick-place/results/p5_preparation')

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true', default=False,
                        help='Run preflight checks and output preflight report')
    parser.add_argument('--rescore', type=Path, default=None,
                        help='Rescore an existing evidence JSON artifact')
    parser.add_argument('--report-name', type=str, default='gate_report_rescore.json',
                        help='Report filename when running rescore')
    parser.add_argument('--dry-run', action='store_true', default=False,
                        help='Run development dry run on existing development inputs')
    parser.add_argument('--candidate', type=str, default=PRIMARY_CANDIDATE,
                        choices=['reacquisition_3frame', 'reacquisition_2frame', 'baseline_p4'],
                        help='Candidate estimator to evaluate against gates')
    parser.add_argument('--capture-dir', type=Path, default=default_capture_dir,
                        help='Path to source P4 capture directory')
    parser.add_argument('--augmented-dir', type=Path, default=default_augmented_dir,
                        help='Path to augmented capture directory')
    parser.add_argument('--output-dir', type=Path, default=default_output_dir,
                        help='Output directory for P5 preparation artifacts')
    parser.add_argument('--root-dir', type=Path, default=None,
                        help='Root directory of the repository')
    parser.add_argument('--start-seed', type=int, default=820,
                        help='Start seed (default: 820)')
    parser.add_argument('--count', type=int, default=10,
                        help='Seed count (default: 10)')
    parser.add_argument('--seeds', type=int, nargs='+', default=None,
                        help='Explicit seed list (e.g. --seeds 820 821)')
    parser.add_argument('--fresh-capture', action='store_true', default=False,
                        help='Attempt fresh capture (FORBIDDEN in Task 003; documents command)')

    args = parser.parse_args()

    if args.fresh_capture:
        raise RuntimeError(
            "Fresh capture is disabled in Task 003. Future fresh execution under a separately reviewed "
            f"and frozen P5 protocol must be authorized and run via:\n  {FUTURE_CAPTURE_COMMAND_TEMPLATE}"
        )

    if args.seeds is None:
        args.seeds = list(range(args.start_seed, args.start_seed + args.count))

    # Guard seeds against held-out set
    validate_seeds_guard(args.seeds)

    if args.preflight:
        run_preflight_command(args)
    elif args.rescore:
        run_rescore_command(args)
    elif args.dry_run:
        run_dry_run_command(args)
    else:
        # Default behavior: run preflight and print usage
        print("No mode specified (--preflight, --rescore, or --dry-run). Running preflight by default:")
        run_preflight_command(args)


if __name__ == '__main__':
    main()
