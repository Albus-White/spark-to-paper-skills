#!/usr/bin/env python3
"""plot_results.py — render a RESULTS figure by running a Claude-authored matplotlib script.

DATA-AWARE mode only. Results plots must be numerically exact, so they are drawn from CODE
(matplotlib), never from an image model. The design is deliberately schema-agnostic: Claude has
already read the user's data (in whatever form) and judged it, so it writes a small SELF-CONTAINED
matplotlib script that embeds the real numbers it is plotting and saves a PNG. This tool just runs
that script safely and guarantees the figure is written.

    python3 plot_results.py --script figures/<label>.plot.py --out figures/<label>.png

The script may simply build a figure with plt and (optionally) call savefig; if it doesn't save,
this runner saves the current figure to --out. `plt` and `np` are pre-imported into its namespace.
stdlib + numpy + matplotlib (Agg). No network, no external data file, no LLM.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plot_style  # publication "house style" (figures4papers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="Claude-authored matplotlib script")
    ap.add_argument("--out", required=True, help="output PNG path")
    a = ap.parse_args()
    script = Path(a.script)
    out = Path(a.out)
    if not script.exists():
        print(json.dumps({"ok": False, "error": f"no script {script}"})); sys.exit(2)
    out.parent.mkdir(parents=True, exist_ok=True)
    plot_style.apply_publication_style()   # house style applied before the script draws
    ns = {"plt": plt, "np": np, "json": json, "Path": Path, "OUT": str(out),
          # house-style helpers, available to the Claude-authored plot script:
          "PALETTE": plot_style.PALETTE, "SEMANTIC": plot_style.SEMANTIC,
          "apply_publication_style": plot_style.apply_publication_style,
          "style_axes": plot_style.style_axes, "finalize": plot_style.finalize}
    try:
        exec(compile(script.read_text(), str(script), "exec"), ns)   # trusted: Claude-authored
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})); sys.exit(1)
    # if the script didn't save, finalize the current figure (PNG + vector PDF) for it
    if not out.exists() and plt.get_fignums():
        plot_style.finalize(plt.gcf(), str(out))
    # born-vector guarantee: ensure a sibling vector PDF exists even if the script
    # called plt.savefig(OUT) itself (which skips the finalize above). matplotlib
    # savefig('.pdf') is vector by default, and the house style sets pdf.fonttype=42
    # so the PDF embeds TrueType (selectable/editable text). (Prefer finalize(fig, OUT);
    # the figure SKILL mandates it. This is a defensive net for a self-saved PNG.)
    pdf = out.with_suffix(".pdf")
    if out.suffix.lower() == ".png" and not pdf.exists() and plt.get_fignums():
        try:
            plt.gcf().savefig(str(pdf))
        except Exception:  # noqa: BLE001 - PDF is a best-effort sibling; PNG already exists
            pass
    plt.close("all")
    if out.exists():
        res = {"ok": True, "out": str(out), "bytes": out.stat().st_size}
        if pdf.exists():
            res["pdf"] = str(pdf)
        print(json.dumps(res))
    else:
        print(json.dumps({"ok": False, "error": "script produced no figure / did not save to OUT"})); sys.exit(1)


if __name__ == "__main__":
    main()
