"""Camera-only live trial launcher and public observation/action client."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from .camera import detect_pixels, pixel_to_world
from .environment import ROOT
from .live import request as file_request
from .realtime import RealtimeConfig
from .vision_runtime import VisionRuntime, VisionTrial


def request(directory, payload):
    status = Path(directory) / "status.json"
    if status.exists() and json.loads(status.read_text()).get("completed"):
        raise ValueError("Camera episode has finished")
    return file_request(directory, payload)


def conventional(directory, target):
    observation = request(directory, {"kind": "observe"})["observation"]
    speed = observation["belt_velocity_m_s"][1]
    for index, detected in enumerate(detect_pixels(observation["image_path"])):
        if detected["perceived_color"] != target:
            continue
        xy = pixel_to_world(detected["pixel_xy"])
        start = observation["time_s"] + (-0.015 - xy[1]) / speed - 2
        y = -0.015 + speed + 0.005
        command = {"object_id": f"object_{index}", "pixel_xy": detected["pixel_xy"],
                   "perceived_color": detected["perceived_color"], "observation_id": observation["observation_id"],
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
    log_path = directory.parent / (case["id"] + ".log")
    cmd = [str(ROOT / ".venv/bin/python"), "-m", "conveyor_sim.vision", "serve", "--episode", str(directory),
           "--config", json.dumps({k: case[k] for k in ["seed", "target_color", "instruction", "belt_speed", "spacing", "scenario"]}
                                 | {"actor": actor})]
    with log_path.open("w") as log:
        process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    until = time.monotonic() + 40
    while not (directory / "ready.json").exists():
        if process.poll() is not None or time.monotonic() > until:
            raise RuntimeError(f"Runtime failed to start; see {log_path}")
        time.sleep(0.02)
    if actor == "conventional":
        conventional(directory, case["target_color"])
        return {"case": case["id"], "actor": actor, "pid": process.pid, "submitted_by": "pixel_color_baseline"}
    return {"case": case["id"], "actor": actor, "pid": process.pid,
            "observation": request(directory, {"kind": "observe"})["observation"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--episode", type=Path, required=True)
    serve.add_argument("--config", required=True, help="Private experiment configuration JSON")
    launch_parser = commands.add_parser("launch")
    launch_parser.add_argument("--cases", nargs="+", required=True)
    launch_parser.add_argument("--actor", choices=["codex_session", "conventional"], required=True)
    launch_parser.add_argument("--root", type=Path, default=ROOT / "runtime/conveyor/phase5")
    for name in ["observe", "submit", "status"]:
        p = commands.add_parser(name)
        p.add_argument("--episode", type=Path, required=True)
        if name == "submit":
            p.add_argument("--command", dest="payload", required=True)
    args = parser.parse_args(argv)
    if args.command == "serve":
        if args.episode.exists():
            raise ValueError("Choose a fresh episode directory")
        result = VisionRuntime(VisionTrial(RealtimeConfig(**json.loads(args.config))), args.episode).run()
        print(json.dumps({"completed": result["completed"], "sorting_success": result["sorting_success"]}))
    elif args.command == "launch":
        cases = json.loads((ROOT / "experiments/conveyor-color-sorting/phase5/cases.json").read_text())
        for id in args.cases:
            case = next(c for c in cases if c["id"] == id)
            print(json.dumps(launch(case, args.actor, args.root)), flush=True)
    elif args.command == "status":
        print((args.episode / "status.json").read_text())
    else:
        payload = {"kind": args.command}
        if args.command == "submit":
            payload["command"] = json.loads(args.payload)
        print(json.dumps(request(args.episode, payload), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
