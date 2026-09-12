"""Conventional policy using only the shared exact-state interface."""
from .baseline import release_target
from .environment import DOWNWARD
from .interface import VERSION, quaternion
from .scene import TABLE_Z


def run_policy(api, release_z=.90, release_closure=.4):
    counter = 0
    def send(action, arguments):
        nonlocal counter
        counter += 1
        response = api.execute({'schema_version': VERSION, 'instruction_version': 1,
                                'request_id': f'policy-{counter}', 'action': action,
                                'arguments': arguments})
        if response['status'] != 'completed':
            raise RuntimeError(f"{action}: {response['status']}: {response.get('error', '')}")
    def move(xyz):
        send('move', {'xyz_m': list(xyz), 'quaternion_wxyz': quaternion(DOWNWARD), 'seconds': 2})
    def hand(closure): send('hand', {'closure': closure, 'seconds': 2})
    def hold(seconds): send('hold', {'seconds': seconds})
    def observe(): return api.observe()['task_state']
    x, y, _ = observe()['object_xyz']; x += .015
    move([x, y, .975]); move([x, y, TABLE_Z+.075]); hand(1)
    contacts = observe()['object_contacts']
    if not (any('thumb' in n for n in contacts) and any('index' in n or 'middle' in n for n in contacts)):
        return 'grasp_failed'
    move([x, y, .975]); hold(.5)
    if observe()['object_bottom'] < TABLE_Z+.04: return 'lift_failed'
    move([.19, -.36, .975])
    target = release_target(observe()); target[2] = release_z
    move(target); hand(release_closure)
    move([target[0], target[1], .975]); move([.24, -.18, .975]); hold(6)
    return None
