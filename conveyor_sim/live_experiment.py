"""Launch fixed live cases; the Codex branch never chooses or submits actions."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from .environment import ROOT
from .live import request


def baseline(directory, target):
    observation = request(directory, {"kind": "observe"})["observation"]
    speed = observation["belt_velocity_m_s"][1]
    selected = sorted((c for c in observation["cubes"] if c["color"] == target),
                      key=lambda c: c["position"][1], reverse=True)
    for cube in selected:
        start = observation["time_s"] + (-0.015 - cube["position"][1]) / speed - 2
        y = -0.015 + speed + 0.005
        command = {"cube_id": cube["id"], "observation_id": observation["observation_id"],
                   "start_at_s": start, "expires_at_s": start + 0.05,
                   "primitives": [{"tool": "move_to", "xyz": [0.18, 0.005, 0.065], "seconds": 2, "joint": True},
                                  {"tool": "move_to", "xyz": [0.18, y, 0.020], "seconds": 1},
                                  {"tool": "sweep", "xyz": [0.30, y + 2 * speed, 0.020], "seconds": 2},
                                  {"tool": "retract"}]}
        request(directory, {"kind": "submit", "command": command})


def launch(case, actor, root):
    directory = root / actor / case["id"]
    directory.parent.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        raise ValueError(f"Case already exists: {directory}")
    log = directory.parent / f"{case['id']}.log"
    cmd = [sys.executable, "-m", "conveyor_sim.live", "serve", "--episode", str(directory),
           "--seed", str(case["seed"]), "--target", case["target_color"], "--instruction", case["instruction"],
           "--actor", actor, "--speed", str(case["belt_speed"]), "--spacing", str(case["spacing"]),
           "--scenario", case["scenario"]]
    with log.open("w") as output:
        process = subprocess.Popen(cmd, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    until = time.monotonic() + 10
    while not (directory / "ready.json").exists():
        if process.poll() is not None or time.monotonic() > until:
            raise RuntimeError(f"Runtime failed to start; see {log}")
        time.sleep(0.02)
    if actor == "conventional":
        baseline(directory, case["target_color"])
        return {"case": case["id"], "actor": actor, "pid": process.pid, "submitted_by": "conventional_selector"}
    return {"case": case["id"], "actor": actor, "pid": process.pid,
            "observation": request(directory, {"kind": "observe"})["observation"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument("--actor", choices=["codex_session", "conventional"], required=True)
    parser.add_argument("--root", type=Path, default=ROOT / "runtime/conveyor/phase4")
    args = parser.parse_args()
    cases = json.loads((ROOT / "experiments/conveyor-color-sorting/phase4/cases.json").read_text())
    for id in args.cases:
        matches = [case for case in cases if case["id"] == id]
        if len(matches) != 1:
            raise ValueError(f"Unknown case {id}")
        print(json.dumps(launch(matches[0], args.actor, args.root)), flush=True)
