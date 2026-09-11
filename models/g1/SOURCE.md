# G1 model provenance

Vendored from Google DeepMind MuJoCo Menagerie, `unitree_g1`, commit
`8161bba264d7fa7c99ca301e91e7fb44737676ad`.

Source: https://github.com/google-deepmind/mujoco_menagerie/tree/8161bba264d7fa7c99ca301e91e7fb44737676ad/unitree_g1

The 60 upstream XML, STL, license, and Markdown files are unmodified. Preview PNGs
were omitted. Every downloaded file was verified against its pinned Git blob hash;
`SHA256SUMS.json` additionally records local SHA-256 hashes. The upstream BSD
3-Clause license is retained in `LICENSE`.

`humanoid_sim/scene.py` builds the separate `scenes/g1_pick_place.xml` task scene
from `g1_with_hands.xml`. Task-specific changes are confined to that generated scene:

- Remove the pelvis free joint and upstream stand keyframe for supported-body trials.
- Use 1 ms physics steps and 50 solver iterations.
- Set contact `solref=".004 1"`, `solimp=".95 .99 .001"`.
- Set hand joint friction loss to 0.02 Nm, armature to 0.001, joint actuator force
  limits to ±0.15 Nm for the right hand (±0.35 Nm for the parked left hand),
  and finger position gains to 30. Other robot actuator limits
  and gains retain upstream values.
- Add a grasp site, a head camera, apparatus, lighting, and one free block.

These are development simulation settings, not a calibrated physical G1 model.
No robot collision geometry is disabled and no grasp attachment is introduced.
The rendered support post is decorative; support is imposed by removing the
pelvis free joint. Initial arm posture is set at reset above the object. All
subsequent robot and object motion uses actuator targets and contact physics.
