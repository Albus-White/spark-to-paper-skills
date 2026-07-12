#!/usr/bin/env python3
"""Project-wide bounded-execution primitives for retrying evidence-producing stages."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


HARD_CAPS = {
    "plan": {"attempts": 3, "timeout": 1_800},
    "cite": {"attempts": 3, "timeout": 7_200},
    "write": {"attempts": 3, "timeout": 7_200},
    "refine": {"attempts": 3, "timeout": 7_200},
    "review": {"attempts": 4, "timeout": 7_200},
    "figure": {"attempts": 10, "timeout": 43_200},
    "latex": {"attempts": 3, "timeout": 1_800},
    "experiment": {"attempts": 3, "timeout": 86_400},
    "handoff": {"attempts": 1, "timeout": 900},
    "gate": {"attempts": 1, "timeout": 3_600},
}


def state_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class StageBudget:
    stage: str
    max_attempts: int
    timeout_seconds: float
    stagnation_limit: int = 2
    consecutive_failure_limit: int = 2
    min_improvement: float = 0.0

    def validate(self) -> list[str]:
        issues: list[str] = []
        cap = HARD_CAPS.get(self.stage)
        if cap is None:
            issues.append(f"unknown bounded stage: {self.stage}")
            return issues
        if not 1 <= self.max_attempts <= cap["attempts"]:
            issues.append(f"{self.stage}.max_attempts must be between 1 and {cap['attempts']}")
        if not 1 <= self.timeout_seconds <= cap["timeout"]:
            issues.append(f"{self.stage}.timeout_seconds must be between 1 and {cap['timeout']}")
        if not 1 <= self.stagnation_limit <= 3:
            issues.append("stagnation_limit must be between 1 and 3")
        if not 1 <= self.consecutive_failure_limit <= 3:
            issues.append("consecutive_failure_limit must be between 1 and 3")
        if not 0 <= self.min_improvement <= 1:
            issues.append("min_improvement must be between 0 and 1")
        return issues


@dataclass
class ProgressTracker:
    budget: StageBudget
    started_at: float = field(default_factory=time.monotonic)
    seen_states: set[str] = field(default_factory=set)
    best_metric: float | None = None
    stagnant: int = 0
    consecutive_failures: int = 0

    def observe(self, *, state: Any, success: bool, metric: float | None = None,
                now: float | None = None) -> str | None:
        current = time.monotonic() if now is None else now
        if current - self.started_at >= self.budget.timeout_seconds:
            return "stage_timeout"
        fingerprint = state_fingerprint(state)
        if fingerprint in self.seen_states:
            return "repeated_state"
        self.seen_states.add(fingerprint)
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.budget.consecutive_failure_limit:
                return "consecutive_failures"
        if metric is not None:
            if self.best_metric is None or metric >= self.best_metric + self.budget.min_improvement:
                self.best_metric = metric
                self.stagnant = 0
            else:
                self.stagnant += 1
                if self.stagnant >= self.budget.stagnation_limit:
                    return "no_material_progress"
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a project-wide stage execution budget.")
    parser.add_argument("--stage", choices=sorted(HARD_CAPS), required=True)
    parser.add_argument("--max-attempts", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--stagnation-limit", type=int, default=2)
    parser.add_argument("--consecutive-failure-limit", type=int, default=2)
    parser.add_argument("--min-improvement", type=float, default=0.0)
    args = parser.parse_args()
    budget = StageBudget(
        stage=args.stage,
        max_attempts=args.max_attempts,
        timeout_seconds=args.timeout_seconds,
        stagnation_limit=args.stagnation_limit,
        consecutive_failure_limit=args.consecutive_failure_limit,
        min_improvement=args.min_improvement,
    )
    issues = budget.validate()
    print(json.dumps({"ok": not issues, "budget": vars(budget), "issues": issues}, indent=2))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
