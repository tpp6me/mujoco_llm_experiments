"""Check native MuJoCo physics, optional rendering, and the macOS viewer."""

import argparse
import platform
import time
from pathlib import Path

import mujoco
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--viewer", action="store_true", help="Open viewer for five seconds")
    args = parser.parse_args()

    scene = Path(__file__).resolve().parents[1] / "scenes" / "basic.xml"
    model = mujoco.MjModel.from_xml_path(str(scene))
    data = mujoco.MjData(model)
    mujoco.mj_step(model, data, nstep=1000)
    mujoco.mj_forward(model, data)
    height = float(data.body("cube").xpos[2])
    if not np.isfinite(data.qpos).all() or not 0.045 < height < 0.055:
        raise RuntimeError(f"Cube did not settle on floor: height={height}")
    if data.ncon == 0:
        raise RuntimeError("Expected cube-floor contacts")
    print(f"Python {platform.python_version()} ({platform.machine()})", flush=True)
    print(f"MuJoCo {mujoco.__version__}: physics OK, t={data.time:.3f}s, cube z={height:.5f}m", flush=True)

    if args.render:
        with mujoco.Renderer(model, height=480, width=640) as renderer:
            renderer.update_scene(data)
            pixels = renderer.render()
            if pixels.shape != (480, 640, 3) or float(pixels.std()) < 1:
                raise RuntimeError("Renderer returned an empty or unexpected image")
            print(f"Rendering OK: {pixels.shape[1]} x {pixels.shape[0]} RGB", flush=True)

    if args.viewer:
        from mujoco import viewer as mujoco_viewer

        mujoco.mj_resetData(model, data)
        mujoco.mj_forward(model, data)
        with mujoco_viewer.launch_passive(model, data) as viewer:
            print("Viewer opened; running for five seconds", flush=True)
            deadline = time.monotonic() + 5
            while viewer.is_running() and time.monotonic() < deadline:
                start = time.monotonic()
                mujoco.mj_step(model, data)
                viewer.sync()
                time.sleep(max(0, model.opt.timestep - (time.monotonic() - start)))
        print("Viewer check complete", flush=True)


if __name__ == "__main__":
    main()
