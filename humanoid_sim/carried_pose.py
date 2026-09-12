"""Experimental monocular cuboid center fitting; not qualified for control.

Inputs are RGB, calibration, known dimensions and robot hand position. No table
plane, object truth, depth image or grasp confirmation is used. Background color
rules are specific to the current scene. Optimization spread is not a confidence
interval and does not enumerate all possible monocular ambiguities.
"""
import io
import itertools

import numpy as np
from PIL import Image


DIMENSIONS = np.array([.05, .07, .12])
HAND_RADIUS_M = .13
STARTS = 20
ITERATIONS = 55
MAX_RMS_PX = .75
NEAR_BEST_PX = .15
MAX_SPREAD_M = .02


def convex_hull(points):
    points = sorted(set(map(tuple, points)))

    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])

    lower, upper = [], []
    for p in points:
        while len(lower) > 1 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper) > 1 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.asarray(lower[:-1]+upper[:-1], dtype=float)


def rotation_vector_matrix(vector):
    angle = np.linalg.norm(vector)
    if angle < 1e-12:
        return np.eye(3)
    x, y, z = vector/angle
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3)+np.sin(angle)*skew+(1-np.cos(angle))*(skew@skew)


def silhouette_features(png, camera):
    with Image.open(io.BytesIO(png)) as image:
        if image.size != (camera['width'], camera['height']):
            raise ValueError('Image dimensions do not match calibration')
        rgb = np.asarray(image.convert('RGB'), dtype=float)
    r, g, b = rgb.transpose(2, 0, 1)
    red = (r > 65) & (r > 1.8*g) & (r > 1.8*b)
    # Treat neutral robot pixels as unknown occluders, not observed object edges.
    background = (((g > 1.4*r) & (b > 1.4*r))
                  | ((r > 1.3*b) & (g > 1.3*b) & (g > 80))
                  | np.all(abs(rgb-[82, 99, 119]) < 3, axis=2)) & ~red
    nearby = np.zeros(red.shape, dtype=bool)
    nearby[1:] |= background[:-1]
    nearby[:-1] |= background[1:]
    nearby[:, 1:] |= background[:, :-1]
    nearby[:, :-1] |= background[:, 1:]
    edges = np.argwhere(red & nearby)[:, ::-1].astype(float)
    points = np.argwhere(red)[:, ::-1].astype(float)
    diagnostics = {'red_pixel_count': len(points), 'boundary_pixel_count': len(edges)}
    if red[0].any() or red[-1].any() or red[:, 0].any() or red[:, -1].any():
        return None, None, {**diagnostics, 'reason': 'image_boundary_truncation'}
    if len(points) < 200 or len(edges) < 30:
        return None, None, {**diagnostics, 'reason': 'insufficient_visible_boundary'}
    return (edges[::max(1, len(edges)//150)],
            points[::max(1, len(points)//200)], diagnostics)


def fit_hypotheses(edges, points, camera, hand):
    corners = np.array(list(itertools.product([-1, 1], repeat=3)))*DIMENSIONS/2
    camera_rotation = np.asarray(camera['world_to_camera_rotation'], dtype=float)
    origin = np.asarray(camera['camera_world_xyz_m'], dtype=float)
    focal = np.asarray(camera['focal_xy_px'], dtype=float)
    principal = np.asarray(camera['principal_xy_px'], dtype=float)
    all_points = np.concatenate([edges, points])

    def residual(parameters):
        world = corners@rotation_vector_matrix(parameters[3:]).T+parameters[:3]
        local = (world-origin)@camera_rotation.T
        uv = local[:, :2]/np.maximum(local[:, 2, None], .01)*focal+principal
        polygon = convex_hull(uv)
        if len(polygon) < 3:
            return np.full(len(all_points)+1, 1e6)
        a, b = polygon, np.roll(polygon, -1, axis=0)
        direction = b-a
        length = np.linalg.norm(direction, axis=1)
        relative = all_points[:, None, :]-a
        t = np.clip(np.sum(relative*direction, axis=2)/length**2, 0, 1)
        distance = np.linalg.norm(relative-t[:, :, None]*direction, axis=2).min(axis=1)
        inside = np.all(direction[:, 0]*relative[:, :, 1]
                        - direction[:, 1]*relative[:, :, 0] >= 0, axis=1)
        proximity = max(0, np.linalg.norm(parameters[:3]-hand)-HAND_RADIUS_M)*1000
        return np.r_[distance[:len(edges)],
                     np.where(inside[len(edges):], 0, distance[len(edges):])*2,
                     proximity]

    rng = np.random.default_rng(1)  # Deterministic optimizer starts, not episode seeds.
    answers = []
    steps = np.array([1e-4]*3+[1e-3]*3)
    for start in range(STARTS):
        parameters = np.r_[hand, np.zeros(3) if start == 0 else rng.uniform(-np.pi, np.pi, 3)]
        damping = 1.
        r = residual(parameters)
        score = r@r
        for _ in range(ITERATIONS):
            jacobian = np.column_stack([
                (residual(parameters+np.eye(6)[j]*steps[j])-r)/steps[j] for j in range(6)])
            try:
                delta = np.linalg.solve(
                    jacobian.T@jacobian+damping*np.diag(np.maximum((jacobian**2).sum(axis=0), 1)),
                    -jacobian.T@r)
            except np.linalg.LinAlgError:
                break
            delta[:3] = np.clip(delta[:3], -.03, .03)
            delta[3:] = np.clip(delta[3:], -.3, .3)
            candidate = parameters+delta
            new_r = residual(candidate)
            new_score = new_r@new_r
            if new_score < score:
                parameters, r, score = candidate, new_r, new_score
                damping = max(damping/2, 1e-5)
                if np.linalg.norm(delta) < 1e-6:
                    break
            else:
                damping = min(damping*5, 1e8)
        world = corners@rotation_vector_matrix(parameters[3:]).T+parameters[:3]
        if (np.linalg.norm(parameters[:3]-hand) > HAND_RADIUS_M
                or np.any(((world-origin)@camera_rotation.T)[:, 2] <= 0)):
            continue
        answers.append({'center_xyz_m': parameters[:3].tolist(),
                        'rotation_world': rotation_vector_matrix(parameters[3:]).tolist(),
                        'rms_px': float(np.sqrt(score/len(r)))})
    return sorted(answers, key=lambda item: item['rms_px'])


def select_hypotheses(hypotheses):
    """Return a candidate only when sampled near-best centers are consistent."""
    if not hypotheses:
        return {'detected': False, 'reason': 'no_feasible_fit'}
    best = min(hypotheses, key=lambda item: item['rms_px'])
    near = [item for item in hypotheses if item['rms_px'] <= best['rms_px']+NEAR_BEST_PX]
    centers = np.array([item['center_xyz_m'] for item in near])
    spread = float(np.linalg.norm(centers[:, None]-centers[None, :], axis=2).max())
    diagnostic = {'best_rms_px': best['rms_px'], 'near_best_count': len(near),
                  'sampled_center_spread_m': spread}
    if best['rms_px'] > MAX_RMS_PX:
        return {'detected': False, 'reason': 'poor_silhouette_fit', **diagnostic}
    if len(near) < 3 or spread > MAX_SPREAD_M:
        return {'detected': False, 'reason': 'ambiguous_depth_or_orientation', **diagnostic}
    return {'detected': True, 'object_center_xyz_m': best['center_xyz_m'], **diagnostic}


def estimate_carried_block(png, camera, hand_xyz_m):
    """Experimental center estimate conditional on a block near the measured hand.

    This proximity assumption is not grasp confirmation. A refusal carries no
    position; the optimizer's best candidate is intentionally not a fallback.
    Rotation is fitted internally, but this API does not qualify orientation.
    """
    hand = np.asarray(hand_xyz_m, dtype=float)
    if hand.shape != (3,) or not np.isfinite(hand).all():
        raise ValueError('Invalid robot hand position')
    for key, shape in [('world_to_camera_rotation', (3, 3)), ('camera_world_xyz_m', (3,)),
                       ('focal_xy_px', (2,)), ('principal_xy_px', (2,))]:
        value = np.asarray(camera[key], dtype=float)
        if value.shape != shape or not np.isfinite(value).all():
            raise ValueError('Invalid camera calibration')
    if np.any(np.asarray(camera['focal_xy_px']) <= 0):
        raise ValueError('Invalid camera focal length')
    edges, points, diagnostics = silhouette_features(png, camera)
    common = {'method': 'monocular_cuboid_silhouette_multistart',
              'experimental': True, 'orientation_qualified': False,
              'assumptions': ['known block dimensions', 'block center within 0.13 m of hand',
                              'single red object', 'fixed calibrated camera and scene colors'],
              **diagnostics}
    if edges is None:
        return {'detected': False, **common}
    return {**select_hypotheses(fit_hypotheses(edges, points, camera, hand)), **common}
