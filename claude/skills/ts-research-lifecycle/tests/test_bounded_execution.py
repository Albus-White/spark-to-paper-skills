from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

P = Path(__file__).parents[1] / "scripts/bounded_execution.py"
spec = importlib.util.spec_from_file_location("rlc_bounded_test", P)
bounded = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bounded
spec.loader.exec_module(bounded)


class BoundedExecutionTest(unittest.TestCase):
    def test_hard_cap_rejects_arbitrary_attempt_expansion(self):
        budget = bounded.StageBudget("experiment", 4, 3600)
        self.assertTrue(any("max_attempts" in issue for issue in budget.validate()))

    def test_repeated_state_stops_even_when_text_is_reordered(self):
        tracker = bounded.ProgressTracker(bounded.StageBudget("refine", 3, 100))
        self.assertIsNone(tracker.observe(state={"errors": ["a", "b"]}, success=False))
        self.assertEqual(
            tracker.observe(state={"errors": ["a", "b"]}, success=False), "repeated_state"
        )

    def test_no_material_progress_and_timeout_are_terminal(self):
        tracker = bounded.ProgressTracker(
            bounded.StageBudget("figure", 3, 10, stagnation_limit=1, min_improvement=0.1)
        )
        self.assertIsNone(tracker.observe(state={"round": 1}, success=True, metric=0.5))
        self.assertEqual(
            tracker.observe(state={"round": 2}, success=True, metric=0.55), "no_material_progress"
        )
        self.assertEqual(
            tracker.observe(state={"round": 3}, success=True, now=tracker.started_at + 10),
            "stage_timeout",
        )


if __name__ == "__main__":
    unittest.main()
