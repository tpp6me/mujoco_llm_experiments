"""Graphics calibration check on a development seed, outside evaluated trials."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import mujoco
import numpy as np

from conveyor_sim.camera import HEIGHT, WIDTH, add_rulers, configure, detect_pixels, pixel_to_world
from conveyor_sim.realtime import RealtimeConfig, RealtimeTrial

env = RealtimeTrial(RealtimeConfig(seed=42, actor="test"))
env.wait(0.5)
configure(env.model)
mujoco.mj_forward(env.model, env.data)
output = Path("runtime/conveyor/camera_debug.png")
output.parent.mkdir(parents=True, exist_ok=True)
with mujoco.Renderer(env.model, width=WIDTH, height=HEIGHT) as renderer:
    renderer.update_scene(env.data, camera="overhead")
    add_rulers(renderer.render(), env.data.time).save(output)
detections = detect_pixels(output)
assert len(detections) == 3, detections
errors = []
for cube in env.cubes:
    detection = next(d for d in detections if d["perceived_color"] == cube.color)
    error = float(np.linalg.norm(np.asarray(pixel_to_world(detection["pixel_xy"])) - env.observations()[cube.id].position[:2]))
    assert error < 0.003, (cube, error)
    errors.append({"color": cube.color, "position_error_m": error, "pixel_xy": detection["pixel_xy"]})
print(json.dumps({"image": str(output), "calibration_passed": True, "checks": errors}, indent=2))
