"""Command-line entry point and explicit conventional comparator for Phase 3."""

import argparse
import json
from pathlib import Path

from .environment import COLORS, ROOT
from .interactive import InteractiveConfig, InteractiveTrial


def conventional(env):
    """Labeled baseline only; the interactive action dispatcher never calls this."""
    def act(command):
        event = env.execute(command)
        if event["error"]:
            raise ValueError(event["error"])

    observation = env.observe()
    targets = sorted((c for c in observation["cubes"] if c["color"] == env.config.target_color),
                     key=lambda c: c["position"][1], reverse=True)
    for target in targets:
        act({"tool": "move_to", "cube_id": target["id"], "xyz": [0.18, 0.005, 0.065],
             "seconds": 2, "joint": True})
        y = env.observations()[target["id"]].position[1]
        act({"tool": "wait", "seconds": max(0, (-0.015 - y) / env.config.belt_speed)})
        y = env.observations()[target["id"]].position[1] + env.config.belt_speed + 0.005
        act({"tool": "move_to", "xyz": [0.18, y, 0.020], "seconds": 1})
        act({"tool": "sweep", "xyz": [0.30, y + env.config.belt_speed * 2, 0.020], "seconds": 2})
        act({"tool": "retract"})
    act({"tool": "wait", "seconds": max(0, env.deadline - env.data.time)})
    act({"tool": "finish"})


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["reset", "baseline"]:
        p = commands.add_parser(name)
        p.add_argument("--episode", type=Path, required=True)
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--target", choices=list(COLORS), required=True, help="Independent grader setting")
        p.add_argument("--instruction", required=True)
    act = commands.add_parser("act")
    act.add_argument("--episode", type=Path, required=True)
    act.add_argument("--actions", required=True, help="JSON object or explicit list of primitive commands")
    for name in ["observe", "report"]:
        p = commands.add_parser(name)
        p.add_argument("--episode", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command in {"reset", "baseline"}:
        if (args.episode / "episode.npz").exists():
            raise ValueError("Episode already exists; choose a new output directory")
        actor = "conventional" if args.command == "baseline" else "codex_session"
        env = InteractiveTrial(InteractiveConfig(args.seed, args.target, args.instruction, actor))
        env.wait(0.5)  # Setup settling only; no selection or arm motion.
        if args.command == "baseline":
            conventional(env)
        env.save(args.episode)
        print(json.dumps(env.report() if args.command == "baseline" else env.observe(), indent=2))
        return 0 if args.command == "reset" or env.report()["sorting_success"] else 1
    env = InteractiveTrial.load(args.episode)
    if args.command == "report":
        print(json.dumps(env.report(), indent=2))
        return 0
    commands = [{"tool": "observe"}] if args.command == "observe" else json.loads(args.actions)
    if isinstance(commands, dict):
        commands = [commands]
    if not isinstance(commands, list) or not 1 <= len(commands) <= 10:
        raise ValueError("Supply one to ten explicit commands")
    for command in commands:
        event = env.execute(command)
        env.save(args.episode)
        print(json.dumps({"event_index": event["index"], "command": command,
                          "error": event["error"], "observation": event["after"]}, indent=2))
        if event["error"]:
            return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
