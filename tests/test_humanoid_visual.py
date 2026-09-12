import base64
import io
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image

from humanoid_sim.environment import Environment
from humanoid_sim.interface import VERSION
from humanoid_sim.visual import VisualSession, integration_state, calibration, project, pixel_to_plane, detect_red_pixels


def png():
    a=np.zeros((20,30,3),dtype=np.uint8);a[5:15,10:20,0]=220
    b=io.BytesIO();Image.fromarray(a).save(b,format='PNG');return b.getvalue()


def camera():
    return calibration(SimpleNamespace(forward=[0,0,-1],up=[0,1,0],pos=[0,0,2],frustum_near=.1,
                                       frustum_top=.05,frustum_bottom=-.05,frustum_center=0))


class Renderer:
    def capture(self):return png(),camera()


def hold():return {'schema_version':VERSION,'instruction_version':1,'request_id':'hold-1','action':'hold','arguments':{'seconds':.02}}


class VisualTests(unittest.TestCase):
    def test_public_rgb_observation_whitelist_and_state_preservation(self):
        env=Environment();s=VisualSession(env,Renderer());before=integration_state(env)
        result=s.capture()
        self.assertEqual(set(result),{'schema_version','observation_id','time_s','robot_state','camera','rgb_png_base64'})
        self.assertNotIn('task_state',result['robot_state']);self.assertNotIn('score',result)
        self.assertEqual(base64.b64decode(result['rgb_png_base64']),png())
        np.testing.assert_array_equal(integration_state(env),before)
        out=s.execute(result['observation_id'],hold())
        self.assertEqual(out['status'],'completed');self.assertNotIn('task_state',out['observation'])
        self.assertEqual(s.execute(result['observation_id'],hold())['status'],'rejected')

    def test_new_capture_invalidates_previous_frame(self):
        env=Environment();s=VisualSession(env,Renderer());old=s.capture();new=s.capture();before=integration_state(env)
        self.assertNotEqual(old['observation_id'],new['observation_id'])
        self.assertEqual(s.execute(old['observation_id'],hold())['status'],'rejected')
        np.testing.assert_array_equal(integration_state(env),before)

    def test_same_time_state_change_invalidates_frame(self):
        env=Environment();s=VisualSession(env,Renderer());observation=s.capture()
        env.data.qvel[0]+=.001;before=integration_state(env)
        self.assertEqual(s.execute(observation['observation_id'],hold())['status'],'rejected')
        np.testing.assert_array_equal(integration_state(env),before)

    def test_rejected_action_consumes_frame(self):
        env=Environment();s=VisualSession(env,Renderer());observation=s.capture();request=hold();request['arguments']['seconds']=-1
        self.assertEqual(s.execute(observation['observation_id'],request)['status'],'rejected')
        self.assertIn('Stale',s.execute(observation['observation_id'],hold())['error'])

    def test_plane_projection_roundtrip_and_bad_rays(self):
        c=camera();point=[.2,.1,.7]
        np.testing.assert_allclose(pixel_to_plane(project(point,c),.7,c),point,atol=1e-12)
        with self.assertRaises(ValueError):project([0,0,3],c)
        with self.assertRaises(ValueError):pixel_to_plane([-1,10],.7,c)
        with self.assertRaises(ValueError):pixel_to_plane([100,100],3,c)

    def test_detector_uses_pixels_and_handles_absence(self):
        d=detect_red_pixels(png());self.assertEqual(d['pixel_count'],100)
        self.assertEqual(d['centroid_xy_px'],[14.5,9.5])
        b=io.BytesIO();Image.new('RGB',(30,20)).save(b,format='PNG')
        self.assertFalse(detect_red_pixels(b.getvalue())['detected'])


if __name__=='__main__':unittest.main()
