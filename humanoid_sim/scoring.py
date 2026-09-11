"""Physical outcome scoring; receives physics state, never requested actions."""
import mujoco
import numpy as np
from .scene import TABLE_Z, BASKET


class Scorer:
    def __init__(self, model):
        self.model=model
        self.object=model.body('red_block').id
        self.geom=model.geom('object').id
        self.floor=model.geom('basket_floor').id
        self.site=model.site('right_grasp').id
        self.lift_dwell=0.
        self.lifted=False
        self.settled_dwell=0.
        self.success=False
        self.max_bottom=-float('inf')
        self.last_time=None
        self.max_penetration=0.
        self.support_contact=False
        self.hand_contact=False

    def update(self, data):
        dt=0. if self.last_time is None else max(0.,float(data.time)-self.last_time)
        self.last_time=float(data.time)
        p=data.xpos[self.object]
        extent=np.abs(data.xmat[self.object].reshape(3,3)) @ self.model.geom_size[self.geom]
        bottom=float(p[2]-extent[2]);self.max_bottom=max(self.max_bottom,bottom)
        support=False;hand=False
        for c in data.contact:
            if c.geom1==self.geom:other=c.geom2
            elif c.geom2==self.geom:other=c.geom1
            else:continue
            self.max_penetration=max(self.max_penetration,float(-c.dist))
            if c.dist>.0005:continue
            support |= other==self.floor
            name=self.model.body(int(self.model.geom_bodyid[other])).name
            hand |= name.startswith('right_hand_') or name=='right_wrist_yaw_link'
        self.support_contact,self.hand_contact=bool(support),bool(hand)
        self.lift_dwell=self.lift_dwell+dt if bottom>TABLE_Z+.04 and hand else 0.
        self.lifted |= self.lift_dwell>=.2
        inside=bool(np.all(np.abs(p[:2]-BASKET)+extent[:2]<=.085+.0005) and bottom>=TABLE_Z+.012-.0005 and p[2]+extent[2]<=TABLE_Z+.14+.0005)
        velocity=np.zeros(6)
        mujoco.mj_objectVelocity(self.model,data,mujoco.mjtObj.mjOBJ_BODY,self.object,velocity,0)
        slow=np.linalg.norm(velocity[3:])<.02 and np.linalg.norm(velocity[:3])<.15
        withdrawn=np.linalg.norm(data.site_xpos[self.site]-p)>.12
        settled=inside and support and not hand and slow and withdrawn
        self.settled_dwell=self.settled_dwell+dt if settled else 0.
        # Revoke success if the object leaves, moves, or is grasped again.
        self.success=bool(self.lifted and self.settled_dwell>=2.)

    def report(self):
        return {'success':self.success,'lifted':bool(self.lifted),'settled_dwell_s':self.settled_dwell,'max_object_bottom_m':self.max_bottom,'max_object_penetration_m':self.max_penetration,'basket_floor_contact':self.support_contact,'hand_contact':self.hand_contact,'supported_body':True}
