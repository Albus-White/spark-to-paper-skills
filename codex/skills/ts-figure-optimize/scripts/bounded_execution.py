"""Shared finite-progress guard for expensive figure reconstruction loops."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProgressGuard:
    max_wall_seconds: float
    stagnation_rounds: int
    min_improvement: float
    max_consecutive_failures: int
    started_at: float = field(default_factory=time.monotonic)
    best_score: float | None = None
    stagnant_count: int = 0
    consecutive_failures: int = 0
    seen_artifact_hashes: set[str] = field(default_factory=set)

    def before_round(self, now: float | None = None) -> str | None:
        current = time.monotonic() if now is None else now
        if current - self.started_at >= self.max_wall_seconds:
            return "wall_clock_budget_exhausted"
        return None

    def observe(self, *, score: float | None, artifact: Path | None,
                pipeline_ok: bool, now: float | None = None) -> str | None:
        deadline = self.before_round(now)
        if deadline:
            return deadline

        if not pipeline_ok or score is None:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures:
                return "consecutive_round_failures"
        else:
            self.consecutive_failures = 0

        if artifact is not None and artifact.is_file():
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if digest in self.seen_artifact_hashes:
                return "artifact_cycle_detected"
            self.seen_artifact_hashes.add(digest)

        if score is not None:
            if self.best_score is None or score >= self.best_score + self.min_improvement:
                self.best_score = score
                self.stagnant_count = 0
            else:
                self.stagnant_count += 1
                if self.stagnant_count >= self.stagnation_rounds:
                    return "score_stagnation"
        return None


def validate_budget(*, max_rounds: int, max_wall_seconds: float, round_timeout_seconds: float,
                    stagnation_rounds: int, min_improvement: float,
                    max_consecutive_failures: int) -> list[str]:
    issues = []
    if not 0 <= max_rounds <= 10:
        issues.append("max_rounds must be between 0 and 10")
    if not 300 <= max_wall_seconds <= 43_200:
        issues.append("max_wall_seconds must be between 300 and 43200")
    if not 60 <= round_timeout_seconds <= min(max_wall_seconds, 14_400):
        issues.append("round_timeout_seconds must be between 60 and min(max_wall_seconds, 14400)")
    if not 1 <= stagnation_rounds <= 4:
        issues.append("stagnation_rounds must be between 1 and 4")
    if not 0 < min_improvement <= 0.1:
        issues.append("min_improvement must be in (0, 0.1]")
    if not 1 <= max_consecutive_failures <= 3:
        issues.append("max_consecutive_failures must be between 1 and 3")
    return issues
