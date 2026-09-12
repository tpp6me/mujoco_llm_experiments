"""Experimental RGB/hand-motion rigid-transform consistency check.

A block fixed relative to the hand is a hypothesis, not grasp confirmation.
Failure means these observations do not support this model; it does not identify
slip uniquely. This candidate is not connected to the acting perception session.
"""
import base64
import itertools

import numpy as np

from .carried_pose import (DIMENSIONS, HAND_RADIUS_M, ITERATIONS, STARTS,
                           convex_hull, fit_hypotheses, rotation_vector_matrix, select_hypotheses,
                           silhouette_features)

WINDOW_SIZE = 3
MIN_BASELINE_M = .08
MAX_GAP_S = 3.
CORNERS = np.array(list(itertools.product([-1, 1], repeat=3)))*DIMENSIONS/2


def quaternion_matrix(quaternion):
    q = np.asarray(quaternion, dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
        raise ValueError('Invalid hand quaternion')
    w, x, y, z = q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def prepare_frame(observation):
    camera = observation['camera']
    robot = observation['robot_state']['robot']
    hand = np.asarray(robot['hand_xyz_m'], dtype=float)
    if hand.shape != (3,) or not np.isfinite(hand).all():
        raise ValueError('Invalid hand position')
    rotation = quaternion_matrix(robot['hand_quaternion_wxyz'])
    geometry = {}
    for target, key, shape in [('origin', 'camera_world_xyz_m', (3,)),
                               ('rotation', 'world_to_camera_rotation', (3, 3)),
                               ('focal', 'focal_xy_px', (2,)),
                               ('principal', 'principal_xy_px', (2,))]:
        value = np.asarray(camera[key], dtype=float)
        if value.shape != shape or not np.isfinite(value).all():
            raise ValueError('Invalid camera calibration')
        geometry[target] = value
    if np.any(geometry['focal'] <= 0):
        raise ValueError('Invalid camera focal length')
    cam_rot = geometry['rotation']
    if (not np.allclose(cam_rot.T @ cam_rot, np.eye(3), atol=1e-4)
            or abs(float(np.linalg.det(cam_rot)) - 1.0) > 1e-4):
        raise ValueError('Invalid camera rotation')
    png = base64.b64decode(observation['rgb_png_base64'], validate=True)
    edges, points, diagnostics = silhouette_features(png, camera)
    if edges is None:
        return None, diagnostics
    return {'hand': hand, 'rotation': rotation, 'camera': geometry,
            'points': np.concatenate([edges, points]), 'edge_count': len(edges),
            'time_s': float(observation['time_s'])}, diagnostics


def frame_residual(parameters, frame):
    rotation = frame['rotation']@rotation_vector_matrix(parameters[3:])
    center = frame['hand']+frame['rotation']@parameters[:3]
    world = CORNERS@rotation.T+center
    camera = frame['camera']
    local = (world-camera['origin'])@camera['rotation'].T
    uv = local[:, :2]/np.maximum(local[:, 2, None], .01)*camera['focal']+camera['principal']
    polygon = convex_hull(uv)
    if len(polygon) < 3:
        return np.full(len(frame['points']), 1e6)
    direction = np.roll(polygon, -1, axis=0)-polygon
    length = np.linalg.norm(direction, axis=1)
    relative = frame['points'][:, None, :]-polygon
    t = np.clip(np.sum(relative*direction, axis=2)/length**2, 0, 1)
    distance = np.linalg.norm(relative-t[:, :, None]*direction, axis=2).min(axis=1)
    inside = np.all(direction[:, 0]*relative[:, :, 1]
                    - direction[:, 1]*relative[:, :, 0] >= 0, axis=1)
    n = frame['edge_count']
    return np.r_[distance[:n], np.where(inside[n:], 0, distance[n:])*2]


def fit_window(frames):
    """Fit one object-to-hand translation/rotation to all supplied views."""
    def residual(parameters):
        return np.r_[np.concatenate([frame_residual(parameters, frame)/np.sqrt(len(frame['points']))
                                     for frame in frames]),
                     max(0, np.linalg.norm(parameters[:3])-HAND_RADIUS_M)*1000]

    # Seed with single-view fits to the newest image; these are hypotheses,
    # never accepted positions or private truth supplied to the temporal fit.
    newest = frames[-1]
    c = newest['camera']
    camera = {'world_to_camera_rotation': c['rotation'], 'camera_world_xyz_m': c['origin'],
              'focal_xy_px': c['focal'], 'principal_xy_px': c['principal']}
    n = newest['edge_count']
    single = fit_hypotheses(newest['points'][:n], newest['points'][n:], camera, newest['hand'])
    starts = []
    for hypothesis in single:
        relative = newest['rotation'].T@np.array(hypothesis['rotation_world'])
        angle = np.arccos(np.clip((np.trace(relative)-1)/2, -1, 1))
        if angle < 1e-8:
            vector = np.zeros(3)
        elif np.pi-angle < 1e-5:
            _, axes = np.linalg.eigh((relative+relative.T+2*np.eye(3))/4)
            vector = axes[:, -1]*angle
        else:
            vector = np.array([relative[2, 1]-relative[1, 2], relative[0, 2]-relative[2, 0],
                               relative[1, 0]-relative[0, 1]])*angle/(2*np.sin(angle))
        starts.append(np.r_[newest['rotation'].T@(np.array(hypothesis['center_xyz_m'])-newest['hand']), vector])
    rng = np.random.default_rng(1)
    while len(starts) < STARTS:
        starts.append(np.r_[np.zeros(3), rng.uniform(-np.pi, np.pi, 3)])
    answers = []
    steps = np.array([1e-4]*3+[1e-3]*3)
    for parameters in starts[:STARTS]:
        r = residual(parameters)
        score, damping = r@r, 1.
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
        if np.linalg.norm(parameters[:3]) > HAND_RADIUS_M:
            continue
        in_front = True
        for frame in frames:
            world = (CORNERS@(frame['rotation']@rotation_vector_matrix(parameters[3:])).T
                     + frame['hand']+frame['rotation']@parameters[:3])
            if np.any(((world-frame['camera']['origin'])@frame['camera']['rotation'].T)[:, 2] <= 0):
                in_front = False
        if not in_front:
            continue
        rms = [float(np.sqrt(np.mean(frame_residual(parameters, f)**2))) for f in frames]
        answers.append({'center_xyz_m': (frames[-1]['hand']+frames[-1]['rotation']@parameters[:3]).tolist(),
                        'rms_px': max(rms), 'frame_rms_px': rms,
                        'object_to_hand_offset_m': parameters[:3].tolist()})
    return sorted(answers, key=lambda item: item['rms_px'])


class TemporalPose:
    """One instance per episode; clear history on loss, gap or inconsistent fit.

    Only fresh observations contribute. No extrapolated or stale position is
    emitted while warming up or after refusal. Call invalidate() on known release
    or reset; the evaluator separately challenges an unannounced release.
    """
    def __init__(self, reacquisition=False, min_reacquisition_frames=2):
        self.reacquisition = bool(reacquisition)
        self.min_reacquisition_frames = int(min_reacquisition_frames)
        self.recovering = False
        self.frames = []
        self.seen = set()
        self.last_time = None

    def invalidate(self):
        self.frames.clear()
        self.recovering = False

    def observe(self, observation):
        try:
            identifier = observation['observation_id']
            timestamp = float(observation['time_s'])
        except (KeyError, TypeError, ValueError, OverflowError):
            self.invalidate()
            raise ValueError('Invalid temporal observation metadata') from None
        if (not isinstance(identifier, str) or not identifier or identifier in self.seen
                or not np.isfinite(timestamp)
                or (self.last_time is not None and timestamp <= self.last_time)):
            self.invalidate()
            raise ValueError('Temporal observations require unique IDs and strictly increasing time')
        self.seen.add(identifier)
        if self.last_time is not None and timestamp-self.last_time > MAX_GAP_S:
            self.invalidate()
        self.last_time = timestamp
        try:
            frame, diagnostic = prepare_frame(observation)
        except Exception:
            self.invalidate()
            raise
        common = {'observation_id': identifier, 'time_s': timestamp,
                  'method': 'temporal_rigid_cuboid_silhouette', 'experimental': True,
                  'orientation_qualified': False, 'rigid_grasp_confirmed': False,
                  'reacquisition_mode': self.reacquisition,
                  'min_reacquisition_frames': self.min_reacquisition_frames,
                  'assumptions': ['one fixed object-to-hand transform within each window',
                                  'known cuboid and P3 scene-color segmentation'], **diagnostic}
        if frame is None:
            self.invalidate()
            return {'detected': False, 'history_size': 0, **common}
        self.frames.append(frame)
        self.frames = self.frames[-WINDOW_SIZE:]
        baseline = max(np.linalg.norm(a['hand']-b['hand']) for a in self.frames for b in self.frames)
        common.update({'history_size': len(self.frames), 'hand_baseline_m': float(baseline),
                       'window_times_s': [f['time_s'] for f in self.frames]})
        required_frames = max(2, self.min_reacquisition_frames) if self.recovering else 2
        if len(self.frames) < required_frames or baseline < MIN_BASELINE_M:
            return {'detected': False, 'reason': 'insufficient_motion_history', **common}
        hypotheses = fit_window(self.frames)
        result = select_hypotheses(hypotheses)
        if hypotheses:
            common['best_window_rms_px'] = hypotheses[0]['frame_rms_px']
        if result.get('reason') in ('poor_silhouette_fit', 'no_feasible_fit'):
            result['reason'] = 'inconsistent_rigid_transform'
            if self.reacquisition:
                self.frames = [frame]
                self.recovering = True
                common['reacquisition_seeded'] = True
            else:
                self.invalidate()
            common['history_cleared'] = True
        elif result.get('detected'):
            self.recovering = False
        return {**result, **common}


class TemporalReacquisitionPose(TemporalPose):
    """Two-frame temporal pose tracker with reacquisition enabled (Task 001).

    On model mismatch, retains only the current valid image as a new seed.
    Requires subsequent fresh motion evidence (>=80 mm); fits across 2 or 3 frames.
    Disconnected from control.
    """
    def __init__(self, min_reacquisition_frames=2):
        super().__init__(reacquisition=True, min_reacquisition_frames=min_reacquisition_frames)


class TemporalThreeFrameReacquisitionPose(TemporalPose):
    """Three-frame temporal pose tracker with reacquisition enabled (Task 002).

    On model mismatch, retains only the current valid image as a new seed.
    Requires at least three distinct, fresh observations since the recovery seed
    (e.g. seed + intermediate + endpoint) and >=80 mm motion before emitting a center.
    Disconnected from control.
    """
    def __init__(self):
        super().__init__(reacquisition=True, min_reacquisition_frames=3)
