from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Mapping

from lxml import etree

from .scientific_svg_profile import validate_scientific_svg_profile
from .svg_reference_utils import (
    is_data_uri as _is_data_uri,
    is_external_or_absolute_ref as _is_external_or_absolute_ref,
    manifest_asset_paths as _manifest_asset_paths,
    resolve_local_ref as _resolve_local_ref,
)


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

_URL_RE = re.compile(r"url\(\s*(?:'([^']*)'|\"([^\"]*)\"|([^)]*))\s*\)", re.IGNORECASE)
_IMPORT_RE = re.compile(r"@import\s+(?:url\(\s*)?(?:'([^']*)'|\"([^\"]*)\"|([^;\)\s]+))", re.IGNORECASE)
_AF_PLACEHOLDER_RE = re.compile(r"\bAF\d{2,}\b")
_ENVIRONMENT_ERROR_RE = re.compile(
    r"(command is unavailable|could not find|cannot find|not found|not installed|"
    r"no such file or directory|missing dependency|modulenotfounderror|importerror|"
    r"executable|permission denied)",
    re.IGNORECASE,
)


CompilerCallable = Callable[[Path, Path], Any]


def check_svg_to_ppt_compatibility(
    svg_path: str | Path,
    output_dir: str | Path,
    export_pptx: bool = True,
    compiler: CompilerCallable | None = None,
    asset_manifest: Mapping[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    """Check whether an SVG fits the local svg-to-PPT compatibility profile.

    Static SVG profile issues are reported before any compiler call. When
    ``export_pptx`` is enabled, ``compiler`` is called as
    ``compiler(svg_path, output_pptx)``. If no compiler is supplied, this uses
    the existing ``drawai.svg_to_ppt.SvgToPptCompiler`` adapter.
    """

    source_svg = Path(svg_path).expanduser().resolve(strict=False)
    export_dir = Path(output_dir).expanduser().resolve(strict=False) / "svg_to_ppt"
    output_pptx = export_dir / f"{source_svg.stem}.svg_to_ppt.pptx"
    report = _base_report(source_svg, output_pptx, export_pptx)
    _remove_stale_output(output_pptx)

    scientific_profile = validate_scientific_svg_profile(source_svg, asset_manifest=asset_manifest)
    report["scientific_svg_profile"] = scientific_profile
    profile_issues = _check_static_svg_profile(source_svg, asset_manifest)
    profile_issues.extend(_scientific_profile_issues(scientific_profile))
    report["scientific_svg_profile_enforced"] = True
    if profile_issues:
        report.update(
            {
                "status": "failed",
                "failure_class": "svg_profile_issue",
                "issues": profile_issues,
            }
        )
        return report

    if not export_pptx:
        report["status"] = "ok"
        return report

    export_dir.mkdir(parents=True, exist_ok=True)

    try:
        if compiler is not None:
            compiler_report = compiler(source_svg, output_pptx)
        else:
            compiler_report = _compile_with_default_adapter(
                source_svg,
                output_pptx,
                export_dir / "svg_to_ppt_report.json",
            )
    except Exception as exc:  # noqa: BLE001 - classification is the purpose of this boundary.
        failure_class = "environment_issue" if _looks_like_environment_issue(exc) else "compiler_tool_issue"
        report.update(
            {
                "status": "failed",
                "failure_class": failure_class,
                "issues": [
                    _issue(
                        "compiler_exception" if failure_class == "compiler_tool_issue" else "environment_exception",
                        "SVG-to-PPT exporter raised an exception.",
                        _exception_detail(exc),
                    )
                ],
                "exception": _exception_detail(exc),
            }
        )
        return report

    prepared_svg = _extract_prepared_svg(compiler_report)
    if prepared_svg is not None:
        report["prepared_svg"] = prepared_svg

    conversion_report_issues = _conversion_report_issues(compiler_report, source_svg=source_svg)
    if conversion_report_issues:
        failure_class = (
            "svg_profile_issue"
            if any(
                issue["code"]
                in {
                    "drawai_conversion_report_blockers",
                    "drawai_conversion_report_issues",
                }
                for issue in conversion_report_issues
            )
            else "compiler_tool_issue"
        )
        report.update(
            {
                "status": "failed",
                "failure_class": failure_class,
                "issues": conversion_report_issues,
                "compiler_report": _json_safe(compiler_report),
            }
        )
        return report

    if not output_pptx.exists():
        report.update(
            {
                "status": "failed",
                "failure_class": "compiler_tool_issue",
                "issues": [
                    _issue(
                        "pptx_missing",
                        "SVG-to-PPT exporter returned without writing the expected PPTX.",
                        {"expected_pptx": str(output_pptx)},
                    )
                ],
            }
        )
        return report

    report["status"] = "ok"
    return report


def _remove_stale_output(output_pptx: Path) -> None:
    try:
        output_pptx.unlink()
    except FileNotFoundError:
        return


def _base_report(source_svg: Path, output_pptx: Path, export_pptx: bool) -> dict[str, Any]:
    return {
        "status": "pending",
        "export_pptx": bool(export_pptx),
        "failure_class": None,
        "issues": [],
        "prepared_svg": str(source_svg),
        "pptx_path": str(output_pptx),
        "exception": None,
    }


def _compile_with_default_adapter(
    source_svg: Path,
    output_pptx: Path,
    report_path: Path,
) -> Any:
    from drawai.svg_to_ppt import SvgToPptCompiler

    return SvgToPptCompiler().compile(svg_path=source_svg, output_path=output_pptx, report_path=report_path)


def _scientific_profile_issues(profile_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    if profile_report.get("compliant") is True:
        return []
    violations = profile_report.get("violations")
    if not isinstance(violations, list):
        return []

    issues: list[dict[str, Any]] = []
    for violation in violations:
        if not isinstance(violation, Mapping):
            continue
        code = str(violation.get("code") or "scientific_svg_profile_violation")
        issues.append(
            _issue(
                code,
                str(violation.get("reason") or "SVG does not comply with the DrawAI Scientific SVG Profile."),
                {
                    "profile": profile_report.get("profile"),
                    "type": violation.get("type"),
                    "element": violation.get("element"),
                    "fix": violation.get("fix"),
                },
            )
        )
    return issues


def _check_static_svg_profile(
    svg_path: Path,
    asset_manifest: Mapping[str, Any] | list[Any] | None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    try:
        raw_svg = svg_path.read_bytes()
    except OSError as exc:
        return [_issue("file_read_error", "Could not read SVG file.", _exception_detail(exc))]

    _scan_xml_declarations(raw_svg, issues)
    root = _parse_svg(raw_svg, issues)
    if root is None:
        return issues

    if _local_name(root.tag) != "svg":
        issues.append(_issue("root_not_svg", "Root element must be an SVG element.", {"tag": _safe_tag(root.tag)}))
        return issues
    if _namespace(root.tag) != SVG_NS:
        issues.append(_issue("missing_svg_namespace", "SVG root must declare the standard SVG namespace."))

    if root.get("viewBox") is None:
        issues.append(_issue("missing_viewbox", "SVG root must declare a viewBox."))

    manifest_paths = _manifest_asset_paths(asset_manifest, svg_path.parent)
    for element in root.iter():
        if _local_name(element.tag) == "script":
            issues.append(_issue("script_element", "SVG must not contain script elements."))
        _validate_text_nodes(element, issues)
        _validate_element_references(element, svg_path.parent, manifest_paths, issues)

    return issues


def _scan_xml_declarations(raw_svg: bytes, issues: list[dict[str, Any]]) -> None:
    upper = raw_svg.upper()
    if b"<!DOCTYPE" in upper:
        issues.append(_issue("doctype", "SVG must not declare a DOCTYPE."))
    if b"<!ENTITY" in upper:
        issues.append(_issue("external_entity", "SVG must not declare XML entities."))


def _parse_svg(raw_svg: bytes, issues: list[dict[str, Any]]) -> etree._Element | None:
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, recover=False)
    try:
        return etree.fromstring(raw_svg, parser=parser)
    except etree.XMLSyntaxError as exc:
        issues.append(_issue("xml_parse_error", "SVG XML could not be parsed.", _exception_detail(exc)))
        return None


def _validate_text_nodes(element: etree._Element, issues: list[dict[str, Any]]) -> None:
    for text in (element.text, element.tail):
        if not text:
            continue
        match = _AF_PLACEHOLDER_RE.search(text)
        if match:
            issues.append(
                _issue(
                    "af_placeholder",
                    "SVG contains an unexpanded AFxx placeholder in text output.",
                    match.group(0),
                )
            )


def _validate_element_references(
    element: etree._Element,
    svg_dir: Path,
    manifest_paths: set[Path],
    issues: list[dict[str, Any]],
) -> None:
    for attr_name, attr_value in element.attrib.items():
        local_name = _local_name(attr_name)
        namespace = _namespace(attr_name)
        value = str(attr_value)

        if local_name in {"href", "src"} and (namespace in {"", XLINK_NS} or local_name == "src"):
            _validate_reference(value, svg_dir, manifest_paths, issues, source=local_name)
        elif local_name == "style":
            _validate_style_references(value, svg_dir, manifest_paths, issues)
        elif "url(" in value.lower():
            _validate_url_functions(
                value,
                svg_dir,
                manifest_paths,
                issues,
                source=f"attribute:{local_name}",
            )

    if _local_name(element.tag) == "style" and element.text:
        _validate_style_references(element.text, svg_dir, manifest_paths, issues)


def _validate_style_references(
    style_text: str,
    svg_dir: Path,
    manifest_paths: set[Path],
    issues: list[dict[str, Any]],
) -> None:
    _validate_url_functions(style_text, svg_dir, manifest_paths, issues, source="style_url")
    for match in _IMPORT_RE.finditer(style_text):
        raw_ref = next(group for group in match.groups() if group is not None)
        _validate_reference(
            raw_ref.strip(),
            svg_dir,
            manifest_paths,
            issues,
            source="style_import",
        )


def _validate_url_functions(
    raw_value: str,
    svg_dir: Path,
    manifest_paths: set[Path],
    issues: list[dict[str, Any]],
    *,
    source: str,
) -> None:
    for match in _URL_RE.finditer(raw_value):
        raw_ref = next(group for group in match.groups() if group is not None)
        _validate_reference(raw_ref.strip(), svg_dir, manifest_paths, issues, source=source)


def _validate_reference(
    raw_ref: str,
    svg_dir: Path,
    manifest_paths: set[Path],
    issues: list[dict[str, Any]],
    *,
    source: str,
) -> None:
    ref = raw_ref.strip().strip("\"'")
    if not ref or ref.startswith("#") or _is_data_uri(ref):
        return

    if _is_external_or_absolute_ref(ref):
        issues.append(
            _issue(
                "external_href",
                "SVG references an external or absolute asset path.",
                {"source": source, "href": ref},
            )
        )
        return

    resolved = _resolve_local_ref(ref, svg_dir)
    if resolved is None or resolved not in manifest_paths:
        issues.append(
            _issue(
                "asset_href_not_in_manifest",
                "Local SVG asset references must resolve to an asset manifest path.",
                {"source": source, "href": ref},
            )
        )


def _extract_prepared_svg(compiler_report: Any) -> str | None:
    if not isinstance(compiler_report, Mapping):
        return None

    for key in ("prepared_svg", "prepared_path", "input_svg"):
        value = compiler_report.get(key)
        if isinstance(value, (str, Path)) and str(value):
            return str(value)

    svg_input = compiler_report.get("svg_input")
    if isinstance(svg_input, Mapping):
        for key in ("prepared_svg", "prepared_path", "input_svg"):
            value = svg_input.get(key)
            if isinstance(value, (str, Path)) and str(value):
                return str(value)

    return None


def _conversion_report_issues(compiler_report: Any, *, source_svg: Path | None = None) -> list[dict[str, Any]]:
    if not isinstance(compiler_report, Mapping):
        return []
    external_report = compiler_report.get("external_report")
    if not isinstance(external_report, Mapping):
        external_report = compiler_report.get("conversion_report")
    if not isinstance(external_report, Mapping):
        external_report = {}
    pptx_structure = external_report.get("pptx_structure")
    if not isinstance(pptx_structure, Mapping):
        pptx_structure = compiler_report.get("pptx_structure")
    if not external_report and not isinstance(pptx_structure, Mapping):
        return []

    issues: list[dict[str, Any]] = []
    if external_report.get("status") not in (None, "ok"):
        issues.append(
            _issue(
                "drawai_conversion_report_status",
                "DrawAI SVG PPT conversion_report.json reported non-ok status.",
                {"status": external_report.get("status")},
            )
        )

    top_level_blockers = external_report.get("blockers")
    svg_analysis = external_report.get("svg_analysis")
    nested_blockers = svg_analysis.get("blockers") if isinstance(svg_analysis, Mapping) else None
    blockers = _non_empty_report_entries(top_level_blockers) or _non_empty_report_entries(nested_blockers)
    if blockers:
        issues.append(
            _issue(
                "drawai_conversion_report_blockers",
                "DrawAI SVG PPT conversion_report.json contains blockers.",
                {
                    "blockers": blockers,
                    "conversion_report_path": compiler_report.get("conversion_report_path")
                    or compiler_report.get("external_report_path"),
                },
            )
        )

    report_issues = _non_empty_report_entries(external_report.get("issues"))
    if report_issues:
        issues.append(
            _issue(
                "drawai_conversion_report_issues",
                "DrawAI SVG PPT conversion_report.json contains issues.",
                {
                    "issues": report_issues,
                    "conversion_report_path": compiler_report.get("conversion_report_path")
                    or compiler_report.get("external_report_path"),
                },
            )
        )

    if isinstance(pptx_structure, Mapping) and pptx_structure.get("is_single_screenshot_like"):
        issues.append(
            _issue(
                "drawai_conversion_report_screenshot_like",
                "DrawAI SVG PPT conversion_report.json marks the PPTX as screenshot-like.",
                {"pptx_structure": dict(pptx_structure)},
            )
        )
    if isinstance(pptx_structure, Mapping):
        svg_text_count = max(_external_report_text_count(external_report), _svg_element_count(source_svg, "text"))
        ppt_text_run_count = _report_int(pptx_structure.get("text_run_count"))
        minimum_native_text_runs = 1 if svg_text_count < 5 else max(1, int(svg_text_count * 0.8))
        if svg_text_count > 0 and ppt_text_run_count < minimum_native_text_runs:
            issues.append(
                _issue(
                    "drawai_conversion_report_text_loss",
                    "DrawAI SVG PPT conversion dropped too many SVG text elements from native PPT text.",
                    {
                        "expected_svg_text_count": svg_text_count,
                        "minimum_native_text_runs": minimum_native_text_runs,
                        "text_run_count": ppt_text_run_count,
                        "conversion_report_path": compiler_report.get("conversion_report_path")
                        or compiler_report.get("external_report_path"),
                    },
                )
            )
    image_count = max(_external_report_image_count(external_report), _svg_element_count(source_svg, "image"))
    if image_count > 0 and isinstance(pptx_structure, Mapping):
        media_count = _report_int(pptx_structure.get("media_count"))
        picture_tag_count = _report_int(pptx_structure.get("picture_tag_count"))
        if media_count == 0 or picture_tag_count == 0:
            issues.append(
                _issue(
                    "drawai_conversion_report_missing_images",
                    "DrawAI SVG PPT conversion dropped SVG image assets from the PPTX.",
                    {
                        "expected_svg_image_count": image_count,
                        "media_count": media_count,
                        "picture_tag_count": picture_tag_count,
                        "conversion_report_path": compiler_report.get("conversion_report_path")
                        or compiler_report.get("external_report_path"),
                    },
                )
            )
    return issues


def _svg_element_count(svg_path: Path | None, local_name: str) -> int:
    if svg_path is None or not svg_path.exists():
        return 0
    tree = etree.parse(str(svg_path))
    return int(tree.xpath(f"count(.//svg:{local_name})", namespaces={"svg": SVG_NS}))


def _external_report_text_count(external_report: Mapping[str, Any]) -> int:
    counts = [
        _nested_report_int(external_report, ("source_profile", "feature_counts", "text")),
        _nested_report_int(external_report, ("canonicalized_profile", "feature_counts", "text")),
        _nested_report_int(external_report, ("svg_analysis", "element_counts", "text")),
    ]
    return max(counts)


def _external_report_image_count(external_report: Mapping[str, Any]) -> int:
    counts = [
        _nested_report_int(external_report, ("source_profile", "feature_counts", "image")),
        _nested_report_int(external_report, ("canonicalized_profile", "feature_counts", "image")),
        _nested_report_int(external_report, ("svg_analysis", "element_counts", "image")),
    ]
    return max(counts)


def _nested_report_int(report: Mapping[str, Any], keys: tuple[str, ...]) -> int:
    value: Any = report
    for key in keys:
        if not isinstance(value, Mapping):
            return 0
        value = value.get(key)
    return _report_int(value)


def _report_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _non_empty_report_entries(value: Any) -> list[Any]:
    if value in (None, "", [], {}, ()):
        return []
    if isinstance(value, list):
        return value
    return [value]


def _looks_like_environment_issue(exc: Exception) -> bool:
    if isinstance(exc, (FileNotFoundError, ModuleNotFoundError, ImportError, PermissionError)):
        return True
    detail = _exception_detail(exc)
    return _ENVIRONMENT_ERROR_RE.search(f"{detail['type']}: {detail['message']}") is not None


def _exception_detail(exc: BaseException) -> dict[str, str]:
    return {"type": exc.__class__.__name__, "message": str(exc)}


def _issue(code: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    issue: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        issue["detail"] = detail
    return issue


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


def _safe_tag(tag: Any) -> str:
    return tag if isinstance(tag, str) else repr(tag)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


__all__ = ["check_svg_to_ppt_compatibility"]
