"""Render saved trajectories without advancing physics."""
from pathlib import Path
import mujoco
import numpy as np
from PIL import Image
from .environment import configure_camera


def snapshot(env, output, time_s=None, close=False):
    data=mujoco.MjData(env.model)
    if time_s is None: data.qpos[:]=env.data.qpos
    else:
        idx=max(0,int(np.searchsorted(env.frame_times,time_s,side='right'))-1)
        data.qpos[:]=env.frames[idx]
    mujoco.mj_forward(env.model,data)
    camera=mujoco.MjvCamera();configure_camera(camera)
    if close:
        camera.lookat[:]=[.24,-.18,.8];camera.distance=.48;camera.azimuth=100;camera.elevation=-15
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with mujoco.Renderer(env.model,720,960) as renderer:
        renderer.update_scene(data,camera=camera)
        Image.fromarray(renderer.render()).save(output)
    return str(output)


def record(env, output, fps=30):
    from PIL import ImageDraw
    from so101_sim.video import record as record_trajectory

    def annotate(pixels, timestamp):
        frame = Image.fromarray(pixels)
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, 0, 960, 46), fill=(20, 25, 32))
        draw.text((15, 10), f'G1 | fixed pelvis | conventional controller | no LLM | t = {timestamp:.2f}s', fill='white')
        return np.asarray(frame)

    return record_trajectory(env, output, fps, camera_setup=configure_camera, annotate=annotate)
