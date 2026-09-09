"""Phase 1 conveyor experiments. Use mjpython for view, snapshot, and record."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import mujoco
import numpy as np

from .environment import COLORS, ROOT, Config, Conveyor, configure_camera

DEFAULT_EPISODE = ROOT / "runtime" / "conveyor" / "phase1"


def load_episode(directory):
    with np.load(Path(directory) / "episode.npz", allow_pickle=False) as saved:
        if "phase" in saved and int(saved["phase"]) == 2:
            from .pushing import PushConfig, PushTrial

            env = PushTrial(PushConfig(**json.loads(str(saved["config"]))))
        else:
            env = Conveyor(Config(**json.loads(str(saved["config"]))))
        env.frames = list(saved["frames"])
        env.frame_times = list(saved["times"])
        env.score_frames = json.loads(str(saved["score_frames"]))
    return env


def annotation(env):
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size=19)
    small = ImageFont.load_default(size=16)
    times = np.asarray(env.frame_times)

    def draw(pixels, timestamp):
        index = max(0, int(np.searchsorted(times, timestamp, side="right")) - 1)
        collected = env.score_frames[index]["collected"]
        image = Image.fromarray(pixels)
        canvas = ImageDraw.Draw(image)
        canvas.rectangle((0, 0, image.width, 72), fill=(18, 24, 31))
        pushing = hasattr(env, "target_ids")
        title = "PHASE 2  |  SO101 pushing  |  Conventional controller" if pushing else "PHASE 1  |  Conveyor transport  |  SO101 parked"
        canvas.text((18, 12), title, font=font, fill="white")
        rejected = env.score_frames[index]["outcomes"].get("correct_reject", 0)
        progress = f"Rejected {rejected}/{len(env.target_ids)}    Passed {collected}" if pushing else f"Collected {collected}/{env.config.count}"
        canvas.text((18, 43), f"Time {timestamp:05.1f}s    Belt {env.config.belt_speed * 100:g} cm/s    "
                    + progress, font=small, fill=(170, 220, 230))
        canvas.rectangle((0, image.height - 38, image.width, image.height), fill=(18, 24, 31))
        caption = (f"Reject {env.config.target_color} targets. Exact target IDs and positions supplied; no LLM decisions."
                   if pushing else f"All colors pass in this transport check. Sorting target: {env.config.target_color} (scoring only).")
        canvas.text((18, image.height - 28), caption,
                    font=small, fill=(210, 215, 225))
        return np.asarray(image)

    return draw


def view(env, seconds=None):
    from mujoco import viewer as mujoco_viewer

    visual = mujoco.MjData(env.model)
    with mujoco_viewer.launch_passive(env.model, visual) as viewer:
        configure_camera(viewer.cam)
        start = time.monotonic()
        index = 0
        print("Replaying conveyor transport. Close the viewer to exit.", flush=True)
        while viewer.is_running() and (seconds is None or time.monotonic() - start < seconds):
            elapsed = time.monotonic() - start
            while index + 1 < len(env.frames) and env.frame_times[index + 1] <= elapsed:
                index += 1
            visual.qpos[:] = env.frames[index]
            mujoco.mj_forward(env.model, visual)
            viewer.sync()
            time.sleep(1 / 60)


def validate(seeds, speeds, output):
    if seeds < 1:
        raise ValueError("At least one seed is required")
    reports = []
    for speed in speeds:
        for seed in range(seeds):
            env = Conveyor(Config(seed=seed, belt_speed=speed), capture=False)
            report = env.run()
            reports.append(report)
            print(f"speed={speed:g} seed={seed} collected={report['collected_cubes']}/6 "
                  f"transport_success={report['transport_success']}", flush=True)
    summary = {"phase": 1, "episodes": len(reports),
               "total_cubes": sum(r["config"]["count"] for r in reports),
               "collected_cubes": sum(r["collected_cubes"] for r in reports),
               "passed_episodes": sum(r["transport_success"] for r in reports),
               "all_passed": all(r["transport_success"] for r in reports),
               "speeds_m_s": speeds, "seeds": list(range(seeds)),
               "criteria": {"all_cubes_in_pass_bin": True, "arm_cube_contacts": 0,
                            "max_arm_deviation_rad": 0.01, "max_belt_speed_error_m_s": 0.002,
                            "max_lateral_drift_m": 0.005, "premature_belt_departures": 0},
               "note": "Phase 1 mechanical validation; this does not measure LLM sorting performance.",
               "runs": reports}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=2), flush=True)
    return summary["all_passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run a complete transport episode and save it")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--count", type=int, default=6)
    run.add_argument("--speed", type=float, default=0.03)
    run.add_argument("--target", choices=list(COLORS), default="red")
    run.add_argument("--seconds", type=float, help="Override the automatic outcome deadline")
    run.add_argument("--output", type=Path, default=DEFAULT_EPISODE)
    check = commands.add_parser("validate", help="Repeat transport across seeds and speeds")
    check.add_argument("--seeds", type=int, default=10)
    check.add_argument("--speeds", nargs="+", type=float, default=[0.01, 0.03, 0.05])
    check.add_argument("--output", type=Path, default=ROOT / "runtime" / "conveyor" / "validation.json")
    push = commands.add_parser("push", help="Run the Phase 2 conventional pushing baseline")
    push.add_argument("--seed", type=int, default=0)
    push.add_argument("--speed", type=float, default=0.01)
    push.add_argument("--target", choices=list(COLORS), default="red")
    push.add_argument("--scenario", choices=["isolated", "neighbors", "stream"], default="neighbors")
    push.add_argument("--spacing", type=float, default=0.12)
    push.add_argument("--output", type=Path, default=ROOT / "runtime" / "conveyor" / "phase2")
    push_check = commands.add_parser("validate-push", help="Run stationary, moving, and spacing validation")
    push_check.add_argument("--trials", type=int, default=100)
    push_check.add_argument("--output", type=Path, default=ROOT / "runtime" / "conveyor" / "push_validation.json")
    playback = commands.add_parser("view", help="Replay saved motion in the macOS viewer")
    playback.add_argument("--episode", type=Path, default=DEFAULT_EPISODE)
    playback.add_argument("--seconds", type=float)
    movie = commands.add_parser("record", help="Export the saved transport episode as MP4")
    movie.add_argument("--episode", type=Path, default=DEFAULT_EPISODE)
    movie.add_argument("--output", type=Path, default=DEFAULT_EPISODE / "conveyor_transport.mp4")
    movie.add_argument("--fps", type=int, default=30)
    snap = commands.add_parser("snapshot", help="Render a recorded scene at the requested simulation time")
    snap.add_argument("--episode", type=Path, default=DEFAULT_EPISODE)
    snap.add_argument("--time", type=float, default=8.0)
    snap.add_argument("--output", type=Path, default=DEFAULT_EPISODE / "conveyor.png")
    args = parser.parse_args()
    try:
        if args.command == "push":
            from .pushing import PushConfig, PushTrial

            env = PushTrial(PushConfig(args.seed, args.speed, args.target, args.scenario, args.spacing))
            report = env.run()
            env.save(args.output)
            print(json.dumps(report, indent=2), flush=True)
            return 0 if report["push_success"] else 1
        if args.command == "validate-push":
            from .push_validation import validate_push

            return 0 if validate_push(args.trials, args.output)["gate_passed"] else 1
        if args.command == "run":
            env = Conveyor(Config(args.seed, args.count, args.speed, args.target))
            report = env.run(args.seconds)
            env.save(args.output)
            print(json.dumps(report, indent=2), flush=True)
            return 0 if report["transport_success"] else 1
        if args.command == "validate":
            return 0 if validate(args.seeds, args.speeds, args.output) else 1
        env = load_episode(args.episode)
        if args.command == "view":
            if args.seconds is not None and not 0 < args.seconds < float("inf"):
                raise ValueError("Viewer duration must be finite and positive")
            view(env, args.seconds)
        elif args.command == "record":
            from so101_sim.video import record

            print(json.dumps(record(env, args.output, args.fps, configure_camera, annotation(env)), indent=2))
        elif args.command == "snapshot":
            from PIL import Image

            if not 0 <= args.time <= env.frame_times[-1]:
                raise ValueError("Snapshot time must be within the saved episode")
            index = max(0, int(np.searchsorted(env.frame_times, args.time, side="right")) - 1)
            env.data.qpos[:] = env.frames[index]
            mujoco.mj_forward(env.model, env.data)
            camera = mujoco.MjvCamera()
            configure_camera(camera)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with mujoco.Renderer(env.model, height=720, width=960) as renderer:
                renderer.update_scene(env.data, camera=camera)
                Image.fromarray(annotation(env)(renderer.render(), args.time)).save(args.output)
            print(args.output)
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
