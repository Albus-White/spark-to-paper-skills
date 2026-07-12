from __future__ import annotations

import html
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


# Copied by the DrawAI runner to the current svg_compose output directory.
# Run from the workflow run root.

RUN_ROOT = Path.cwd()
OUT_DIR = Path(__file__).resolve(strict=False).parent
PAGE_SPEC_PATH = RUN_ROOT / "nodes/asset_prepare/runs/001/output/page_spec.json"
HREF_BASE_DIR = "svg"
TOOL = shlex.split(os.environ.get("DRAWAI_TOOL_COMMAND", f"{sys.executable} -m drawai.cli tool"))
ROUND_INDEX = 0
DECLARED_FINAL_SVG_RUN_ROOT_PATH = "__DRAWAI_DECLARED_FINAL_SVG_RUN_ROOT_PATH__"

LAYER_ORDER = ("background", "underlay", "shape", "connector", "asset", "custom", "text", "overlay")

# Every PageSpec element should have one entry here.
# Reuse helpers for simple elements; create draw_svg_<element_id_lower>() for case-specific shapes/charts/icons.
ELEMENT_RENDERERS = {
    # "E001": ("draw_text", {"font_size": 22, "fill": "#111827"}),
    # "E002": ("draw_asset", {"href_key": "default"}),
    # "E003": ("draw_shape", {"fill": "#f8fafc", "stroke": "#94a3b8", "rx": 10}),
    # "E004": ("draw_connector", {"stroke": "#334155", "stroke_width": 2.2}),
    # "E005": ("skip", {"reason": "duplicate/removed element"}),
    # "E006": ("draw_svg_e006", {"bar_color": "#60a5fa"}),
}


class SvgComposeTemplate:
    def __init__(self) -> None:
        self.spec = self.load_spec()
        self.assets = self.load_assets()
        self.elements = [item for item in self.spec.get("elements", []) if isinstance(item, dict)]
        self.by_id = {eid(item): item for item in self.elements}
        self.width, self.height = canvas_size(self.spec)
        self.logs: list[dict[str, Any]] = []

    def run(self) -> None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)

        # Iteration flow:
        # 1. Set ROUND_INDEX = 0, run, inspect rendered_0.png.
        # 2. Edit this same script, set ROUND_INDEX = 1, run again.
        # 3. Repeat only when needed. Each run snapshots this script as
        #    build_semantic_svg_<ROUND_INDEX>.py beside the SVG/PNG/report.
        svg_path = self.write_round(ROUND_INDEX)
        self.finalize(svg_path)
        self.write_logs()

    # 1. Inputs

    def load_spec(self) -> dict[str, Any]:
        payload = json.loads(PAGE_SPEC_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("PageSpec must be a JSON object")
        return payload

    def load_assets(self) -> dict[str, dict[str, str]]:
        raw = subprocess.check_output(
            TOOL + ["page-spec-assets", "--page-spec", str(PAGE_SPEC_PATH), "--svg-dir", HREF_BASE_DIR],
            text=True,
        )
        assets: dict[str, dict[str, str]] = {}
        for item in json.loads(raw).get("assets", []):
            element_id = str(item["element_id"])
            output_key = str(item.get("output_key") or "default")
            href = str(item["svg_href"])
            assets.setdefault(element_id, {})[output_key] = href
            assets[element_id].setdefault("default", href)
        return assets

    # 2. Whole SVG flow

    def build_svg(self) -> str:
        layers = {name: [] for name in LAYER_ORDER}
        self.draw_background(layers)
        self.draw_derived_from_spec(layers)
        self.draw_spec_elements(layers)
        self.draw_extra_outside_spec(layers)
        return self.assemble(layers)

    def draw_spec_elements(self, layers: dict[str, list[str]]) -> None:
        for element in sorted(self.elements, key=element_sort_key):
            renderer_name, params = self.renderer_for(element)
            renderer = getattr(self, renderer_name)
            renderer(element, layers, **params)

    def renderer_for(self, element: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        element_id = eid(element)
        if element_id not in ELEMENT_RENDERERS:
            raise ValueError(f"missing ELEMENT_RENDERERS entry for {element_id}")
        entry = ELEMENT_RENDERERS[element_id]
        if isinstance(entry, str):
            return entry, {}
        renderer_name, params = entry
        return renderer_name, dict(params)

    # 3. Reusable element helpers

    def skip(self, element: dict[str, Any], layers: dict[str, list[str]], *, reason: str = "") -> None:
        self.log("skip", eid(element), reason or "deleted")

    def draw_asset(
        self,
        element: dict[str, Any],
        layers: dict[str, list[str]],
        *,
        href_key: str = "default",
        preserve_aspect_ratio: str = "none",
    ) -> None:
        x, y, w, h = bbox(element)
        element_id = eid(element)
        href = self.assets.get(element_id, {}).get(href_key)
        if not href:
            raise ValueError(f"missing allowed asset href for {element_id} key={href_key}")
        layers["asset"].append(
            tag(
                "image",
                {
                    "id": f"image-{element_id}",
                    "href": href,
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "preserveAspectRatio": preserve_aspect_ratio,
                    "data-pb-editable": "false",
                    "data-drawai-element-id": element_id,
                },
            )
        )

    def draw_text(
        self,
        element: dict[str, Any],
        layers: dict[str, list[str]],
        *,
        value: str | None = None,
        font_size: float | None = None,
        fill: str | None = None,
        font_weight: str | int | None = None,
        x_offset: float = 0,
        y_offset: float = 0,
        anchor: str = "start",
    ) -> None:
        x, y, w, h = bbox(element)
        content = element_text(element) if value is None else value
        size = font_size or fit_font_size(content, w, h)
        layers["text"].append(
            tag(
                "text",
                {
                    "id": f"label-{eid(element)}",
                    "x": x + x_offset,
                    "y": y + min(h * 0.78, size) + y_offset,
                    "font-family": "Arial, Helvetica, sans-serif",
                    "font-size": size,
                    "font-weight": font_weight or style(element, "font_weight", "400"),
                    "fill": fill or style(element, "fill", "#111827"),
                    "text-anchor": anchor,
                    "data-pb-editable": "true",
                    "data-pb-role": "text",
                    "data-drawai-element-id": eid(element),
                },
                text(content),
            )
        )

    def draw_shape(
        self,
        element: dict[str, Any],
        layers: dict[str, list[str]],
        *,
        fill: str | None = None,
        stroke: str | None = None,
        stroke_width: float | None = None,
        rx: float | None = None,
        layer: str = "shape",
    ) -> None:
        x, y, w, h = bbox(element)
        layers[layer].append(
            tag(
                "rect",
                {
                    "id": f"shape-{eid(element)}",
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "rx": rx if rx is not None else min(12, max(2, min(w, h) * 0.08)),
                    "fill": fill or style(element, "fill", "#f8fafc"),
                    "stroke": stroke or style(element, "stroke", "#94a3b8"),
                    "stroke-width": stroke_width or style(element, "stroke_width", 1.5),
                    "data-pb-editable": "true",
                    "data-drawai-element-id": eid(element),
                },
            )
        )

    def draw_connector(
        self,
        element: dict[str, Any],
        layers: dict[str, list[str]],
        *,
        stroke: str = "#334155",
        stroke_width: float = 2.2,
        arrow: bool = True,
    ) -> None:
        x, y, w, h = bbox(element)
        if w >= h:
            attrs = {"x1": x, "y1": y + h / 2, "x2": x + w, "y2": y + h / 2}
        else:
            attrs = {"x1": x + w / 2, "y1": y, "x2": x + w / 2, "y2": y + h}
        attrs.update(
            {
                "id": f"connector-{eid(element)}",
                "stroke": stroke,
                "stroke-width": stroke_width,
                "stroke-linecap": "round",
                "marker-end": "url(#arrowhead)" if arrow else None,
                "data-pb-editable": "true",
                "data-drawai-element-id": eid(element),
            }
        )
        layers["connector"].append(tag("line", attrs))

    def draw_formula(
        self,
        element: dict[str, Any],
        layers: dict[str, list[str]],
        *,
        value: str | None = None,
        font_size: float | None = None,
    ) -> None:
        x, y, w, h = bbox(element)
        content = value or element_text(element) or "x_i"
        size = font_size or fit_font_size(content, w, h)
        layers["text"].append(
            tag(
                "text",
                {
                    "id": f"formula-{eid(element)}",
                    "x": x,
                    "y": y + min(h * 0.78, size),
                    "font-family": "Arial, Helvetica, sans-serif",
                    "font-size": size,
                    "font-style": "italic",
                    "fill": "#111827",
                    "data-pb-role": "formula",
                    "data-pb-editable": "true",
                    "data-drawai-element-id": eid(element),
                },
                text(content),
            )
        )

    # 4. Case-specific renderers

    def draw_svg_e006(
        self,
        element: dict[str, Any],
        layers: dict[str, list[str]],
        *,
        bar_color: str = "#60a5fa",
    ) -> None:
        x, y, w, h = bbox(element)
        bars = [0.42, 0.72, 0.55]
        items = [
            tag("line", {"x1": x, "y1": y + h, "x2": x + w, "y2": y + h, "stroke": "#475569"}),
            tag("line", {"x1": x, "y1": y, "x2": x, "y2": y + h, "stroke": "#475569"}),
        ]
        for index, value in enumerate(bars):
            bar_w = w * 0.14
            bar_x = x + w * (0.2 + index * 0.24)
            bar_h = h * value
            items.append(tag("rect", {"x": bar_x, "y": y + h - bar_h, "width": bar_w, "height": bar_h, "fill": bar_color}))
        layers["custom"].append(group(f"chart-{eid(element)}", items, {"data-drawai-element-id": eid(element)}))

    def draw_svg_e018(
        self,
        element: dict[str, Any],
        layers: dict[str, list[str]],
        *,
        fill: str = "#fde68a",
    ) -> None:
        x, y, w, h = bbox(element)
        d = f"M {num(x)} {num(y + h)} L {num(x + w / 2)} {num(y)} L {num(x + w)} {num(y + h)} Z"
        layers["custom"].append(
            tag(
                "path",
                {
                    "id": f"icon-{eid(element)}",
                    "d": d,
                    "fill": fill,
                    "stroke": "#92400e",
                    "stroke-width": 1.5,
                    "data-pb-editable": "true",
                    "data-drawai-element-id": eid(element),
                },
            )
        )

    # 5. Spec-derived and spec-external additions

    def draw_derived_from_spec(self, layers: dict[str, list[str]]) -> None:
        # Example: infer a panel behind multiple PageSpec elements.
        # panel_box = union_bbox([self.by_id[x] for x in ("E021", "E022") if x in self.by_id], pad=12)
        # if panel_box:
        #     x, y, w, h = panel_box
        #     layers["underlay"].append(tag("rect", {"id": "derived-panel", "x": x, "y": y, "width": w, "height": h, "rx": 12, "fill": "#eef2ff"}))
        return

    def draw_extra_outside_spec(self, layers: dict[str, list[str]]) -> None:
        # Examples for visible items not present in PageSpec at all.
        # layers["overlay"].append(tag("circle", {"id": "extra-dot", "cx": 42, "cy": 42, "r": 5, "fill": "#ef4444"}))
        # layers["overlay"].append(tag("text", {"id": "extra-label", "x": 56, "y": 48, "font-size": 16}, text("missing label")))
        # layers["underlay"].append(tag("path", {"id": "extra-ribbon", "d": "M 20 20 H 220 L 204 52 H 20 Z", "fill": "#e0f2fe"}))
        return

    def draw_background(self, layers: dict[str, list[str]]) -> None:
        background = self.spec.get("background") if isinstance(self.spec.get("background"), dict) else {}
        layers["background"].append(
            tag("rect", {"id": "background-page", "x": 0, "y": 0, "width": self.width, "height": self.height, "fill": background.get("fill") or "#ffffff"})
        )

    # 6. Output, PNG render, validation, logs

    def write_round(self, round_index: int) -> Path:
        self.snapshot_script(round_index)
        svg_path = OUT_DIR / f"semantic_{round_index}.svg"
        svg_path.write_text(self.build_svg(), encoding="utf-8")
        report = self.validate(svg_path, OUT_DIR / f"rendered_{round_index}.png", OUT_DIR / f"validation_report_{round_index}.json")
        self.log("round", svg_path.name, f"status={report.get('status')}")
        return svg_path

    def snapshot_script(self, round_index: int) -> None:
        source = Path(__file__).resolve(strict=False)
        target = OUT_DIR / f"build_semantic_svg_{round_index}.py"
        if source != target:
            shutil.copyfile(source, target)
        self.log("script", target.name, f"snapshot for round {round_index}")

    def finalize(self, accepted_svg: Path) -> None:
        final_svg = declared_final_svg_path()
        final_svg.parent.mkdir(parents=True, exist_ok=True)
        if accepted_svg != final_svg:
            shutil.copyfile(accepted_svg, final_svg)
        report = self.validate(final_svg, OUT_DIR / "rendered.png", OUT_DIR / "validation_report_final.json")
        if report.get("status") != "ok":
            raise RuntimeError("final validation failed")
        self.log("final", final_svg.name, f"source={accepted_svg.name}")

    def validate(self, svg_path: Path, png_path: Path, report_path: Path) -> dict[str, Any]:
        subprocess.run(
            TOOL + ["svg-validate", "--svg", str(svg_path), "--page-spec", str(PAGE_SPEC_PATH), "--rendered", str(png_path), "--report", str(report_path), "--href-base-dir", HREF_BASE_DIR],
            check=True,
        )
        return json.loads(report_path.read_text(encoding="utf-8"))

    def assemble(self, layers: dict[str, list[str]]) -> str:
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{num(self.width)}" height="{num(self.height)}" viewBox="0 0 {num(self.width)} {num(self.height)}">',
            "  <defs>",
            '    <marker id="arrowhead" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">',
            '      <polygon points="0 0, 10 4, 0 8" fill="#334155"/>',
            "    </marker>",
            "  </defs>",
        ]
        for name in LAYER_ORDER:
            if layers[name]:
                lines.append(f'  <g id="layer-{name}">')
                lines.extend("    " + item for item in layers[name])
                lines.append("  </g>")
        lines.append("</svg>")
        return "\n".join(lines) + "\n"

    def write_logs(self) -> None:
        (OUT_DIR / "iteration_log.md").write_text(
            "\n".join(f"- {item['step']}: {item['target']} - {item['note']}" for item in self.logs) + "\n",
            encoding="utf-8",
        )
        with (OUT_DIR / "iteration_log.jsonl").open("w", encoding="utf-8") as handle:
            for item in self.logs:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    def log(self, step: str, target: str, note: str) -> None:
        self.logs.append({"step": step, "target": target, "note": note})


def canvas_size(spec: dict[str, Any]) -> tuple[float, float]:
    canvas = spec.get("canvas") if isinstance(spec.get("canvas"), dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    width = float(canvas.get("width_px") or canvas.get("width") or source.get("width_px") or source.get("width") or 0)
    height = float(canvas.get("height_px") or canvas.get("height") or source.get("height_px") or source.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("PageSpec canvas width/height must be positive")
    return width, height


def declared_final_svg_path() -> Path:
    if DECLARED_FINAL_SVG_RUN_ROOT_PATH.startswith("__DRAWAI_"):
        return OUT_DIR / "semantic.svg"
    return RUN_ROOT / DECLARED_FINAL_SVG_RUN_ROOT_PATH


def bbox(element: dict[str, Any]) -> tuple[float, float, float, float]:
    raw = element.get("box_px")
    if isinstance(raw, list) and len(raw) >= 4:
        return float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])
    raw = element.get("bbox")
    if isinstance(raw, dict):
        return float(raw.get("x") or 0), float(raw.get("y") or 0), float(raw.get("width") or 0), float(raw.get("height") or 0)
    if isinstance(raw, list) and len(raw) >= 4:
        x1, y1, x2, y2 = [float(value) for value in raw[:4]]
        return x1, y1, x2 - x1, y2 - y1
    geometry = element.get("geometry") if isinstance(element.get("geometry"), dict) else {}
    raw = geometry.get("bbox")
    if isinstance(raw, list) and len(raw) >= 4:
        x1, y1, x2, y2 = [float(value) for value in raw[:4]]
        return x1, y1, x2 - x1, y2 - y1
    raise ValueError(f"missing bbox for {eid(element)}")


def union_bbox(elements: list[dict[str, Any]], pad: float = 0) -> tuple[float, float, float, float] | None:
    if not elements:
        return None
    boxes = [bbox(element) for element in elements]
    x1 = min(x for x, _, _, _ in boxes) - pad
    y1 = min(y for _, y, _, _ in boxes) - pad
    x2 = max(x + w for x, _, w, _ in boxes) + pad
    y2 = max(y + h for _, y, _, h in boxes) + pad
    return x1, y1, x2 - x1, y2 - y1


def eid(element: dict[str, Any]) -> str:
    return str(element.get("id") or "element")


def element_text(element: dict[str, Any]) -> str:
    if element.get("text") not in (None, ""):
        return str(element["text"])
    measurement = element.get("measurement") if isinstance(element.get("measurement"), dict) else {}
    return str(measurement.get("text") or "")


def style(element: dict[str, Any], key: str, default: Any) -> Any:
    style_obj = element.get("style") if isinstance(element.get("style"), dict) else {}
    return style_obj.get(key, default)


def element_sort_key(element: dict[str, Any]) -> tuple[float, str]:
    return float(element.get("z_index") or 0), eid(element)


def fit_font_size(value: str, width: float, height: float) -> float:
    size = max(8, min(48, height * 0.66))
    if value:
        size = min(size, max(8, width / max(len(value) * 0.55, 1)))
    return size


def tag(name: str, attrs: dict[str, Any], body: str | None = None) -> str:
    attr_text = " ".join(f'{key}="{attr(value)}"' for key, value in attrs.items() if value is not None)
    if body is None:
        return f"<{name} {attr_text}/>"
    return f"<{name} {attr_text}>{body}</{name}>"


def group(group_id: str, items: list[str], attrs: dict[str, Any] | None = None) -> str:
    return tag("g", {"id": group_id, **(attrs or {})}, "\n".join(items))


def text(value: str) -> str:
    return html.escape(value, quote=False)


def attr(value: Any) -> str:
    if isinstance(value, (float, int)):
        return num(float(value))
    return html.escape(str(value), quote=True)


def num(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


if __name__ == "__main__":
    SvgComposeTemplate().run()
