"""RGB and proprioception boundary; no model API or object-state policy inputs."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import uuid

import mujoco
import numpy as np
from PIL import Image

from .environment import Environment
from .interface import PolicyInterface

WIDTH, HEIGHT = 960, 720
VERSION = 'humanoid-visual-v1'


def integration_state(env):
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    value = np.empty(mujoco.mj_stateSize(env.model, spec))
    mujoco.mj_getState(env.model, env.data, value, spec)
    return value


def state_key(env):
    # Private freshness check: never include simulator-state hashes in policy inputs.
    return hashlib.sha256(integration_state(env).tobytes()).hexdigest()


def calibration(camera):
    forward = np.asarray(camera.forward, dtype=float); forward /= np.linalg.norm(forward)
    up = np.asarray(camera.up, dtype=float); up /= np.linalg.norm(up)
    right = np.cross(forward, up); right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    near = float(camera.frustum_near)
    vertical = float(camera.frustum_top-camera.frustum_bottom)
    focal = HEIGHT*near/vertical
    center = float(camera.frustum_center)
    # Pixel coordinates address pixel centers; y points down in exported camera frame.
    return {'width': WIDTH, 'height': HEIGHT, 'projection': 'pinhole',
            'camera_world_xyz_m': list(map(float, camera.pos)),
            'world_to_camera_rotation': np.stack([right, -up, forward]).tolist(),
            'focal_xy_px': [focal, focal],
            'principal_xy_px': [(WIDTH-1)/2-center*focal/near,
                                (HEIGHT-1)/2+(float(camera.frustum_top+camera.frustum_bottom)/2)*focal/near],
            'axes': 'camera X right, Y down, Z forward; world Z up; pixel centers indexed from 0'}


def project(world_xyz, camera):
    local = np.asarray(camera['world_to_camera_rotation']) @ (np.asarray(world_xyz)-camera['camera_world_xyz_m'])
    if local[2] <= 0: raise ValueError('Point behind camera')
    return (np.asarray(camera['principal_xy_px']) + np.asarray(camera['focal_xy_px'])*local[:2]/local[2]).tolist()


def pixel_to_plane(pixel_xy, plane_z, camera):
    """Conventional perception helper with explicit known-plane assumption, not depth."""
    point = np.asarray(pixel_xy, dtype=float)
    if point.shape != (2,) or not np.isfinite(point).all() or not np.isfinite(plane_z):
        raise ValueError('Invalid pixel/plane')
    if not (0 <= point[0] < camera['width'] and 0 <= point[1] < camera['height']):
        raise ValueError('Pixel outside image')
    ray = np.r_[(point-camera['principal_xy_px'])/camera['focal_xy_px'],1.]
    ray = np.asarray(camera['world_to_camera_rotation']).T @ ray
    origin = np.asarray(camera['camera_world_xyz_m'])
    if abs(ray[2]) < 1e-10: raise ValueError('Ray parallel to plane')
    distance = (plane_z-origin[2])/ray[2]
    if distance <= 0: raise ValueError('Plane behind camera')
    return (origin+distance*ray).tolist()


class RGBRenderer:
    def __init__(self, env, camera='fixed'):
        if camera not in ('fixed', 'head'): raise ValueError('Unknown camera')
        self.env, self.camera = env, camera
        self.renderer = mujoco.Renderer(env.model, HEIGHT, WIDTH)
    def close(self): self.renderer.close()
    def capture(self):
        env = self.env
        scratch = mujoco.MjData(env.model)
        mujoco.mj_copyData(scratch, env.model, env.data)
        mujoco.mj_forward(env.model, scratch)
        camera = 'head'
        if self.camera == 'fixed':
            camera = mujoco.MjvCamera()
            camera.lookat[:] = [.24, -.24, .8]
            camera.distance = 1.35; camera.azimuth = 90; camera.elevation = -65
        option = mujoco.MjvOption(); option.sitegroup[:] = 0
        self.renderer.update_scene(scratch, camera=camera, scene_option=option)
        gl = mujoco.mjv_averageCamera(self.renderer.scene.camera[0], self.renderer.scene.camera[1])
        image = Image.fromarray(self.renderer.render())
        output = io.BytesIO(); image.save(output, format='PNG')
        return output.getvalue(), calibration(gl)


class VisualSession:
    def __init__(self, env, renderer):
        self.env, self.renderer = env, renderer
        self.api = PolicyInterface(env, 'robot_state')
        self.pending = None
    def capture(self):
        robot = self.api.observe()
        before = state_key(self.env)
        png, camera = self.renderer.capture()
        if state_key(self.env) != before: raise RuntimeError('Renderer changed physics state')
        identifier = uuid.uuid4().hex
        self.pending = (identifier, before)
        return {'schema_version': VERSION, 'observation_id': identifier, 'time_s': robot['time_s'],
                'robot_state': robot, 'camera': camera,
                'rgb_png_base64': base64.b64encode(png).decode('ascii')}
    def execute(self, observation_id, request):
        if self.pending is None or observation_id != self.pending[0] or state_key(self.env) != self.pending[1]:
            result = {'status': 'rejected', 'error': 'Stale or unknown visual observation',
                      'observation': self.api.observe()}
            self.env.events.append({'visual_observation_id': observation_id, 'interface_request': request,
                                    'interface_response': result, 'score': self.env.scorer.report()})
            self.pending = None
            return result
        self.pending = None  # One action attempt consumes the observation, including rejection.
        return self.api.execute(request)


def detect_red_pixels(png):
    """Pixel-only perception development helper; no robot/world state access."""
    rgb = np.asarray(Image.open(io.BytesIO(png)).convert('RGB'), dtype=float)
    r,g,b = rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
    mask = (r > 65) & (r > 1.8*g) & (r > 1.8*b)
    coords = np.argwhere(mask)
    if len(coords) < 25: return {'detected': False, 'reason': 'insufficient_red_pixels'}
    return {'detected': True, 'pixel_count': len(coords),
            'centroid_xy_px': coords[:,::-1].mean(axis=0).tolist(),
            'bbox_xyxy_px': [int(coords[:,1].min()),int(coords[:,0].min()),int(coords[:,1].max()),int(coords[:,0].max())],
            'assumption': 'single red object; visible red surface only, not a 3D pose'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--camera', choices=['fixed','head'], default='fixed')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    env = Environment(); env.load(args.episode)
    renderer = RGBRenderer(env,args.camera)
    try: observation = VisualSession(env,renderer).capture()
    finally: renderer.close()
    png = base64.b64decode(observation['rgb_png_base64'])
    (args.output/'rgb.png').write_bytes(png)
    (args.output/'observation.json').write_text(json.dumps(observation,indent=2)+'\n')
    print(json.dumps({'output':str(args.output),'camera':args.camera,'time_s':observation['time_s'],
                      'observation_id':observation['observation_id']}))


if __name__ == '__main__': main()
