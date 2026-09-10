"""Phase 6 renderer uses exactly the same varied scene as the physics owner."""

import argparse
import json
from pathlib import Path
import time

import mujoco
import numpy as np

from .camera import WIDTH, HEIGHT, add_rulers, configure
from .realtime import write_json
from .phase6_scene import Config, Trial


def serve(directory):
    private = directory / "private"
    env = Trial(Config(**json.loads((private / "config.json").read_text())))
    with mujoco.Renderer(env.model, width=WIDTH, height=HEIGHT) as renderer:
        # Warm up graphics before starting the timed physics run.
        renderer.update_scene(env.data, camera="overhead")
        renderer.render()
        write_json(private / "renderer_ready.json", {"ready": True})
        while not (private / "render_stop").exists():
            for source in sorted((private / "render_requests").glob("*.npz")):
                output = directory / "images" / (source.stem + ".png")
                if output.exists():
                    continue
                with np.load(source, allow_pickle=False) as frame:
                    env.data.qpos[:] = frame["qpos"]
                    timestamp = float(frame["time_s"])
                mujoco.mj_forward(env.model, env.data)
                renderer.update_scene(env.data, camera="overhead")
                image = add_rulers(renderer.render(), timestamp)
                temporary = output.with_suffix(".tmp")
                image.save(temporary, format="PNG")
                temporary.replace(output)
            time.sleep(0.005)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    serve(parser.parse_args().episode)
