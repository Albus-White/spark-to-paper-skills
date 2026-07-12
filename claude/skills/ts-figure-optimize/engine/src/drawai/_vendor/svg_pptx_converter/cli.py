"""Standalone command line interface for the vendored ppt-master converter."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .svg_to_pptx.pptx_builder import create_pptx_with_native_svg


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = slug.strip("._-")
    return slug or "slide"


def _find_svg_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".svg":
            raise ValueError(f"Input file is not an SVG: {input_path}")
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")
    return sorted(
        path
        for path in input_path.rglob("*.svg")
        if not any(part.startswith(".") for part in path.relative_to(input_path).parts)
    )


def _default_output_stem(svg_path: Path, input_path: Path, used: set[str]) -> str:
    if input_path.is_file():
        base = svg_path.stem
    else:
        rel = svg_path.relative_to(input_path)
        parent = rel.parent.as_posix().replace("/", "_")
        base = parent if parent and parent != "." else svg_path.stem
    stem = _slugify(base)
    candidate = stem
    counter = 2
    while candidate in used:
        candidate = f"{stem}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert SVG files to editable PPTX files using native DrawingML shapes."
    )
    parser.add_argument("input", type=Path, help="SVG file or directory containing SVG files")
    parser.add_argument("output", type=Path, help="Output PPTX file or output directory")
    parser.add_argument(
        "--format",
        dest="canvas_format",
        default=None,
        help="Canvas format key such as ppt169/ppt43; defaults to the first SVG viewBox.",
    )
    parser.add_argument("--trace", action="store_true", help="Write per-output conversion trace JSON")
    parser.add_argument("--quiet", action="store_true", help="Reduce converter output")
    parser.add_argument(
        "--transition",
        default=None,
        help="Page transition name; omit for none in this standalone wrapper.",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Keep dy-stacked text lines as separate text boxes.",
    )
    return parser


def convert(input_path: Path, output_path: Path, options: dict[str, Any]) -> list[dict[str, Any]]:
    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    svg_files = _find_svg_files(input_path)
    if not svg_files:
        raise FileNotFoundError(f"No SVG files found under: {input_path}")

    single_output = input_path.is_file() or output_path.suffix.lower() == ".pptx"
    if single_output and len(svg_files) > 1:
        raise ValueError("A .pptx output path can only be used with one SVG input")

    if single_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    used_stems: set[str] = set()
    for svg_path in svg_files:
        if single_output:
            pptx_path = output_path
            stem = output_path.stem
        else:
            stem = _default_output_stem(svg_path, input_path, used_stems)
            pptx_path = output_path / f"{stem}.pptx"
        trace_path = pptx_path.with_suffix(".trace.json") if options["trace"] else None
        ok = create_pptx_with_native_svg(
            [svg_path],
            pptx_path,
            canvas_format=options["canvas_format"],
            verbose=not options["quiet"],
            transition=options["transition"],
            use_native_shapes=True,
            enable_notes=False,
            animation=None,
            merge_paragraphs=not options["no_merge"],
            conversion_trace_path=trace_path,
            doc_metadata={
                "title": stem,
                "subject": "Standalone native SVG to PPTX conversion",
            },
        )
        results.append(
            {
                "svg": str(svg_path),
                "pptx": str(pptx_path),
                "trace": str(trace_path) if trace_path else None,
                "ok": bool(ok),
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    options = {
        "canvas_format": args.canvas_format,
        "trace": args.trace,
        "quiet": args.quiet,
        "transition": args.transition,
        "no_merge": args.no_merge,
    }

    results = convert(args.input, args.output, options)
    output_path = args.output.expanduser().resolve()
    manifest_dir = output_path.parent if output_path.suffix.lower() == ".pptx" else output_path
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({"input": str(args.input.expanduser().resolve()), "outputs": results}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    failed = [item for item in results if not item["ok"]]
    print(f"Converted {len(results) - len(failed)}/{len(results)} SVG file(s)")
    print(f"Manifest: {manifest_path}")
    if failed:
        for item in failed:
            print(f"FAILED: {item['svg']} -> {item['pptx']}", file=sys.stderr)
        return 1
    return 0
