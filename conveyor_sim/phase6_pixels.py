"""Conventional pixel baseline with calibrated ROI rotation."""
from collections import deque
import math
import numpy as np
from PIL import Image
from .camera import CAMERA_POSITION, WIDTH, HEIGHT, METRES_PER_PIXEL

def detect_pixels(image_path, degrees=0):
    """Conventional baseline only: threshold colors and find connected pixel regions."""
    rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=float)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    vv, uu = np.indices(r.shape)
    world_x = CAMERA_POSITION[0] + (uu - WIDTH / 2) * METRES_PER_PIXEL
    world_y = CAMERA_POSITION[1] - (vv - HEIGHT / 2) * METRES_PER_PIXEL
    a = math.radians(degrees)
    dx, dy = world_x - 0.22, world_y + 0.18
    world_x = 0.22 + math.cos(a) * dx - math.sin(a) * dy
    world_y = -0.18 + math.sin(a) * dx + math.cos(a) * dy
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
