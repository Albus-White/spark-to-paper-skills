from __future__ import annotations

import base64
import io
import mimetypes
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from lxml import etree
from PIL import Image, ImageColor, ImageDraw, ImageFont

from .svg_reference_utils import (
    is_data_uri as _is_data_uri,
    is_external_or_absolute_ref as _is_external_or_absolute_ref,
    manifest_asset_paths as _manifest_asset_paths,
    resolve_local_ref as _resolve_local_ref,
)


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_URL_RE = re.compile(r"url\(\s*(?:'([^']*)'|\"([^\"]*)\"|([^)]*))\s*\)", re.IGNORECASE)
_IMPORT_RE = re.compile(r"@import\s+(?:url\(\s*)?(?:'([^']*)'|\"([^\"]*)\"|([^;\)\s]+))", re.IGNORECASE)
_AF_PLACEHOLDER_RE = re.compile(r"\bAF\d{2,}\b")
_DIMENSION_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))(?:px)?\s*$", re.IGNORECASE)
_BROWSER_RENDERER_ENV = "DRAWAI_SVG_RENDERER_BROWSER"
_BROWSER_RENDER_TIMEOUT_SECONDS = 600
_BROWSER_RENDERER_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
_BROWSER_RENDERER_NAMES = [
    "google-chrome",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
]


def validate_svg_file(
    svg_path: str | Path,
    canvas: Any,
    asset_manifest: Mapping[str, Any] | None,
    rendered_path: str | Path,
    require_nonblank: bool = True,
    allow_external_assets: bool = False,
    reference_dir: str | Path | None = None,
) -> dict[str, Any]:
    svg_path = Path(svg_path)
    rendered_path = Path(rendered_path)
    href_base_dir = Path(reference_dir) if reference_dir is not None else svg_path.parent
    issues: list[dict[str, Any]] = []
    _unlink_rendered_path(rendered_path, issues)
    canvas_size = _normalize_canvas(canvas, issues)
    report_canvas = {"width": canvas_size[0], "height": canvas_size[1]} if canvas_size else canvas

    try:
        raw_svg = svg_path.read_bytes()
    except OSError as exc:
        issues.append(_issue("file_read_error", "Could not read SVG file.", str(exc)))
        return _report(issues, rendered_path, report_canvas)

    _scan_xml_declarations(raw_svg, issues)
    root = _parse_svg(raw_svg, issues)
    if root is not None:
        if _is_svg_root(root):
            if canvas_size is not None:
                _validate_viewbox(root, canvas_size, issues)
                _validate_dimensions(root, canvas_size, issues)
            manifest_paths = _manifest_asset_paths(asset_manifest, href_base_dir)
            _validate_elements(
                root,
                href_base_dir,
                manifest_paths,
                allow_external_assets,
                issues,
            )
        else:
            issues.append(
                _issue(
                    "root_not_svg",
                    "Root element must be an SVG element in the SVG namespace.",
                    {"tag": _safe_tag(root)},
                )
            )

    if root is not None and _is_svg_root(root) and not _has_unsafe_reference_issue(issues):
        render_report = _render_svg(root, href_base_dir, manifest_paths, rendered_path, issues)
        if require_nonblank and rendered_path.exists():
            _validate_nonblank_render(rendered_path, issues)
    else:
        render_report = None

    return _report(issues, rendered_path, report_canvas, render_report)


def _report(
    issues: list[dict[str, Any]],
    rendered_path: Path,
    canvas: Any,
    render_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "status": "failed" if issues else "ok",
        "issues": issues,
        "rendered_path": str(rendered_path),
        "canvas": canvas,
    }
    if render_report is not None:
        report["render"] = dict(render_report)
    return report


def _issue(code: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    issue: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        issue["detail"] = detail
    return issue


def _unlink_rendered_path(rendered_path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        rendered_path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        issues.append(_issue("render_cleanup_failed", "Could not remove stale rendered SVG validation output.", str(exc)))


def _normalize_canvas(canvas: Any, issues: list[dict[str, Any]]) -> tuple[float, float] | None:
    if isinstance(canvas, Mapping):
        raw_width = canvas.get("width")
        raw_height = canvas.get("height")
    else:
        try:
            raw_width, raw_height = canvas
        except (TypeError, ValueError):
            issues.append(_issue("canvas_invalid", "Canvas must provide width and height.", repr(canvas)))
            return None

    try:
        width = float(raw_width)
        height = float(raw_height)
    except (TypeError, ValueError):
        issues.append(_issue("canvas_invalid", "Canvas width and height must be numeric.", repr(canvas)))
        return None

    if width <= 0 or height <= 0:
        issues.append(_issue("canvas_invalid", "Canvas width and height must be positive.", repr(canvas)))
        return None
    return width, height


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
        issues.append(_issue("xml_parse_error", "SVG XML could not be parsed.", str(exc)))
        return None


def _is_svg_root(root: etree._Element) -> bool:
    return _local_name(root.tag) == "svg" and _namespace(root.tag) == SVG_NS


def _validate_viewbox(
    root: etree._Element,
    canvas_size: tuple[float, float],
    issues: list[dict[str, Any]],
) -> None:
    viewbox = root.get("viewBox")
    if viewbox is None:
        issues.append(_issue("viewbox_mismatch", "SVG viewBox is required."))
        return

    values = _parse_number_list(viewbox)
    expected = (0.0, 0.0, canvas_size[0], canvas_size[1])
    if values is None or len(values) != 4 or not all(_same_number(actual, wanted) for actual, wanted in zip(values, expected)):
        issues.append(
            _issue(
                "viewbox_mismatch",
                "SVG viewBox must be exactly 0 0 width height for the canvas.",
                {"actual": viewbox, "expected": f"0 0 {_format_number(canvas_size[0])} {_format_number(canvas_size[1])}"},
            )
        )


def _validate_dimensions(
    root: etree._Element,
    canvas_size: tuple[float, float],
    issues: list[dict[str, Any]],
) -> None:
    for attr_name, expected in (("width", canvas_size[0]), ("height", canvas_size[1])):
        raw_value = root.get(attr_name)
        if raw_value is None:
            continue
        parsed = _parse_dimension(raw_value)
        if parsed is None or not _same_number(parsed, expected):
            issues.append(
                _issue(
                    "size_mismatch",
                    "SVG width/height must not conflict with the canvas.",
                    {"attribute": attr_name, "actual": raw_value, "expected": _format_number(expected)},
                )
            )


def _validate_elements(
    root: etree._Element,
    svg_dir: Path,
    manifest_paths: set[Path],
    allow_external_assets: bool,
    issues: list[dict[str, Any]],
) -> None:
    for element in root.iter():
        if _local_name(element.tag) == "script":
            issues.append(_issue("script_element", "SVG must not contain script elements."))

        _validate_text_nodes(element, issues)
        _validate_element_references(element, svg_dir, manifest_paths, allow_external_assets, issues)


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
    allow_external_assets: bool,
    issues: list[dict[str, Any]],
) -> None:
    for attr_name, attr_value in element.attrib.items():
        local_name = _local_name(attr_name)
        namespace = _namespace(attr_name)
        value = str(attr_value)

        if local_name in {"href", "src"} and (namespace in {"", XLINK_NS} or local_name == "src"):
            _validate_reference(
                value,
                svg_dir,
                manifest_paths,
                allow_external_assets,
                issues,
                require_manifest=True,
                source=local_name,
            )
        elif local_name == "style":
            _validate_style_urls(value, svg_dir, manifest_paths, allow_external_assets, issues)
        elif "url(" in value.lower():
            _validate_url_functions(
                value,
                svg_dir,
                manifest_paths,
                allow_external_assets,
                issues,
                source=f"attribute:{local_name}",
            )

    if _local_name(element.tag) == "style" and element.text:
        _validate_style_urls(element.text, svg_dir, manifest_paths, allow_external_assets, issues)


def _validate_style_urls(
    style_text: str,
    svg_dir: Path,
    manifest_paths: set[Path],
    allow_external_assets: bool,
    issues: list[dict[str, Any]],
) -> None:
    _validate_url_functions(style_text, svg_dir, manifest_paths, allow_external_assets, issues, source="style_url")
    for match in _IMPORT_RE.finditer(style_text):
        raw_ref = next(group for group in match.groups() if group is not None)
        _validate_reference(
            raw_ref.strip(),
            svg_dir,
            manifest_paths,
            allow_external_assets,
            issues,
            require_manifest=True,
            source="style_import",
        )


def _validate_url_functions(
    raw_value: str,
    svg_dir: Path,
    manifest_paths: set[Path],
    allow_external_assets: bool,
    issues: list[dict[str, Any]],
    *,
    source: str,
) -> None:
    for match in _URL_RE.finditer(raw_value):
        raw_ref = next(group for group in match.groups() if group is not None)
        _validate_reference(
            raw_ref.strip(),
            svg_dir,
            manifest_paths,
            allow_external_assets,
            issues,
            require_manifest=True,
            source=source,
        )


def _validate_reference(
    raw_ref: str,
    svg_dir: Path,
    manifest_paths: set[Path],
    allow_external_assets: bool,
    issues: list[dict[str, Any]],
    *,
    require_manifest: bool,
    source: str,
) -> None:
    ref = raw_ref.strip().strip("\"'")
    if not ref or ref.startswith("#"):
        return

    if _is_external_or_absolute_ref(ref):
        if not allow_external_assets:
            issues.append(
                _issue(
                    "external_href",
                    "SVG references an external or absolute asset path.",
                    {"source": source, "href": ref},
                )
            )
        return

    if not require_manifest or _is_data_uri(ref):
        return

    resolved = _resolve_local_ref(ref, svg_dir)
    if resolved is None or resolved not in manifest_paths:
        issues.append(
            _issue(
                "asset_href_not_in_manifest",
                "Local SVG image references must resolve to an asset manifest path.",
                {"source": source, "href": ref},
            )
        )


def _render_svg(
    root: etree._Element,
    svg_dir: Path,
    manifest_paths: set[Path],
    rendered_path: Path,
    issues: list[dict[str, Any]],
) -> dict[str, Any] | None:
    render_root = _svg_for_safe_render(root, svg_dir, manifest_paths, issues)
    if render_root is None:
        return None

    browser_path = _browser_renderer_path()
    browser_error = None
    if browser_path is not None:
        browser_error = _render_svg_with_browser(root, svg_dir, rendered_path, browser_path)
        if browser_error is None:
            return {"backend": "browser", "executable": str(browser_path)}

    cairosvg_error = None
    try:
        import cairosvg

        rendered_path.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(bytestring=etree.tostring(render_root), write_to=str(rendered_path), unsafe=False)
        report: dict[str, Any] = {"backend": "cairosvg"}
        if browser_error is not None:
            report["fallbacks"] = {"browser": browser_error}
        return report
    except Exception as exc:  # CairoSVG raises import, parser, and fetcher-specific exceptions.
        cairosvg_error = str(exc)
        fallback_error = _render_svg_pillow_fallback(render_root, rendered_path)
        if fallback_error:
            errors = {"cairosvg": cairosvg_error, "fallback": fallback_error}
            if browser_error is not None:
                errors["browser"] = browser_error
            issues.append(
                _issue(
                    "render_failed",
                    "Browser/CairoSVG SVG rendering failed and the lightweight fallback also failed.",
                    errors,
                )
            )
            return {"backend": "failed", "errors": errors}

        report = {"backend": "pillow_fallback", "fallbacks": {"cairosvg": cairosvg_error}}
        if browser_error is not None:
            report["fallbacks"]["browser"] = browser_error
        return report


def _browser_renderer_path() -> Path | None:
    configured = os.environ.get(_BROWSER_RENDERER_ENV)
    if configured:
        if configured.strip().lower() in {"0", "false", "none", "off", "disabled"}:
            return None
        path = Path(configured)
        if path.exists() and os.access(path, os.X_OK):
            return path

    for candidate in _browser_renderer_candidate_paths():
        path = Path(candidate)
        if path.exists() and os.access(path, os.X_OK):
            return path

    for name in _BROWSER_RENDERER_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)

    return None


def _browser_renderer_candidate_paths() -> list[str]:
    candidates = list(_BROWSER_RENDERER_PATHS)
    if os.name != "nt":
        return candidates

    browser_parts = [
        ("Google", "Chrome", "Application", "chrome.exe"),
        ("Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for root_name in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        root = os.environ.get(root_name)
        if not root:
            continue
        for parts in browser_parts:
            candidates.append(str(Path(root, *parts)))
    return candidates


def _render_svg_with_browser(root: etree._Element, svg_dir: Path, rendered_path: Path, browser_path: Path) -> str | None:
    canvas = _canvas_from_svg_root(root)
    if canvas is None:
        return "could not infer canvas size"

    width, height = canvas
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="drawai-svg-browser-profile-") as temp_dir:
        with tempfile.NamedTemporaryFile(prefix=".drawai-render-", suffix=".svg", dir=svg_dir, delete=False) as handle:
            svg_path = Path(handle.name)
            handle.write(etree.tostring(root, xml_declaration=True, encoding="utf-8"))
        user_data_dir = Path(temp_dir) / "browser-profile"
        command = [
            str(browser_path),
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--allow-file-access-from-files",
            *_browser_renderer_keychain_flags(),
            f"--user-data-dir={user_data_dir}",
            f"--window-size={width},{height}",
            "--force-device-scale-factor=1",
            f"--screenshot={rendered_path}",
            svg_path.as_uri(),
        ]
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=os.name == "posix",
            )
            deadline = time.monotonic() + _BROWSER_RENDER_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if rendered_path.exists() and rendered_path.stat().st_size > 0:
                    _stop_browser_renderer(process)
                    return None
                if process.poll() is not None:
                    break
                time.sleep(0.2)

            if process.poll() is None:
                _stop_browser_renderer(process, force=True)
                return f"timed out after {_BROWSER_RENDER_TIMEOUT_SECONDS} seconds"

            stdout, stderr = process.communicate(timeout=5)
        except OSError as exc:
            return str(exc)
        except subprocess.TimeoutExpired:
            if process is not None:
                _stop_browser_renderer(process, force=True)
            return "browser renderer did not finish after process exit"
        finally:
            svg_path.unlink(missing_ok=True)

    if not rendered_path.exists():
        if process is not None and process.returncode != 0:
            return (stderr or stdout or f"exit code {process.returncode}").strip()
        return "browser completed without writing screenshot"
    return None


def _browser_renderer_keychain_flags(platform: str | None = None) -> list[str]:
    if (platform or sys.platform) != "darwin":
        return []
    return ["--use-mock-keychain", "--password-store=basic"]


def _stop_browser_renderer(process: subprocess.Popen[str], *, force: bool = False) -> None:
    if process.poll() is not None:
        return
    signal_value = signal.SIGKILL if force else signal.SIGTERM
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal_value)
        elif force:
            process.kill()
        else:
            process.terminate()
        process.wait(timeout=5)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        if not force:
            _stop_browser_renderer(process, force=True)


def _render_svg_pillow_fallback(root: etree._Element, rendered_path: Path) -> str:
    canvas = _canvas_from_svg_root(root)
    if canvas is None:
        return "could not infer canvas size"
    width, height = canvas
    try:
        image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        gradient_fills = _gradient_fill_map(root)
        for element in root.iter():
            _draw_simple_svg_element(draw, image, element, gradient_fills)
        rendered_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(rendered_path)
    except Exception as exc:  # noqa: BLE001 - fallback is best-effort.
        return str(exc)
    return ""


def _canvas_from_svg_root(root: etree._Element) -> tuple[int, int] | None:
    viewbox = root.get("viewBox")
    values = _parse_number_list(viewbox or "")
    if values is not None and len(values) == 4 and values[2] > 0 and values[3] > 0:
        return max(1, int(round(values[2]))), max(1, int(round(values[3])))
    width = _parse_dimension(root.get("width") or "")
    height = _parse_dimension(root.get("height") or "")
    if width is not None and height is not None and width > 0 and height > 0:
        return max(1, int(round(width))), max(1, int(round(height)))
    return None


def _gradient_fill_map(root: etree._Element) -> dict[str, tuple[int, int, int, int]]:
    fills: dict[str, tuple[int, int, int, int]] = {}
    for element in root.iter():
        if _local_name(element.tag) not in {"linearGradient", "radialGradient"}:
            continue
        gradient_id = element.get("id")
        if not gradient_id:
            continue
        for child in element:
            if _local_name(child.tag) != "stop":
                continue
            color = _color_from_value(child.get("stop-color") or _style_value(child.get("style") or "", "stop-color"))
            if color is not None:
                fills[gradient_id] = color
                break
    return fills


def _draw_simple_svg_element(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    element: etree._Element,
    gradient_fills: Mapping[str, tuple[int, int, int, int]],
) -> None:
    tag = _local_name(element.tag)
    fill = _element_color(element, "fill", gradient_fills)
    stroke = _element_color(element, "stroke", gradient_fills)
    stroke_width = max(1, int(round(_float_attr(element, "stroke-width", 1))))
    if tag == "rect":
        x = _float_attr(element, "x", 0)
        y = _float_attr(element, "y", 0)
        width = _float_attr(element, "width", 0)
        height = _float_attr(element, "height", 0)
        if width > 0 and height > 0:
            draw.rectangle([x, y, x + width, y + height], fill=fill, outline=stroke, width=stroke_width)
    elif tag == "circle":
        cx = _float_attr(element, "cx", 0)
        cy = _float_attr(element, "cy", 0)
        radius = _float_attr(element, "r", 0)
        if radius > 0:
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=fill, outline=stroke, width=stroke_width)
    elif tag == "ellipse":
        cx = _float_attr(element, "cx", 0)
        cy = _float_attr(element, "cy", 0)
        rx = _float_attr(element, "rx", 0)
        ry = _float_attr(element, "ry", 0)
        if rx > 0 and ry > 0:
            draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill, outline=stroke, width=stroke_width)
    elif tag == "line":
        draw.line(
            [
                (_float_attr(element, "x1", 0), _float_attr(element, "y1", 0)),
                (_float_attr(element, "x2", 0), _float_attr(element, "y2", 0)),
            ],
            fill=stroke or fill or (0, 0, 0, 255),
            width=stroke_width,
        )
    elif tag in {"polyline", "polygon"}:
        points = _parse_points(element.get("points") or "")
        if len(points) >= 2:
            if tag == "polygon":
                draw.polygon(points, fill=fill, outline=stroke)
            else:
                draw.line(points, fill=stroke or fill or (0, 0, 0, 255), width=stroke_width)
    elif tag == "path":
        points = _parse_path_points(element.get("d") or "")
        if len(points) >= 2:
            draw.line(points, fill=stroke or fill or (0, 0, 0, 255), width=stroke_width)
    elif tag == "image":
        _paste_data_uri_image(image, element)
    elif tag == "text":
        _draw_text_element(draw, element, fill or stroke or (0, 0, 0, 255))


def _draw_text_element(
    draw: ImageDraw.ImageDraw,
    element: etree._Element,
    fill: tuple[int, int, int, int],
) -> None:
    raw_text = "".join(element.itertext())
    if not raw_text:
        return
    font_size = max(1, int(round(_float_attr(element, "font-size", 12))))
    font = _image_font_for_size(font_size)
    x = _float_attr(element, "x", 0)
    y = _float_attr(element, "y", 0)
    bbox = draw.textbbox((0, 0), raw_text, font=font)
    width = bbox[2] - bbox[0]
    anchor = (element.get("text-anchor") or "").strip().lower()
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    # SVG y is the text baseline; Pillow y is the top-left drawing origin.
    y -= font_size * 0.82
    draw.text((x, y), raw_text, fill=fill, font=font)


def _image_font_for_size(font_size: int) -> ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, font_size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()


def _element_color(
    element: etree._Element,
    attr_name: str,
    gradient_fills: Mapping[str, tuple[int, int, int, int]],
) -> tuple[int, int, int, int] | None:
    value = element.get(attr_name) or _style_value(element.get("style") or "", attr_name)
    if not value and attr_name == "fill" and _local_name(element.tag) in {"rect", "circle", "ellipse", "polygon", "path", "text"}:
        value = "black"
    if not value:
        return None
    match = re.fullmatch(r"url\(#([^)]+)\)", value.strip())
    if match:
        return gradient_fills.get(match.group(1))
    return _color_from_value(value)


def _style_value(style: str, attr_name: str) -> str:
    for part in style.split(";"):
        key, separator, value = part.partition(":")
        if separator and key.strip() == attr_name:
            return value.strip()
    return ""


def _color_from_value(raw: Any) -> tuple[int, int, int, int] | None:
    value = str(raw or "").strip()
    if not value or value.lower() == "none":
        return None
    try:
        return ImageColor.getcolor(value, "RGBA")
    except ValueError:
        return None


def _float_attr(element: etree._Element, attr_name: str, default: float) -> float:
    raw_value = element.get(attr_name)
    parsed = _parse_dimension(raw_value or "")
    return float(parsed if parsed is not None else default)


def _parse_points(raw: str) -> list[tuple[float, float]]:
    numbers = [float(value) for value in re.findall(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", raw)]
    return list(zip(numbers[0::2], numbers[1::2]))


def _parse_path_points(raw: str) -> list[tuple[float, float]]:
    return _parse_points(raw)


def _paste_data_uri_image(image: Image.Image, element: etree._Element) -> None:
    href = element.get("href") or element.get(f"{{{XLINK_NS}}}href") or ""
    if not href.startswith("data:") or ";base64," not in href:
        return
    encoded = href.split(";base64,", maxsplit=1)[1]
    pasted = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
    width = max(1, int(round(_float_attr(element, "width", pasted.width))))
    height = max(1, int(round(_float_attr(element, "height", pasted.height))))
    if pasted.size != (width, height):
        pasted = pasted.resize((width, height))
    x = int(round(_float_attr(element, "x", 0)))
    y = int(round(_float_attr(element, "y", 0)))
    image.alpha_composite(pasted, (x, y))


def _svg_for_safe_render(
    root: etree._Element,
    svg_dir: Path,
    manifest_paths: set[Path],
    issues: list[dict[str, Any]],
) -> etree._Element | None:
    render_root = etree.fromstring(etree.tostring(root))
    for element in render_root.iter():
        for attr_name, attr_value in list(element.attrib.items()):
            local_name = _local_name(attr_name)
            attr_text = str(attr_value)
            if local_name in {"href", "src"}:
                data_uri = _manifest_asset_data_uri(attr_text, svg_dir, manifest_paths, issues)
                if data_uri is None:
                    if issues and issues[-1].get("code") == "asset_read_error":
                        return None
                else:
                    element.set(attr_name, data_uri)
            elif local_name == "style":
                element.set(
                    attr_name,
                    _embed_manifest_urls(attr_text, svg_dir, manifest_paths, issues),
                )
                if issues and issues[-1].get("code") == "asset_read_error":
                    return None
            elif "url(" in attr_text.lower():
                element.set(
                    attr_name,
                    _embed_manifest_urls(attr_text, svg_dir, manifest_paths, issues),
                )
                if issues and issues[-1].get("code") == "asset_read_error":
                    return None

        if _local_name(element.tag) == "style" and element.text:
            element.text = _embed_manifest_urls(element.text, svg_dir, manifest_paths, issues)
            if issues and issues[-1].get("code") == "asset_read_error":
                return None

    return render_root


def _embed_manifest_urls(
    style_text: str,
    svg_dir: Path,
    manifest_paths: set[Path],
    issues: list[dict[str, Any]],
) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_ref = next(group for group in match.groups() if group is not None)
        data_uri = _manifest_asset_data_uri(raw_ref.strip(), svg_dir, manifest_paths, issues)
        if data_uri is None:
            return match.group(0)
        return f'url("{data_uri}")'

    return _URL_RE.sub(replace, style_text)


def _manifest_asset_data_uri(
    raw_ref: str,
    svg_dir: Path,
    manifest_paths: set[Path],
    issues: list[dict[str, Any]],
) -> str | None:
    ref = raw_ref.strip().strip("\"'")
    if not ref or ref.startswith("#") or _is_data_uri(ref) or _is_external_or_absolute_ref(ref):
        return None

    resolved = _resolve_local_ref(ref, svg_dir)
    if resolved is None or resolved not in manifest_paths:
        return None

    try:
        asset_bytes = resolved.read_bytes()
    except OSError as exc:
        issues.append(_issue("asset_read_error", "Manifest asset could not be read for SVG render.", str(exc)))
        return None

    mime_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(asset_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _validate_nonblank_render(rendered_path: Path, issues: list[dict[str, Any]]) -> None:
    try:
        with Image.open(rendered_path) as image:
            rgba = image.convert("RGBA")
    except Exception as exc:
        issues.append(_issue("render_read_failed", "Rendered PNG could not be read.", str(exc)))
        return

    alpha = rgba.getchannel("A")
    if alpha.getbbox() is None:
        issues.append(_issue("blank_render", "Rendered SVG is fully transparent."))
        return

    pixels = rgba.load()
    nonwhite_visible = 0
    visible_pixels = 0
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha_value = pixels[x, y]
            if alpha_value <= 8:
                continue
            visible_pixels += 1
            if max(abs(red - 255), abs(green - 255), abs(blue - 255)) > 5:
                nonwhite_visible += 1

    if nonwhite_visible == 0:
        issues.append(
            _issue(
                "blank_render",
                "Rendered SVG does not contain meaningful non-white visible content.",
                {"visible_pixels": visible_pixels, "nonwhite_visible_pixels": nonwhite_visible},
            )
        )


def _parse_number_list(raw: str) -> tuple[float, ...] | None:
    parts = [part for part in re.split(r"[\s,]+", raw.strip()) if part]
    values: list[float] = []
    for part in parts:
        try:
            values.append(float(part))
        except ValueError:
            return None
    return tuple(values)


def _parse_dimension(raw: str) -> float | None:
    match = _DIMENSION_RE.match(raw)
    if not match:
        return None
    return float(match.group(1))


def _same_number(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-6


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


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


def _safe_tag(element: etree._Element) -> str:
    return element.tag if isinstance(element.tag, str) else repr(element.tag)


def _has_unsafe_reference_issue(issues: list[dict[str, Any]]) -> bool:
    unsafe_codes = {
        "doctype",
        "external_entity",
        "external_href",
        "script_element",
        "asset_href_not_in_manifest",
        "xml_parse_error",
    }
    return any(issue.get("code") in unsafe_codes for issue in issues)
