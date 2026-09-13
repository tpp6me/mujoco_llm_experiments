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

FUTURE_CAPTURE_API_SKETCH = (
    "# Future fresh execution (Python API sketch for future reviewed task; DO NOT RUN IN TASK 003):\n"
    "# from pathlib import Path\n"
    "# from humanoid_sim.perception_evaluation import audit\n"
    "# audit(\n"
    "#     output=Path('runtime/humanoid/temporal-P5/capture'),\n"
    "#     seeds=range(840, 850),\n"
    "#     protocol=Path('experiments/humanoid-pick-place/protocols/P5_REVISED_PROPOSAL.md'),\n"
    "#     protocol_id='P5_capture',\n"
    "# )"
)


def validate_seeds_guard(seeds, allow_non_development=False):
    """Validate seeds, ensuring uniqueness, integer types, and held-out protection."""
    if not isinstance(seeds, (list, tuple, set, range)):
        raise ValueError(f"Seeds must be a sequence, got {type(seeds).__name__}")
    seeds_list = list(seeds)
    if not seeds_list:
        raise ValueError("Seeds list must be non-empty")
    for s in seeds_list:
        if isinstance(s, bool) or not isinstance(s, int):
            raise ValueError(f"Seed must be an integer, got {type(s).__name__}: {s}")
        if s < 0:
            raise ValueError(f"Seed must be non-negative, got {s}")
        if s in HELD_OUT_SEEDS:
            raise ValueError(
                f"Execution on held-out seed {s} (range 840-849) is strictly forbidden in Task 003. "
                "These seeds are reserved for future frozen validation."
            )
        if not allow_non_development and s not in DEVELOPMENT_SEEDS:
            raise ValueError(
                f"Seed {s} is outside authorized development seeds (820-829) for executable/rescore mode."
            )
    if len(seeds_list) != len(set(seeds_list)):
        raise ValueError(f"Duplicate seeds are forbidden. Received: {seeds_list}")
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


def get_git_status_description(cwd=None):
    """Return git commit hash, dirty flag, and provenance note."""
    head = get_git_commit_hash(cwd=cwd)
    try:
        res = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True, text=True, check=True, cwd=cwd
        )
        is_dirty = bool(res.stdout.strip())
    except Exception:
        is_dirty = False
    return {
        'head_commit': head,
        'is_dirty': is_dirty,
        'provenance_note': (
            f"Worktree snapshot based on commit {head}"
            + (" with uncommitted task modifications" if is_dirty else " (clean working tree)")
        )
    }


def validate_evidence_structure(evidence_or_results, candidate_name=PRIMARY_CANDIDATE,
                                required_seeds=None):
    """Validate every declared condition and return the selected augmented metrics.

    A full comparison requires all three prespecified candidates on both schedules.
    Standalone augmented results remain supported for isolated gate tests/rescores.
    Malformed external evidence is returned as incomplete, never certified or raised.
    """
    try:
        if not isinstance(evidence_or_results, dict):
            return False, "Evidence must be a dictionary", None, None
        if evidence_or_results.get('status') != 'complete':
            return False, "Evidence status invalid; expected 'complete'", None, None
        seeds = validate_seeds_guard(evidence_or_results.get('seeds'))
        if required_seeds is not None and set(seeds) != set(validate_seeds_guard(required_seeds)):
            return False, "Evidence seeds do not match required seeds", None, None

        full_comparison = 'original_stream' in evidence_or_results
        if full_comparison:
            streams = [('original_stream', EXPECTED_STAGES), ('augmented_stream', AUGMENTED_STAGES)]
        elif 'augmented_stream' in evidence_or_results:
            streams = [('augmented_stream', AUGMENTED_STAGES)]
        else:
            streams = [(None, AUGMENTED_STAGES)]

        selected = None
        for stream_name, stages in streams:
            stream = evidence_or_results if stream_name is None else evidence_or_results.get(stream_name)
            if not isinstance(stream, dict) or stream.get('status') != 'complete':
                return False, f"Required stream {stream_name} is missing or incomplete", None, None
            if set(validate_seeds_guard(stream.get('seeds'))) != set(seeds):
                return False, f"Stream {stream_name} seeds disagree with the envelope", None, None
            candidates = stream.get('candidates')
            if not isinstance(candidates, dict) or candidate_name not in candidates:
                return False, f"Stream {stream_name} lacks selected candidate {candidate_name}", None, None
            names = ('baseline_p4', 'reacquisition_2frame', 'reacquisition_3frame') if full_comparison else tuple(candidates)
            for name in names:
                valid, reason, data, _ = _validate_candidate_evidence(
                    stream, candidate_name=name, required_seeds=seeds, stages=stages)
                if not valid:
                    return False, f"{stream_name or 'augmented'}/{name}: {reason}", None, None
                if stream_name != 'original_stream' and name == candidate_name:
                    selected = data
        return True, None, selected, seeds
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as error:
        return False, f"Malformed evidence: {type(error).__name__}: {error}", None, None


def _validate_candidate_evidence(evidence_or_results, candidate_name=PRIMARY_CANDIDATE,
                                 required_seeds=None, stages=AUGMENTED_STAGES):
    """Validate completeness, consistency, and record grid of evidence before gate scoring.

    Returns (is_valid: bool, error_message: str, candidate_data: dict, seeds: list).
    """
    if not isinstance(evidence_or_results, dict):
        return False, "Evidence is not a valid dictionary", None, None

    # Top-level status check: must be explicitly 'complete'
    top_status = evidence_or_results.get('status')
    if top_status != 'complete':
        return False, f"Evidence top-level status is '{top_status}', expected 'complete'", None, None

    # Comparative envelope check
    if 'original_stream' in evidence_or_results and 'augmented_stream' in evidence_or_results:
        orig_stream = evidence_or_results['original_stream']
        aug_stream = evidence_or_results['augmented_stream']
        if not isinstance(orig_stream, dict) or orig_stream.get('status') != 'complete':
            return False, f"Original stream status is '{orig_stream.get('status') if isinstance(orig_stream, dict) else None}', expected 'complete'", None, None
        if not isinstance(aug_stream, dict) or aug_stream.get('status') != 'complete':
            return False, f"Augmented stream status is '{aug_stream.get('status') if isinstance(aug_stream, dict) else None}', expected 'complete'", None, None
    elif 'augmented_stream' in evidence_or_results:
        aug_stream = evidence_or_results['augmented_stream']
        if not isinstance(aug_stream, dict) or aug_stream.get('status') != 'complete':
            return False, f"Augmented stream status is '{aug_stream.get('status') if isinstance(aug_stream, dict) else None}', expected 'complete'", None, None
    else:
        aug_stream = evidence_or_results

    # Extract and validate seeds
    seeds_raw = evidence_or_results.get('seeds') or aug_stream.get('seeds')
    if seeds_raw is None:
        return False, "Evidence missing 'seeds' declaration", None, None
    try:
        seeds = validate_seeds_guard(seeds_raw, allow_non_development=False)
    except Exception as e:
        return False, f"Seed validation failed: {e}", None, None

    if required_seeds is not None:
        try:
            req_seeds = validate_seeds_guard(required_seeds, allow_non_development=False)
        except Exception as e:
            return False, f"Required seeds invalid: {e}", None, None
        if set(seeds) != set(req_seeds):
            return False, f"Evidence seeds {seeds} do not match required seeds {req_seeds}", None, None

    # Candidate presence
    candidates = aug_stream.get('candidates')
    if not isinstance(candidates, dict) or candidate_name not in candidates:
        return False, f"Candidate '{candidate_name}' not present in augmented candidates", None, None

    candidate_data = candidates[candidate_name]
    if not isinstance(candidate_data, dict):
        return False, f"Candidate data for '{candidate_name}' is not a dict", None, None

    aggregate = candidate_data.get('aggregate')
    records = candidate_data.get('records')

    if not isinstance(aggregate, dict):
        return False, "Candidate missing 'aggregate' dictionary", None, None
    if not isinstance(records, list) or len(records) == 0:
        return False, "Candidate 'records' list is empty or invalid; cannot verify evidence", None, None

    # Validate aggregate contains all required variants
    for var in EXPECTED_VARIANTS:
        if var not in aggregate:
            return False, f"Candidate aggregate missing required disruption variant: '{var}'", None, None
        v_agg = aggregate[var]
        if not isinstance(v_agg, dict):
            return False, f"Candidate aggregate for variant '{var}' is not a dict", None, None
        if v_agg.get('missing_responses', 0) > 0:
            return False, f"Variant '{var}' reports {v_agg.get('missing_responses')} missing responses", None, None
        if v_agg.get('missing_or_invalid_truth', 0) > 0:
            return False, f"Variant '{var}' reports {v_agg.get('missing_or_invalid_truth')} missing/invalid truth entries", None, None
        if v_agg.get('unscored_accepted', 0) > 0:
            return False, f"Variant '{var}' reports {v_agg.get('unscored_accepted')} unscored accepted poses", None, None

    # Validate record grid completeness and uniqueness
    expected_total_records = len(seeds) * len(stages) * len(EXPECTED_VARIANTS)
    if len(records) != expected_total_records:
        return False, (
            f"Record count {len(records)} does not match expected grid count {expected_total_records} "
            f"({len(seeds)} seeds x {len(stages)} stages x {len(EXPECTED_VARIANTS)} variants)"
        ), None, None

    seen_grid = set()
    for idx, r in enumerate(records):
        if not isinstance(r, dict):
            return False, f"Record index {idx} is not a dict", None, None
        r_seed = r.get('seed')
        r_stage = r.get('stage')
        r_var = r.get('variant')

        if r_seed not in seeds:
            return False, f"Record index {idx} has unexpected or out-of-scope seed: {r_seed}", None, None
        if r_stage not in stages:
            return False, f"Record index {idx} has unexpected stage: {r_stage}", None, None
        if r_var not in EXPECTED_VARIANTS:
            return False, f"Record index {idx} has unexpected variant: {r_var}", None, None

        grid_key = (r_seed, r_stage, r_var)
        if grid_key in seen_grid:
            return False, f"Duplicate grid entry in records: {grid_key}", None, None
        seen_grid.add(grid_key)

        r_status = r.get('status')
        if r_status != 'evaluated':
            return False, f"Record {grid_key} has non-evaluated status '{r_status}': {r.get('error_message')}", None, None

        # Inspect ground truth
        truth_xyz = r.get('private_true_xyz_m')
        if not is_valid_truth_xyz(truth_xyz):
            return False, f"Record {grid_key} has invalid or missing ground truth: {truth_xyz}", None, None

        # Inspect estimate and scoring
        estimate = r.get('estimate')
        if not isinstance(estimate, dict):
            return False, f"Record {grid_key} has invalid estimate dict", None, None

        if not isinstance(estimate.get('detected'), bool):
            return False, f"Record {grid_key} detected flag must be boolean", None, None
        err = r.get('error_3d_m')
        if estimate['detected']:
            if (isinstance(err, bool) or not isinstance(err, (int, float))
                    or not np.isfinite(err) or err < 0):
                return False, f"Record {grid_key} has invalid or non-finite error_3d_m (must be non-negative): {err}", None, None
        elif err is not None:
            return False, f"Refused record {grid_key} must not have a scored error", None, None
        scoring_status = r.get('scoring_status')
        if scoring_status is not None and scoring_status != ('scored' if estimate['detected'] else 'not_detected'):
            return False, f"Record {grid_key} has inconsistent scoring_status: {scoring_status}", None, None

    # Check that all expected grid combinations were seen
    for s in seeds:
        for st in stages:
            for v in EXPECTED_VARIANTS:
                if (s, st, v) not in seen_grid:
                    return False, f"Missing expected grid entry: {(s, st, v)}", None, None

    # Recompute aggregate from validated records and check agreement with candidate aggregate
    try:
        recomputed_agg = compute_aggregate(records, seeds, stages=stages, post_warmup_stages=NOMINAL_POST_WARMUP_STAGES)
    except Exception as e:
        return False, f"Failed to recompute aggregate from records: {e}", None, None

    for v in EXPECTED_VARIANTS:
        supplied, recomputed = aggregate[v], recomputed_agg[v]
        count_fields = (
            'expected_responses', 'evaluated_responses', 'missing_responses',
            'accepted', 'scored_responses', 'unscored_accepted',
            'missing_or_invalid_truth', 'post_warmup_accepted',
            'post_warmup_targets', 'post_warmup_scored', 'release_or_retract_accepted',
        )
        for field in count_fields:
            value = supplied.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value != recomputed[field]:
                return False, f"Summary aggregate {v}.{field} disagrees with records", None, None
        for field in ('post_warmup_mean_error_m', 'accepted_max_error_m'):
            value, actual = supplied.get(field), recomputed[field]
            if actual is None:
                agrees = value is None
            else:
                agrees = (not isinstance(value, bool) and isinstance(value, (int, float))
                           and np.isfinite(value)
                           and np.isclose(value, actual, rtol=1e-10, atol=1e-12))
            if not agrees:
                return False, f"Summary aggregate {v}.{field} disagrees with records", None, None

    # Gates always use per-record metrics, including at threshold boundaries.
    validated = {**candidate_data, 'aggregate': recomputed_agg}
    return True, None, validated, seeds


def build_preflight_report(source_capture_dir, augmented_capture_dir,
                           seeds=None, root_dir=None):
    """Generate structured preflight report detailing configuration, inputs, dependencies, and hashes."""
    if seeds is None:
        seeds = list(range(820, 830))
    validate_seeds_guard(seeds)

    root = Path(root_dir) if root_dir else Path.cwd()
    source_capture_dir = Path(source_capture_dir)
    augmented_capture_dir = Path(augmented_capture_dir)

    protocol_revised = root / P5_REVISED_PROPOSAL_PATH
    protocol_hist = root / P5_HISTORICAL_PROPOSAL_PATH
    evidence_task002 = root / TASK_002_EVIDENCE_PATH
    req_lock = root / 'requirements-lock.txt'
    req_txt = root / 'requirements.txt'

    code_hashes = {
        'temporal_pose.py': file_sha256(root / 'humanoid_sim' / 'temporal_pose.py'),
        'temporal_reacquisition_evaluation.py': file_sha256(root / 'humanoid_sim' / 'temporal_reacquisition_evaluation.py'),
        'p5_evaluation.py': file_sha256(root / 'humanoid_sim' / 'p5_evaluation.py'),
    }

    dependency_hashes = {
        'requirements_lock_sha256': file_sha256(req_lock),
        'requirements_txt_sha256': file_sha256(req_txt),
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

    git_status = get_git_status_description(cwd=str(root))

    report = {
        'status': 'development_preparation',
        'fresh_validation_executed': False,
        'held_out_seeds_touched': False,
        'held_out_seeds_reserved': sorted(list(HELD_OUT_SEEDS)),
        'executable_development_seeds': seeds,
        'future_capture_api_sketch': FUTURE_CAPTURE_API_SKETCH,
        'git_provenance': git_status,
        'provenance_hashes': {
            'scene_sha256': get_scene_sha256(),
            'protocol_revised_sha256': file_sha256(protocol_revised),
            'protocol_historical_sha256': file_sha256(protocol_hist),
            'code_sha256': code_hashes,
            'dependency_hashes': dependency_hashes,
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
                        is_rescore=False, provenance_notes=None,
                        required_seeds=None, evidence_path=None, root_dir=None):
    """Compute structured gate report with strict validation of grid evidence and continuation gates."""
    root = Path(root_dir) if root_dir else Path.cwd()
    git_status = get_git_status_description(cwd=str(root))

    # Validate evidence structure before gate scoring
    is_valid, val_err, candidate_data, seeds = validate_evidence_structure(
        evidence_or_results, candidate_name=candidate_name, required_seeds=required_seeds
    )

    source_snapshot = {
        'git_head': git_status['head_commit'],
        'git_dirty': git_status['is_dirty'],
        'provenance_note': git_status['provenance_note'],
        'p5_evaluation_sha256': file_sha256(root / 'humanoid_sim' / 'p5_evaluation.py'),
        'temporal_reacquisition_evaluation_sha256': file_sha256(root / 'humanoid_sim' / 'temporal_reacquisition_evaluation.py'),
        'temporal_pose_sha256': file_sha256(root / 'humanoid_sim' / 'temporal_pose.py'),
        'scene_sha256': get_scene_sha256(),
        'protocol_revised_sha256': file_sha256(root / P5_REVISED_PROPOSAL_PATH),
        'requirements_lock_sha256': file_sha256(root / 'requirements-lock.txt'),
    }

    if not is_valid:
        # Build an actionable INCOMPLETE report without uncaught exceptions or PASS
        reported_seeds = seeds if seeds is not None else (
            evidence_or_results.get('seeds') if isinstance(evidence_or_results, dict) else []
        )
        if not isinstance(reported_seeds, (list, tuple, set, range)):
            reported_seeds = []
        return {
            'report_type': 'gate_report_rescore' if is_rescore else 'gate_report_development',
            'is_rescore': is_rescore,
            'candidate': candidate_name,
            'schedule': 'augmented_stream',
            'seeds': reported_seeds,
            'seed_count': len(reported_seeds) if reported_seeds else 0,
            'evaluation_status': 'incomplete',
            'is_complete': False,
            'validation_error': val_err,
            'provenance_notes': provenance_notes or ('Task 002 development evidence rescore' if is_rescore else 'Development dry run'),
            'evidence_path': str(evidence_path) if evidence_path else None,
            'evidence_sha256': file_sha256(evidence_path) if evidence_path else None,
            'source_code_snapshot': source_snapshot,
            'gates': {
                'gate_1_coverage': {
                    'description': f'>={GATE_MIN_COVERAGE_TARGETS}/{GATE_TOTAL_TARGETS} nominal post-warmup targets accepted',
                    'status': 'incomplete',
                    'reason': f"Incomplete evidence: {val_err}",
                },
                'gate_2_accuracy': {
                    'description': f'<={GATE_MAX_MEAN_ERROR_M*1000:.1f} mm mean 3D center error over accepted original targets',
                    'status': 'incomplete',
                    'reason': f"Incomplete evidence: {val_err}",
                },
                'gate_3_nominal_max_error': {
                    'description': f'<={GATE_MAX_NOMINAL_ERROR_M*1000:.1f} mm maximum center error across all accepted nominal stages',
                    'status': 'incomplete',
                    'reason': f"Incomplete evidence: {val_err}",
                },
                'gate_4_relationship_loss_safety': {
                    'description': 'Zero accepted poses on release or retract endpoints (0/20)',
                    'status': 'incomplete',
                    'reason': f"Incomplete evidence: {val_err}",
                },
                'gate_5_disruption_robustness': {
                    'description': 'Zero accepted poses on corrupted transport frames',
                    'status': 'incomplete',
                    'reason': f"Incomplete evidence: {val_err}",
                },
            },
            'descriptive_metrics': {},
            'overall_outcome': 'INCOMPLETE',
            'overall_reason': f"Evidence is incomplete or inconsistent: {val_err}",
        }

    aggregate = candidate_data['aggregate']
    records = candidate_data['records']

    nominal_agg = aggregate['original']
    black_agg = aggregate['black_transport']
    frozen_agg = aggregate['frozen_transport_rgb']

    num_seeds = len(seeds)
    is_full_10_seeds = (set(seeds) == DEVELOPMENT_SEEDS)

    # Disaggregate midpoint from original targets in records
    mid_records = [r for r in records if r.get('variant') == 'original' and r.get('stage') == 'lower_mid']
    mid_accepted = [r for r in mid_records if r.get('estimate', {}).get('detected')]
    mid_scored = [r for r in mid_accepted if r.get('error_3d_m') is not None]
    mid_errors = [r['error_3d_m'] for r in mid_scored]

    mid_mean_error_m = float(np.mean(mid_errors)) if mid_errors else None
    mid_max_error_m = max(mid_errors) if mid_errors else None

    # Corrupted transport acceptances
    corrupted_transport_accepted = sum(
        1 for r in records
        if r.get('stage') == 'transport'
        and r.get('variant') in ('black_transport', 'frozen_transport_rgb')
        and r.get('estimate', {}).get('detected')
    )

    # Gate 1: Nominal Post-Warmup Coverage
    pw_accepted = nominal_agg.get('post_warmup_accepted', 0)
    pw_targets = nominal_agg.get('post_warmup_targets', num_seeds * 2)
    pw_scored = nominal_agg.get('post_warmup_scored', 0)
    pw_unscored = nominal_agg.get('unscored_accepted', 0)

    if not is_full_10_seeds:
        gate_1_status = 'not_applicable'
        gate_1_reason = f"Subset dry run ({num_seeds} seeds; full screen requires exactly 820-829)"
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
        gate_2_reason = f"Subset dry run ({num_seeds} seeds; full screen requires exactly 820-829)"
    elif pw_mean_m is None or pw_accepted == 0:
        gate_2_status = 'fail'
        gate_2_reason = "Zero accepted post-warmup targets (accuracy cannot be verified)"
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

    if nom_max_m is None or nominal_agg.get('accepted', 0) == 0:
        gate_3_status = 'fail'
        gate_3_reason = "Zero accepted nominal responses (containment cannot be verified)"
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

    if rel_ret_accepted == GATE_MAX_RELEASE_RETRACT_ACCEPTED:
        gate_4_status = 'pass'
        gate_4_reason = f"0/{rel_ret_denom} positions emitted on release or retract endpoints"
    else:
        gate_4_status = 'fail'
        gate_4_reason = f"{rel_ret_accepted}/{rel_ret_denom} positions emitted on release or retract endpoints (FAIL)"

    # Gate 5: Sensor Disruption Robustness (Corrupted Transport)
    black_acc = black_agg.get('accepted', 0)
    frozen_acc = frozen_agg.get('accepted', 0)

    if corrupted_transport_accepted == GATE_MAX_CORRUPTED_TRANSPORT_ACCEPTED:
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
    if any(g == 'fail' for g in all_gates):
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
        overall_reason = f"Subset dry run on {num_seeds} seeds; formal gate evaluation requires all 10 seeds (820-829)."
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
        'evaluation_status': 'complete',
        'is_complete': True,
        'provenance_notes': provenance_notes or ('Task 002 development evidence rescore' if is_rescore else 'Development dry run'),
        'evidence_path': str(evidence_path) if evidence_path else None,
        'evidence_sha256': file_sha256(evidence_path) if evidence_path else None,
        'source_code_snapshot': source_snapshot,
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
    desc = report.get('descriptive_metrics', {})
    if desc:
        mid = desc.get('midpoint_metrics', {})
        all_m = desc.get('all_accepted_metrics', {})
        print("-" * 70)
        mid_mean_str = f"{mid['midpoint_mean_error_mm']:.4f} mm" if mid.get('midpoint_mean_error_mm') is not None else "N/A"
        mid_max_str = f"{mid['midpoint_max_error_mm']:.4f} mm" if mid.get('midpoint_max_error_mm') is not None else "N/A"
        all_mean_str = f"{all_m['all_accepted_mean_error_mm']:.4f} mm" if all_m.get('all_accepted_mean_error_mm') is not None else "N/A"
        all_max_str = f"{all_m['all_accepted_max_error_mm']:.4f} mm" if all_m.get('all_accepted_max_error_mm') is not None else "N/A"
        print(f"Midpoint (lower_mid): accepted {mid.get('midpoint_accepted')}/{mid.get('midpoint_expected')}; mean: {mid_mean_str}; max: {mid_max_str}")
        print(f"All accepted (nom): count {all_m.get('all_accepted_count')}; mean: {all_mean_str}; max: {all_max_str}")
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
    print(f"Git commit: {report['git_provenance']['head_commit']} (dirty: {report['git_provenance']['is_dirty']})")
    print(f"Scene SHA-256: {report['provenance_hashes']['scene_sha256']}")
    print(f"Requirements lock SHA-256: {report['provenance_hashes']['dependency_hashes']['requirements_lock_sha256']}")
    print(f"Augmented cache valid: {report['input_availability']['augmented_cache_valid']}")
    return report


def run_rescore_command(args):
    """Rescore an existing evidence JSON artifact and generate structured gate report."""
    evidence_path = Path(args.rescore)
    if not evidence_path.is_file():
        raise FileNotFoundError(f"Evidence file not found: {evidence_path}")

    evidence = json.loads(evidence_path.read_text())
    if not isinstance(evidence, dict):
        raise ValueError('Rescore artifact must be a dictionary with declared seeds')

    # Validate embedded seeds in artifact (R2)
    embedded_seeds = evidence.get('seeds') or evidence.get('augmented_stream', {}).get('seeds')
    if embedded_seeds is None:
        raise ValueError(f"Evidence artifact at '{evidence_path}' does not declare 'seeds'.")

    # This will reject held-out seeds (840-849), duplicate seeds, and out-of-scope seeds:
    validated_embedded_seeds = validate_seeds_guard(embedded_seeds, allow_non_development=False)
    for stream_name in ('original_stream', 'augmented_stream'):
        if stream_name in evidence:
            stream = evidence[stream_name]
            if not isinstance(stream, dict):
                raise ValueError(f"Evidence {stream_name} must be a dictionary")
            stream_seeds = validate_seeds_guard(stream.get('seeds'))
            if set(stream_seeds) != set(validated_embedded_seeds):
                raise ValueError(f"Evidence {stream_name} seeds disagree with the envelope")

    # If CLI seeds were explicitly supplied, verify they match embedded seeds
    if getattr(args, 'seeds_explicitly_set', False):
        cli_validated = validate_seeds_guard(args.seeds, allow_non_development=False)
        if set(cli_validated) != set(validated_embedded_seeds):
            raise ValueError(
                f"Supplied CLI seeds {cli_validated} do not match evidence artifact seeds {validated_embedded_seeds}"
            )
    else:
        args.seeds = validated_embedded_seeds

    report = compute_gate_report(
        evidence,
        candidate_name=args.candidate,
        is_rescore=True,
        provenance_notes=f"Artifact rescore of: {evidence_path.resolve()}",
        evidence_path=evidence_path,
        root_dir=args.root_dir
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
    validate_seeds_guard(args.seeds, allow_non_development=False)
    source_capture_dir = Path(args.capture_dir)
    augmented_capture_dir = Path(args.augmented_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running development dry run on seeds {args.seeds}...")
    evidence_file = out_dir / "p5_development_evidence.json"
    evidence = evaluate_evidence(
        source_capture_dir=source_capture_dir,
        augmented_capture_dir=augmented_capture_dir,
        seeds=args.seeds,
        output_file=evidence_file,
        render_if_missing=False  # Reuses validated cache read-only
    )

    report = compute_gate_report(
        evidence,
        candidate_name=args.candidate,
        is_rescore=False,
        provenance_notes=f"Development dry run on seeds {args.seeds}; cache read-only from {augmented_capture_dir.resolve()}",
        evidence_path=evidence_file,
        root_dir=args.root_dir
    )

    report_file = out_dir / "gate_report_development.json"
    write_json(report_file, report)
    print_gate_report_summary(report)
    print(f"Development evidence written to: {evidence_file}")
    print(f"Development gate report written to: {report_file}")

    # Write task manifest
    root = Path(args.root_dir) if args.root_dir else Path.cwd()
    git_status = get_git_status_description(cwd=str(root))
    manifest = {
        'manifest_version': 1,
        'generator': 'humanoid_sim.p5_evaluation.dry_run',
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'git_provenance': git_status,
        'seeds': args.seeds,
        'candidate': args.candidate,
        'source_capture_dir': str(source_capture_dir.resolve()),
        'augmented_capture_dir': str(augmented_capture_dir.resolve()),
        'artifacts': {
            'evidence': {
                'path': str(evidence_file.resolve()),
                'sha256': file_sha256(evidence_file),
            },
            'gate_report': {
                'path': str(report_file.resolve()),
                'sha256': file_sha256(report_file),
            },
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

    parser = argparse.ArgumentParser(
        description="P5 preparation and evaluation wrapper for passive temporal reacquisition.",
        epilog=(
            "Supported modes:\n"
            "  --preflight: Run preflight checks and output preflight_report.json\n"
            "  --rescore <path>: Rescore an existing evidence JSON artifact\n"
            "  --dry-run: Run development dry run on existing development inputs\n\n"
            f"{FUTURE_CAPTURE_API_SKETCH}\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
    parser.add_argument('--start-seed', type=int, default=None,
                        help='Start seed (default: 820)')
    parser.add_argument('--count', type=int, default=None,
                        help='Seed count (default: 10)')
    parser.add_argument('--seeds', type=int, nargs='+', default=None,
                        help='Explicit seed list (e.g. --seeds 820 821)')
    parser.add_argument('--fresh-capture', action='store_true', default=False,
                        help='Attempt fresh capture (FORBIDDEN in Task 003; documents Python API sketch)')

    args = parser.parse_args()

    if args.fresh_capture:
        raise RuntimeError(
            "Fresh capture is disabled in Task 003. Future fresh execution under a separately reviewed "
            f"and frozen P5 protocol must be authorized and run via Python API:\n\n{FUTURE_CAPTURE_API_SKETCH}"
        )

    cli_seeds_specified = (args.seeds is not None or args.start_seed is not None or args.count is not None)
    args.seeds_explicitly_set = cli_seeds_specified
    if args.seeds is not None:
        args.seeds = args.seeds
    elif args.start_seed is not None or args.count is not None:
        start = args.start_seed if args.start_seed is not None else 820
        cnt = args.count if args.count is not None else 10
        args.seeds = list(range(start, start + cnt))
    else:
        args.seeds = list(range(820, 830))

    if args.preflight:
        validate_seeds_guard(args.seeds, allow_non_development=False)
        run_preflight_command(args)
    elif args.rescore:
        run_rescore_command(args)
    elif args.dry_run:
        validate_seeds_guard(args.seeds, allow_non_development=False)
        run_dry_run_command(args)
    else:
        # Default behavior: run preflight and print usage
        print("No mode specified (--preflight, --rescore, or --dry-run). Running preflight by default:")
        validate_seeds_guard(args.seeds, allow_non_development=False)
        run_preflight_command(args)


if __name__ == '__main__':
    main()
