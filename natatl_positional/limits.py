"""Optional explicit resource ceilings; exhaustion is UNKNOWN, never FALSE."""
from dataclasses import dataclass
import time

from .errors import ResourceLimit


@dataclass(frozen=True)
class Limits:
    max_candidates: int | None = None
    timeout_seconds: float | None = None
    max_guard_masks: int | None = 100000
    max_dp_states: int | None = 100000

    def __post_init__(self):
        for name in ("max_candidates", "max_guard_masks", "max_dp_states"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"{name} must be a positive integer or None")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class RunBudget:
    def __init__(self, limits=None):
        self.limits = limits or Limits()
        self.started = time.monotonic()
        self.candidates = 0

    def check_time(self):
        limit = self.limits.timeout_seconds
        if limit is not None and time.monotonic() - self.started >= limit:
            raise ResourceLimit("Time limit reached")

    def next_candidate(self):
        self.check_time()
        maximum = self.limits.max_candidates
        if maximum is not None and self.candidates >= maximum:
            raise ResourceLimit("Candidate limit reached")
        self.candidates += 1
