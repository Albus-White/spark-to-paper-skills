from __future__ import annotations

import base64
import binascii
import copy
import json
import math
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from PIL import Image, ImageDraw, ImageFont

from drawai.pptx_inspector import inspect_pptx_structure


SVG_TO_PPT_SAFE_BACKGROUND_ID = "canvas_background"
SVG_TO_PPT_SAFE_OBJECT_ID_PREFIX = "svg_to_ppt_object"
SVG_TO_PPT_EXPORT_MODE_NATIVE_SHAPES = "native_shapes"
DRAWAI_NATIVE_SHAPES_BACKEND = "drawai_native_shapes"
SVG_TO_PPT_EXPORT_MODE_NATIVE_SHAPES_WITH_OFFICE_MATH = "native_shapes+office_math"
DRAWAI_FORMULA_ROLE = "formula"
DRAWAI_FORMULA_LATEX_ATTR = "data-pb-formula-latex"
DRAWAI_FORMULA_LATEX_B64_ATTR = "data-pb-formula-latex-b64"
DRAWAI_FORMULA_BBOX_ATTR = "data-pb-formula-bbox"
SVG_TO_PPT_UNSAFE_BACKGROUND_IDS = {
    "page_background",
    "page_bg",
    "slide_background",
    "slide_bg",
}
SVG_TO_PPT_POSITIONED_TSPAN_INHERITED_ATTRS = (
    "text-anchor",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "fill",
    "fill-opacity",
    "opacity",
)
SVG_TO_PPT_TSPAN_TEXT_WIDTH_FALLBACK_EM_RATIO = 0.6
SVG_TO_PPT_FONT_MEASURE_SCALE = 4
SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS = {
    "arial": (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ),
    "arial-bold": (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    "arial-italic": (
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "/Library/Fonts/Arial Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    ),
    "arial-bold-italic": (
        "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
        "/Library/Fonts/Arial Bold Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    ),
    "times": (
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ),
    "times-bold": (
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ),
    "courier": (
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ),
    "courier-bold": (
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    ),
    "verdana": (
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ),
    "cjk": (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ),
}
SVG_ID_ATTR_RE = re.compile(r"\bid=(['\"])([^'\"]+)\1")
SVG_TO_PPT_PAGE_ID_RE = re.compile(r"page|slide", re.IGNORECASE)
SVG_NUMERIC_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
SVG_PATH_TOKEN_RE = re.compile(r"[A-Za-z]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
SVG_MARKER_URL_RE = re.compile(r"^url\(\s*#([^)'\"]+)\s*\)$")
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
PPTX_PRESENTATION_NAMESPACE = "http://schemas.openxmlformats.org/presentationml/2006/main"
PPTX_DRAWING_NAMESPACE = "http://schemas.openxmlformats.org/drawingml/2006/main"
PPTX_RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PPTX_DRAWING_2010_NAMESPACE = "http://schemas.microsoft.com/office/drawing/2010/main"
PPTX_OFFICE_MATH_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/math"
PPTX_MARKUP_COMPATIBILITY_NAMESPACE = "http://schemas.openxmlformats.org/markup-compatibility/2006"

ElementTree.register_namespace("p", PPTX_PRESENTATION_NAMESPACE)
ElementTree.register_namespace("a", PPTX_DRAWING_NAMESPACE)
ElementTree.register_namespace("r", PPTX_RELATIONSHIPS_NAMESPACE)
ElementTree.register_namespace("a14", PPTX_DRAWING_2010_NAMESPACE)
ElementTree.register_namespace("m", PPTX_OFFICE_MATH_NAMESPACE)
ElementTree.register_namespace("mc", PPTX_MARKUP_COMPATIBILITY_NAMESPACE)


@dataclass(frozen=True)
class SvgFormulaStyle:
    font_family: str | None = None
    font_size: float | None = None
    fill: str | None = None
    font_weight: str | None = None
    font_style: str | None = None


@dataclass(frozen=True)
class SvgFormulaSpec:
    element_id: str
    latex: str
    bbox: tuple[float, float, float, float]
    latex_source: str
    style: SvgFormulaStyle = SvgFormulaStyle()


@dataclass(frozen=True)
class ConvertedFormulaSpec:
    source: SvgFormulaSpec
    omml_xml: str


class SvgToPptError(RuntimeError):
    """Raised when the deterministic SVG-to-PPT backend cannot produce a valid PPTX."""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_svg_to_ppt_unsafe_background_id(svg_id: str) -> bool:
    if svg_id in SVG_TO_PPT_UNSAFE_BACKGROUND_IDS:
        return True
    return any(
        svg_id.startswith(f"{prefix}_")
        for prefix in SVG_TO_PPT_UNSAFE_BACKGROUND_IDS
        if prefix.endswith("background")
    )


def _is_svg_to_ppt_unsafe_page_id(svg_id: str) -> bool:
    if svg_id == SVG_TO_PPT_SAFE_BACKGROUND_ID or svg_id.startswith(f"{SVG_TO_PPT_SAFE_OBJECT_ID_PREFIX}_"):
        return False
    return _is_svg_to_ppt_unsafe_background_id(svg_id) or SVG_TO_PPT_PAGE_ID_RE.search(svg_id) is not None


def _next_available_svg_id(existing_ids: set[str], preferred_id: str) -> str:
    if preferred_id not in existing_ids:
        existing_ids.add(preferred_id)
        return preferred_id
    suffix = 2
    while f"{preferred_id}_{suffix}" in existing_ids:
        suffix += 1
    candidate = f"{preferred_id}_{suffix}"
    existing_ids.add(candidate)
    return candidate


def _replace_svg_id_references(svg_text: str, id_rewrites: dict[str, str]) -> str:
    def replace_id_attr(match: re.Match[str]) -> str:
        quote, svg_id = match.groups()
        return f"id={quote}{id_rewrites.get(svg_id, svg_id)}{quote}"

    rewritten = SVG_ID_ATTR_RE.sub(replace_id_attr, svg_text)
    for old_id, new_id in id_rewrites.items():
        rewritten = rewritten.replace(f"url(#{old_id})", f"url(#{new_id})")
        rewritten = rewritten.replace(f"href=\"#{old_id}\"", f"href=\"#{new_id}\"")
        rewritten = rewritten.replace(f"href='#{old_id}'", f"href='#{new_id}'")
        rewritten = rewritten.replace(f"xlink:href=\"#{old_id}\"", f"xlink:href=\"#{new_id}\"")
        rewritten = rewritten.replace(f"xlink:href='#{old_id}'", f"xlink:href='#{new_id}'")
    return rewritten


def _svg_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag


def _parse_svg_number(value: str | None) -> float | None:
    if value is None:
        return None
    match = SVG_NUMERIC_RE.search(value)
    if match is None:
        return None
    return float(match.group(0))


def _format_svg_number(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _decode_formula_latex(element: ElementTree.Element) -> tuple[str, str] | tuple[None, None]:
    latex_b64 = element.get(DRAWAI_FORMULA_LATEX_B64_ATTR)
    if latex_b64:
        try:
            return base64.b64decode(latex_b64, validate=True).decode("utf-8"), DRAWAI_FORMULA_LATEX_B64_ATTR
        except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
            raise SvgToPptError(
                f"Formula {DRAWAI_FORMULA_LATEX_B64_ATTR} is not valid UTF-8 base64."
            ) from exc
    latex = element.get(DRAWAI_FORMULA_LATEX_ATTR)
    if latex:
        return latex, DRAWAI_FORMULA_LATEX_ATTR
    return None, None


def _parse_formula_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    numbers = [float(match.group(0)) for match in SVG_NUMERIC_RE.finditer(value)]
    if len(numbers) != 4:
        return None
    x, y, width, height = numbers
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _fallback_formula_bbox(element: ElementTree.Element) -> tuple[float, float, float, float] | None:
    boxes: list[tuple[float, float, float, float]] = []
    for text_element in element.iter():
        if _svg_local_name(text_element.tag) != "text":
            continue
        box = _fallback_formula_text_bbox(text_element)
        if box is not None:
            boxes.append(box)
    if not boxes:
        return None

    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes)
    bottom = max(box[1] + box[3] for box in boxes)
    return left, top, max(1.0, right - left), max(1.0, bottom - top)


def _fallback_formula_text_bbox(text_element: ElementTree.Element) -> tuple[float, float, float, float] | None:
    x = _parse_svg_number(_svg_style_value(text_element, "x"))
    baseline_y = _parse_svg_number(_svg_style_value(text_element, "y"))
    font_size = _parse_svg_number(_svg_style_value(text_element, "font-size"))
    if x is None or baseline_y is None or font_size is None or font_size <= 0:
        return None

    text = "".join(text_element.itertext()).strip()
    if not text:
        return None

    width = _fallback_formula_text_width(text_element, text, font_size)
    if width is None or width <= 0:
        return None

    anchor = (_svg_style_value(text_element, "text-anchor") or "").strip().lower()
    if anchor == "middle":
        x -= width / 2.0
    elif anchor == "end":
        x -= width

    top = baseline_y - font_size * 0.85
    height = font_size * 1.2
    return x, top, width, height


def _fallback_formula_text_width(
    text_element: ElementTree.Element,
    text: str,
    font_size: float,
) -> float | None:
    explicit_length = _parse_svg_number(_svg_style_value(text_element, "textLength"))
    if explicit_length is not None:
        return explicit_length

    font_family = _svg_style_value(text_element, "font-family") or ""
    font_weight = _svg_style_value(text_element, "font-weight") or ""
    font_style = _svg_style_value(text_element, "font-style") or ""
    measured = _measure_svg_to_ppt_text_width(text, font_family, font_size, font_weight, font_style)
    if measured is None:
        measured = len(text) * font_size * SVG_TO_PPT_TSPAN_TEXT_WIDTH_FALLBACK_EM_RATIO

    letter_spacing = _parse_svg_number(_svg_style_value(text_element, "letter-spacing"))
    if letter_spacing is not None and len(text) > 1:
        measured += letter_spacing * (len(text) - 1)
    return measured


def _fallback_formula_style(element: ElementTree.Element) -> SvgFormulaStyle:
    text_element = None
    for descendant in element.iter():
        if _svg_local_name(descendant.tag) == "text":
            text_element = descendant
            break
    if text_element is None:
        return SvgFormulaStyle()

    def style_value(name: str) -> str | None:
        return _svg_style_value(text_element, name) or _svg_style_value(element, name)

    return SvgFormulaStyle(
        font_family=style_value("font-family"),
        font_size=_parse_svg_number(style_value("font-size")),
        fill=style_value("fill"),
        font_weight=style_value("font-weight"),
        font_style=style_value("font-style"),
    )


def _should_replace_formula_bbox_with_fallback(
    metadata_bbox: tuple[float, float, float, float],
    fallback_bbox: tuple[float, float, float, float],
) -> bool:
    metadata_center_x = metadata_bbox[0] + metadata_bbox[2] / 2.0
    metadata_center_y = metadata_bbox[1] + metadata_bbox[3] / 2.0
    fallback_center_x = fallback_bbox[0] + fallback_bbox[2] / 2.0
    fallback_center_y = fallback_bbox[1] + fallback_bbox[3] / 2.0

    center_x_delta = abs(metadata_center_x - fallback_center_x)
    center_y_delta = abs(metadata_center_y - fallback_center_y)
    if center_x_delta > max(12.0, fallback_bbox[2] * 0.25):
        return True
    if center_y_delta > max(8.0, fallback_bbox[3] * 0.75):
        return True
    if metadata_bbox[2] < fallback_bbox[2] * 0.45:
        return True
    if metadata_bbox[3] < fallback_bbox[3] * 0.45:
        return True
    return False


def _collect_svg_formula_specs(svg_path: str | Path) -> tuple[list[SvgFormulaSpec], dict[str, Any]]:
    source = Path(svg_path).resolve(strict=False)
    try:
        root = ElementTree.fromstring(source.read_text(encoding="utf-8"))
    except ElementTree.ParseError as exc:
        raise SvgToPptError("semantic SVG XML could not be parsed for formula extraction") from exc

    specs: list[SvgFormulaSpec] = []
    issues: list[dict[str, Any]] = []
    bbox_corrections: list[dict[str, Any]] = []
    candidate_count = 0
    for index, element in enumerate(root.iter(), start=1):
        if element.get("data-pb-role") != DRAWAI_FORMULA_ROLE:
            continue
        if not element.get(DRAWAI_FORMULA_LATEX_B64_ATTR) and not element.get(DRAWAI_FORMULA_LATEX_ATTR):
            continue
        candidate_count += 1
        element_id = element.get("id") or f"formula_{index}"
        try:
            latex, latex_source = _decode_formula_latex(element)
        except SvgToPptError as exc:
            issues.append(
                {
                    "element_id": element_id,
                    "issue_type": "formula_latex_decode_failed",
                    "severity": "warning",
                    "message": str(exc),
                }
            )
            continue
        bbox = _parse_formula_bbox(element.get(DRAWAI_FORMULA_BBOX_ATTR))
        fallback_bbox = _fallback_formula_bbox(element)
        style = _fallback_formula_style(element)
        if latex is None:
            issues.append(
                {
                    "element_id": element_id,
                    "issue_type": "formula_latex_missing",
                    "severity": "warning",
                    "message": "Formula metadata is missing a LaTeX source attribute.",
                }
            )
            continue
        if bbox is None:
            if fallback_bbox is None:
                issues.append(
                    {
                        "element_id": element_id,
                        "issue_type": "formula_bbox_missing",
                        "severity": "warning",
                        "message": f"Formula metadata must include {DRAWAI_FORMULA_BBOX_ATTR}=\"x y width height\".",
                    }
                )
                continue
            bbox = fallback_bbox
            bbox_corrections.append(
                {
                    "element_id": element_id,
                    "old_bbox": None,
                    "new_bbox": list(bbox),
                    "reason": "fallback_text_bbox_missing_metadata",
                }
            )
        elif fallback_bbox is not None and _should_replace_formula_bbox_with_fallback(bbox, fallback_bbox):
            old_bbox = bbox
            bbox = fallback_bbox
            bbox_corrections.append(
                {
                    "element_id": element_id,
                    "old_bbox": list(old_bbox),
                    "new_bbox": list(bbox),
                    "reason": "fallback_text_bbox_misaligned",
                }
            )
        specs.append(
            SvgFormulaSpec(
                element_id=element_id,
                latex=latex,
                bbox=bbox,
                latex_source=latex_source or "",
                style=style,
            )
        )

    report = {
        "candidate_count": candidate_count,
        "convertible_count": len(specs),
        "issues": issues,
        "bbox_corrections": bbox_corrections,
        "items": [
            {
                "element_id": spec.element_id,
                "latex_source": spec.latex_source,
                "bbox": list(spec.bbox),
                "style": _formula_style_report(spec.style),
            }
            for spec in specs
        ],
    }
    return specs, report


def _formula_style_report(style: SvgFormulaStyle) -> dict[str, Any]:
    report: dict[str, Any] = {}
    if style.font_family:
        report["font_family"] = style.font_family
    if style.font_size is not None:
        report["font_size"] = style.font_size
    if style.fill:
        report["fill"] = style.fill
    if style.font_weight:
        report["font_weight"] = style.font_weight
    if style.font_style:
        report["font_style"] = style.font_style
    return report


def _strip_converted_formula_elements(
    svg_path: str | Path,
    formulas: list[ConvertedFormulaSpec],
) -> tuple[Path, dict[str, Any]]:
    source = Path(svg_path).resolve(strict=False)
    if not formulas:
        return source, {
            "status": "unchanged",
            "source_svg": str(source),
            "stripped_svg": str(source),
            "removed_formula_ids": [],
        }

    try:
        root = ElementTree.fromstring(source.read_text(encoding="utf-8"))
    except ElementTree.ParseError as exc:
        raise SvgToPptError("semantic SVG XML could not be parsed for formula stripping") from exc

    target_ids = {formula.source.element_id for formula in formulas}
    parent_by_child = {child: parent for parent in root.iter() for child in list(parent)}
    removed_ids: list[str] = []
    for element in list(root.iter()):
        element_id = element.get("id")
        if element_id not in target_ids:
            continue
        parent = parent_by_child.get(element)
        if parent is None:
            continue
        parent.remove(element)
        removed_ids.append(element_id)

    if not removed_ids:
        return source, {
            "status": "unchanged",
            "source_svg": str(source),
            "stripped_svg": str(source),
            "removed_formula_ids": [],
        }

    ElementTree.register_namespace("", SVG_NAMESPACE)
    stripped = source.with_name(f"{source.stem}.formula_stripped{source.suffix}")
    stripped.write_text(ElementTree.tostring(root, encoding="unicode"), encoding="utf-8")
    return stripped, {
        "status": "stripped",
        "source_svg": str(source),
        "stripped_svg": str(stripped),
        "removed_formula_ids": removed_ids,
    }


def _extract_first_math_xml_from_pptx(pptx_path: str | Path) -> str:
    with zipfile.ZipFile(pptx_path) as archive:
        slide_names = sorted(
            name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for slide_name in slide_names:
            root = ElementTree.fromstring(archive.read(slide_name))
            for element in root.iter():
                if element.tag == f"{{{PPTX_DRAWING_2010_NAMESPACE}}}m":
                    return ElementTree.tostring(element, encoding="unicode")
                if element.tag == f"{{{PPTX_OFFICE_MATH_NAMESPACE}}}oMathPara":
                    wrapper = ElementTree.Element(f"{{{PPTX_DRAWING_2010_NAMESPACE}}}m")
                    wrapper.append(copy.deepcopy(element))
                    return ElementTree.tostring(wrapper, encoding="unicode")
    raise SvgToPptError("Pandoc PPTX output did not contain Office Math XML.")


def _latex_to_omml(latex: str) -> str:
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise SvgToPptError("pandoc is required to convert LaTeX formulas to Office Math for PPT export.")

    with tempfile.TemporaryDirectory(prefix="drawai_latex_omml_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        markdown_path = temp_dir / "formula.md"
        pptx_path = temp_dir / "formula.pptx"
        markdown_path.write_text(f"$$\n{latex}\n$$\n", encoding="utf-8")
        try:
            subprocess.run(
                [pandoc, "--standalone", "--slide-level=1", "-o", str(pptx_path), str(markdown_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            message = "pandoc failed to convert LaTeX formula to Office Math"
            if stderr:
                message = f"{message}: {stderr}"
            raise SvgToPptError(message) from exc
        return _extract_first_math_xml_from_pptx(pptx_path)


def _convert_formula_specs(specs: list[SvgFormulaSpec]) -> tuple[list[ConvertedFormulaSpec], list[dict[str, Any]]]:
    converted: list[ConvertedFormulaSpec] = []
    issues: list[dict[str, Any]] = []
    for spec in specs:
        try:
            converted.append(ConvertedFormulaSpec(source=spec, omml_xml=_latex_to_omml(spec.latex)))
        except SvgToPptError as exc:
            issues.append(
                {
                    "element_id": spec.element_id,
                    "issue_type": "formula_omml_convert_failed",
                    "severity": "warning",
                    "message": str(exc),
                }
            )
    return converted, issues


def _svg_viewbox(svg_path: str | Path) -> tuple[float, float, float, float]:
    source = Path(svg_path).resolve(strict=False)
    try:
        root = ElementTree.fromstring(source.read_text(encoding="utf-8"))
    except ElementTree.ParseError as exc:
        raise SvgToPptError("semantic SVG XML could not be parsed for formula geometry") from exc

    view_box = root.get("viewBox")
    if view_box:
        numbers = [float(match.group(0)) for match in SVG_NUMERIC_RE.finditer(view_box)]
        if len(numbers) == 4 and numbers[2] > 0 and numbers[3] > 0:
            return numbers[0], numbers[1], numbers[2], numbers[3]

    width = _parse_svg_number(root.get("width"))
    height = _parse_svg_number(root.get("height"))
    if width is not None and height is not None and width > 0 and height > 0:
        return 0.0, 0.0, width, height
    raise SvgToPptError("Formula export requires an SVG viewBox or positive width/height.")


def _pptx_slide_size_emu(extracted_pptx_dir: Path) -> tuple[int, int]:
    presentation_xml = extracted_pptx_dir / "ppt" / "presentation.xml"
    root = ElementTree.fromstring(presentation_xml.read_bytes())
    slide_size = root.find(f".//{{{PPTX_PRESENTATION_NAMESPACE}}}sldSz")
    if slide_size is None:
        raise SvgToPptError("PPTX presentation.xml is missing p:sldSz.")
    cx = int(slide_size.get("cx") or "0")
    cy = int(slide_size.get("cy") or "0")
    if cx <= 0 or cy <= 0:
        raise SvgToPptError("PPTX slide size is invalid.")
    return cx, cy


def _formula_bbox_to_emu(
    bbox: tuple[float, float, float, float],
    svg_viewbox: tuple[float, float, float, float],
    slide_size_emu: tuple[int, int],
) -> tuple[int, int, int, int]:
    bbox_x, bbox_y, bbox_width, bbox_height = bbox
    view_x, view_y, view_width, view_height = svg_viewbox
    slide_width, slide_height = slide_size_emu
    return (
        round(((bbox_x - view_x) / view_width) * slide_width),
        round(((bbox_y - view_y) / view_height) * slide_height),
        max(1, round((bbox_width / view_width) * slide_width)),
        max(1, round((bbox_height / view_height) * slide_height)),
    )


def _next_pptx_shape_id(slide_root: ElementTree.Element) -> int:
    max_id = 0
    for element in slide_root.iter(f"{{{PPTX_PRESENTATION_NAMESPACE}}}cNvPr"):
        value = element.get("id")
        if value and value.isdigit():
            max_id = max(max_id, int(value))
    return max_id + 1


def _office_math_element(omml_xml: str) -> ElementTree.Element:
    element = ElementTree.fromstring(omml_xml)
    if element.tag == f"{{{PPTX_DRAWING_2010_NAMESPACE}}}m":
        return element
    if element.tag == f"{{{PPTX_OFFICE_MATH_NAMESPACE}}}oMathPara":
        wrapper = ElementTree.Element(f"{{{PPTX_DRAWING_2010_NAMESPACE}}}m")
        wrapper.append(element)
        return wrapper
    raise SvgToPptError("Formula converter returned XML without an a14:m or m:oMathPara root.")


def _formula_drawing_run_attrs(style: SvgFormulaStyle) -> dict[str, str]:
    attrs: dict[str, str] = {}
    if style.font_size is not None and style.font_size > 0:
        attrs["sz"] = str(max(100, int(round(style.font_size * 100))))
    if _svg_font_weight_is_bold(style.font_weight or ""):
        attrs["b"] = "1"
    if (style.font_style or "").strip().lower() in {"italic", "oblique"}:
        attrs["i"] = "1"
    return attrs


def _svg_color_to_srgb_hex(value: str | None) -> str | None:
    if value is None:
        return None
    color = value.strip()
    if not color or color.lower() in {"none", "currentcolor", "context-fill", "context-stroke"}:
        return None
    if color.startswith("#"):
        digits = color[1:].strip()
        if len(digits) == 3 and all(ch in "0123456789abcdefABCDEF" for ch in digits):
            return "".join(ch * 2 for ch in digits).upper()
        if len(digits) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in digits):
            return digits.upper()
    return None


def _primary_svg_font_family(font_family: str | None) -> str | None:
    if not font_family:
        return None
    names = _svg_font_family_names(font_family)
    return names[0].title() if names else None


def _append_formula_drawing_style(parent: ElementTree.Element, style: SvgFormulaStyle) -> None:
    run_attrs = _formula_drawing_run_attrs(style)
    fill = _svg_color_to_srgb_hex(style.fill)
    typeface = _primary_svg_font_family(style.font_family)
    if not run_attrs and fill is None and typeface is None:
        return

    default_run = ElementTree.SubElement(parent, f"{{{PPTX_DRAWING_NAMESPACE}}}defRPr", run_attrs)
    if fill is not None:
        solid_fill = ElementTree.SubElement(default_run, f"{{{PPTX_DRAWING_NAMESPACE}}}solidFill")
        ElementTree.SubElement(solid_fill, f"{{{PPTX_DRAWING_NAMESPACE}}}srgbClr", {"val": fill})
    if typeface is not None:
        for tag_name in ("latin", "ea", "cs"):
            ElementTree.SubElement(default_run, f"{{{PPTX_DRAWING_NAMESPACE}}}{tag_name}", {"typeface": typeface})


def _office_math_style_value(style: SvgFormulaStyle) -> str | None:
    bold = _svg_font_weight_is_bold(style.font_weight or "")
    italic = (style.font_style or "").strip().lower() in {"italic", "oblique"}
    if bold and italic:
        return "bi"
    if bold:
        return "b"
    if italic:
        return "i"
    return None


def _apply_office_math_style(math_element: ElementTree.Element, style: SvgFormulaStyle) -> None:
    style_value = _office_math_style_value(style)
    if style_value is None:
        return
    for run in math_element.iter(f"{{{PPTX_OFFICE_MATH_NAMESPACE}}}r"):
        run_properties = run.find(f"{{{PPTX_OFFICE_MATH_NAMESPACE}}}rPr")
        if run_properties is None:
            run_properties = ElementTree.Element(f"{{{PPTX_OFFICE_MATH_NAMESPACE}}}rPr")
            run.insert(0, run_properties)
        sty = run_properties.find(f"{{{PPTX_OFFICE_MATH_NAMESPACE}}}sty")
        if sty is None:
            sty = ElementTree.SubElement(run_properties, f"{{{PPTX_OFFICE_MATH_NAMESPACE}}}sty")
        sty.set(f"{{{PPTX_OFFICE_MATH_NAMESPACE}}}val", style_value)


def _append_office_math_shape(
    slide_root: ElementTree.Element,
    formula: ConvertedFormulaSpec,
    shape_id: int,
    geometry_emu: tuple[int, int, int, int],
) -> None:
    x, y, width, height = geometry_emu
    sp_tree = slide_root.find(f".//{{{PPTX_PRESENTATION_NAMESPACE}}}spTree")
    if sp_tree is None:
        raise SvgToPptError("PPTX slide XML is missing p:spTree.")

    alternate_content = ElementTree.Element(f"{{{PPTX_MARKUP_COMPATIBILITY_NAMESPACE}}}AlternateContent")
    choice = ElementTree.SubElement(
        alternate_content,
        f"{{{PPTX_MARKUP_COMPATIBILITY_NAMESPACE}}}Choice",
        {"Requires": "a14"},
    )
    sp = ElementTree.SubElement(choice, f"{{{PPTX_PRESENTATION_NAMESPACE}}}sp")
    nv_sp_pr = ElementTree.SubElement(sp, f"{{{PPTX_PRESENTATION_NAMESPACE}}}nvSpPr")
    ElementTree.SubElement(
        nv_sp_pr,
        f"{{{PPTX_PRESENTATION_NAMESPACE}}}cNvPr",
        {"id": str(shape_id), "name": f"DrawAI formula {formula.source.element_id}"},
    )
    ElementTree.SubElement(nv_sp_pr, f"{{{PPTX_PRESENTATION_NAMESPACE}}}cNvSpPr", {"txBox": "1"})
    ElementTree.SubElement(nv_sp_pr, f"{{{PPTX_PRESENTATION_NAMESPACE}}}nvPr")

    sp_pr = ElementTree.SubElement(sp, f"{{{PPTX_PRESENTATION_NAMESPACE}}}spPr")
    xfrm = ElementTree.SubElement(sp_pr, f"{{{PPTX_DRAWING_NAMESPACE}}}xfrm")
    ElementTree.SubElement(xfrm, f"{{{PPTX_DRAWING_NAMESPACE}}}off", {"x": str(x), "y": str(y)})
    ElementTree.SubElement(xfrm, f"{{{PPTX_DRAWING_NAMESPACE}}}ext", {"cx": str(width), "cy": str(height)})
    prst_geom = ElementTree.SubElement(sp_pr, f"{{{PPTX_DRAWING_NAMESPACE}}}prstGeom", {"prst": "rect"})
    ElementTree.SubElement(prst_geom, f"{{{PPTX_DRAWING_NAMESPACE}}}avLst")
    ElementTree.SubElement(sp_pr, f"{{{PPTX_DRAWING_NAMESPACE}}}noFill")
    line = ElementTree.SubElement(sp_pr, f"{{{PPTX_DRAWING_NAMESPACE}}}ln")
    ElementTree.SubElement(line, f"{{{PPTX_DRAWING_NAMESPACE}}}noFill")

    tx_body = ElementTree.SubElement(sp, f"{{{PPTX_PRESENTATION_NAMESPACE}}}txBody")
    body_pr = ElementTree.SubElement(
        tx_body,
        f"{{{PPTX_DRAWING_NAMESPACE}}}bodyPr",
        {
            "wrap": "none",
            "anchor": "ctr",
            "rtlCol": "0",
            "lIns": "0",
            "tIns": "0",
            "rIns": "0",
            "bIns": "0",
        },
    )
    ElementTree.SubElement(body_pr, f"{{{PPTX_DRAWING_NAMESPACE}}}noAutofit")
    ElementTree.SubElement(tx_body, f"{{{PPTX_DRAWING_NAMESPACE}}}lstStyle")
    paragraph = ElementTree.SubElement(tx_body, f"{{{PPTX_DRAWING_NAMESPACE}}}p")
    paragraph_properties = ElementTree.SubElement(paragraph, f"{{{PPTX_DRAWING_NAMESPACE}}}pPr", {"algn": "ctr"})
    _append_formula_drawing_style(paragraph_properties, formula.source.style)
    math_element = _office_math_element(formula.omml_xml)
    _apply_office_math_style(math_element, formula.source.style)
    paragraph.append(math_element)
    sp_tree.append(alternate_content)


def _rewrite_pptx_zip(extracted_pptx_dir: Path, target_pptx: Path) -> None:
    patched_pptx = target_pptx.with_suffix(".formula_patch.pptx")
    with zipfile.ZipFile(patched_pptx, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(extracted_pptx_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(extracted_pptx_dir).as_posix())
    patched_pptx.replace(target_pptx)


def _inject_office_math_formulas(
    pptx_path: str | Path,
    svg_path: str | Path,
    formulas: list[ConvertedFormulaSpec],
) -> dict[str, Any]:
    if not formulas:
        return {"status": "skipped", "inserted": 0, "items": []}

    target = Path(pptx_path).resolve(strict=False)
    svg_viewbox = _svg_viewbox(svg_path)
    with tempfile.TemporaryDirectory(prefix="drawai_pptx_formula_") as temp_dir_name:
        extracted = Path(temp_dir_name) / "pptx"
        with zipfile.ZipFile(target) as archive:
            archive.extractall(extracted)

        slide_xml_path = extracted / "ppt" / "slides" / "slide1.xml"
        slide_root = ElementTree.fromstring(slide_xml_path.read_bytes())
        slide_size = _pptx_slide_size_emu(extracted)
        shape_id = _next_pptx_shape_id(slide_root)
        items: list[dict[str, Any]] = []
        for offset, formula in enumerate(formulas):
            geometry = _formula_bbox_to_emu(formula.source.bbox, svg_viewbox, slide_size)
            _append_office_math_shape(slide_root, formula, shape_id + offset, geometry)
            items.append(
                {
                    "element_id": formula.source.element_id,
                    "shape_id": shape_id + offset,
                    "bbox": list(formula.source.bbox),
                    "geometry_emu": list(geometry),
                }
            )

        slide_xml_path.write_text(ElementTree.tostring(slide_root, encoding="unicode"), encoding="utf-8")
        _rewrite_pptx_zip(extracted, target)

    return {"status": "ok", "inserted": len(formulas), "items": items}


def _prepare_formula_export(svg_path: str | Path) -> tuple[Path, list[ConvertedFormulaSpec], dict[str, Any]]:
    source = Path(svg_path).resolve(strict=False)
    specs, collection_report = _collect_svg_formula_specs(source)
    converted, conversion_issues = _convert_formula_specs(specs)
    stripped_svg, strip_report = _strip_converted_formula_elements(source, converted)

    total = collection_report["candidate_count"]
    converted_count = len(converted)
    fallback_count = total - converted_count
    if total == 0:
        status = "not_found"
    elif fallback_count == 0:
        status = "ok"
    elif converted_count:
        status = "partial"
    else:
        status = "fallback"

    report = {
        "status": status,
        "count": total,
        "converted": converted_count,
        "fallback": fallback_count,
        "collection": collection_report,
        "conversion_issues": conversion_issues,
        "strip": strip_report,
    }
    return stripped_svg, converted, report


def _normalize_tspan_dy_positions_for_svg_to_ppt(svg_text: str) -> tuple[str, list[dict[str, Any]]]:
    """Expand relative tspan dy positions into absolute y values for PPT export."""

    try:
        root = ElementTree.fromstring(svg_text)
    except ElementTree.ParseError as exc:
        raise SvgToPptError("semantic SVG XML could not be parsed for svg_to_ppt preparation") from exc

    normalizations: list[dict[str, Any]] = []
    changed = False
    for text_el in root.iter():
        if _svg_local_name(text_el.tag) != "text":
            continue
        base_y = _parse_svg_number(text_el.get("y"))
        if base_y is None:
            continue
        current_y = base_y
        normalized_count = 0
        for child in list(text_el):
            if _svg_local_name(child.tag) != "tspan":
                continue
            child_y = _parse_svg_number(child.get("y"))
            child_dy = _parse_svg_number(child.get("dy"))
            if child_y is not None:
                current_y = child_y + (child_dy or 0.0)
                if child_dy is not None:
                    child.set("y", _format_svg_number(current_y))
                    child.attrib.pop("dy", None)
                    changed = True
                    normalized_count += 1
                continue
            if child_dy is None:
                continue
            current_y += child_dy
            child.set("y", _format_svg_number(current_y))
            child.attrib.pop("dy", None)
            changed = True
            normalized_count += 1
        if normalized_count:
            normalizations.append(
                {
                    "text_id": text_el.get("id") or "",
                    "tspan_count": normalized_count,
                }
            )

    if not changed:
        return svg_text, []

    ElementTree.register_namespace("", SVG_NAMESPACE)
    return ElementTree.tostring(root, encoding="unicode"), normalizations


def _svg_style_value(element: ElementTree.Element, name: str) -> str | None:
    direct = element.get(name)
    if direct is not None:
        return direct
    style = element.get("style")
    if not style:
        return None
    for part in style.split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        if key.strip() == name:
            return value.strip()
    return None


def _materialize_positioned_tspan_inherited_attrs_for_svg_to_ppt(
    svg_text: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Make positioned tspans self-contained before PPT export."""

    try:
        root = ElementTree.fromstring(svg_text)
    except ElementTree.ParseError as exc:
        raise SvgToPptError("semantic SVG XML could not be parsed for svg_to_ppt preparation") from exc

    normalizations: list[dict[str, Any]] = []
    changed = False
    for text_el in root.iter():
        if _svg_local_name(text_el.tag) != "text":
            continue
        inherited_values = {
            attr_name: value
            for attr_name in SVG_TO_PPT_POSITIONED_TSPAN_INHERITED_ATTRS
            if (value := _svg_style_value(text_el, attr_name)) is not None
        }
        if not inherited_values:
            continue

        copied_attrs: set[str] = set()
        copied_tspan_count = 0
        for child in list(text_el):
            if _svg_local_name(child.tag) != "tspan":
                continue
            is_positioned = any(_svg_style_value(child, name) is not None for name in ("x", "y", "dx", "dy"))
            if not is_positioned:
                continue

            copied_this_tspan = False
            for attr_name, inherited_value in inherited_values.items():
                if _svg_style_value(child, attr_name) is not None:
                    continue
                child.set(attr_name, inherited_value)
                copied_attrs.add(attr_name)
                copied_this_tspan = True
                changed = True
            if copied_this_tspan:
                copied_tspan_count += 1

        if copied_tspan_count:
            normalizations.append(
                {
                    "text_id": text_el.get("id") or "",
                    "tspan_count": copied_tspan_count,
                    "attributes": sorted(copied_attrs),
                }
            )

    if not changed:
        return svg_text, []

    ElementTree.register_namespace("", SVG_NAMESPACE)
    return ElementTree.tostring(root, encoding="unicode"), normalizations


def _normalize_positioned_tspan_anchors_for_svg_to_ppt(svg_text: str) -> tuple[str, list[dict[str, Any]]]:
    """Rewrite centered/end-aligned tspans into start-aligned positioned runs.

    svg_to_ppt handles ``text-anchor`` on plain ``text`` reasonably, but treats
    positioned ``tspan`` rows as independent start-aligned text boxes. Adjusting
    the tspan x coordinate before conversion preserves the browser-rendered
    visual anchor while keeping editable PowerPoint text.
    """

    try:
        root = ElementTree.fromstring(svg_text)
    except ElementTree.ParseError as exc:
        raise SvgToPptError("semantic SVG XML could not be parsed for svg_to_ppt preparation") from exc

    normalizations: list[dict[str, Any]] = []
    changed = False
    for text_el in root.iter():
        if _svg_local_name(text_el.tag) != "text":
            continue

        text_normalizations: list[dict[str, Any]] = []
        for child in list(text_el):
            if _svg_local_name(child.tag) != "tspan":
                continue
            anchor = (_svg_style_value(child, "text-anchor") or "").strip().lower()
            if anchor not in {"middle", "end"}:
                continue
            x, x_source = _positioned_tspan_x(child, text_el)
            if x is None:
                continue
            width = _estimated_svg_to_ppt_tspan_text_width(child)
            if width is None or width <= 0.0:
                continue

            adjusted_x = x - (width / 2.0 if anchor == "middle" else width)
            child.set("x", _format_svg_number(adjusted_x))
            child.attrib.pop("dx", None)
            child.set("text-anchor", "start")
            text_normalizations.append(
                {
                    "text": "".join(child.itertext()),
                    "anchor": anchor,
                    "x_source": x_source,
                    "old_x": x,
                    "new_x": adjusted_x,
                    "estimated_width": width,
                }
            )
            changed = True

        if text_normalizations:
            normalizations.append(
                {
                    "text_id": text_el.get("id") or "",
                    "tspans": text_normalizations,
                }
            )

    if not changed:
        return svg_text, []

    ElementTree.register_namespace("", SVG_NAMESPACE)
    return ElementTree.tostring(root, encoding="unicode"), normalizations


def _positioned_tspan_x(
    tspan: ElementTree.Element,
    text_element: ElementTree.Element,
) -> tuple[float | None, str]:
    child_x = _parse_svg_number(_svg_style_value(tspan, "x"))
    if child_x is None:
        x = _parse_svg_number(_svg_style_value(text_element, "x"))
        source = "parent_text_x"
    else:
        x = child_x
        source = "tspan_x"
    if x is None:
        return None, "missing"

    dx = _parse_svg_number(_svg_style_value(tspan, "dx"))
    if dx is not None:
        return x + dx, f"{source}+tspan_dx"
    return x, source


def _estimated_svg_to_ppt_tspan_text_width(element: ElementTree.Element) -> float | None:
    explicit_length = _parse_svg_number(_svg_style_value(element, "textLength"))
    if explicit_length is not None:
        return explicit_length
    font_size = _parse_svg_number(_svg_style_value(element, "font-size"))
    if font_size is None:
        return None
    text = "".join(element.itertext())
    if not text:
        return None
    font_family = _svg_style_value(element, "font-family") or ""
    font_weight = _svg_style_value(element, "font-weight") or ""
    font_style = _svg_style_value(element, "font-style") or ""
    measured = _measure_svg_to_ppt_text_width(text, font_family, font_size, font_weight, font_style)
    letter_spacing = _parse_svg_number(_svg_style_value(element, "letter-spacing"))
    if measured is not None:
        if letter_spacing is not None and len(text) > 1:
            measured += letter_spacing * (len(text) - 1)
        return measured
    return len(text) * font_size * SVG_TO_PPT_TSPAN_TEXT_WIDTH_FALLBACK_EM_RATIO


def _measure_svg_to_ppt_text_width(
    text: str,
    font_family: str,
    font_size: float,
    font_weight: str,
    font_style: str,
) -> float | None:
    scaled_size = max(1, int(round(font_size * SVG_TO_PPT_FONT_MEASURE_SCALE)))
    font = _svg_to_ppt_measurement_font(font_family, font_weight, font_style, scaled_size)
    if font is None:
        return None
    image = Image.new("RGB", (1, 1), "white")
    draw = ImageDraw.Draw(image)
    bbox = draw.textbbox((0, 0), text, font=font)
    return (bbox[2] - bbox[0]) / SVG_TO_PPT_FONT_MEASURE_SCALE


@lru_cache(maxsize=512)
def _svg_to_ppt_measurement_font(
    font_family: str,
    font_weight: str,
    font_style: str,
    font_size: int,
) -> ImageFont.ImageFont | None:
    for candidate in _svg_to_ppt_font_candidate_paths(font_family, font_weight, font_style):
        try:
            return ImageFont.truetype(candidate, font_size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()


def _svg_to_ppt_font_candidate_paths(font_family: str, font_weight: str, font_style: str) -> list[str]:
    families = _svg_font_family_names(font_family)
    if not families:
        families = ["arial"]
    bold = _svg_font_weight_is_bold(font_weight)
    italic = font_style.strip().lower() in {"italic", "oblique"}

    candidates: list[str] = []
    for family in families:
        if family in {"arial", "helvetica", "sans-serif", "sans"}:
            if bold and italic:
                candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["arial-bold-italic"])
            elif bold:
                candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["arial-bold"])
            elif italic:
                candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["arial-italic"])
            candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["arial"])
        elif family in {"times", "times new roman", "serif", "georgia"}:
            if bold:
                candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["times-bold"])
            candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["times"])
        elif family in {"courier", "courier new", "monospace"}:
            if bold:
                candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["courier-bold"])
            candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["courier"])
        elif family == "verdana":
            candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["verdana"])
        elif family in {"pingfang sc", "hiragino sans gb", "songti sc", "noto sans cjk", "microsoft yahei"}:
            candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["cjk"])

    candidates.extend(SVG_TO_PPT_GENERIC_FONT_FAMILY_PATHS["arial"])
    return list(dict.fromkeys(candidates))


def _svg_font_family_names(font_family: str) -> list[str]:
    names: list[str] = []
    for raw_name in font_family.split(","):
        name = raw_name.strip().strip("'\"").lower()
        if name:
            names.append(name)
    return names


def _svg_font_weight_is_bold(font_weight: str) -> bool:
    text = font_weight.strip().lower()
    if text in {"bold", "bolder"}:
        return True
    numeric = _parse_svg_number(text)
    return numeric is not None and numeric >= 600


def _svg_marker_url_id(value: str | None) -> str | None:
    if not value:
        return None
    match = SVG_MARKER_URL_RE.match(value.strip())
    return match.group(1) if match else None


def _svg_view_box_values(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    values = [float(part) for part in re.split(r"[\s,]+", value.strip()) if part]
    if len(values) != 4 or values[2] == 0.0 or values[3] == 0.0:
        return None
    return values[0], values[1], values[2], values[3]


def _svg_marker_view_box(
    marker: ElementTree.Element,
    marker_width: float,
    marker_height: float,
) -> tuple[float, float, float, float] | None:
    raw_view_box = marker.get("viewBox")
    if raw_view_box:
        return _svg_view_box_values(raw_view_box)
    if marker_width == 0.0 or marker_height == 0.0:
        return None
    return 0.0, 0.0, marker_width, marker_height


def _svg_path_polygon_points(path_data: str) -> list[tuple[float, float]] | None:
    tokens = SVG_PATH_TOKEN_RE.findall(path_data)
    index = 0
    command = ""
    current = (0.0, 0.0)
    points: list[tuple[float, float]] = []

    def is_command(token: str) -> bool:
        return len(token) == 1 and token.isalpha()

    def read_number() -> float | None:
        nonlocal index
        if index >= len(tokens) or is_command(tokens[index]):
            return None
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        if is_command(tokens[index]):
            command = tokens[index]
            index += 1
        if not command:
            return None
        absolute = command.isupper()
        op = command.upper()
        if op == "Z":
            command = ""
            continue
        if op == "M":
            x = read_number()
            y = read_number()
            if x is None or y is None:
                return points if len(points) >= 3 else None
            current = (x, y) if absolute else (current[0] + x, current[1] + y)
            points.append(current)
            command = "L" if absolute else "l"
            continue
        if op == "L":
            x = read_number()
            y = read_number()
            if x is None or y is None:
                return points if len(points) >= 3 else None
            current = (x, y) if absolute else (current[0] + x, current[1] + y)
            points.append(current)
            continue
        if op == "H":
            x = read_number()
            if x is None:
                return points if len(points) >= 3 else None
            current = (x, current[1]) if absolute else (current[0] + x, current[1])
            points.append(current)
            continue
        if op == "V":
            y = read_number()
            if y is None:
                return points if len(points) >= 3 else None
            current = (current[0], y) if absolute else (current[0], current[1] + y)
            points.append(current)
            continue
        return None

    if len(points) >= 2 and points[0] == points[-1]:
        points.pop()
    return points if len(points) >= 3 else None


def _svg_points_from_marker_child(child: ElementTree.Element) -> list[tuple[float, float]] | None:
    local_name = _svg_local_name(child.tag)
    if local_name == "polygon":
        raw_points = child.get("points", "")
        values = [float(match.group(0)) for match in SVG_NUMERIC_RE.finditer(raw_points)]
        if len(values) < 6 or len(values) % 2 != 0:
            return None
        return list(zip(values[0::2], values[1::2]))
    if local_name == "path":
        return _svg_path_polygon_points(child.get("d", ""))
    else:
        return None


def _svg_marker_profiles(root: ElementTree.Element) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for marker in root.iter():
        if _svg_local_name(marker.tag) != "marker":
            continue
        marker_id = marker.get("id")
        if not marker_id:
            continue
        marker_width = _parse_svg_number(marker.get("markerWidth"))
        marker_height = _parse_svg_number(marker.get("markerHeight"))
        ref_x = _parse_svg_number(marker.get("refX"))
        ref_y = _parse_svg_number(marker.get("refY"))
        if marker_width is None or marker_height is None or ref_x is None or ref_y is None:
            continue
        view_box = _svg_marker_view_box(marker, marker_width, marker_height)
        if view_box is None:
            continue
        child = next((candidate for candidate in list(marker) if _svg_points_from_marker_child(candidate)), None)
        if child is None:
            continue
        points = _svg_points_from_marker_child(child)
        if points is None:
            continue
        fill = _svg_style_value(child, "fill") or "context-stroke"
        stroke = _svg_style_value(child, "stroke") or "none"
        style_attrs: dict[str, str] = {}
        for attr_name in (
            "fill-opacity",
            "stroke-opacity",
            "stroke-width",
            "stroke-linecap",
            "stroke-linejoin",
            "opacity",
        ):
            attr_value = _svg_style_value(child, attr_name)
            if attr_value is not None:
                style_attrs[attr_name] = attr_value
        profiles[marker_id] = {
            "view_box": view_box,
            "marker_width": marker_width,
            "marker_height": marker_height,
            "ref_x": ref_x,
            "ref_y": ref_y,
            "marker_units": marker.get("markerUnits") or "strokeWidth",
            "orient": marker.get("orient") or "0",
            "points": points,
            "fill": fill,
            "stroke": stroke,
            "style_attrs": style_attrs,
        }
    return profiles


def _svg_float_style_or_attr(element: ElementTree.Element, name: str, default: float) -> float:
    value = _svg_style_value(element, name)
    parsed = _parse_svg_number(value)
    return default if parsed is None else parsed


def _svg_line_terminal_segment(element: ElementTree.Element) -> tuple[tuple[float, float], tuple[float, float]] | None:
    x1 = _parse_svg_number(element.get("x1"))
    y1 = _parse_svg_number(element.get("y1"))
    x2 = _parse_svg_number(element.get("x2"))
    y2 = _parse_svg_number(element.get("y2"))
    if x1 is None or y1 is None or x2 is None or y2 is None:
        return None
    return (x1, y1), (x2, y2)


def _svg_polyline_terminal_segment(element: ElementTree.Element) -> tuple[tuple[float, float], tuple[float, float]] | None:
    values = [float(match.group(0)) for match in SVG_NUMERIC_RE.finditer(element.get("points", ""))]
    if len(values) < 4 or len(values) % 2 != 0:
        return None
    points = list(zip(values[0::2], values[1::2]))
    return points[-2], points[-1]


def _svg_polyline_initial_segment(element: ElementTree.Element) -> tuple[tuple[float, float], tuple[float, float]] | None:
    values = [float(match.group(0)) for match in SVG_NUMERIC_RE.finditer(element.get("points", ""))]
    if len(values) < 4 or len(values) % 2 != 0:
        return None
    points = list(zip(values[0::2], values[1::2]))
    return points[0], points[1]


def _svg_path_segments(element: ElementTree.Element) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    tokens = SVG_PATH_TOKEN_RE.findall(element.get("d", ""))
    index = 0
    command = ""
    current = (0.0, 0.0)
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []

    def is_command(token: str) -> bool:
        return len(token) == 1 and token.isalpha()

    def read_number() -> float | None:
        nonlocal index
        if index >= len(tokens) or is_command(tokens[index]):
            return None
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        if is_command(tokens[index]):
            command = tokens[index]
            index += 1
        if not command:
            return segments
        absolute = command.isupper()
        op = command.upper()
        if op == "M":
            x = read_number()
            y = read_number()
            if x is None or y is None:
                return segments
            point = (x, y) if absolute else (current[0] + x, current[1] + y)
            current = point
            command = "L" if absolute else "l"
            continue
        if op == "L":
            x = read_number()
            y = read_number()
            if x is None or y is None:
                return segments
            point = (x, y) if absolute else (current[0] + x, current[1] + y)
            segments.append((current, point))
            current = point
            continue
        if op == "H":
            x = read_number()
            if x is None:
                return segments
            point = (x, current[1]) if absolute else (current[0] + x, current[1])
            segments.append((current, point))
            current = point
            continue
        if op == "V":
            y = read_number()
            if y is None:
                return segments
            point = (current[0], y) if absolute else (current[0], current[1] + y)
            segments.append((current, point))
            current = point
            continue
        if op == "C":
            x1 = read_number()
            y1 = read_number()
            x2 = read_number()
            y2 = read_number()
            x = read_number()
            y = read_number()
            if None in (x1, y1, x2, y2, x, y):
                return segments
            control_2 = (x2, y2) if absolute else (current[0] + x2, current[1] + y2)
            point = (x, y) if absolute else (current[0] + x, current[1] + y)
            segments.append((control_2, point))
            current = point
            continue
        return segments
    return segments


def _svg_path_terminal_segment(element: ElementTree.Element) -> tuple[tuple[float, float], tuple[float, float]] | None:
    segments = _svg_path_segments(element)
    return segments[-1] if segments else None


def _svg_path_initial_segment(element: ElementTree.Element) -> tuple[tuple[float, float], tuple[float, float]] | None:
    segments = _svg_path_segments(element)
    return segments[0] if segments else None


def _svg_terminal_segment(
    element: ElementTree.Element,
    position: str,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    local_name = _svg_local_name(element.tag)
    if local_name == "line":
        return _svg_line_terminal_segment(element)
    if local_name in {"polyline", "polygon"}:
        return _svg_polyline_initial_segment(element) if position == "start" else _svg_polyline_terminal_segment(element)
    if local_name == "path":
        return _svg_path_initial_segment(element) if position == "start" else _svg_path_terminal_segment(element)
    return None


def _svg_marker_polygon_points(
    marker_profile: dict[str, Any],
    *,
    stroke_width: float,
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
    marker_position: str,
) -> list[tuple[float, float]] | None:
    dx = segment_end[0] - segment_start[0]
    dy = segment_end[1] - segment_start[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return None
    orient = str(marker_profile.get("orient") or "0").strip()
    if orient in {"auto", "auto-start-reverse"}:
        angle = math.atan2(dy, dx)
        if marker_position == "start" and orient == "auto-start-reverse":
            angle += math.pi
    else:
        numeric_orient = _parse_svg_number(orient)
        if numeric_orient is None:
            return None
        angle = math.radians(numeric_orient)
    cos_theta = math.cos(angle)
    sin_theta = math.sin(angle)
    anchor = segment_start if marker_position == "start" else segment_end
    min_x, min_y, view_width, view_height = marker_profile["view_box"]
    scale_unit = stroke_width if marker_profile["marker_units"] == "strokeWidth" else 1.0
    scale_x = marker_profile["marker_width"] * scale_unit / view_width
    scale_y = marker_profile["marker_height"] * scale_unit / view_height
    ref_x = marker_profile["ref_x"]
    ref_y = marker_profile["ref_y"]
    polygon_points: list[tuple[float, float]] = []
    for point_x, point_y in marker_profile["points"]:
        local_x = (point_x - min_x - ref_x) * scale_x
        local_y = (point_y - min_y - ref_y) * scale_y
        rotated_x = local_x * cos_theta - local_y * sin_theta
        rotated_y = local_x * sin_theta + local_y * cos_theta
        polygon_points.append((anchor[0] + rotated_x, anchor[1] + rotated_y))
    return polygon_points


def _format_svg_points(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{_format_svg_number(x)},{_format_svg_number(y)}" for x, y in points)


def _expand_svg_marker_endings_for_svg_to_ppt(svg_text: str) -> tuple[str, list[dict[str, Any]]]:
    try:
        root = ElementTree.fromstring(svg_text)
    except ElementTree.ParseError as exc:
        raise SvgToPptError("semantic SVG XML could not be parsed for marker expansion") from exc

    marker_profiles = _svg_marker_profiles(root)
    if not marker_profiles:
        return svg_text, []

    existing_ids = {element_id for element in root.iter() if (element_id := element.get("id"))}
    expansions: list[dict[str, Any]] = []
    changed = False
    for parent in root.iter():
        children = list(parent)
        for index, element in enumerate(children):
            insert_offset = 1
            for marker_position, marker_attr in (("start", "marker-start"), ("end", "marker-end")):
                marker_id = _svg_marker_url_id(element.get(marker_attr))
                if marker_id is None or marker_id not in marker_profiles:
                    continue
                terminal_segment = _svg_terminal_segment(element, marker_position)
                if terminal_segment is None:
                    continue
                stroke_width = _svg_float_style_or_attr(element, "stroke-width", 1.0)
                polygon_points = _svg_marker_polygon_points(
                    marker_profiles[marker_id],
                    stroke_width=stroke_width,
                    segment_start=terminal_segment[0],
                    segment_end=terminal_segment[1],
                    marker_position=marker_position,
                )
                if polygon_points is None:
                    continue
                element.attrib.pop(marker_attr, None)
                element_id = element.get("id") or _svg_local_name(element.tag)
                polygon_id = _next_available_svg_id(existing_ids, f"{element_id}_marker_{marker_position}_{marker_id}")
                marker_profile = marker_profiles[marker_id]
                fill = marker_profile["fill"]
                if fill in {"context-stroke", "currentColor"}:
                    fill = _svg_style_value(element, "stroke") or "#000000"
                stroke = marker_profile["stroke"]
                if stroke in {"context-stroke", "currentColor"}:
                    stroke = _svg_style_value(element, "stroke") or "#000000"
                polygon_attrs = {
                    "id": polygon_id,
                    "points": _format_svg_points(polygon_points),
                    "fill": fill,
                    "stroke": stroke,
                    "data-drawai-svg_to_ppt-marker": marker_id,
                }
                polygon_attrs.update(marker_profile.get("style_attrs", {}))
                polygon = ElementTree.Element(f"{{{SVG_NAMESPACE}}}polygon", polygon_attrs)
                parent.insert(index + insert_offset, polygon)
                insert_offset += 1
                expansions.append(
                    {
                        "element_id": element.get("id") or "",
                        "marker_id": marker_id,
                        "position": marker_position,
                        "polygon_id": polygon_id,
                    }
                )
                changed = True

    if not changed:
        return svg_text, []

    ElementTree.register_namespace("", SVG_NAMESPACE)
    return ElementTree.tostring(root, encoding="unicode"), expansions


def prepare_svg_for_ppt_input(svg_path: str | Path, prepared_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Create a compiler-safe SVG by rewriting risky IDs and URL/hash references."""

    source = Path(svg_path).resolve(strict=False)
    if not source.exists():
        raise SvgToPptError(f"semantic SVG does not exist: {source}")

    svg_text = source.read_text(encoding="utf-8")
    existing_ids = {match.group(2) for match in SVG_ID_ATTR_RE.finditer(svg_text)}
    id_rewrites: dict[str, str] = {}
    for match in SVG_ID_ATTR_RE.finditer(svg_text):
        svg_id = match.group(2)
        if svg_id in id_rewrites or not _is_svg_to_ppt_unsafe_page_id(svg_id):
            continue
        preferred_id = SVG_TO_PPT_SAFE_BACKGROUND_ID if _is_svg_to_ppt_unsafe_background_id(svg_id) else SVG_TO_PPT_SAFE_OBJECT_ID_PREFIX
        id_rewrites[svg_id] = _next_available_svg_id(existing_ids, preferred_id)

    rewritten_svg_text = _replace_svg_id_references(svg_text, id_rewrites) if id_rewrites else svg_text
    marker_expanded_svg_text, marker_expansions = _expand_svg_marker_endings_for_svg_to_ppt(rewritten_svg_text)
    positioned_svg_text, tspan_position_normalizations = _normalize_tspan_dy_positions_for_svg_to_ppt(marker_expanded_svg_text)
    prepared_svg_text, tspan_attribute_normalizations = _materialize_positioned_tspan_inherited_attrs_for_svg_to_ppt(
        positioned_svg_text
    )
    prepared_svg_text, tspan_anchor_normalizations = _normalize_positioned_tspan_anchors_for_svg_to_ppt(
        prepared_svg_text
    )

    if (
        not id_rewrites
        and not marker_expansions
        and not tspan_position_normalizations
        and not tspan_attribute_normalizations
        and not tspan_anchor_normalizations
    ):
        return source, {
            "status": "unchanged",
            "source_svg": str(source),
            "prepared_svg": str(source),
            "id_rewrites": [],
        }

    prepared = (
        Path(prepared_path).resolve(strict=False)
        if prepared_path is not None
        else source.with_name(f"{source.stem}.svg_to_ppt{source.suffix}")
    )
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_text(prepared_svg_text, encoding="utf-8")
    report = {
        "status": "rewritten",
        "source_svg": str(source),
        "prepared_svg": str(prepared),
        "id_rewrites": [{"old_id": old_id, "new_id": new_id} for old_id, new_id in id_rewrites.items()],
    }
    if marker_expansions:
        report["marker_expansions"] = marker_expansions
    if tspan_position_normalizations:
        report["tspan_position_normalizations"] = tspan_position_normalizations
    if tspan_attribute_normalizations:
        report["tspan_attribute_normalizations"] = tspan_attribute_normalizations
    if tspan_anchor_normalizations:
        report["tspan_anchor_normalizations"] = tspan_anchor_normalizations
    return prepared, report



class SvgToPptCompiler:
    """In-process DrawAI SVG-to-PPTX exporter backed by native PowerPoint shapes."""

    def __init__(self) -> None:
        self.backend = DRAWAI_NATIVE_SHAPES_BACKEND
        self.requested_export_mode = SVG_TO_PPT_EXPORT_MODE_NATIVE_SHAPES
        self.effective_export_mode = SVG_TO_PPT_EXPORT_MODE_NATIVE_SHAPES

    def _export_mode_report_fields(self) -> dict[str, str]:
        return {
            "requested_export_mode": self.requested_export_mode,
            "effective_export_mode": self.effective_export_mode,
            "export_mode": self.effective_export_mode,
        }

    def compile(
        self,
        svg_path: str | Path,
        output_path: str | Path,
        report_path: str | Path | None = None,
    ) -> dict[str, Any]:
        from drawai._vendor.svg_pptx_converter.svg_to_pptx.pptx_builder import create_pptx_with_native_svg

        source_svg = Path(svg_path).resolve(strict=False)
        final_pptx = Path(output_path).resolve(strict=False)
        report_target = Path(report_path).resolve(strict=False) if report_path is not None else None
        if not source_svg.exists():
            raise SvgToPptError(f"semantic SVG does not exist: {source_svg}")

        formula_source_svg, converted_formulas, formula_export_report = _prepare_formula_export(source_svg)
        prepared_svg, svg_input_report = prepare_svg_for_ppt_input(formula_source_svg)
        trace_path = final_pptx.with_suffix(".trace.json")

        final_pptx.parent.mkdir(parents=True, exist_ok=True)
        for generated_path in (final_pptx, trace_path):
            if generated_path.exists() and generated_path.is_file():
                generated_path.unlink()

        ok = create_pptx_with_native_svg(
            [prepared_svg],
            final_pptx,
            canvas_format=None,
            verbose=False,
            transition=None,
            use_native_shapes=True,
            enable_notes=False,
            animation=None,
            merge_paragraphs=True,
            conversion_trace_path=trace_path,
            doc_metadata={
                "title": final_pptx.stem,
                "subject": "DrawAI native SVG to PPTX conversion",
            },
        )
        if not ok or not final_pptx.exists():
            message = f"DrawAI native SVG-to-PPTX export did not write {final_pptx}"
            report = {
                "status": "error",
                "backend": DRAWAI_NATIVE_SHAPES_BACKEND,
                "editable_surface": "native_shapes",
                **self._export_mode_report_fields(),
                "source_svg": str(source_svg),
                "prepared_svg": str(prepared_svg),
                "svg_input": svg_input_report,
                "formula_export": formula_export_report,
                "output_pptx": str(final_pptx),
                "conversion_trace_path": str(trace_path),
                "issues": [
                    {
                        "issue_type": "native_shapes_convert_failed",
                        "severity": "error",
                        "message": message,
                    }
                ],
            }
            if report_target is not None:
                _write_json(report_target, report)
            raise SvgToPptError(message)

        formula_injection_report = _inject_office_math_formulas(final_pptx, source_svg, converted_formulas)
        formula_export_report["injection"] = formula_injection_report
        pptx_structure = inspect_pptx_structure(final_pptx)
        report = {
            "status": "ok",
            "backend": DRAWAI_NATIVE_SHAPES_BACKEND,
            "editable_surface": (
                SVG_TO_PPT_EXPORT_MODE_NATIVE_SHAPES_WITH_OFFICE_MATH
                if converted_formulas
                else SVG_TO_PPT_EXPORT_MODE_NATIVE_SHAPES
            ),
            **self._export_mode_report_fields(),
            "source_svg": str(source_svg),
            "prepared_svg": str(prepared_svg),
            "svg_input": svg_input_report,
            "formula_export": formula_export_report,
            "output_pptx": str(final_pptx),
            "conversion_trace_path": str(trace_path),
            "pptx_structure": pptx_structure,
        }
        if pptx_structure.get("is_single_screenshot_like"):
            report["status"] = "error"
            report["issues"] = [
                {
                    "issue_type": "pptx_single_screenshot_output",
                    "severity": "error",
                    "message": "DrawAI native SVG-to-PPTX output appears to be a single screenshot-like picture.",
                }
            ]
            if report_target is not None:
                _write_json(report_target, report)
            raise SvgToPptError("DrawAI native SVG-to-PPTX output appears to be a single screenshot-like picture.")

        if report_target is not None:
            _write_json(report_target, report)
        return report
