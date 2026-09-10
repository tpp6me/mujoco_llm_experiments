"""Aggregate every predeclared Phase 3 case, including failures and full logs."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .environment import ROOT


def summarize(reports):
    outcomes = Counter()
    for report in reports:
        outcomes.update(report["scoring"]["outcomes"])
    targets = sum(len(r["target_ids"]) for r in reports)
    cubes = sum(r["scoring"]["total_cubes"] for r in reports)
    duration = sum(r["simulation_duration_s"] for r in reports)
    return {"episodes": len(reports), "successful_episodes": sum(r["sorting_success"] for r in reports),
            "correct_selection_episodes": sum(r["selection_correct"] for r in reports),
            "target_cubes": targets, "non_target_cubes": cubes - targets,
            "target_rejection_rate": outcomes["correct_reject"] / targets,
            "wrong_rejection_rate": outcomes["wrong_reject"] / (cubes - targets),
            "outcomes": dict(outcomes), "tool_calls": sum(r["tool_calls"] for r in reports),
            "tool_errors": sum(r["tool_errors"] for r in reports),
            "episodes_with_unintended_contacts": sum(bool(r["unintended_cube_contacts"] or
                                                          r["cube_neighbor_contacts_on_belt"] or
                                                          r["fixture_contacts"]) for r in reports),
            "max_endpoint_error_m": max(r["max_tracking_error_m"] for r in reports),
            "simulation_time_s": duration,
            "correct_cubes_per_simulation_minute":
                60 * (outcomes["correct_reject"] + outcomes["correct_pass"]) / duration}


def evaluate(root, output):
    cases_path = ROOT / "experiments/conveyor-color-sorting/phase3/cases.json"
    cases = json.loads(cases_path.read_text())
    groups = {}
    for actor in ["codex_session", "conventional"]:
        reports = []
        for case in cases:
            report = json.loads((root / actor / case["id"] / "report.json").read_text())
            if report["actor"] != actor or not report["completed"]:
                raise ValueError(f"Missing or unfinished {actor} case {case['id']}")
            for key in ["seed", "target_color", "instruction"]:
                if report["config"][key] != case[key]:
                    raise ValueError(f"Case configuration mismatch: {case['id']} {key}")
            for path, digest in report["source_sha256"].items():
                if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
                    raise ValueError(f"Source changed since trial: {path}")
            reports.append(report)
        groups[actor] = {"summary": summarize(reports),
                         "by_color": {c: summarize([r for r in reports if r["config"]["target_color"] == c])
                                      for c in ["red", "blue", "green"]}, "runs": reports}
    for agent, baseline in zip(groups["codex_session"]["runs"], groups["conventional"]["runs"], strict=True):
        if agent["initial_cubes"] != baseline["initial_cubes"]:
            raise ValueError("Comparator cube layouts differ")
    result = {"phase": 3, "gate_passed": all(g["summary"]["successful_episodes"] == len(cases)
                                               for g in groups.values()),
              "protocol": "phase3/PROTOCOL.md", "cases": cases,
              "case_manifest_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
              "groups": groups, "matched_initial_states": True,
              "limitations": ["Interactive development demonstration; not a blinded benchmark",
                              "Exact state and known motion reference supplied",
                              "Simulation paused between actions",
                              "Three cube layouts; nine episodes per controller",
                              "No measured model-call count, tokens, cost, or isolated inference latency",
                              "No statistical or real-robot generalization claim"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"gate_passed": result["gate_passed"],
                      "groups": {k: v["summary"] for k, v in groups.items()}}, indent=2))
    return result["gate_passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "runtime/conveyor/phase3")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "experiments/conveyor-color-sorting/results/phase3_comparison.json")
    args = parser.parse_args()
    raise SystemExit(0 if evaluate(args.root, args.output) else 1)
