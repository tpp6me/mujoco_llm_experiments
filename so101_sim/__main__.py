"""Run with python -m so101_sim; use mjpython for viewer commands on macOS."""

import argparse
import json
import sys
import time
from pathlib import Path

import mujoco

from .environment import Environment, ROOT, configure_camera


def emit(result):
    print(json.dumps(result, indent=2), flush=True)


def demo(env):
    """Scripted baseline for checking the controller; Codex can call primitives separately."""
    emit(env.reset())
    emit(env.gripper(1.0))
    x, y, _ = env.observe()["cube_xyz_m"]
    emit(env.move([x, y, 0.075]))
    emit(env.move([x, y, 0.020]))
    closed = env.gripper(0.0)
    emit(closed)
    if not closed["observation"]["both_jaws_contact"]:
        raise RuntimeError("The cube is not contacting both jaws; stopping before lift")
    emit(env.move([x, y, 0.080], seconds=3.0))
    held = env.hold(3.0)
    emit(held)
    if not held["held_throughout"] or held["cube_drift_m"] > 0.005:
        raise RuntimeError("Cube did not remain securely lifted during the hold")


def view(env, replay, seconds):
    from mujoco import viewer as mujoco_viewer

    # Replays use separate visualization data. They never modify the saved simulation.
    visual = mujoco.MjData(env.model)
    visual.qpos[:] = env.data.qpos
    mujoco.mj_forward(env.model, visual)
    with mujoco_viewer.launch_passive(env.model, visual) as viewer:
        configure_camera(viewer.cam)
        start = time.monotonic()
        frames = env.frames if replay else []
        index = 0
        while viewer.is_running() and (seconds is None or time.monotonic() - start < seconds):
            if frames:
                elapsed = time.monotonic() - start
                while index + 1 < len(frames) and env.frame_times[index + 1] <= elapsed:
                    index += 1
                visual.qpos[:] = frames[index]
                mujoco.mj_forward(env.model, visual)
            viewer.sync()
            time.sleep(1 / 60)


def live_demo(env):
    from mujoco import viewer as mujoco_viewer

    with mujoco_viewer.launch_passive(env.model, env.data) as viewer:
        configure_camera(viewer.cam)
        start = time.monotonic()

        def sync():
            if not viewer.is_running():
                raise KeyboardInterrupt
            viewer.sync()
            time.sleep(max(0, start + env.data.time - time.monotonic()))

        env.on_frame = sync
        try:
            demo(env)
        finally:
            env.on_frame = None
        print("Pickup complete. Final state is paused; close the viewer to exit.", flush=True)
        while viewer.is_running():
            viewer.sync()
            time.sleep(1 / 60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=ROOT / "runtime" / "episode.npz")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset", help="Start a new episode")
    reset.add_argument("--x", type=float, default=0.22)
    reset.add_argument("--y", type=float, default=0.0)
    commands.add_parser("observe", help="Read state and contact evidence as JSON")
    move = commands.add_parser("move", help="Move the tool to XYZ with a downward grasp orientation")
    move.add_argument("xyz", nargs=3, type=float)
    move.add_argument("--seconds", type=float, default=2.0)
    grip = commands.add_parser("gripper", help="Open or close the jaws")
    grip.add_argument("position", choices=["open", "close"])
    grip.add_argument("--seconds", type=float, default=3.0)
    hold = commands.add_parser("hold", help="Hold controls and measure grasp stability")
    hold.add_argument("--seconds", type=float, default=3.0)
    snap = commands.add_parser("snapshot", help="Render the current scene to PNG")
    snap.add_argument("--output", type=Path, default=ROOT / "runtime" / "so101.png")
    recording = commands.add_parser("record", help="Export saved motion as an H.264 MP4 (requires ffmpeg)")
    recording.add_argument("--output", type=Path, default=ROOT / "runtime" / "so101_pickup.mp4")
    recording.add_argument("--fps", type=int, default=30)
    viewer = commands.add_parser("view", help="View the paused state or replay saved motion")
    viewer.add_argument("--replay", action="store_true")
    viewer.add_argument("--seconds", type=float, help="Auto-close after this many wall-clock seconds")
    baseline = commands.add_parser("demo", help="Run the scripted pickup baseline from reset")
    baseline.add_argument("--viewer", action="store_true")
    args = parser.parse_args()

    env = Environment()
    mutating = args.command in {"reset", "move", "gripper", "hold", "demo"}
    if args.command != "demo" and args.state.exists():
        env.load(args.state)
    elif args.command not in {"reset", "demo"}:
        parser.error("No saved episode. Run 'reset' or 'demo' first.")
    try:
        match args.command:
            case "reset":
                emit(env.reset(args.x, args.y))
            case "observe":
                emit(env.observe())
            case "move":
                emit(env.move(args.xyz, args.seconds))
            case "gripper":
                emit(env.gripper(1.0 if args.position == "open" else 0.0, args.seconds))
            case "hold":
                emit(env.hold(args.seconds))
            case "snapshot":
                emit({"image": env.snapshot(args.output)})
            case "record":
                from .video import record

                emit(record(env, args.output, args.fps))
            case "view":
                if args.seconds is not None and not 0 < args.seconds < float("inf"):
                    raise ValueError("Viewer duration must be finite and positive")
                view(env, args.replay, args.seconds)
            case "demo":
                live_demo(env) if args.viewer else demo(env)
    except (ValueError, RuntimeError) as exc:
        emit({"error": str(exc)})
        return 1
    except KeyboardInterrupt:
        print("Stopped; simulation state saved.", file=sys.stderr)
        return 130
    finally:
        if mutating:
            env.save(args.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
