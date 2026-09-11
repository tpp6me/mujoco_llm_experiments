"""Build the supported-body task without modifying vendored G1 assets."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / 'scenes/g1_pick_place.xml'
COMMIT = '8161bba264d7fa7c99ca301e91e7fb44737676ad'
TABLE_Z = .70
OBJECT_HALF = (.025, .035, .06)
BASKET = (.18, -.36)


def build_scene():
    root = ET.parse(ROOT / 'models/g1/g1_with_hands.xml').getroot()
    root.set('model', 'G1 supported-body pick and basket development task')
    root.find('compiler').set('meshdir', '../models/g1/assets')
    root.find('option').attrib.update(timestep='0.001', iterations='50')
    ET.SubElement(root.find('default'), 'geom', solref='.004 1', solimp='.95 .99 .001')
    root.find(".//default[@class='collision']/geom").attrib.update(solref='.004 1', solimp='.95 .99 .001')
    for joint in root.findall('.//joint'):
        if '_hand_' in joint.get('name', ''):
            joint.attrib.update(frictionloss='.02', armature='.001', actuatorfrcrange='-.15 .15' if joint.get('name', '').startswith('right_hand_') else '-.35 .35')
    for actuator in root.findall('actuator/position'):
        if '_hand_' in actuator.get('name', ''):
            actuator.set('kp', '30')
    root.remove(root.find('keyframe'))
    pelvis = root.find(".//body[@name='pelvis']")
    pelvis.remove(pelvis.find('freejoint'))
    wrist = root.find(".//body[@name='right_wrist_yaw_link']")
    ET.SubElement(wrist, 'site', name='right_grasp', pos='.14 .04 0', size='.004', rgba='0 1 0 1')
    ET.SubElement(root.find(".//body[@name='torso_link']"), 'camera', name='head', pos='.08 0 .35', xyaxes='0 -1 0 .6 0 .8', fovy='65')
    world = root.find('worldbody')
    ET.SubElement(world, 'geom', name='floor', type='plane', size='3 3 .05', rgba='.19 .23 .28 1')
    ET.SubElement(world, 'geom', name='support', type='box', pos='-.10 0 .42', size='.06 .08 .36', rgba='.3 .4 .5 .6', contype='0', conaffinity='0')
    ET.SubElement(world, 'geom', name='table', type='box', pos='.38 -.20 .68', size='.30 .43 .02', rgba='.65 .55 .4 1')
    for y in [-.57, .17]:
        ET.SubElement(world, 'geom', type='box', pos=f'.58 {y} .34', size='.025 .025 .34', rgba='.3 .3 .3 1')
    obj = ET.SubElement(world, 'body', name='red_block', pos='.24 -.18 .761')
    ET.SubElement(obj, 'freejoint', name='object_free')
    ET.SubElement(obj, 'geom', name='object', type='box', size='.025 .035 .06', mass='.06', rgba='.85 .06 .035 1', friction='1 .005 .0001', condim='4')
    basket = ET.SubElement(world, 'body', name='basket', pos=f'{BASKET[0]} {BASKET[1]} {TABLE_Z}')
    ET.SubElement(basket, 'geom', name='basket_floor', type='box', pos='0 0 .006', size='.085 .085 .006', rgba='.15 .5 .65 1')
    for name, pos, size in [('left','-.09 0 .07','.005 .095 .07'),('right','.09 0 .07','.005 .095 .07'),('front','0 -.09 .07','.085 .005 .07'),('back','0 .09 .07','.085 .005 .07')]:
        ET.SubElement(basket, 'geom', name=f'basket_{name}', type='box', pos=pos, size=size, rgba='.15 .5 .65 .7')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='960', offheight='720')
    ET.SubElement(visual, 'headlight', ambient='.35 .35 .35', diffuse='.7 .7 .7')
    ET.indent(root)
    ET.ElementTree(root).write(SCENE, encoding='unicode')
    return SCENE

if __name__ == '__main__':
    print(build_scene())
