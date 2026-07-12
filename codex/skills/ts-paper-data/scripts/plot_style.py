#!/usr/bin/env python3
"""plot_style.py — publication "house style" for matplotlib RESULTS figures.

Distilled from the figures4papers / scientific-figure-making repository (figures that
appear in Nature MI / ICML / NeurIPS). plot_results.py applies this automatically and
injects PALETTE / SEMANTIC / finalize into the plot-script namespace, so every results
figure inherits a consistent, publication-grade look instead of default matplotlib.

Use the SEMANTIC mapping for colour meaning:
  ours -> blue (the proposed method)   positive -> green (gains/related positives)
  contrast -> red (alternatives)       baseline -> neutral grey
"""
from __future__ import annotations

# ── rcParams preset (minimalist, high-contrast, publication-oriented) ──
PUBLICATION_RCPARAMS = {
    "font.family": "DejaVu Sans",
    "mathtext.fontset": "dejavusans",
    "font.size": 16,             # bump to 22-24 for large single-panel comparison bars
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 2.0,       # 3 for big bars, 2 for compact figures
    "axes.titlesize": 16,
    "axes.labelsize": 16,
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "legend.frameon": False,
    "legend.fontsize": 14,
    "svg.fonttype": "none",      # keep editable text in SVG exports
    "pdf.fonttype": 42,          # embed TrueType in PDF (not Type-3) → selectable/editable text
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
}

# ── semantic palette (figures4papers family) ──
PALETTE = {
    "blue_main": "#0F4D92", "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE", "green_2": "#AADCA9", "green_3": "#8BCF8B",
    "red_1": "#F6CFCB", "red_2": "#E9A6A1", "red_strong": "#B64342",
    "neutral": "#CFCECE", "grey_mid": "#767676", "grey_dark": "#4D4D4D",
    "highlight": "#FFD700",
}

# colour BY MEANING — use these, not arbitrary colours
SEMANTIC = {
    "ours": PALETTE["blue_main"],         # the proposed method / method of interest
    "positive": PALETTE["green_3"],       # improvements / related positives
    "contrast": PALETTE["red_strong"],    # alternative / competing methods
    "baseline": PALETTE["neutral"],       # baselines / background categories
    "highlight": PALETTE["highlight"],
}


def apply_publication_style(scale: str = "compact", font_family: str | None = None) -> None:
    """Set publication defaults; an active venue may supply its own font family."""
    import logging
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    rc = dict(PUBLICATION_RCPARAMS)
    if font_family:
        rc["font.family"] = font_family
    if scale == "large":
        rc.update({"font.size": 22, "axes.linewidth": 3.0,
                   "axes.titlesize": 22, "axes.labelsize": 22,
                   "xtick.labelsize": 18, "ytick.labelsize": 18, "legend.fontsize": 18})
    plt.rcParams.update(rc)


def style_axes(ax) -> None:
    """Idempotent per-axis cleanup: drop top/right spines, light y-grid."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)


def _layout_overlaps(fig, threshold: float = 0.35) -> list[str]:
    """Return severe visible text collisions in display coordinates.

    This is a deterministic backstop for the overlap failure that image-only visual review can miss.
    It deliberately ignores tiny bounding-box touches and flags only overlap covering at least
    ``threshold`` of the smaller label.
    """
    from matplotlib.text import Text
    renderer = fig.canvas.get_renderer()
    labels = []
    for text in fig.findobj(match=Text):
        value = text.get_text().strip()
        alpha = text.get_alpha()
        if not value or not text.get_visible() or (alpha is not None and float(alpha) == 0):
            continue
        box = text.get_window_extent(renderer=renderer)
        if box.width > 0 and box.height > 0:
            labels.append((value.replace("\n", " ")[:60], box))
    issues = []
    for index, (left_text, left) in enumerate(labels):
        for right_text, right in labels[index + 1:]:
            x0, y0 = max(left.x0, right.x0), max(left.y0, right.y0)
            x1, y1 = min(left.x1, right.x1), min(left.y1, right.y1)
            if x1 <= x0 or y1 <= y0:
                continue
            overlap = (x1 - x0) * (y1 - y0)
            smaller = min(left.width * left.height, right.width * right.height)
            if smaller and overlap / smaller >= threshold:
                issues.append(f"{left_text!r} overlaps {right_text!r} ({overlap / smaller:.0%})")
    return issues


def finalize(fig, out_path: str, pad: float = 2.0, dpi: int = 300, also_pdf: bool = True,
             strict_layout: bool = True) -> list:
    """Lay out, reject severe text collisions, then save PNG and vector PDF."""
    from pathlib import Path
    fig.tight_layout(pad=pad)
    fig.canvas.draw()
    collisions = _layout_overlaps(fig)
    if strict_layout and collisions:
        raise RuntimeError("text overlap gate failed: " + "; ".join(collisions[:8]))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = [str(out)]
    fig.savefig(out, dpi=dpi)
    if also_pdf:
        pdf = out.with_suffix(".pdf")
        fig.savefig(pdf)
        written.append(str(pdf))
    return written
