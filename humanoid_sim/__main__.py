"""G1 supported-body mechanics. Use mjpython for rendering/viewer on macOS."""
import argparse
import json
from pathlib import Path
import sys
import time

import mujoco

from .environment import Environment, configure_camera
from .scene import ROOT


def view(env, seconds=None):
    from mujoco import viewer as mujoco_viewer
    visual = mujoco.MjData(env.model)
    with mujoco_viewer.launch_passive(env.model, visual) as viewer:
        configure_camera(viewer.cam)
        start = time.monotonic()
        index = 0
        while viewer.is_running() and (seconds is None or time.monotonic()-start < seconds):
            elapsed = time.monotonic()-start
            while index+1 < len(env.frames) and env.frame_times[index+1] <= elapsed:
                index += 1
            visual.qpos[:] = env.frames[index]
            mujoco.mj_forward(env.model, visual)
            viewer.sync()
            time.sleep(1/60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', type=Path, default=ROOT/'runtime/humanoid/demo')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ['demo', 'reset']:
        cmd = commands.add_parser(command)
        cmd.add_argument('--seed', type=int, default=0)
        cmd.add_argument('--randomize', action='store_true')
    commands.add_parser('observe')
    move = commands.add_parser('move')
    move.add_argument('xyz', type=float, nargs=3)
    move.add_argument('--seconds', type=float, default=2)
    hand = commands.add_parser('hand')
    hand.add_argument('closure', type=float, help='0=open, 1=closed')
    hand.add_argument('--seconds', type=float, default=2)
    hold = commands.add_parser('hold')
    hold.add_argument('--seconds', type=float, default=2)
    viewer = commands.add_parser('view')
    viewer.add_argument('--seconds', type=float)
    snap = commands.add_parser('snapshot')
    snap.add_argument('--output', type=Path)
    snap.add_argument('--time', type=float)
    snap.add_argument('--close', action='store_true')
    recording = commands.add_parser('record')
    recording.add_argument('--output', type=Path)
    recording.add_argument('--fps', type=int, default=30)
    validation = commands.add_parser('validate')
    validation.add_argument('--output', type=Path, required=True)
    validation.add_argument('--seeds', type=int, default=100)
    validation.add_argument('--first-seed', type=int, default=0)
    args = parser.parse_args()
    try:
        if args.command == 'validate':
            from .evaluation import validate
            result = validate(args.output, args.seeds, args.first_seed)
            print(json.dumps({k:v for k,v in result.items() if k != 'reports'}, indent=2))
            return 0 if result['gate_passed'] else 1
        if args.command == 'demo':
            from .evaluation import run_trial
            result = run_trial(args.episode, args.seed, args.randomize)
            print(json.dumps(result, indent=2))
            return 0 if result['gate_success'] else 1
        env = Environment()
        if args.command == 'reset':
            if args.episode.exists():
                raise ValueError('Reset needs a new episode directory; choose --episode')
            env.reset(args.seed, args.randomize)
            env.save(args.episode)
            result = env.observe()
        else:
            env.load(args.episode)
            mutating = args.command in {'move', 'hand', 'hold'}
            if mutating and (args.episode/'report.json').exists():
                raise ValueError('Completed baseline trials are immutable; start a new episode with reset')
            try:
                match args.command:
                    case 'observe':
                        result = {'observation':env.observe(), 'score':env.scorer.report()}
                    case 'move': result = env.move(args.xyz, args.seconds)
                    case 'hand': result = env.hand(args.closure, args.seconds)
                    case 'hold': result = env.hold(args.seconds)
                    case 'view':
                        if args.seconds is not None and not 0 < args.seconds < float('inf'):
                            raise ValueError('Viewer duration must be finite and positive')
                        view(env, args.seconds)
                        result = {'episode':str(args.episode)}
                    case 'snapshot':
                        from .render import snapshot
                        result = {'image':snapshot(env, args.output or args.episode/'snapshot.png', args.time, args.close)}
                    case 'record':
                        from .render import record, controller_label
                        report_path = args.episode/'report.json'
                        report = json.loads(report_path.read_text()) if report_path.exists() else {}
                        result = record(env, args.output or args.episode/'pick_place.mp4', args.fps, controller_label(report))
            finally:
                if mutating:
                    env.save(args.episode)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({'error':str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
