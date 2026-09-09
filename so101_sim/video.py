"""Render a saved physics trajectory to a portable H.264 MP4."""

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import mujoco
import numpy as np

from .environment import configure_camera


def record(env, output, fps=30, camera_setup=configure_camera, annotate=None):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("Video export requires ffmpeg on PATH")
    if not 1 <= fps <= 120:
        raise ValueError("Frame rate must be between 1 and 120")
    if not env.frames:
        raise ValueError("No recorded motion; run an episode first")
    output = Path(output).resolve()
    if output.suffix.lower() != ".mp4":
        raise ValueError("Video output must have an .mp4 extension")
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = 960, 720
    times = np.asarray(env.frame_times)
    # Include the final recorded state despite floating-point simulation times.
    frame_count = math.ceil(round(float(times[-1] - times[0]), 6) * fps) + 1
    visual = mujoco.MjData(env.model)
    camera = mujoco.MjvCamera()
    camera_setup(camera)

    # Render scratch data only. Neither the saved episode nor live physics changes.
    with tempfile.TemporaryDirectory(prefix="so101-video-", dir=output.parent) as folder:
        temporary = Path(folder) / "recording.mp4"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "rawvideo", "-pixel_format", "rgb24",
            "-video_size", f"{width}x{height}", "-framerate", str(fps),
            "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast",
            "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(temporary),
        ]
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
            try:
                with mujoco.Renderer(env.model, height=height, width=width) as renderer:
                    for frame in range(frame_count):
                        timestamp = min(times[-1], times[0] + frame / fps)
                        index = max(0, int(np.searchsorted(times, timestamp, side="right")) - 1)
                        visual.qpos[:] = env.frames[index]
                        mujoco.mj_forward(env.model, visual)
                        renderer.update_scene(visual, camera=camera)
                        pixels = renderer.render()
                        if annotate is not None:
                            pixels = annotate(pixels, timestamp)
                        process.stdin.write(pixels.tobytes())
                process.stdin.close()
                returncode = process.wait(timeout=60)
                if returncode:
                    errors.seek(0)
                    raise RuntimeError(f"Video encoding failed: {errors.read().decode(errors='replace')}")
            except BaseException:
                if process.poll() is None:
                    process.kill()
                process.wait()
                if not process.stdin.closed:
                    process.stdin.close()
                raise
        temporary.replace(output)
    return {"video": str(output), "width": width, "height": height,
            "fps": fps, "frames": frame_count, "duration_s": frame_count / fps}
