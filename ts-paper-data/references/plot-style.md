# Results-figure house style (matplotlib) — distilled from figures4papers

The `scripts/plot_style.py` module is applied automatically by `plot_results.py` (it sets the
rcParams and injects `PALETTE` / `SEMANTIC` / `style_axes` / `finalize` into your plot script's
namespace). Write the plot script to these conventions so the results figure looks like a
Nature-MI / ICML / NeurIPS figure, not default matplotlib.

## Colour BY MEANING (use the injected `SEMANTIC` dict, never arbitrary colours)
- `SEMANTIC["ours"]` (blue) — the proposed method / method of interest.
- `SEMANTIC["positive"]` (green) — improvements / related positives.
- `SEMANTIC["contrast"]` (red) — competing / alternative methods.
- `SEMANTIC["baseline"]` (neutral grey) — baselines / background categories.
Keep the mapping consistent across every panel of the paper.

## Encoding rules by chart type
- **Grouped / ablation bars:** black edges (`edgecolor='black', linewidth=1.5`); print the value
  above each bar (`ax.text`, readable size) so exact numbers read without a grid; for an ablation
  use ONE colour at varying `alpha` (0.3→1.0) to show "completeness"; add a `hatch` channel when two
  bars share a hue so it survives grayscale print. Hide x-tick labels and use a legend when comparing
  many methods × metrics. Tighten the y-limits to the relevant range (emphasise differences, not 0→1).
- **Trend / line:** 2–4 primary curves max, linewidth 2–3, `SEMANTIC` colours; `fill_between` for
  variance/CI; minimal/no grid; direct legend (frameless).
- **Heatmap:** a perceptually-uniform map (e.g. `viridis`/`magma`), a colorbar with a labelled metric,
  annotate cells only if the grid is small.
- **Radar / polar:** few series, same line-weight discipline as Cartesian; one colour per method.
- **Scatter / illustration:** lowered alpha for dense scenes; saturated accent + arrows for the key
  relation; drop axis ticks for purely conceptual geometry.

## Layout
- Multi-metric comparison → a WIDE canvas (read left→right as a narrative), e.g. `figsize=(14,4)` for
  3–4 metrics in a column-fit panel (scale up for a full-width `figure*`).
- Complex multi-axis figure → give the legend its OWN sub-axis (`ax.set_axis_off()`) so it never
  overlaps data.
- Multi-panel consistency over per-axis embellishment: same fonts, linewidths, and colour semantics
  across all subplots.
- Always finish with `finalize(fig, OUT)` (it does `tight_layout(pad=2)` + saves PNG **and** a vector
  PDF at dpi 300). For a very dense bar panel pass `dpi=600`.

## Integrity (unchanged)
A `null`/`TBD` value is a GAP in the plot, never a fabricated point. Plot only numbers that exist in
the user's data (and in `results.facts.json`). No invented trends.
