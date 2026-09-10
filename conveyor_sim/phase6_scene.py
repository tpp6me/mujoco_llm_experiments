"""Phase 6 scene variations, calibrated camera, and independent rule scoring."""

from dataclasses import dataclass
import math
import re

import mujoco
import numpy as np

from . import camera
from .realtime import RealtimeConfig
from .scoring import Scorer
from .vision_runtime import VisionTrial


@dataclass(frozen=True)
class Config(RealtimeConfig):
    layout: int = 0
    position_spread: float = 0.006
    yaw_limit: float = 0.15
    illumination: float = 1.0
    camera_rotation: float = 0.0
    front_y: float = -0.14
    rule_colors: tuple = ("red",)
    rule_count: int = 3
    switch_at_s: float = 0.0
    next_instruction: str = ""
    next_colors: tuple = ()

    def __post_init__(self):
        super().__post_init__()
        if not 0 <= self.layout < 3 or not 0 < self.position_spread <= 0.015:
            raise ValueError("Invalid layout variation")
        if not 0 <= self.yaw_limit <= 0.8 or not 0.2 <= self.illumination <= 1:
            raise ValueError("Invalid rotation or illumination")
        if abs(self.camera_rotation) > 20 or not -0.20 <= self.front_y <= -0.14:
            raise ValueError("Invalid camera or belt placement")
        if not self.rule_colors or set(self.rule_colors) - {"red", "green", "blue"} or not 1 <= self.rule_count <= 3:
            raise ValueError("Invalid scoring rule")
        if self.switch_at_s and (self.switch_at_s != 20 or not self.next_instruction or
                                 not self.next_colors or set(self.next_colors) - {"red", "blue", "green"} or
                                 self.front_y != -0.20 or self.belt_speed != 0.005):
            raise ValueError("Switch probes must precede every interception")


class RuleScorer(Scorer):
    def __init__(self, cubes, targets):
        super().__init__(cubes)
        self.targets = set(targets)

    def update(self, time_s, observations):
        super().update(time_s, observations)
        for id, result in self.results.items():
            target = id in self.targets
            result["outcome"] = (("correct_reject" if target else "wrong_reject") if result["destination"] == "reject"
                                 else ("target_missed" if target else "correct_pass"))

    def summary(self):
        result = super().summary()
        result.pop("target_color")
        result["target_ids"] = sorted(self.targets)
        return result


class Trial(VisionTrial):
    def __init__(self, config, capture=True):
        super().__init__(config, capture)
        rng = np.random.default_rng(config.seed + 900000)
        for item in self.initial:
            yaw = float(rng.uniform(-config.yaw_limit, config.yaw_limit))
            item["yaw_rad"] = yaw
            joint = self.model.joint(item["id"] + "_joint").id
            address = self.model.jnt_qposadr[joint]
            self.data.qpos[address + 3:address + 7] = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
        final_colors = config.next_colors if config.switch_at_s else config.rule_colors
        ordered = sorted(self.initial, key=lambda c: c["position_m"][1], reverse=True)
        self.target_ids = [c["id"] for c in ordered if c["color"] in final_colors][:config.rule_count]
        self.scorer = RuleScorer(self.cubes, self.target_ids)
        self.frames, self.frame_times, self.score_frames = [], [], []
        configure_camera(self.model, config)
        mujoco.mj_forward(self.model, self.data)
        self._sample()

    def _colors(self, rng):
        if self.config.scenario == "stream":
            return [self.config.target_color] * 3
        colors = ["red", "green", "blue"]
        return colors[self.config.layout:] + colors[:self.config.layout]

    def _initial_position(self, i, rng):
        return [0.22 + rng.uniform(-self.config.position_spread, self.config.position_spread),
                self.config.front_y - (2 - i) * self.config.spacing + rng.uniform(-0.004, 0.004), 0.016]


def configure_camera(model, config):
    camera.configure(model)
    angle = math.radians(config.camera_rotation)
    model.cam_quat[model.camera("overhead").id] = [math.cos(angle / 2), 0, 0, math.sin(angle / 2)]
    model.light_diffuse[:] *= config.illumination
    model.light_ambient[:] *= config.illumination
    model.vis.headlight.diffuse[:] *= config.illumination
    model.vis.headlight.ambient[:] *= config.illumination


def calibration(config):
    result = camera.calibration()
    result.update(rotation_degrees=config.camera_rotation,
                  pixel_to_world="[x,y]=[0.22,-0.18]+R(rotation_degrees)*[(u-480)*scale,-(v-360)*scale]",
                  axes="Calibrated rotation about vertical axis; image need not align with belt")
    return result


def pixel_to_world(pixel, degrees=0):
    unrotated = np.asarray(camera.pixel_to_world(pixel)) - [0.22, -0.18]
    a = math.radians(degrees)
    return (np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]]) @ unrotated + [0.22, -0.18]).tolist()


def parse_instruction(instruction):
    """Conventional finite grammar, declared before trials; no model call."""
    match = re.fullmatch(r"Reject (red|green|blue)(?: and (red|green|blue))? cubes; let the others pass\.", instruction)
    if match:
        return [c for c in match.groups() if c], 3
    match = re.fullmatch(r"Reject the next two (red|green|blue) cubes; let the rest pass\.", instruction)
    if match:
        return [match.group(1)], 2
    raise ValueError("Instruction outside the conventional parser's declared grammar")
