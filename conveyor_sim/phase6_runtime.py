"""Versioned camera decisions for robustness and instruction-change trials."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import time
import numpy as np

from . import camera
from .environment import ROOT
from .phase6_scene import calibration, pixel_to_world
from .realtime import utc, write_json
from .vision_runtime import VisionRuntime


class Runtime(VisionRuntime):
    def __init__(self, env, directory):
        super().__init__(env, directory)
        self.version = 0
        self.rule_changes = []

    def active_instruction(self):
        return self.env.config.next_instruction if self.version else self.env.config.instruction

    def apply_rule_change(self):
        switch = self.env.config.switch_at_s
        if switch and not self.version and self.env.data.time >= switch:
            self.version = 1
            cancelled = []
            for event in self.env.events:
                if event['status'] in {'planning', 'queued'}:
                    event.update(status='cancelled_rule_change', error='Pending old-rule motion cancelled at instruction change')
                    cancelled.append(event['request_id'])
            self.rule_changes.append({'effective_at_s': switch, 'applied_at_s': float(self.env.data.time),
                                      'instruction': self.active_instruction(), 'cancelled_requests': cancelled})

    def begin_image(self, id):
        super().begin_image(id)
        self.pending[id].update(instruction=self.active_instruction(), calibration=calibration(self.env.config),
                                rule_version=self.version, next_rule_change_at_s=self.env.config.switch_at_s or None,
                                time_mode='continuous_wall_clock_camera_phase6')

    def submit(self, command, request_id):
        command = dict(command)
        version = command.pop('rule_version', None)
        if version != self.version:
            event = {'request_id': request_id, 'command': command, 'rule_version': version,
                     'status': 'rejected', 'error': 'Stale or missing instruction version',
                     'received_at_sim_s': float(self.env.data.time), 'received_at_utc': utc(),
                     'actual_start_s': None, 'actual_end_s': None}
            self.env.events.append(event)
            return event
        observation = self.observations.get(command.get('observation_id'), {}).get('observation', {})
        if observation.get('rule_version') != version:
            return self.submit({**command, 'rule_version': -1}, request_id)
        original_pixel = command.get('pixel_xy')
        try:
            xy = pixel_to_world(original_pixel, self.env.config.camera_rotation)
        except (ValueError, TypeError):
            return super().submit(command, request_id)
        # Parent accepts its fixed calibration; map coordinates algebraically only.
        command['pixel_xy'] = camera.world_to_pixel(xy)
        event = super().submit(command, request_id)
        event['rule_version'] = version
        if 'perception' in event:
            event['perception']['pixel_xy'] = original_pixel
        return event

    def report(self):
        report = super().report()
        events = {e['request_id']: e for e in self.env.events}
        current = []
        for audit in report['perception_audits']:
            event = events[audit['request_id']]
            audit['is_target'] = audit['matched_physical_id'] in self.env.target_ids
            audit['rule_version'] = event.get('rule_version')
            audit['superseded'] = audit['rule_version'] != self.version
            if not audit['superseded']:
                current.append(audit)
        selected = [a['matched_physical_id'] for a in current]
        selection_correct = (set(selected) == set(self.env.target_ids) and
                             all(a['color_correct'] and a['is_target'] for a in current))
        outcomes = report['scoring']['outcomes']
        physical = (outcomes.get('correct_reject', 0) == len(self.env.target_ids) and
                    outcomes.get('correct_pass', 0) == 3 - len(self.env.target_ids) and
                    not report['unintended_cube_contacts'] and not self.env.fixture_contacts and
                    not self.env.neighbor_contacts and self.env.max_tracking_error <= 0.005 and
                    set(self.env.target_ids).issubset(self.env.contact_cubes))
        first_new = [e['received_at_sim_s'] for e in self.env.events if e.get('rule_version') == 1]
        report.update(phase=6, selection_correct=selection_correct, selected_cube_ids=selected,
                      push_success=bool(physical), sorting_success=bool(physical and selection_correct and report['realtime_healthy']),
                      rule_changes=self.rule_changes, final_rule_version=self.version,
                      adaptation_delay_s=min(first_new) - self.env.config.switch_at_s if first_new else None,
                      note='Camera decisions with explicit rule versions; cancelled old-rule commands excluded from final selection scoring.')
        for name in ['conveyor_sim/phase6_scene.py', 'conveyor_sim/phase6_runtime.py', 'conveyor_sim/phase6_render.py',
                     'conveyor_sim/phase6.py', 'conveyor_sim/phase6_pixels.py', 'experiments/conveyor-color-sorting/phase6/PROTOCOL.md',
                     'experiments/conveyor-color-sorting/phase6/cases.json']:
            report['source_sha256'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        return report

    def run(self):
        write_json(self.private / "config.json", asdict(self.env.config))
        with (self.private / "renderer.log").open("w") as log:
            renderer = subprocess.Popen([str(ROOT / ".venv/bin/mjpython"), "-m", "conveyor_sim.phase6_render",
                                         "--episode", str(self.directory)], stdout=log, stderr=subprocess.STDOUT)
        until = time.monotonic() + 30
        while not (self.private / "renderer_ready.json").exists():
            if renderer.poll() is not None or time.monotonic() > until:
                renderer.terminate()
                renderer.wait(timeout=5)
                raise RuntimeError("Camera initialization failed; see private/renderer.log")
            time.sleep(0.01)
        self.env.wait(0.5)
        self.epoch = time.monotonic() - self.env.data.time
        self.wall_started = utc()
        write_json(self.directory / "ready.json", {"started_at_utc": self.wall_started,
                   "instruction": self.env.config.instruction, "observation_mode": "camera"})
        try:
            while self.env.data.time < self.env.deadline:
                now = time.monotonic()
                if now >= self.next_poll:
                    self.apply_rule_change()
                    self.poll_requests()
                    self.prepare_jobs()
                    self.next_poll = now + 0.01
                elapsed = time.monotonic() - self.epoch
                self.max_lag = max(self.max_lag, elapsed - self.env.data.time)
                if elapsed >= self.env.data.time + self.env.model.opt.timestep:
                    self.control_before_step()
                    self.env._step()
                    self.control_after_step()
                else:
                    time.sleep(min(0.001, self.env.data.time + self.env.model.opt.timestep - elapsed))
                if now >= self.next_status:
                    write_json(self.directory / "status.json", {"time_s": float(self.env.data.time),
                               "max_lag_s": self.max_lag, "completed": False,
                               "rule_version": self.version, "instruction": self.active_instruction(),
                               "jobs": [{"object_id": e.get("perception", {}).get("object_id"),
                                         "status": e["status"], "error": e["error"]} for e in self.env.events]})
                    self.next_status = now + 0.5
        except KeyboardInterrupt:
            self.interrupted = True
        except Exception:
            self.interrupted = True
            raise
        finally:
            self.wall_finished = utc()
            for job in self.jobs:
                if job["event"]["status"] in {"planning", "queued", "running"}:
                    job["event"].update(status="unfinished", error="Episode ended before command completed")
            self.pool.shutdown(wait=True)
            (self.private / "render_stop").touch()
            renderer.wait(timeout=10)
            self.env._sample()
            self.env.scorer.finish()
            self.env.completed = True
            write_json(self.private / "report.json", self.report())
            np.savez_compressed(self.private / "episode.npz", phase=6, config=json.dumps(asdict(self.env.config)),
                                frames=np.asarray(self.env.frames), times=np.asarray(self.env.frame_times),
                                score_frames=json.dumps(self.env.score_frames))
            write_json(self.directory / "status.json", {"time_s": float(self.env.data.time), "completed": True})
        return self.report()
