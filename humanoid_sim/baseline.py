"""Exact-state conventional controller; never invokes an LLM."""
from .scene import TABLE_Z


def run_baseline(env):
    x, y, _ = env.observe()['object_xyz']
    # Keep the palm clear of the block before coordinated finger closure.
    x += .015
    env.move([x, y, .975])
    env.move([x, y, TABLE_Z + .075])
    env.hand(1)
    contacts = env.observe()['object_contacts']
    thumb = any('thumb' in name for name in contacts)
    finger = any('index' in name or 'middle' in name for name in contacts)
    if not (thumb and finger):
        return 'grasp_failed'
    env.move([x, y, .975])
    env.hold(.5)
    if env.observe()['object_bottom'] < TABLE_Z + .04:
        return 'lift_failed'
    env.move([.19, -.36, .975])
    env.move([.19, -.36, .86])
    env.hand(0)
    env.move([.24, -.18, .975])
    env.hold(8)
    return None if env.scorer.success else 'placement_failed'
