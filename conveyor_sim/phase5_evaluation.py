"""Audit the complete camera matrix against the retained Phase 4 comparison."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

from .environment import ROOT
from .phase4_evaluation import summarize


def camera_summary(reports):
    result = summarize(reports)
    audits = [a for r in reports for a in r["perception_audits"]]
    delays = [o["capture_to_image_ready_wall_s"] for r in reports for o in r["observations"]]
    result.update(perception_estimates=len(audits),
                  correct_perceived_colors=sum(a["color_correct"] for a in audits),
                  target_estimates=sum(a["is_target"] for a in audits),
                  position_error_m={"median": float(np.median([a["position_error_m"] for a in audits])),
                                    "max": max(a["position_error_m"] for a in audits)},
                  max_abs_y_error_m=max(abs(a["y_error_m"]) for a in audits),
                  image_ready_delay_s={"median": float(np.median(delays)), "max": max(delays)})
    return result


def evaluate(root, output):
    folder = ROOT / "experiments/conveyor-color-sorting"
    cases = json.loads((folder / "phase5/cases.json").read_text())
    reference_path = folder / "results/phase4_comparison.json"
    reference = json.loads(reference_path.read_text())
    groups, image_manifest, comparisons = {}, [], []
    public_keys = {"observation_id", "instruction", "time_s", "observed_at_utc", "time_mode",
                   "belt_velocity_m_s", "calibration", "image_path", "capture_to_image_ready_wall_s", "image_ready_at_utc"}
    for actor in ["codex_session", "conventional"]:
        reports = []
        for case, prior in zip(cases, reference["groups"][actor]["runs"], strict=True):
            report = json.loads((root / actor / case["id"] / "private/report.json").read_text())
            if not report["completed"] or report["actor"] != actor:
                raise ValueError("Missing, unfinished, or mislabeled camera trial")
            for key in ["seed", "target_color", "instruction", "belt_speed", "spacing", "scenario"]:
                if report["config"][key] != case[key]:
                    raise ValueError(f"Changed case setting: {case['id']} {key}")
            if report["initial_cubes"] != prior["initial_cubes"]:
                raise ValueError("Camera and Phase 4 physical layouts differ")
            if report["scoring"]["classified_cubes"] != 3:
                raise ValueError("A cube is missing from accounting")
            for file, sha in report["source_sha256"].items():
                if hashlib.sha256((ROOT / file).read_bytes()).hexdigest() != sha:
                    raise ValueError(f"Source changed: {file}")
            for observation in report["observations"]:
                if set(observation) != public_keys:
                    raise ValueError("Unexpected field in a camera observation")
                source = Path(observation["image_path"])
                destination = folder / "phase5/inputs" / actor / f"{case['id']}.png"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                image_manifest.append({"case": case["id"], "actor": actor,
                                       "image": str(destination.relative_to(folder)),
                                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                       "observation": observation})
            comparisons.append({"case": case["id"], "actor": actor,
                                "phase4_success": prior["sorting_success"], "phase5_success": report["sorting_success"],
                                "phase4_outcomes": prior["scoring"]["outcomes"], "phase5_outcomes": report["scoring"]["outcomes"]})
            reports.append(report)
        conditions = {}
        for speed in [0.005, 0.01, 0.02, 0.03]:
            conditions[f"mixed_{speed:g}"] = camera_summary([r for r in reports if r["config"]["scenario"] == "mixed"
                                                             and r["config"]["belt_speed"] == speed])
        for spacing in [0.08, 0.06]:
            conditions[f"stream_{spacing:g}"] = camera_summary([r for r in reports if r["config"]["scenario"] == "stream"
                                                                and r["config"]["spacing"] == spacing])
        groups[actor] = {"summary": camera_summary(reports), "conditions": conditions, "runs": reports}
    result = {"phase": 5, "measurement_complete": True,
              "gate_passed": all(r["realtime_healthy"] for g in groups.values() for r in g["runs"]),
              "gate_definition": "Complete camera measurement and comparison with healthy continuous-time execution; failures retained",
              "matched_phase4_initial_states": True, "public_observation_schema_verified": True,
              "phase4_reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
              "cases": cases, "groups": groups, "paired_comparisons": comparisons,
              "phase4_summaries": {k: v["summary"] for k, v in reference["groups"].items()},
              "images": image_manifest,
              "limitations": ["Same development session and previously seen case layouts; not a blinded benchmark",
                              "One initial image per episode with known camera calibration and belt velocity",
                              "Selected-object estimates only, not exhaustive detection or tracking metrics",
                              "End-to-end response gaps include image delivery, reasoning, and orchestration",
                              "Small sample, fixed lighting, and target-position confounding"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"gate_passed": result["gate_passed"], "groups": {k: v["summary"] for k, v in groups.items()}}, indent=2))
    return result["gate_passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "runtime/conveyor/phase5")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/conveyor-color-sorting/results/phase5_comparison.json")
    args = parser.parse_args()
    raise SystemExit(0 if evaluate(args.root, args.output) else 1)
