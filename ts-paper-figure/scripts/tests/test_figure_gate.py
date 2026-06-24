import importlib.util, pathlib, json

RUN_GATES = pathlib.Path(__file__).resolve().parents[3] / "ts-paper" / "scripts" / "run_gates.py"
spec = importlib.util.spec_from_file_location("rg", RUN_GATES)
rg = importlib.util.module_from_spec(spec); spec.loader.exec_module(rg)


def _manifest(figs, **over):
    fig = {"label": "arch", "type": "architecture", "engine": "image-model",
           "critic_rounds": 2, "grounding": "image-cond", "reference_used": "2103.00208#fig2"}
    fig.update(over)
    (figs / "figures.manifest.json").write_text(json.dumps({"figures": [fig]}))


def test_figure_critique_gate_flags_empty_repair_log(tmp_path):
    figs = tmp_path / "figures"; (figs / "repair_logs").mkdir(parents=True)
    _manifest(figs)
    (figs / "repair_logs" / "arch.log").write_text("")   # EMPTY -> must fail
    problems = rg.check_figure_critique(str(tmp_path))
    assert any("arch" in p and ("empty" in p.lower() or "missing" in p.lower()) for p in problems)


def test_figure_critique_gate_flags_low_rounds(tmp_path):
    figs = tmp_path / "figures"; (figs / "repair_logs").mkdir(parents=True)
    _manifest(figs, critic_rounds=1)
    (figs / "repair_logs" / "arch.log").write_text("round1: x\n")
    problems = rg.check_figure_critique(str(tmp_path))
    assert any("critic_rounds" in p for p in problems)


def test_figure_critique_gate_flags_missing_grounding(tmp_path):
    figs = tmp_path / "figures"; (figs / "repair_logs").mkdir(parents=True)
    _manifest(figs, grounding="")
    (figs / "repair_logs" / "arch.log").write_text("round1: x\nround2: y\n")
    problems = rg.check_figure_critique(str(tmp_path))
    assert any("grounding" in p for p in problems)


def test_figure_critique_gate_passes_with_trace(tmp_path):
    figs = tmp_path / "figures"; (figs / "repair_logs").mkdir(parents=True)
    _manifest(figs)
    (figs / "repair_logs" / "arch.log").write_text("round1: added real tiles\nround2: denser labels\n")
    assert rg.check_figure_critique(str(tmp_path)) == []


def test_figure_critique_gate_noop_without_manifest(tmp_path):
    assert rg.check_figure_critique(str(tmp_path)) == []   # no figures stage yet


def test_figure_critique_gate_ignores_matplotlib(tmp_path):
    figs = tmp_path / "figures"; figs.mkdir(parents=True)
    (figs / "figures.manifest.json").write_text(json.dumps(
        {"figures": [{"label": "res", "type": "results", "engine": "matplotlib"}]}))
    assert rg.check_figure_critique(str(tmp_path)) == []   # matplotlib not subject to critique gate


def test_gate_blocks_svg_native_freeform(tmp_path):
    # THE carbon-paper regression: a free-form figure hand-authored as flat SVG must FAIL the gate
    figs = tmp_path / "figures"; figs.mkdir(parents=True)
    (figs / "figures.manifest.json").write_text(json.dumps({"figures": [
        {"label": "framework", "type": "framework", "engine": "svg-native", "critic_rounds": 2}]}))
    problems = rg.check_figure_critique(str(tmp_path))
    assert any("framework" in p and ("svg-native" in p or "not allowed" in p) for p in problems)


def test_gate_blocks_matplotlib_for_schematic(tmp_path):
    # a free-form schematic may NOT be code-drawn — must be image-model
    figs = tmp_path / "figures"; figs.mkdir(parents=True)
    (figs / "figures.manifest.json").write_text(json.dumps({"figures": [
        {"label": "arch", "type": "architecture", "engine": "matplotlib"}]}))
    problems = rg.check_figure_critique(str(tmp_path))
    assert any("arch" in p and "image-model" in p for p in problems)
