"""Outcome scoring from physical observations, independent of robot commands."""

from collections import Counter
from dataclasses import asdict, dataclass
import math

CONTACT_TOLERANCE_M = 0.0005


@dataclass(frozen=True)
class Region:
    lower: tuple[float, float, float]
    upper: tuple[float, float, float]
    contact_prefix: str

    def contains(self, observation):
        # MuJoCo's compliant contacts can settle slightly inside a tray wall.
        return all(lo - CONTACT_TOLERANCE_M <= p - extent and p + extent <= hi + CONTACT_TOLERANCE_M
                   for lo, hi, p, extent in zip(
            self.lower, self.upper, observation.position, observation.half_extents, strict=True))


PASS_REGION = Region((0.11, 0.41, -0.252), (0.33, 0.73, -0.025), "pass_bin_")
REJECT_REGION = Region((0.29, -0.18, -0.152), (0.51, 0.18, -0.025), "reject_bin_")


@dataclass(frozen=True)
class Cube:
    id: str
    color: str


@dataclass(frozen=True)
class Observation:
    position: tuple[float, float, float]
    half_extents: tuple[float, float, float]
    velocity: tuple[float, float, float]
    contacts: tuple[str, ...]


class Scorer:
    SETTLE_SECONDS = 0.3
    STUCK_SECONDS = 2.0

    def __init__(self, cubes, target_color="red"):
        self.cubes = {cube.id: cube for cube in cubes}
        if len(self.cubes) != len(cubes):
            raise ValueError("Cube IDs must be unique")
        if target_color not in {"red", "blue", "green"}:
            raise ValueError("Target color must be red, blue, or green")
        self.target_color = target_color
        self.latest = {}
        self.candidates = {}
        self.last_moving = {cube.id: 0.0 for cube in cubes}
        self.results = {}
        self.time = 0.0

    def update(self, time_s, observations):
        if not math.isfinite(time_s) or time_s < self.time:
            raise ValueError("Observation timestamps must be finite and nondecreasing")
        if set(observations) != set(self.cubes):
            raise ValueError("Every cube must appear in each observation")
        for id, obs in observations.items():
            if not all(math.isfinite(v) for v in (*obs.position, *obs.half_extents, *obs.velocity)):
                raise ValueError(f"Nonfinite observation for {id}")
        # Contact chains count cubes stacked on other cubes inside a tray.
        # Mere passage through a tray's bounding volume is insufficient.
        supported = {}
        for name, region in (("pass", PASS_REGION), ("reject", REJECT_REGION)):
            inside = {id for id, obs in observations.items() if region.contains(obs)}
            grounded = {id for id in inside if any(
                c.startswith(region.contact_prefix) for c in observations[id].contacts)}
            while True:
                connected = grounded | {id for id in inside if set(observations[id].contacts) & grounded}
                if connected == grounded:
                    break
                grounded = connected
            supported[name] = grounded
        self.time = time_s
        for id, obs in observations.items():
            self.latest[id] = obs
            speed = math.sqrt(sum(v * v for v in obs.velocity))
            if speed > 0.002:
                self.last_moving[id] = time_s
            destination = None
            for name in ("pass", "reject"):
                if id in supported[name] and speed < 0.05:
                    destination = name
                    break
            previous, since = self.candidates.get(id, (None, time_s))
            if destination is None:
                self.candidates.pop(id, None)
                # A cube that leaves a bin must not retain a successful outcome.
                self.results.pop(id, None)
            else:
                if destination != previous:
                    since = time_s
                    self.results.pop(id, None)
                self.candidates[id] = destination, since
                if time_s - since >= self.SETTLE_SECONDS - 1e-9:
                    target = self.cubes[id].color == self.target_color
                    outcome = ("correct_reject" if target else "wrong_reject") if destination == "reject" else (
                        "target_missed" if target else "correct_pass")
                    self.results[id] = self._result(id, destination, outcome, since + self.SETTLE_SECONDS)

    def _result(self, id, destination, outcome, resolved_at):
        return {**asdict(self.cubes[id]), "destination": destination, "outcome": outcome,
                "resolved_at_s": resolved_at, "final_position_m": list(self.latest[id].position),
                "final_contacts": list(self.latest[id].contacts)}

    def finish(self):
        for id in self.cubes:
            if id in self.results:
                continue
            obs = self.latest.get(id)
            if obs is None:
                outcome = "unresolved"
            elif ("world_floor" in obs.contacts or obs.position[2] < -0.30 or
                  not (-0.15 < obs.position[0] < 0.65 and -0.65 < obs.position[1] < 0.90)):
                outcome = "lost"
            elif "belt" in obs.contacts and self.time - self.last_moving[id] >= self.STUCK_SECONDS:
                outcome = "stuck"
            else:
                outcome = "unresolved"
            if obs is None:
                self.results[id] = {**asdict(self.cubes[id]), "destination": None,
                                    "outcome": outcome, "resolved_at_s": self.time, "final_position_m": None}
            else:
                self.results[id] = self._result(id, None, outcome, self.time)
        return self.summary()

    def summary(self):
        counts = Counter(result["outcome"] for result in self.results.values())
        return {"target_color": self.target_color, "total_cubes": len(self.cubes),
                "classified_cubes": len(self.results),
                "resolved_cubes": sum(r["outcome"] != "unresolved" for r in self.results.values()),
                "outcomes": dict(sorted(counts.items())),
                "cubes": [self.results[id] for id in sorted(self.results)]}
