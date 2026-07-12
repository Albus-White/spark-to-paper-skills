import importlib.util
import json
import pathlib
import sys
import time

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("reconstruct", SCRIPTS / "run_reconstruction.py")
reconstruct = importlib.util.module_from_spec(spec); spec.loader.exec_module(reconstruct)
spec_gate = importlib.util.spec_from_file_location("vector_gate", SCRIPTS / "check_vector_pdf.py")
vector_gate = importlib.util.module_from_spec(spec_gate); spec_gate.loader.exec_module(vector_gate)

DRAWAI = SCRIPTS.parent / "engine"


def test_official_quality_profile_is_accepted():
    assert reconstruct.validate_quality_config(DRAWAI / "configs/drawai/config.yaml") == []


def test_fast_and_smoke_profiles_are_rejected():
    for name in ("config_fast_poster.yaml", "harbor_smoke_2048.yaml"):
        issues = reconstruct.validate_quality_config(DRAWAI / "configs/drawai" / name)
        assert issues, name


def test_full_svg_rejects_whole_canvas_raster(tmp_path):
    svg = tmp_path / "hybrid.svg"
    svg.write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <image width="100" height="100" href="data:image/png;base64,AA=="/>
      <text x="10" y="20">Encoder</text><rect x="2" y="2" width="20" height="20"/>
    </svg>''')
    report = vector_gate.lint_svg(svg, "architecture", False, "full")
    assert not report["ok"] and any("whole_canvas_raster" in error for error in report["errors"])
    assert vector_gate.lint_svg(svg, "architecture", False, "fidelity-hybrid")["ok"]


def test_full_svg_accepts_semantic_primitives_and_local_asset(tmp_path):
    svg = tmp_path / "full.svg"
    svg.write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <image x="2" y="2" width="20" height="20" href="data:image/png;base64,AA=="/>
      <rect x="25" y="25" width="50" height="30"/><path d="M 25 40 L 75 40"/>
      <text x="30" y="43">Fusion</text>
    </svg>''')
    assert vector_gate.lint_svg(svg, "architecture", False, "full")["ok"]


def test_collect_preserves_drawai_v2_packages_and_traces(tmp_path):
    case = tmp_path / "case_001"
    (case / "reports" / "parser_outputs").mkdir(parents=True)
    (case / "elements").mkdir()
    (case / "trace").mkdir()
    (case / "exports").mkdir()
    (case / "drawai_package.json").write_text('{"schema":"drawai.package.v1"}')
    (case / "elements" / "fused.json").write_text("{}")
    (case / "trace" / "refine.json").write_text("{}")
    (case / "reports" / "parser_outputs" / "ocr.json").write_text("{}")
    (case / "exports" / "semantic.svg").write_text("<svg/>")

    layout = reconstruct.make_layout(tmp_path / "skill-run")
    copied = reconstruct.collect(case, layout)

    assert (layout["drawai"] / "drawai_package.json").is_file()
    assert (layout["drawai"] / "elements" / "fused.json").is_file()
    assert (layout["drawai"] / "trace" / "refine.json").is_file()
    assert (layout["drawai"] / "parser_outputs" / "ocr.json").is_file()
    assert (layout["drawai"] / "exports" / "semantic.svg").is_file()
    assert copied["elements_tree"] == str(layout["drawai"] / "elements")


def test_whole_run_deadline_shortens_late_subprocess(monkeypatch, tmp_path):
    monkeypatch.setattr(reconstruct, "_EXECUTION_DEADLINE", time.monotonic() + 0.05)
    started = time.monotonic()
    result = reconstruct._bounded_command(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        cwd=tmp_path,
        timeout_seconds=30,
    )
    assert result["timed_out"] is True
    assert time.monotonic() - started < 1
