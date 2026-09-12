"""RGB-only initial block-position estimate under declared geometry/lighting priors."""
import io
from collections import deque
import math

import numpy as np
from PIL import Image

from .visual import project


def top_surface_pixels(png):
    rgb=np.asarray(Image.open(io.BytesIO(png)).convert('RGB'),dtype=float)
    r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
    mask=(r>65)&(r>1.8*g)&(r>1.8*b)
    values=r[mask]
    if values.size<100:return None,'insufficient_red_pixels'
    # Two brightness clusters separate the illuminated top from darker side faces.
    low,high=np.percentile(values,[15,85])
    for _ in range(20):
        bright=values>(low+high)/2
        if not bright.any() or bright.all():return None,'ambiguous_surface_brightness'
        new_low,new_high=values[~bright].mean(),values[bright].mean()
        if abs(new_low-low)+abs(new_high-high)<.001:break
        low,high=new_low,new_high
    if high-low<25:return None,'ambiguous_surface_brightness'
    mask &= r>(low+high)/2
    # Keep the largest connected patch; do not merge disconnected red objects.
    remaining=set(map(tuple,np.argwhere(mask)));components=[]
    while remaining:
        queue=deque([remaining.pop()]);pixels=[]
        while queue:
            v,u=queue.popleft();pixels.append((u,v))
            for neighbor in [(v-1,u),(v+1,u),(v,u-1),(v,u+1)]:
                if neighbor in remaining:remaining.remove(neighbor);queue.append(neighbor)
        components.append(pixels)
    components.sort(key=len,reverse=True)
    if not components or len(components[0])<75:return None,'insufficient_top_surface'
    if len(components)>1 and len(components[1])>.15*len(components[0]):return None,'multiple_or_split_surfaces'
    return np.asarray(components[0],dtype=float),None


def estimate_supported_block(png,camera,table_z=.70,dimensions=(.05,.07,.12)):
    """Estimate a table-supported upright block, never its pose during carrying.

    Uses only pixels, calibrated camera and explicit priors. No simulator state.
    The brighter red patch is assumed to be the horizontal top face. Coverage
    checks reject many occlusions but do not prove the assumption is true.
    """
    with Image.open(io.BytesIO(png)) as image:
        if image.size != (camera['width'],camera['height']):
            raise ValueError('Image dimensions do not match calibration')
    pixels,error=top_surface_pixels(png)
    if error:return {'detected':False,'reason':error}
    size=np.asarray(dimensions,dtype=float)
    if size.shape!=(3,) or not np.isfinite(size).all() or np.any(size<=0) or not math.isfinite(table_z):
        raise ValueError('Invalid block/table prior')
    plane=table_z+size[2]
    rays=np.column_stack([(pixels-np.asarray(camera['principal_xy_px']))/np.asarray(camera['focal_xy_px']),np.ones(len(pixels))])
    rays=rays@np.asarray(camera['world_to_camera_rotation'])
    origin=np.asarray(camera['camera_world_xyz_m'])
    if np.any(np.abs(rays[:,2])<1e-10):return {'detected':False,'reason':'parallel_plane_ray'}
    distance=(plane-origin[2])/rays[:,2]
    if np.any(distance<=0):return {'detected':False,'reason':'plane_behind_camera'}
    points=origin+distance[:,None]*rays
    xy=points[:,:2].mean(axis=0)
    covariance=np.cov(points[:,:2].T)
    _,vectors=np.linalg.eigh(covariance)
    long_axis=vectors[:,1]
    yaw=(math.atan2(-long_axis[0],long_axis[1])+math.pi/2)%math.pi-math.pi/2
    c,s=math.cos(yaw),math.sin(yaw);rotation=np.array([[c,-s],[s,c]])
    local=(points[:,:2]-xy)@rotation
    spans=np.ptp(local,axis=0)
    corners=[np.r_[xy+rotation@np.array([sx*size[0]/2,sy*size[1]/2]),plane] for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    polygon=np.asarray([project(p,camera) for p in corners])
    area=abs(np.dot(polygon[:,0],np.roll(polygon[:,1],1))-np.dot(polygon[:,1],np.roll(polygon[:,0],1)))/2
    coverage=len(pixels)/area
    diagnostics={'top_pixel_count':len(pixels),'top_coverage_ratio':float(coverage),'measured_top_spans_m':spans.tolist()}
    if not .8<=coverage<=1.08 or np.any(np.abs(spans-size[:2])>.12*size[:2]):
        return {'detected':False,'reason':'top_shape_or_coverage_mismatch',**diagnostics}
    return {'detected':True,'object_center_xyz_m':[float(xy[0]),float(xy[1]),float(table_z+size[2]/2)],
            'top_face_yaw_rad_mod_pi':yaw,'method':'bright_top_surface_known_plane',
            'assumptions':['upright table-supported known cuboid','single red object','top brighter than side faces','fixed calibrated camera'],**diagnostics}
