"""Guarded offline test runner for Task 010.

Executes only offline unit and audit tests with strict process-level guards preventing:
- Any live model or API invocations (including Codex CLI exec decisions)
- Any MuJoCo physics steps (mj_step, mj_step1, mj_step2)
- Any Environment instantiation or resets
"""
import os
import sys
import subprocess
import unittest
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def guard_offline_execution():
    """Install process-level guards against physics steps, resets, and live exec calls."""
    import mujoco
    import humanoid_sim.environment

    def forbidden_physics(*args, **kwargs):
        raise AssertionError("Physics step forbidden in offline tests (R4 guard)")

    def forbidden_env_init(*args, **kwargs):
        raise AssertionError("Environment instantiation forbidden in offline tests (R4 guard)")

    def forbidden_env_reset(*args, **kwargs):
        raise AssertionError("Environment.reset forbidden in offline tests (R4 guard)")

    mujoco.mj_step = forbidden_physics
    mujoco.mj_step1 = forbidden_physics
    mujoco.mj_step2 = forbidden_physics
    humanoid_sim.environment.Environment.__init__ = forbidden_env_init
    humanoid_sim.environment.Environment.reset = forbidden_env_reset

    # Guard against live subprocess model calls (e.g. codex exec)
    orig_popen = subprocess.Popen

    def guarded_popen(cmd, *args, **kwargs):
        cmd_list = cmd if isinstance(cmd, (list, tuple)) else str(cmd).split()
        if any(arg == 'exec' for arg in cmd_list):
            raise AssertionError(f"Live Codex process execution forbidden in offline tests: {cmd}")
        return orig_popen(cmd, *args, **kwargs)

    subprocess.Popen = guarded_popen

    orig_run = subprocess.run

    def guarded_run(cmd, *args, **kwargs):
        cmd_list = cmd if isinstance(cmd, (list, tuple)) else str(cmd).split()
        if any(arg == 'exec' for arg in cmd_list):
            raise AssertionError(f"Live Codex process execution forbidden in offline tests: {cmd}")
        return orig_run(cmd, *args, **kwargs)

    subprocess.run = guarded_run


class Tee:
    def __init__(self, *files):
        self.files = files

    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()

    def flush(self):
        for f in self.files:
            f.flush()


def main():
    log_path = REPO_ROOT / 'coordination/agy/reports/010-focused-tests.log'
    if '--log' in sys.argv:
        idx = sys.argv.index('--log')
        if idx + 1 < len(sys.argv):
            log_path = Path(sys.argv[idx + 1])

    log_file = open(log_path, 'w', encoding='utf-8')
    orig_stdout, orig_stderr = sys.stdout, sys.stderr
    sys.stdout = Tee(orig_stdout, log_file)
    sys.stderr = Tee(orig_stderr, log_file)

    try:
        print("======================================================================")
        print("Task 010 Offline Software Verification Suite")
        print("Label: offline_synthetic_software_check (Zero-Physics / Zero-Reset / Zero-Model)")
        print("======================================================================")

        guard_offline_execution()

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        # Targeted offline test modules only (no discovery over physics integration tests)
        modules = [
            'tests.test_codex_policy',
            'tests.test_codex_c1_audit',
            'tests.test_codex_c2_audit',
        ]

        for mod_name in modules:
            try:
                mod = __import__(mod_name, fromlist=['*'])
                suite.addTests(loader.loadTestsFromModule(mod))
            except Exception as exc:
                print(f"FAILED to load {mod_name}: {exc}")
                sys.exit(1)

        runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
        result = runner.run(suite)

        print("\n======================================================================")
        print(f"Summary: ran {result.testsRun} tests, {len(result.failures)} failures, {len(result.errors)} errors")
        print("======================================================================")

        if not result.wasSuccessful():
            sys.exit(1)
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        log_file.close()


if __name__ == '__main__':
    main()
