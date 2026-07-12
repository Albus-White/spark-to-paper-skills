import importlib.util
import json
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hybrid", SCRIPTS / "build_hybrid_pptx.py")
hybrid = importlib.util.module_from_spec(spec); spec.loader.exec_module(hybrid)


def test_hybrid_svg_uses_requested_venue_family(tmp_path):
    bg = tmp_path / "bg.png"; bg.write_bytes(b"not-opened-by-svg-writer")
    svg = tmp_path / "out.svg"
    runs = [{"x": 10, "ymid": 20, "fh": 12, "col": (0, 0, 0), "segs": [("Encoder", "n")]}]
    hybrid.write_svg_pdf(bg, runs, 100, 50, svg, None, "Source Sans 3")
    content = svg.read_text()
    assert 'font-family="Source Sans 3, sans-serif"' in content
