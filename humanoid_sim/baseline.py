"""Exact-state conventional controller; never invokes an LLM."""
import numpy as np

from .scene import TABLE_Z


def release_target(observation):
    """Center the carried object using exact-state feedback, within tested reach.

    This is a policy decision, not a hidden correction inside the move primitive.
    The object can shift relative to the grasp site during finger closure.
    """
    offset = np.asarray(observation['hand_xyz']) - observation['object_xyz']
    target = np.asarray(observation['basket_xyz'], dtype=float) + offset
    # Larger X targets at this height approach the fixed-orientation IK boundary.
    target[0] = min(float(target[0]), .235)
    target[2] = .86
    return target.tolist()


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
    target = release_target(env.observe())
    env.move(target)
    env.hand(0)
    # Clear the block and rim before traversing back to the parked position.
    env.move([target[0], target[1], .975])
    env.move([.24, -.18, .975])
    env.hold(6)  # Keep the original 25-second episode deadline.
    return None if env.scorer.success else 'placement_failed'
