import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from conveyor_sim.phase6_scene import Config, Trial, RuleScorer, parse_instruction, pixel_to_world
from conveyor_sim.phase6_runtime import Runtime
from conveyor_sim.scoring import Cube, Observation
from test_camera import command


class Phase6Tests(unittest.TestCase):
    def test_balanced_layouts_and_counting_truth(self):
        for color in ['red', 'green', 'blue']:
            ranks=[]
            for layout in range(3):
                env=Trial(Config(seed=42,layout=layout,target_color=color,rule_colors=(color,)),capture=False)
                ranks.append([c['color'] for c in reversed(env.initial)].index(color))
            self.assertEqual(sorted(ranks), [0,1,2])
        env=Trial(Config(seed=42,scenario='stream',target_color='green',rule_colors=('green',),rule_count=2))
        self.assertEqual(env.target_ids,['cube_002','cube_001'])

    def test_rule_scorer_counts_miss_without_promoting_third(self):
        cubes=[Cube(f'cube_{i:03}', 'green') for i in range(3)]
        scorer=RuleScorer(cubes, ['cube_002','cube_001'])
        obs={c.id:Observation((.22,.50,-.22),(.015,)*3,(0,0,0),('pass_bin_floor',)) for c in cubes}
        scorer.update(0,obs); scorer.update(.4,obs)
        self.assertEqual(scorer.summary()['outcomes'], {'correct_pass':1,'target_missed':2})

    def test_camera_geometry_and_parser(self):
        np.testing.assert_allclose(pixel_to_world([480,360],15),[.22,-.18])
        delta=np.asarray(pixel_to_world([500,360],15))-[.22,-.18]
        self.assertGreater(delta[1],0)
        self.assertEqual(parse_instruction('Reject red and blue cubes; let the others pass.'),(['red','blue'],3))
        self.assertEqual(parse_instruction('Reject the next two green cubes; let the rest pass.'),(['green'],2))
        with self.assertRaises(ValueError): parse_instruction('Reject red or maybe blue')

    def test_switch_cancels_pending_and_rejects_stale_observation(self):
        config=Config(seed=42,front_y=-.20,spacing=.10,switch_at_s=20,
                      next_instruction='Reject blue cubes; let the others pass.',next_colors=('blue',))
        with tempfile.TemporaryDirectory() as folder:
            runtime=Runtime(Trial(config),folder)
            try:
                runtime.epoch=time.monotonic()
                runtime.begin_image('obs')
                old={**command([480,400]),'rule_version':0}
                event=runtime.submit(old,'old')
                self.assertEqual(event['status'],'planning')
                runtime.env.data.time=20
                runtime.apply_rule_change()
                self.assertEqual(event['status'],'cancelled_rule_change')
                self.assertEqual(runtime.submit(old,'stale')['status'],'rejected')
                runtime.begin_image('new')
                self.assertEqual(runtime.pending['new']['rule_version'],1)
                self.assertEqual(runtime.pending['new']['instruction'],config.next_instruction)
                self.assertNotIn('cubes',runtime.pending['new'])
                self.assertEqual(runtime.submit({**old,'rule_version':1},'old_image')['status'],'rejected')
            finally: runtime.pool.shutdown()


if __name__=='__main__': unittest.main()
