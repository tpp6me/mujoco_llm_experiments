"""Aggregate the fixed live protocol with timing failures retained."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np

from .environment import ROOT


def summarize(reports):
    outcomes, statuses = Counter(), Counter()
    latencies, margins = [], []
    for report in reports:
        outcomes.update(report["scoring"]["outcomes"])
        for event in report["events"]:
            statuses[event["status"]] += 1
            if "observation_to_submission_wall_s" in event:
                latencies.append(event["observation_to_submission_wall_s"])
                margins.append(event["command"]["start_at_s"] - event["received_at_sim_s"])
    targets = sum(len(r["target_ids"]) for r in reports)
    non_targets = sum(r["scoring"]["total_cubes"] - len(r["target_ids"]) for r in reports)
    return {"episodes": len(reports), "successful_episodes": sum(r["sorting_success"] for r in reports),
            "selection_correct_episodes": sum(r["selection_correct"] for r in reports),
            "realtime_healthy_episodes": sum(r["realtime_healthy"] for r in reports),
            "target_cubes": targets, "non_target_cubes": non_targets, "outcomes": dict(outcomes),
            "target_rejection_rate": outcomes["correct_reject"] / targets,
            "wrong_rejection_rate": outcomes["wrong_reject"] / non_targets if non_targets else None,
            "command_statuses": dict(statuses),
            "response_wall_s": {"min": min(latencies), "median": float(np.median(latencies)),
                                "p95": float(np.quantile(latencies, 0.95)), "max": max(latencies)},
            "min_submission_margin_to_planned_start_s": min(margins),
            "max_simulation_lag_s": max(r["max_simulation_lag_s"] for r in reports),
            "max_endpoint_error_m": max(r["max_tracking_error_m"] for r in reports),
            "episodes_with_unintended_contacts": sum(bool(r["unintended_cube_contacts"] or
                                                          r["cube_neighbor_contacts_on_belt"] or
                                                          r["fixture_contacts"]) for r in reports),
            "correct_cubes_per_simulation_minute": 60 * (outcomes["correct_reject"] + outcomes["correct_pass"]) /
                sum(r["simulation_duration_s"] for r in reports)}


def evaluate(root, output):
    path = ROOT / "experiments/conveyor-color-sorting/phase4/cases.json"
    cases = json.loads(path.read_text())
    groups = {}
    for actor in ["codex_session", "conventional"]:
        reports = []
        for case in cases:
            report = json.loads((root / actor / case["id"] / "report.json").read_text())
            if not report["completed"] or report["actor"] != actor:
                raise ValueError(f"Unfinished or mislabeled trial: {actor} {case['id']}")
            for key in ["seed", "target_color", "instruction", "belt_speed", "spacing", "scenario"]:
                if report["config"][key] != case[key]:
                    raise ValueError(f"Case settings changed: {case['id']} {key}")
            for file, digest in report["source_sha256"].items():
                if hashlib.sha256((ROOT / file).read_bytes()).hexdigest() != digest:
                    raise ValueError(f"Source changed: {file}")
            if report["scoring"]["classified_cubes"] != report["scoring"]["total_cubes"]:
                raise ValueError("Cube missing from outcome accounting")
            reports.append(report)
        groups[actor] = {"summary": summarize(reports), "runs": reports,
                         "conditions": {key: summarize([r for r in reports if r["config"]["scenario"] == "mixed"
                                                          and r["config"]["belt_speed"] == speed])
                                        for key, speed in [("mixed_0.005", 0.005), ("mixed_0.01", 0.01),
                                                           ("mixed_0.02", 0.02), ("mixed_0.03", 0.03)]}}
        for spacing in [0.08, 0.06]:
            groups[actor]["conditions"][f"stream_{spacing}"] = summarize(
                [r for r in reports if r["config"]["scenario"] == "stream" and r["config"]["spacing"] == spacing])
    for a, b in zip(groups["codex_session"]["runs"], groups["conventional"]["runs"], strict=True):
        if a["initial_cubes"] != b["initial_cubes"]:
            raise ValueError("Comparator initial layouts differ")
    gate = all(report["sorting_success"] for group in groups.values()
               for case, report in zip(cases, group["runs"], strict=True) if case["required_for_gate"])
    result = {"phase": 4, "gate_passed": gate, "matched_initial_states": True,
              "cases": cases, "groups": groups,
              "limitations": ["Development trials with exact state and a supplied motion recipe",
                              "Codex decisions made in this development conversation, sometimes batched across cases",
                              "Observation-to-submission wall gaps include reasoning and orchestration",
                              "Fixed interception entry; no late-command replanning or retry",
                              "Small sample; observed conditions do not establish a universal speed limit",
                              "Model version, inference-only latency, tokens, and cost unavailable"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"gate_passed": gate, "groups": {k: v["summary"] for k, v in groups.items()}}, indent=2))
    return gate


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT / "runtime/conveyor/phase4")
    p.add_argument("--output", type=Path, default=ROOT / "experiments/conveyor-color-sorting/results/phase4_comparison.json")
    args = p.parse_args()
    raise SystemExit(0 if evaluate(args.root, args.output) else 1)
