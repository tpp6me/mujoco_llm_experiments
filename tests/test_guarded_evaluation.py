"""Qualification accounting and immutable, frozen evaluation outputs."""
import json
from pathlib import Path
import tempfile
import unittest

from humanoid_sim.guarded_evaluation import provenance, run_trial, validate


class GuardedEvaluationTests(unittest.TestCase):
    def test_g2_report_accounting_freeze_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'diagnostic'
            summary = validate(root, count=1, first_seed=300, protocol='g2')
            self.assertFalse(summary['gate_passed'])
            self.assertFalse(summary['protocol_matched'])
            self.assertEqual(summary['gate_successes'], 1)
            saved = json.loads((root/'seed-0300/report.json').read_text())
            self.assertEqual(saved, summary['reports'][0])
            self.assertEqual(saved['action_attempts'], 11)
            self.assertEqual(saved['rejected_actions'], 0)
            self.assertEqual(saved['provenance']['policy_configuration']['release_z'], .88)
            with self.assertRaises(FileExistsError):
                validate(root, count=1, first_seed=300, protocol='g2')
            frozen = provenance('g2'); frozen['protocol_id'] = 'different'
            with self.assertRaisesRegex(ValueError, 'Configuration changed'):
                run_trial(Path(folder)/'changed', 300, frozen, protocol='g2')


if __name__ == '__main__': unittest.main()
