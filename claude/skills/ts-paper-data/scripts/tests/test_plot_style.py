import importlib.util
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("style", SCRIPTS / "plot_style.py")
style = importlib.util.module_from_spec(spec); spec.loader.exec_module(style)


def test_typography_is_venue_overridable():
    assert style.PUBLICATION_RCPARAMS["font.family"] == "DejaVu Sans"


def test_overlap_gate_detects_colliding_text():
    import matplotlib.pyplot as plt
    style.apply_publication_style()
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.text(0.5, 0.5, "Encoder", transform=ax.transAxes)
    ax.text(0.5, 0.5, "Decoder", transform=ax.transAxes)
    fig.canvas.draw()
    assert style._layout_overlaps(fig)
    plt.close(fig)
