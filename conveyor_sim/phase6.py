"""Phase 6 launcher; Codex explicitly supplies every selected pixel and color."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from .environment import ROOT
from .phase6_scene import Config, Trial, parse_instruction, pixel_to_world
from .phase6_runtime import Runtime
from .phase6_pixels import detect_pixels
from .vision import request

CASES = ROOT / "experiments/conveyor-color-sorting/phase6/cases.json"


def decide(directory, observation, selections):
    """Arithmetic on explicitly supplied estimates, never object or color selection."""
    speed = observation["belt_velocity_m_s"][1]
    receipts = []
    for i, item in enumerate(selections):
        xy = pixel_to_world(item["pixel_xy"], observation["calibration"]["rotation_degrees"])
        start = observation["time_s"] + (-0.015 - xy[1]) / speed - 2
        command = {"object_id": f"object_v{observation['rule_version']}_{i}",
                   "pixel_xy": item["pixel_xy"], "perceived_color": item["perceived_color"],
                   "rule_version": observation["rule_version"], "observation_id": observation["observation_id"],
                   "start_at_s": start, "expires_at_s": start + 0.05,
                   "primitives": [{"tool": "move_to", "xyz": [0.18, 0.005, 0.065], "seconds": 2, "joint": True},
                                  {"tool": "move_to", "xyz": [0.18, speed - 0.01, 0.020], "seconds": 1},
                                  {"tool": "sweep", "xyz": [0.30, 3 * speed - 0.01, 0.020], "seconds": 2},
                                  {"tool": "retract"}]}
        receipts.append(request(directory, {"kind": "submit", "command": command})["receipt"])
    return [{k: e.get(k) for k in ["request_id", "status", "error", "observation_to_submission_wall_s"]} for e in receipts]


def baseline(directory):
    observation = request(directory, {"kind": "observe"})["observation"]
    while True:
        colors, count = parse_instruction(observation["instruction"])
        pixels = detect_pixels(observation["image_path"], observation["calibration"]["rotation_degrees"])
        # Order by calibrated longitudinal position, not image vertical coordinate.
        pixels.sort(key=lambda d: pixel_to_world(d["pixel_xy"], observation["calibration"]["rotation_degrees"])[1], reverse=True)
        selected = [p for p in pixels if p["perceived_color"] in colors][:count]
        decide(directory, observation, selected)
        if not observation["next_rule_change_at_s"] or observation["rule_version"] == 1:
            break
        while True:
            status = json.loads((directory / "status.json").read_text())
            if status.get("rule_version") == 1:
                break
            time.sleep(0.02)
        observation = request(directory, {"kind": "observe"})["observation"]


def launch(case, actor, root):
    directory = root / actor / case["id"]
    directory.parent.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        raise ValueError("Use a fresh case directory; evaluated trials cannot be overwritten")
    config = {**case["config"], "actor": actor}
    with (directory.parent / (case["id"] + ".log")).open("w") as log:
        process = subprocess.Popen([str(ROOT / ".venv/bin/python"), "-m", "conveyor_sim.phase6", "serve",
                                    "--episode", str(directory), "--config", json.dumps(config)],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    until = time.monotonic() + 40
    while not (directory / "ready.json").exists():
        if process.poll() is not None or time.monotonic() > until:
            raise RuntimeError(f"Runtime failed: {case['id']}; inspect launch log")
        time.sleep(0.02)
    if actor == "conventional":
        with (directory / "baseline.log").open("w") as log:
            subprocess.Popen([str(ROOT / ".venv/bin/python"), "-m", "conveyor_sim.phase6", "baseline",
                              "--episode", str(directory)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        return {"case": case["id"], "actor": actor, "submitted_by": "conventional_pixel_and_rule_parser"}
    return {"case": case["id"], "actor": actor,
            "observation": request(directory, {"kind": "observe"})["observation"]}


def check_camera():
    import mujoco
    import numpy as np
    from .camera import add_rulers

    output = ROOT / 'runtime/conveyor/phase6_debug'
    output.mkdir(parents=True, exist_ok=True)
    for label, change in [('pose', {'position_spread': .015, 'yaw_limit': .75}),
                          ('dim', {'illumination': .35}), ('camera', {'camera_rotation': 15})]:
        env = Trial(Config(seed=42, **change))
        env.wait(.5)
        with mujoco.Renderer(env.model, width=960, height=720) as renderer:
            renderer.update_scene(env.data, camera='overhead')
            path = output / f'{label}.png'
            add_rulers(renderer.render(), env.data.time).save(path)
        detections = detect_pixels(path, env.config.camera_rotation)
        errors = []
        for detected in detections:
            actual = next(c for c in env.cubes if c.color == detected['perceived_color'])
            errors.append(float(np.linalg.norm(np.asarray(pixel_to_world(detected['pixel_xy'], env.config.camera_rotation)) -
                                               env.observations()[actual.id].position[:2])))
        assert len(detections) == 3 and max(errors) < .006, (label, detections, errors)
        print(json.dumps({'development_variant': label, 'detected': len(detections), 'max_error_m': max(errors)}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check-camera")
    launch_parser = commands.add_parser("launch")
    launch_parser.add_argument("--cases", nargs="+", required=True)
    launch_parser.add_argument("--actor", choices=["codex_session", "conventional"], required=True)
    launch_parser.add_argument("--root", type=Path, default=ROOT / "runtime/conveyor/phase6")
    for name in ["serve", "baseline", "observe", "decide"]:
        sub = commands.add_parser(name)
        sub.add_argument("--episode", type=Path, required=True)
        if name == "serve":
            sub.add_argument("--config", required=True)
        if name == "decide":
            sub.add_argument("--observation", required=True, help="Public observation response JSON path")
            sub.add_argument("--selections", required=True, help="Explicit pixel/color estimates chosen by the caller")
    args = parser.parse_args(argv)
    if args.command == "check-camera":
        check_camera()
    elif args.command == "launch":
        cases = json.loads(CASES.read_text())
        for id in args.cases:
            print(json.dumps(launch(next(c for c in cases if c["id"] == id), args.actor, args.root)), flush=True)
    elif args.command == "serve":
        if args.episode.exists():
            raise ValueError("Episode directory already exists")
        Runtime(Trial(Config(**json.loads(args.config))), args.episode).run()
    elif args.command == "baseline":
        baseline(args.episode)
    elif args.command == "observe":
        print(json.dumps(request(args.episode, {"kind": "observe"})), flush=True)
    else:
        observation = json.loads(Path(args.observation).read_text())["observation"]
        print(json.dumps(decide(args.episode, observation, json.loads(args.selections))), flush=True)


if __name__ == "__main__":
    main()
