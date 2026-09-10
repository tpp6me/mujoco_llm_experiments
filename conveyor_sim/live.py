"""Local file-queue client for the continuously running Phase 4 simulator."""

import argparse
import json
from pathlib import Path
import time
import uuid

from .realtime import RealtimeConfig, RealtimeTrial, Runtime, write_json


def request(directory, payload, timeout=5):
    directory = Path(directory)
    if (directory / "report.json").exists():
        raise ValueError("Episode has finished; inspect its report")
    if not (directory / "ready.json").exists():
        raise ValueError("Runtime is not ready")
    name = uuid.uuid4().hex + ".json"
    write_json(directory / "requests" / name, payload)
    response = directory / "responses" / name
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if response.exists():
            return json.loads(response.read_text())
        time.sleep(0.01)
    raise TimeoutError("Runtime response timed out; request remains queued")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--episode", type=Path, required=True)
    serve.add_argument("--seed", type=int, default=0)
    serve.add_argument("--target", choices=["red", "blue", "green"], required=True)
    serve.add_argument("--instruction", required=True)
    serve.add_argument("--actor", choices=["codex_session", "conventional", "test"], default="codex_session")
    serve.add_argument("--speed", type=float, default=0.005)
    serve.add_argument("--spacing", type=float, default=0.12)
    serve.add_argument("--scenario", choices=["mixed", "stream"], default="mixed")
    for name in ["observe", "submit", "status"]:
        p = commands.add_parser(name)
        p.add_argument("--episode", type=Path, required=True)
        if name == "submit":
            p.add_argument("--command", dest="command_payload", required=True, help="Explicit timestamped motion sequence as JSON")
    args = parser.parse_args(argv)
    if args.command == "serve":
        if args.episode.exists():
            raise ValueError("Choose a new episode directory")
        config = RealtimeConfig(seed=args.seed, target_color=args.target, instruction=args.instruction,
                                actor=args.actor, belt_speed=args.speed, spacing=args.spacing, scenario=args.scenario)
        result = Runtime(RealtimeTrial(config), args.episode).run()
        print(json.dumps({k: result[k] for k in ["sorting_success", "realtime_healthy", "max_simulation_lag_s", "scoring"]}, indent=2))
        return 0 if result["sorting_success"] else 1
    if args.command == "status":
        path = args.episode / "report.json"
        if not path.exists():
            path = args.episode / "status.json"
        result = json.loads(path.read_text())
    else:
        payload = {"kind": args.command}
        if args.command == "submit":
            payload["command"] = json.loads(args.command_payload)
        result = request(args.episode, payload)
    print(json.dumps(result, indent=2))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
