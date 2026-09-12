"""Guarded policy uses public observations/actions; scorer stays in the evaluator."""
import unittest
from humanoid_sim.environment import Environment
from humanoid_sim.interface import PolicyInterface
from humanoid_sim.guarded_baseline import run_policy


class GuardedBaselineTests(unittest.TestCase):
    def test_withdrawal_regression_via_public_interface_only(self):
        env = Environment(); env.reset(300, True)
        api = PolicyInterface(env)
        class PublicProxy:
            def observe(self): return api.observe()
            def execute(self, request): return api.execute(request)
        self.assertIsNone(run_policy(PublicProxy()))
        self.assertTrue(env.scorer.success)
        self.assertLessEqual(env.scorer.max_penetration, .002)
        self.assertAlmostEqual(env.data.time, 25, places=6)
        self.assertTrue(all(e['interface_response']['status']=='completed' for e in env.events))
        self.assertEqual(len(env.events), 11)

    def test_rejection_stops_policy_without_hidden_retry(self):
        class RejectingAPI:
            calls = 0
            def observe(self): return {'task_state': {'object_xyz': [.24, -.18, .76]}}
            def execute(self, request):
                self.calls += 1
                return {'status': 'rejected', 'error': 'test collision'}
        api=RejectingAPI()
        with self.assertRaisesRegex(RuntimeError, 'test collision'): run_policy(api)
        self.assertEqual(api.calls, 1)


if __name__ == '__main__': unittest.main()
