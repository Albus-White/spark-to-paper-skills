import importlib.util
import pathlib
import sys
import time

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bounded_execution", SCRIPTS / "bounded_execution.py")
bounded = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bounded
spec.loader.exec_module(bounded)


def _guard(**overrides):
    values = {
        "max_wall_seconds": 100,
        "stagnation_rounds": 3,
        "min_improvement": 0.01,
        "max_consecutive_failures": 2,
    }
    values.update(overrides)
    return bounded.ProgressGuard(**values)


def test_material_improvement_resets_stagnation():
    guard = _guard()
    assert guard.observe(score=0.50, artifact=None, pipeline_ok=True) is None
    assert guard.observe(score=0.505, artifact=None, pipeline_ok=True) is None
    assert guard.stagnant_count == 1
    assert guard.observe(score=0.52, artifact=None, pipeline_ok=True) is None
    assert guard.stagnant_count == 0


def test_score_stagnation_stops_at_declared_budget():
    guard = _guard()
    assert guard.observe(score=0.50, artifact=None, pipeline_ok=True) is None
    assert guard.observe(score=0.501, artifact=None, pipeline_ok=True) is None
    assert guard.observe(score=0.502, artifact=None, pipeline_ok=True) is None
    assert guard.observe(score=0.503, artifact=None, pipeline_ok=True) == "score_stagnation"


def test_repeated_artifact_and_ab_a_cycle_stop(tmp_path):
    a = tmp_path / "figure.svg"
    guard = _guard()
    a.write_text("A")
    assert guard.observe(score=0.5, artifact=a, pipeline_ok=True) is None
    a.write_text("B")
    assert guard.observe(score=0.52, artifact=a, pipeline_ok=True) is None
    a.write_text("A")
    assert guard.observe(score=0.54, artifact=a, pipeline_ok=True) == "artifact_cycle_detected"


def test_wall_clock_and_failure_budgets_stop():
    guard = _guard(max_wall_seconds=10)
    assert guard.before_round(now=guard.started_at + 10.001) == "wall_clock_budget_exhausted"
    assert guard.observe(score=None, artifact=None, pipeline_ok=False) is None
    assert guard.observe(score=None, artifact=None, pipeline_ok=False) == "consecutive_round_failures"


def test_invalid_or_effectively_unbounded_policy_is_rejected():
    issues = bounded.validate_budget(
        max_rounds=1000,
        max_wall_seconds=1_000_000,
        round_timeout_seconds=1_000_000,
        stagnation_rounds=100,
        min_improvement=0,
        max_consecutive_failures=100,
    )
    assert len(issues) == 6
