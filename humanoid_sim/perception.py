"""Conservative RGB perception: pixel visibility and an initial support prior.

No carried-object 3D estimate is implemented. A successful red-pixel detection
must never be interpreted as a successful grasp or a measured 3D position.
"""
import base64
import math

from .visual import detect_red_pixels
from .vision_pose import estimate_supported_block


class RGBPerception:
    """One instance per episode initialized with an upright block on the table.

    The known support prior expires before the first action attempt, or when
    observation time changes. It cannot be restored by a plausible-looking image.
    """
    def __init__(self):
        self._seen = set()
        self._initial_time = None
        self._last_time = None
        self._support_valid = True

    def invalidate_support(self):
        self._support_valid = False

    def observe(self, observation):
        identifier = observation['observation_id']
        time = float(observation['time_s'])
        if not isinstance(identifier, str) or not identifier or identifier in self._seen:
            raise ValueError('Unknown or reused observation ID')
        if not math.isfinite(time) or (self._last_time is not None and time < self._last_time):
            raise ValueError('Invalid or regressing observation time; create a new tracker for a reset')
        png = base64.b64decode(observation['rgb_png_base64'], validate=True)
        self._seen.add(identifier)
        if self._initial_time is None:
            self._initial_time = time
        elif time != self._initial_time:
            self.invalidate_support()
        self._last_time = time
        visibility = detect_red_pixels(png)
        if self._support_valid:
            pose = estimate_supported_block(png, observation['camera'])
            pose['scope'] = 'initial_upright_table_supported_block'
        else:
            pose = {'detected': False, 'reason': 'support_prior_expired',
                    'scope': 'no_validated_carried_or_released_pose'}
        return {'observation_id': identifier, 'time_s': time,
                'visibility': visibility, 'pose': pose,
                'support_prior_valid': self._support_valid}


class PerceptionSession:
    """Pair a VisualSession with perception and expire priors before actions.

    Instantiate at episode reset. All policy actions must use this wrapper.
    Its underlying VisualSession still enforces physics-state freshness.
    """
    def __init__(self, visual_session):
        self.visual_session = visual_session
        self.perception = RGBPerception()

    def capture(self):
        observation = self.visual_session.capture()
        return observation, self.perception.observe(observation)

    def execute(self, observation_id, request):
        # Even a rejected or stale attempt cannot silently restore the support prior.
        self.perception.invalidate_support()
        return self.visual_session.execute(observation_id, request)
