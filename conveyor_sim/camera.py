"""Fixed overhead camera calibration and a separately labeled pixel-only baseline."""

from collections import deque
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 960, 720
CAMERA_POSITION = (0.22, -0.18, 0.70)
FOVY = 45.0
TOP_PLANE_Z = 0.030
FOCAL_PX = HEIGHT / (2 * math.tan(math.radians(FOVY) / 2))
METRES_PER_PIXEL = (CAMERA_POSITION[2] - TOP_PLANE_Z) / FOCAL_PX


def calibration():
    return {"width": WIDTH, "height": HEIGHT, "camera_world_xyz_m": list(CAMERA_POSITION),
            "fovy_degrees": FOVY, "focal_length_px": FOCAL_PX,
            "principal_point_px": [WIDTH / 2, HEIGHT / 2], "object_top_plane_z_m": TOP_PLANE_Z,
            "metres_per_pixel_on_top_plane": METRES_PER_PIXEL,
            "pixel_to_world": "x=0.22+(u-480)*metres_per_pixel; y=-0.18-(v-360)*metres_per_pixel",
            "axes": "u right = world +X; v down = world -Y; camera looks straight down"}


def pixel_to_world(pixel):
    point = np.asarray(pixel, dtype=float)
    if point.shape != (2,) or not np.isfinite(point).all() or not (0 <= point[0] < WIDTH and 0 <= point[1] < HEIGHT):
        raise ValueError("Pixel center must be inside the camera image")
    return [CAMERA_POSITION[0] + (point[0] - WIDTH / 2) * METRES_PER_PIXEL,
            CAMERA_POSITION[1] - (point[1] - HEIGHT / 2) * METRES_PER_PIXEL]


def world_to_pixel(xy):
    return [WIDTH / 2 + (xy[0] - CAMERA_POSITION[0]) / METRES_PER_PIXEL,
            HEIGHT / 2 - (xy[1] - CAMERA_POSITION[1]) / METRES_PER_PIXEL]


def configure(model):
    camera_id = model.camera("overhead").id
    model.cam_pos[camera_id] = CAMERA_POSITION
    model.cam_fovy[camera_id] = FOVY


def add_rulers(rgb, timestamp):
    """Static image-coordinate rulers; no object detection or oracle labels."""
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=14)
    for v in range(50, HEIGHT, 50):
        draw.line((35, v, WIDTH - 1, v), fill=(85, 92, 99), width=1)
        draw.text((3, v - 8), str(v), font=font, fill="white", stroke_width=1, stroke_fill="black")
    for u in range(50, WIDTH, 50):
        draw.text((u - 12, 3), str(u), font=font, fill="white", stroke_width=1, stroke_fill="black")
    draw.text((8, HEIGHT - 22), f"Camera at simulation {timestamp:.3f}s | pixel rulers only | belt moves toward image top",
              font=font, fill="white", stroke_width=1, stroke_fill="black")
    return image


def detect_pixels(image_path):
    """Conventional baseline only: threshold colors and find connected pixel regions."""
    rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=float)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    vv, uu = np.indices(r.shape)
    world_x = CAMERA_POSITION[0] + (uu - WIDTH / 2) * METRES_PER_PIXEL
    world_y = CAMERA_POSITION[1] - (vv - HEIGHT / 2) * METRES_PER_PIXEL
    roi = (world_x > 0.16) & (world_x < 0.28) & (world_y > -0.43) & (world_y < 0.06)
    masks = {"red": (r > 60) & (r > 1.5 * g) & (r > 1.5 * b),
             "blue": (b > 60) & (b > 1.4 * r) & (b > 1.2 * g),
             "green": (g > 60) & (g > 1.4 * r) & (g > 1.4 * b)}
    detections = []
    for color, mask in masks.items():
        # Rulers may split a face; connect across a one-pixel horizontal line.
        mask = mask & roi
        mask[1:-1] |= mask[:-2] & mask[2:]
        remaining = set(map(tuple, np.argwhere(mask)))
        while remaining:
            queue = deque([remaining.pop()])
            pixels = []
            while queue:
                v, u = queue.popleft()
                pixels.append((v, u))
                for neighbor in [(v - 1, u), (v + 1, u), (v, u - 1), (v, u + 1)]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        queue.append(neighbor)
            if len(pixels) >= 150:
                center = np.mean(pixels, axis=0)
                detections.append({"perceived_color": color, "pixel_xy": [float(center[1]), float(center[0])],
                                   "area_pixels": len(pixels)})
    return sorted(detections, key=lambda d: d["pixel_xy"][1])
