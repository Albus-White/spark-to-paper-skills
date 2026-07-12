#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_imagegen  # noqa: E402
from drawai.slide_image_prompt import (  # noqa: E402
    build_legacy_workbench_image_generation_prompt,
    build_slide_image_generation_prompt,
    build_slide_image_prompt_comparison,
)


ACADEMIC_DEMO_PAYLOAD: dict[str, Any] = {
    "prompt": (
        "Create a single premium 16:9 academic conference slide image explaining a research result: "
        "a multimodal foundation model improves Nature-style figure-to-editable-PPT reconstruction by combining "
        "OCR text grounding, segmentation masks, asset selection, and SVG/PPT native-shape rebuilding. "
        "The slide should look like a polished methods/results overview for a high-impact computer-science paper."
    ),
    "size": "2048x1152",
    "quality": "high",
    "background": "opaque",
    "output_format": "png",
    "slide_type": "academic methods and results overview",
    "audience": "computer vision and scientific-communication researchers",
    "tone": "rigorous, modern, high-impact journal presentation",
    "style": "Swiss editorial scientific slide with restrained color, dense but readable structure, strong hierarchy",
    "locked_visible_text": [
        "DrawAI: Figure-to-Editable-PPT Reconstruction",
        "OCR grounding",
        "Segmentation masks",
        "Asset selection",
        "Native SVG/PPT rebuild",
        "Editable output",
    ],
    "claims": [
        {
            "claim": "The pipeline combines OCR text grounding, segmentation masks, asset selection, and native SVG/PPT rebuilding.",
            "source": "user-supplied project brief",
        },
        {
            "claim": "The output target is an editable SVG/PPT representation rather than a flat raster slide.",
            "source": "user-supplied project brief",
        },
    ],
    "research_context": {
        "source_basis": "user-supplied project brief for DrawAI architecture; no external benchmark numbers supplied",
        "forbidden": [
            "invented accuracy numbers",
            "fake dataset names",
            "fake citation callouts",
            "random axis labels",
            "unverified institution logos",
        ],
    },
    "quality_gates": [
        "must read as an academic PPT slide, not a marketing poster",
        "visible text must be readable, source-grounded, and sufficient for explanation",
        "diagram arrows and module boxes must be cleanly separated",
        "no invented numeric metrics or fake citations",
    ],
    "drawai_postprocess": [
        "module boxes, arrows, text labels, and image-like assets should be spatially separable for later DrawAI reconstruction",
        "avoid tiny labels that OCR cannot recover",
    ],
}


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(args)
    _apply_strategy_args(payload, args)
    runtime_config: dict[str, object] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model

    started_at = time.time()
    comparison = build_slide_image_prompt_comparison(
        payload,
        variant_index=args.variant_index,
        variant_count=args.variant_count,
    )
    legacy_prompt = comparison["legacy_prompt"]
    improved_prompt = comparison["improved_prompt"]
    (output_dir / "payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "legacy_prompt.txt").write_text(legacy_prompt + "\n", encoding="utf-8")
    (output_dir / "improved_prompt.txt").write_text(improved_prompt + "\n", encoding="utf-8")

    report: dict[str, Any] = {
        "schema": "drawai.codex_slide_imagegen_ab_report.v1",
        "status": "prompt_only",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "payload_path": str(output_dir / "payload.json"),
        "legacy_prompt_path": str(output_dir / "legacy_prompt.txt"),
        "improved_prompt_path": str(output_dir / "improved_prompt.txt"),
        "comparison": comparison,
        "generation": {},
    }

    if args.generate:
        report["status"] = "running"
        _write_report(output_dir, report)
        generation_root = output_dir / "generated"
        legacy_result = invoke_codex_python_sdk_imagegen(
            prompt=legacy_prompt,
            output_dir=generation_root / "legacy",
            task_name="drawai.experiment.codex_slide_imagegen.legacy.v1",
            output_stem="legacy-slide-image",
            runtime_config=runtime_config,
            trace_path=output_dir / "legacy_trace.jsonl",
            isolated_cwd=args.cwd or output_dir / "legacy_cwd",
        )
        improved_result = invoke_codex_python_sdk_imagegen(
            prompt=improved_prompt,
            output_dir=generation_root / "improved",
            task_name="drawai.experiment.codex_slide_imagegen.improved.v1",
            output_stem="improved-slide-image",
            runtime_config=runtime_config,
            trace_path=output_dir / "improved_trace.jsonl",
            isolated_cwd=args.cwd or output_dir / "improved_cwd",
        )
        report["status"] = "ok"
        report["generation"] = {
            "legacy": legacy_result.to_dict(),
            "improved": improved_result.to_dict(),
            "manual_review_checklist": _manual_review_checklist(),
        }

    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_report(output_dir, report)
    print(json.dumps(_printable_summary(report), ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare legacy and improved DrawAI Codex slide-image prompts, optionally generating both images."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--payload", type=Path, help="JSON payload containing prompt and optional grounding/design fields.")
    source.add_argument("--prompt", help="Plain prompt. Uses defaults for the rest of the payload.")
    source.add_argument("--academic-demo", action="store_true", help="Use a hard academic PPT demo payload.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "codex_slide_imagegen_compare",
    )
    parser.add_argument("--generate", action="store_true", help="Actually call Codex imageGeneration for legacy and improved prompts.")
    parser.add_argument("--variant-index", type=int, default=1)
    parser.add_argument("--variant-count", type=int, default=1)
    parser.add_argument("--model", default="", help="Optional Codex model override.")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--cwd", type=Path, help="Optional Codex SDK cwd. Defaults to separate experiment directories.")
    parser.add_argument("--strategy", default="auto", help="Deck intent/strategy, e.g. auto, academic, business, data, product, teaching, document.")
    parser.add_argument("--template", default="", help="Template id to force, e.g. academic_technical, consulting_report, data_journalism.")
    parser.add_argument("--source-mode", default="", help="Optional source mode override: prompt_only, source_grounded, data_driven, brand_template, web_research.")
    parser.add_argument("--style-candidate-index", type=int, default=1)
    parser.add_argument("--style-candidate-count", type=int, default=3)
    return parser.parse_args()


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload:
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit("--payload JSON must be an object")
        return payload
    if args.prompt:
        payload = dict(ACADEMIC_DEMO_PAYLOAD)
        payload["prompt"] = args.prompt.strip()
        return payload
    return dict(ACADEMIC_DEMO_PAYLOAD)


def _apply_strategy_args(payload: dict[str, Any], args: argparse.Namespace) -> None:
    if args.strategy and args.strategy != "auto":
        payload["strategy"] = args.strategy
    if args.template:
        payload["template_id"] = args.template
    if args.source_mode:
        payload["source_mode"] = args.source_mode
    payload["style_candidate_index"] = args.style_candidate_index
    payload["style_candidate_count"] = args.style_candidate_count
    payload["rendering_mode"] = "baked_text"


def _manual_review_checklist() -> list[str]:
    return [
        "factual content stays within supplied source context",
        "no invented metrics, citations, logos, dates, or dataset names",
        "visible text is exact, readable, and OCR-friendly",
        "layout has clear hierarchy, balanced margins, and no overcrowding",
        "semantic regions are separable for DrawAI reconstruction",
        "image quality is presentation-grade at target resolution",
    ]


def _write_report(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "comparison_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _printable_summary(report: dict[str, Any]) -> dict[str, Any]:
    comparison = report.get("comparison") if isinstance(report.get("comparison"), dict) else {}
    diff = comparison.get("diff_summary") if isinstance(comparison.get("diff_summary"), dict) else {}
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    return {
        "status": report.get("status"),
        "legacy_prompt_path": report.get("legacy_prompt_path"),
        "improved_prompt_path": report.get("improved_prompt_path"),
        "added_controls": diff.get("added_controls"),
        "legacy_images": _image_paths(generation.get("legacy")),
        "improved_images": _image_paths(generation.get("improved")),
        "report_path": str(Path(str(report.get("legacy_prompt_path", "."))).parent / "comparison_report.json"),
    }


def _image_paths(result: Any) -> list[str]:
    if not isinstance(result, dict):
        return []
    images = result.get("images")
    if not isinstance(images, list):
        return []
    return [str(image.get("path")) for image in images if isinstance(image, dict) and image.get("path")]


if __name__ == "__main__":
    raise SystemExit(main())
