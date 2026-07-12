from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Mapping

from lxml import etree

from .svg_reference_utils import (
    is_external_or_absolute_ref as _is_external_or_absolute_ref,
    manifest_asset_paths as _manifest_asset_paths,
    resolve_local_ref as _resolve_local_ref,
)


PROFILE_NAME = "DrawAI Scientific SVG Profile v1"
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

ALLOWED_TAGS = {
    "svg",
    "defs",
    "g",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "path",
    "text",
    "tspan",
    "marker",
    "linearGradient",
    "radialGradient",
    "stop",
    "image",
    "symbol",
    "use",
    "title",
    "desc",
}
BLOCKED_TAGS = {
    "filter": ("risky_feature", "SVG filters are not PPT-native editable objects."),
    "mask": ("unsupported_feature", "SVG mask has no deterministic editable PPT mapping in profile v1."),
    "clipPath": ("unsupported_feature", "SVG clipPath has no deterministic editable PPT mapping in profile v1."),
    "foreignObject": ("unsupported_feature", "foreignObject depends on browser layout and cannot be edited as native PPT."),
    "textPath": ("unsupported_feature", "textPath cannot be mapped to simple editable PPT text reliably."),
}
URL_RE = re.compile(r"url\(\s*(?:'([^']*)'|\"([^\"]*)\"|([^)]*))\s*\)", re.IGNORECASE)


def validate_scientific_svg_profile(
    svg_path: str | Path,
    *,
    asset_manifest: Mapping[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    source = Path(svg_path).expanduser().resolve(strict=False)
    report = _base_report(source)

    try:
        raw_svg = source.read_bytes()
    except OSError as exc:
        _add_violation(
            report,
            code="file_read_error",
            violation_type="unsupported_feature",
            element=str(source),
            reason=f"Could not read SVG file: {exc}",
            fix="Write a readable SVG file before profile validation.",
        )
        return _finalize(report)

    if b"<!DOCTYPE" in raw_svg.upper() or b"<!ENTITY" in raw_svg.upper():
        _add_violation(
            report,
            code="doctype_or_entity",
            violation_type="unsupported_feature",
            element="document",
            reason="DOCTYPE and entity declarations are unsafe and unnecessary for DrawAI SVG.",
            fix="Remove DOCTYPE and entity declarations.",
        )

    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, recover=False)
    try:
        root = etree.fromstring(raw_svg, parser=parser)
    except etree.XMLSyntaxError as exc:
        _add_violation(
            report,
            code="xml_parse_error",
            violation_type="unsupported_feature",
            element=str(source),
            reason=f"SVG XML could not be parsed: {exc}",
            fix="Return well-formed XML with a single <svg> root.",
        )
        return _finalize(report)

    if _local_name(root.tag) != "svg" or _namespace(root.tag) != SVG_NS:
        _add_violation(
            report,
            code="missing_svg_namespace",
            violation_type="unsupported_feature",
            element=_element_ref(root),
            reason="Root element must be an SVG element in the standard SVG namespace.",
            fix="Use <svg xmlns=\"http://www.w3.org/2000/svg\" ...> as the root.",
        )

    viewbox = _parse_viewbox(root.get("viewBox"))
    manifest_paths = _manifest_asset_paths(asset_manifest, source.parent)
    ids_by_role: dict[str, int] = {}

    for element in root.iter():
        local = _local_name(element.tag)
        role = element.get("data-pb-role")
        if role:
            ids_by_role[role] = ids_by_role.get(role, 0) + 1

        if local in BLOCKED_TAGS:
            violation_type, reason = BLOCKED_TAGS[local]
            _set_feature_flag(report, local)
            _add_violation(
                report,
                code=f"blocked_{local}",
                violation_type=violation_type,
                element=_element_ref(element),
                reason=reason,
                fix=f"Replace <{local}> usage with editable SVG primitives supported by the staged mainline.",
            )
            continue

        if local == "pattern":
            report["uses_pattern"] = True
            _add_violation(
                report,
                code="risky_pattern",
                violation_type="risky_feature",
                element=_element_ref(element),
                reason="SVG pattern is only acceptable after deterministic canonicalization, which this profile validator does not perform.",
                fix="Replace the pattern with editable lines, dots, simple fills, or mark and canonicalize it before conversion.",
            )
            continue

        if local and local not in ALLOWED_TAGS:
            _add_violation(
                report,
                code="unsupported_element",
                violation_type="unsupported_feature",
                element=_element_ref(element),
                reason=f"<{local}> is outside the DrawAI Scientific SVG Profile v1 element set.",
                fix="Rewrite it using rect, circle, ellipse, line, polyline, polygon, path, text/tspan, g, marker, gradient, or image assets.",
            )

        _validate_element_attributes(element, report)
        if local == "image":
            _validate_image_element(element, source.parent, manifest_paths, viewbox, report)

    report["has_semantic_roles"] = bool(ids_by_role)
    report["role_counts"] = ids_by_role
    return _finalize(report)


def _base_report(source: Path) -> dict[str, Any]:
    return {
        "profile": PROFILE_NAME,
        "source_svg": str(source),
        "compliant": True,
        "violations": [],
        "warnings": [],
        "uses_filter": False,
        "uses_mask": False,
        "uses_clipPath": False,
        "uses_foreignObject": False,
        "uses_pattern": False,
        "has_semantic_roles": False,
        "role_counts": {},
    }


def _finalize(report: dict[str, Any]) -> dict[str, Any]:
    report["compliant"] = not bool(report["violations"])
    return report


def _validate_element_attributes(element: etree._Element, report: dict[str, Any]) -> None:
    element_ref = _element_ref(element)
    for raw_name, raw_value in element.attrib.items():
        name = _local_name(raw_name)
        value = str(raw_value)
        lowered = value.lower()
        if name == "filter" or "filter:" in lowered:
            report["uses_filter"] = True
            _add_violation(
                report,
                code="blocked_filter",
                violation_type="risky_feature",
                element=element_ref,
                reason="filter usage would require browser or raster behavior for a visual effect.",
                fix="Remove the filter or rewrite it as editable vector decoration.",
            )
        if name == "mask" or "mask:" in lowered:
            report["uses_mask"] = True
            _add_violation(
                report,
                code="blocked_mask",
                violation_type="unsupported_feature",
                element=element_ref,
                reason="mask usage hides core geometry behind a browser-specific feature.",
                fix="Rewrite the visible geometry directly without mask.",
            )
        if name == "clip-path" or "clip-path:" in lowered:
            report["uses_clipPath"] = True
            _add_violation(
                report,
                code="blocked_clipPath",
                violation_type="unsupported_feature",
                element=element_ref,
                reason="clipPath usage is not guaranteed to become editable PPT geometry.",
                fix="Rewrite clipped shapes into explicit editable paths or crop as a real image asset only when appropriate.",
            )
        if name in {"fill", "stroke", "style"} and "url(" in lowered:
            _validate_paint_server_references(value, element_ref, report)


def _validate_paint_server_references(raw_value: str, element_ref: str, report: dict[str, Any]) -> None:
    for match in URL_RE.finditer(raw_value):
        raw_ref = next(group for group in match.groups() if group is not None).strip().strip("\"'")
        if not raw_ref.startswith("#"):
            continue
        ref = raw_ref[1:]
        if "pattern" in ref.lower():
            report["uses_pattern"] = True
            _add_violation(
                report,
                code="risky_pattern_reference",
                violation_type="risky_feature",
                element=element_ref,
                reason="Pattern paint servers are not accepted in the profile without deterministic canonicalization.",
                fix="Use solid fill, simple dots/lines, or a supported gradient if the effect is non-semantic.",
            )


def _validate_image_element(
    element: etree._Element,
    svg_dir: Path,
    manifest_paths: set[Path],
    viewbox: tuple[float, float, float, float] | None,
    report: dict[str, Any],
) -> None:
    element_ref = _element_ref(element)
    href = element.get("href") or element.get(f"{{{XLINK_NS}}}href") or ""
    if not href.strip():
        _add_violation(
            report,
            code="missing_image_href",
            violation_type="unsupported_feature",
            element=element_ref,
            reason="Image elements must reference explicit local raster assets.",
            fix="Use the asset manifest svg_href value for real raster assets.",
        )
        return

    ref = href.strip().strip("\"'")
    if ref.lower().startswith("data:"):
        _add_violation(
            report,
            code="base64_image",
            violation_type="editability_risk",
            element=element_ref,
            reason="Base64 image data can hide text, arrows, or whole structures from PPT editing.",
            fix="Reference a manifest asset by relative href; never embed full-slide or structural bitmaps.",
        )
    elif _is_external_or_absolute_ref(ref):
        _add_violation(
            report,
            code="external_or_absolute_image",
            violation_type="unsupported_feature",
            element=element_ref,
            reason="Image href must be portable and job-relative, not external or absolute.",
            fix="Use the manifest asset.svg_href relative path.",
        )
    else:
        resolved = _resolve_local_ref(ref, svg_dir)
        if resolved is None or resolved not in manifest_paths:
            _add_violation(
                report,
                code="image_not_in_manifest",
                violation_type="editability_risk",
                element=element_ref,
                reason="Image references must correspond to known asset_manifest entries.",
                fix="In the staged mainline, redraw this region with editable SVG primitives instead of inventing asset placeholders.",
            )

    if viewbox is not None and _image_covers_canvas(element, viewbox):
        _add_violation(
            report,
            code="whole_slide_image",
            violation_type="editability_risk",
            element=element_ref,
            reason="A full-canvas image likely rasterizes the whole figure instead of preserving editable semantics.",
            fix="Use images only for real photo/icon/figure assets; keep panels, arrows, labels, and structure as SVG objects.",
        )


def _image_covers_canvas(element: etree._Element, viewbox: tuple[float, float, float, float]) -> bool:
    _, _, canvas_width, canvas_height = viewbox
    x = _float_attr(element, "x", default=0.0)
    y = _float_attr(element, "y", default=0.0)
    width = _float_attr(element, "width", default=0.0)
    height = _float_attr(element, "height", default=0.0)
    if width <= 0 or height <= 0 or canvas_width <= 0 or canvas_height <= 0:
        return False
    area_ratio = (width * height) / (canvas_width * canvas_height)
    return x <= canvas_width * 0.05 and y <= canvas_height * 0.05 and area_ratio >= 0.85


def _parse_viewbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [part for part in raw.replace(",", " ").split() if part]
    if len(parts) != 4:
        return None
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    return values  # type: ignore[return-value]


def _float_attr(element: etree._Element, name: str, *, default: float) -> float:
    value = element.get(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if math.isfinite(parsed) else default


def _set_feature_flag(report: dict[str, Any], local_name: str) -> None:
    if local_name == "filter":
        report["uses_filter"] = True
    elif local_name == "mask":
        report["uses_mask"] = True
    elif local_name == "clipPath":
        report["uses_clipPath"] = True
    elif local_name == "foreignObject":
        report["uses_foreignObject"] = True
    elif local_name == "pattern":
        report["uses_pattern"] = True


def _add_violation(
    report: dict[str, Any],
    *,
    code: str,
    violation_type: str,
    element: str,
    reason: str,
    fix: str,
) -> None:
    report["violations"].append(
        {
            "code": code,
            "type": violation_type,
            "element": element,
            "reason": reason,
            "fix": fix,
        }
    )


def _element_ref(element: etree._Element) -> str:
    local = _local_name(element.tag) or "unknown"
    svg_id = element.get("id")
    css_class = element.get("class")
    if svg_id:
        return f"{local}#{svg_id}"
    if css_class:
        return f"{local}.{css_class}"
    return local


def _local_name(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def _namespace(tag: Any) -> str:
    if not isinstance(tag, str) or not tag.startswith("{"):
        return ""
    return tag[1:].split("}", 1)[0]


__all__ = ["PROFILE_NAME", "validate_scientific_svg_profile"]
