"""Reproducible Phase 2 gate trials and explicitly separate overload probes."""

import json
from pathlib import Path

from .pushing import PushConfig, PushTrial


def summarize(reports):
    return {
        "episodes": len(reports), "passed": sum(r["push_success"] for r in reports),
        "target_cubes": sum(len(r["target_ids"]) for r in reports),
        "targets_rejected": sum(r["scoring"]["outcomes"].get("correct_reject", 0) for r in reports),
        "non_target_cubes": sum(len(r["initial_cubes"]) - len(r["target_ids"]) for r in reports),
        "non_targets_passed": sum(r["scoring"]["outcomes"].get("correct_pass", 0) for r in reports),
        "episodes_with_unintended_contacts": sum(bool(r["unintended_cube_contacts"] or
                                                       r["cube_neighbor_contacts_on_belt"]) for r in reports),
        "episodes_with_fixture_contacts": sum(bool(r["fixture_contacts"]) for r in reports),
        "max_tracking_error_m": max(r["max_tracking_error_m"] for r in reports),
        "max_motion_cycle_s": max((sum(a["end_s"] - a["start_s"] for a in r["actions"][i:i + 4])
                                    for r in reports for i in range(0, len(r["actions"]) - 3, 4)), default=0),
    }


def validate_push(trials, output):
    if not 1 <= trials <= 1000:
        raise ValueError("Trial count must be between 1 and 1000")
    groups = {}
    colors = ["red", "blue", "green"]

    def run_group(name, configs, required):
        reports = []
        for i, config in enumerate(configs):
            report = PushTrial(config, capture=False).run()
            reports.append(report)
            if (i + 1) % 10 == 0 or not report["push_success"]:
                print(f"{name}: {i + 1}/{len(configs)}, passed={sum(r['push_success'] for r in reports)}", flush=True)
        groups[name] = {"required_for_gate": required, "summary": summarize(reports), "runs": reports}

    for name, speed in [("stationary", 0.0), ("moving_1cm_s", 0.01)]:
        run_group(name, [PushConfig(seed=1000 + i, belt_speed=speed, target_color=colors[i % 3])
                         for i in range(trials)], True)
    for speed in [0.005, 0.01, 0.02, 0.03]:
        run_group(f"neighbors_{speed:g}m_s", [
            PushConfig(seed=2000 + i, belt_speed=speed, scenario="neighbors", target_color=colors[i % 3])
            for i in range(10)], True)
    for spacing in [0.08, 0.10, 0.12]:
        run_group(f"stream_spacing_{spacing:g}m", [
            PushConfig(seed=3000 + i, scenario="stream", spacing=spacing, target_color=colors[i % 3])
            for i in range(10)], True)
    # Report missed targets under overload; these cases do not define the supported envelope.
    for name, speed, spacing in [("overload_6cm_spacing", 0.01, 0.06), ("overload_2cm_s", 0.02, 0.12)]:
        run_group(name, [PushConfig(seed=4000 + i, scenario="stream", belt_speed=speed,
                                    spacing=spacing, target_color=colors[i % 3]) for i in range(10)], False)
    isolated = [groups[n]["summary"] for n in ["stationary", "moving_1cm_s"]]
    other_required = [g["summary"] for name, g in groups.items()
                      if g["required_for_gate"] and name not in {"stationary", "moving_1cm_s"}]
    gate = (trials >= 100 and all(g["passed"] / g["episodes"] >= 0.95 for g in isolated)
            and all(g["passed"] == g["episodes"] for g in other_required))
    summary = {
        "phase": 2, "gate_passed": gate,
        "criteria": {"isolated_trials_per_condition_at_least": 100,
                     "isolated_success_rate_at_least": 0.95,
                     "required_neighbor_and_stream_checks": "all must pass",
                     "max_endpoint_tracking_error_m": 0.005,
                     "unintended_cube_or_fixture_contacts_in_successful_trial": 0},
        "evaluation_seeds": {"isolated": [1000, 1000 + trials - 1], "neighbors": [2000, 2009],
                             "stream": [3000, 3009], "overload": [4000, 4009]},
        "groups": groups,
        "note": "Mechanical controller validation with exact target IDs/state. Overload groups are reported separately; no LLM evaluated.",
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"gate_passed": gate, "groups": {n: g["summary"] for n, g in groups.items()}}, indent=2))
    return summary
