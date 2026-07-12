#!/usr/bin/env python
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.codex_python_sdk_svg import (  # noqa: E402
    _archive_codex_session_logs,
    _codex_sdk_env,
    _codex_sdk_jsonable,
    _isolated_codex_home,
    _load_openai_codex_sdk,
    _normalize_codex_model_name,
    _normalize_codex_reasoning_effort,
    _run_thread_with_timeout,
    controlled_codex_config_overrides,
)
from drawai.codex_cli import resolve_codex_executable  # noqa: E402
from drawai.config import load_drawai_config  # noqa: E402
from drawai.asset_geometry import geometry_crop, normalize_asset_geometry  # noqa: E402
from drawai.acp_agent import invoke_acp_agent_text  # noqa: E402
from drawai.agent_cli_svg import invoke_agent_cli_text  # noqa: E402
from drawai.v2.refine import (  # noqa: E402
    CodexElementRefiner,
    RefineConfig,
    REFINED_ELEMENT_PLANS_EXPORT_SCHEMA,
    codex_analysis_to_v2_removal_records,
)


SCHEMA_REQUEST = "drawai.codex_element_analysis_request.v1"
SCHEMA_OUTPUT = "drawai.codex_element_analysis.v1"
CATEGORIES = ("svg_self_draw", "crop", "crop_nobg")
REFINEMENT_ACTIONS = ("unchanged", "adjusted", "split", "added", "removed", "merged")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    case_dirs = [path.expanduser().resolve(strict=False) for path in args.case_dirs]
    if not case_dirs:
        raise SystemExit("At least one case directory is required.")

    started_at = time.monotonic()
    if args.max_workers == 1 or len(case_dirs) == 1:
        results = [run_case(case_dir, args) for case_dir in case_dirs]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as pool:
            futures = [pool.submit(run_case, case_dir, args) for case_dir in case_dirs]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
            results.sort(key=lambda item: item["case_dir"])

    summary = {
        "schema": "drawai.codex_element_analysis_batch.v1",
        "status": "ok" if all(item["status"] == "ok" for item in results) else "failed",
        "case_count": len(results),
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "ok" else 1


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Codex pass that classifies DrawAI layout elements into SVG/crop/no-bg buckets."
    )
    parser.add_argument("case_dirs", nargs="+", type=Path, help="DrawAI case output directories.")
    parser.add_argument("--max-workers", type=int, default=1, help="Parallel Codex workers.")
    parser.add_argument("--model", default="", help="Optional Codex model override.")
    parser.add_argument(
        "--reasoning-effort",
        default="medium",
        choices=("none", "minimal", "low", "medium", "high", "xhigh"),
        help="Codex reasoning effort for this analysis pass.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--invoker",
        choices=("cli", "sdk", "agent_cli", "acp_agent"),
        default="cli",
        help="Use codex exec CLI by default; sdk/agent_cli are retained for parity with SVG generation experiments.",
    )
    parser.add_argument(
        "--agent-cli-agent",
        choices=("kimi", "claude", "codex", "openclaw", "hermes", "custom"),
        default="kimi",
        help="Agent CLI preset used when --invoker agent_cli is selected.",
    )
    parser.add_argument(
        "--agent-cli-command",
        nargs="+",
        default=[],
        help="Base agent CLI command used when --invoker agent_cli is selected.",
    )
    parser.add_argument(
        "--acp-agent",
        choices=("kimi", "custom"),
        default="kimi",
        help="ACP agent preset used when --invoker acp_agent is selected.",
    )
    parser.add_argument(
        "--acp-agent-command",
        nargs="+",
        default=[],
        help="Base ACP server command used when --invoker acp_agent is selected.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Do not invoke Codex when element_analysis.json already exists.",
    )
    parser.add_argument(
        "--config-override",
        action="append",
        default=[],
        help="Additional Codex -c key=value override for the SDK app-server.",
    )
    parsed = parser.parse_args(argv)
    if parsed.max_workers <= 0:
        parser.error("--max-workers must be positive")
    if parsed.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return parsed


def run_case(case_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    output_dir = case_dir / "reports" / "element_analysis_codex"
    output_path = output_dir / "element_analysis.json"
    runtime_config = _load_case_runtime_config(case_dir)
    started_at = time.monotonic()
    if args.skip_existing and output_path.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        request = build_request(case_dir, output_dir)
        request_path = output_dir / "element_analysis_request.json"
        write_json(request_path, request)
        validation, v2_export = finalize_analysis_outputs(
            case_dir=case_dir,
            output_dir=output_dir,
            output_path=output_path,
            request=request,
        )
        return {
            "status": "ok",
            "case_dir": str(case_dir),
            "output_path": str(output_path),
            "v2_output_path": str(output_dir / "element_plans.v2.json"),
            "skipped": True,
            "validation": validation,
            "v2_validation": v2_export["validation"],
            "category_counts": validation["category_counts"],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    request = build_request(case_dir, output_dir)
    request_path = output_dir / "element_analysis_request.json"
    candidate_table_path = output_dir / "candidate_table.tsv"
    prompt_path = output_dir / "prompt.txt"
    trace_path = output_dir / "codex_element_analysis_trace.jsonl"
    write_json(request_path, request)
    write_candidate_table(candidate_table_path, request)
    if args.invoker == "agent_cli":
        prompt_builder = build_agent_cli_review_prompt
    elif args.invoker == "acp_agent":
        prompt_builder = build_acp_agent_review_prompt
    else:
        prompt_builder = build_prompt
    prompt_path.write_text(
        prompt_builder(case_dir, request_path, candidate_table_path, output_path),
        encoding="utf-8",
    )

    status_path = output_dir / "run_status.json"
    write_json(
        status_path,
        {
            "schema": "drawai.codex_element_analysis_status.v1",
            "status": "running",
            "case_dir": str(case_dir),
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "request_path": str(request_path),
            "candidate_table_path": str(candidate_table_path),
            "prompt_path": str(prompt_path),
        },
    )

    if args.invoker == "sdk":
        codex_result = invoke_codex_element_analysis_sdk(
            case_dir=case_dir,
            prompt=prompt_path.read_text(encoding="utf-8"),
            image_paths=analysis_images(case_dir),
            output_dir=output_dir,
            trace_path=trace_path,
            model_name=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
            config_overrides=args.config_override,
            runtime_config=runtime_config,
        )
    elif args.invoker == "agent_cli":
        codex_result = invoke_agent_cli_element_analysis(
            case_dir=case_dir,
            prompt=prompt_path.read_text(encoding="utf-8"),
            image_paths=analysis_images(case_dir),
            output_dir=output_dir,
            trace_path=trace_path,
            model_name=args.model,
            timeout_seconds=args.timeout_seconds,
            agent=args.agent_cli_agent,
            command=args.agent_cli_command,
        )
    elif args.invoker == "acp_agent":
        codex_result = invoke_acp_agent_element_analysis(
            case_dir=case_dir,
            prompt=prompt_path.read_text(encoding="utf-8"),
            image_paths=analysis_images(case_dir),
            output_dir=output_dir,
            trace_path=trace_path,
            model_name=args.model,
            timeout_seconds=args.timeout_seconds,
            agent=args.acp_agent,
            command=args.acp_agent_command,
        )
    else:
        codex_result = invoke_codex_element_analysis_cli(
            case_dir=case_dir,
            prompt=prompt_path.read_text(encoding="utf-8"),
            image_paths=analysis_images(case_dir),
            output_dir=output_dir,
            trace_path=trace_path,
            model_name=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
            config_overrides=args.config_override,
            runtime_config=runtime_config,
        )
    validation, v2_export = finalize_analysis_outputs(
        case_dir=case_dir,
        output_dir=output_dir,
        output_path=output_path,
        request=request,
    )
    elapsed_seconds = round(time.monotonic() - started_at, 3)
    summary = {
        "schema": "drawai.codex_element_analysis_status.v1",
        "status": "ok",
        "case_dir": str(case_dir),
        "output_path": str(output_path),
        "v2_output_path": str(output_dir / "element_plans.v2.json"),
        "request_path": str(request_path),
        "candidate_table_path": str(candidate_table_path),
        "prompt_path": str(prompt_path),
        "trace_path": str(trace_path),
        "elapsed_seconds": elapsed_seconds,
        "validation": validation,
        "v2_validation": v2_export["validation"],
        "codex_result": codex_result,
        "ended_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    write_json(status_path, summary)
    return {
        "status": "ok",
        "case_dir": str(case_dir),
        "output_path": str(output_path),
        "elapsed_seconds": elapsed_seconds,
        "category_counts": validation["category_counts"],
    }


def _load_case_runtime_config(case_dir: Path) -> dict[str, Any]:
    config_path = case_dir / "drawai.config.yaml"
    if not config_path.exists():
        return {}
    try:
        cfg = load_drawai_config(config_path, validate_input_exists=False)
    except Exception:
        return {}
    return cfg.model_runtime.to_runtime_dict()


def finalize_analysis_outputs(
    *,
    case_dir: Path,
    output_dir: Path,
    output_path: Path,
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis = backfill_omitted_candidates(read_json(output_path), request)
    analysis = enrich_analysis_with_source_geometry(case_dir, analysis)
    write_json(output_path, analysis)
    validation = validate_analysis(analysis, request)
    write_json(output_dir / "validation.json", validation)
    v2_export = write_v2_element_plans_export(output_dir, analysis, request)
    return validation, v2_export


def build_request(case_dir: Path, output_dir: Path) -> dict[str, Any]:
    figure_path = case_dir / "inputs" / "figure.png"
    with Image.open(figure_path) as image:
        width, height = image.size
        source_image = image.convert("RGBA")

    box_ir = read_json(case_dir / "box_ir" / "box_ir.json")
    raw_box_ir = read_json(case_dir / "box_ir" / "box_ir.raw.json", default={})
    ocr = read_json(case_dir / "ocr" / "ocr_boxes.json", default={"ocr_text_boxes": []})
    initial_decisions = read_json(
        case_dir / "svg_to_ppt" / "assets" / "initial_asset_decisions.json",
        default={"decisions": []},
    )
    asset_decisions = read_json(
        case_dir / "svg_to_ppt" / "assets" / "asset_decisions.json",
        default={"decisions": []},
    )
    asset_policy = read_json(
        case_dir / "svg_to_ppt" / "assets" / "asset_policy_report.json",
        default={"assets": []},
    )
    asset_manifest = read_json(
        case_dir / "svg_to_ppt" / "assets" / "asset_manifest.json",
        default={"assets": []},
    )

    initial_by_box = records_by_key(initial_decisions.get("decisions"), "box_id")
    decision_by_box = records_by_key(asset_decisions.get("decisions"), "box_id")
    policy_by_asset = records_by_key(asset_policy.get("assets"), "asset_id")
    manifest_by_asset = records_by_key(asset_manifest.get("assets"), "asset_id")
    ocr_boxes = [dict(item) for item in ocr.get("ocr_text_boxes", []) if isinstance(item, Mapping)]
    candidates = []
    mask_previews: list[dict[str, Any]] = []
    mask_preview_dir = output_dir / "mask_previews"
    reset_directory(mask_preview_dir)
    for index, box in enumerate(box_ir.get("boxes", []) or [], start=1):
        if not isinstance(box, Mapping):
            continue
        box_id = str(box.get("id") or f"B{index:03d}")
        decision = decision_by_box.get(box_id, {})
        initial = initial_by_box.get(box_id, {})
        asset_id = str(
            decision.get("asset_id")
            or initial.get("asset_id")
            or decision.get("recovered_asset_id")
            or ""
        )
        policy = policy_by_asset.get(asset_id, {})
        manifest = manifest_by_asset.get(asset_id, {})
        current_method = current_pipeline_method(decision, initial, policy, manifest)
        candidate = {
            "box_id": box_id,
            "type": box.get("type", "unknown"),
            "bbox": box.get("bbox"),
            "parent_ids": box.get("parent_ids", []),
            "child_ids": box.get("child_ids", []),
            "source_box_ids": box.get("source_box_ids", []),
            "source_prompt": box.get("source_prompt", ""),
            "score": box.get("score", None),
            "current_pipeline_method": current_method,
            "asset_id": asset_id,
            "asset_decision": compact_mapping(decision),
            "initial_asset_decision": compact_mapping(initial),
            "asset_policy": compact_mapping(policy),
            "asset_manifest": compact_mapping(manifest),
            "asset_hrefs": asset_hrefs(manifest),
            "overlapping_ocr": overlapping_ocr(box.get("bbox"), ocr_boxes),
        }
        geometry_context = candidate_geometry_context(
            box,
            box_id,
            source_image,
            case_dir=case_dir,
            output_dir=output_dir,
            mask_preview_dir=mask_preview_dir,
        )
        if geometry_context:
            candidate.update(geometry_context)
            if geometry_context.get("geometry_kind") == "mask":
                mask_previews.append(
                    {
                        "box_id": box_id,
                        "bbox": box.get("bbox"),
                        "preview_path": geometry_context.get("geometry_preview"),
                    }
                )
        candidates.append(candidate)

    mask_preview_sheet = write_mask_preview_sheet(case_dir, output_dir, mask_previews)

    return {
        "schema": SCHEMA_REQUEST,
        "case_dir": str(case_dir),
        "canvas": {"width": width, "height": height},
        "source_image": "inputs/figure.png",
        "asset_plan_overlay": "reports/assemble_debug/assets/08_asset_plan.png",
        "mask_preview_sheet": mask_preview_sheet,
        "files": {
            "final_box_ir": "box_ir/box_ir.json",
            "raw_box_ir": "box_ir/box_ir.raw.json",
            "ocr": "ocr/ocr_boxes.json",
            "initial_asset_decisions": "svg_to_ppt/assets/initial_asset_decisions.json",
            "asset_decisions": "svg_to_ppt/assets/asset_decisions.json",
            "asset_policy_report": "svg_to_ppt/assets/asset_policy_report.json",
            "asset_manifest": "svg_to_ppt/assets/asset_manifest.json (optional pre-analysis preview; usually absent before final materialization)",
        },
        "raw_sam_box_count": len(raw_box_ir.get("boxes", []) or []),
        "ocr_box_count": len(ocr_boxes),
        "candidate_count": len(candidates),
        "mask_candidate_count": len(mask_previews),
        "candidates": candidates,
        "classification_contract": {
            "categories": list(CATEGORIES),
            "refinement_actions": list(REFINEMENT_ACTIONS),
            "required_coverage_for_existing_candidates": True,
            "allow_added_candidates": True,
            "coverage_field": "source_candidate_ids",
            "output_path": str(Path("reports") / "element_analysis_codex" / "element_analysis.json"),
        },
    }


def candidate_geometry_context(
    box: Mapping[str, Any],
    box_id: str,
    source_image: Image.Image,
    *,
    case_dir: Path,
    output_dir: Path,
    mask_preview_dir: Path,
) -> dict[str, Any]:
    geometry = normalize_asset_geometry(box.get("geometry"), fallback_bbox=box.get("bbox"), image_size=source_image.size)
    if geometry is None:
        return {}
    kind = str(geometry.get("kind") or "")
    public_geometry = {
        key: value
        for key, value in geometry.items()
        if key not in {"mask_path", "alpha_mask_path", "path"}
    }
    context: dict[str, Any] = {
        "geometry_kind": kind,
        "geometry": public_geometry,
    }
    if kind == "mask":
        bbox = int_bbox(geometry.get("bbox") or box.get("bbox"), source_image.size)
        if bbox is None:
            return context
        preview = geometry_crop(source_image, bbox, geometry, base_dir=case_dir)
        preview_path = mask_preview_dir / f"{safe_token(box_id)}_mask_preview.png"
        preview.save(preview_path)
        preview_rel = preview_path.relative_to(case_dir).as_posix()
        context.update(
            {
                "geometry_preview": preview_rel,
                "mask_preview": preview_rel,
                "geometry_locked": True,
                "geometry_rule": "This is a SAM mask region. Use the mask_preview PNG as visual evidence. Do not adjust its bbox or geometry; only merge/remove it when it is clearly duplicate or noise.",
            }
        )
        public_geometry["preview_path"] = preview_rel
    elif kind == "polygon":
        context["geometry_rule"] = "This is a polygon region. Keep the polygon points when preserving this asset; resize/move only when the polygon was user-adjusted."
    return context


def enrich_analysis_with_source_geometry(case_dir: Path, analysis: Mapping[str, Any]) -> dict[str, Any]:
    """Restore source-only geometry that Codex should not need to read directly."""
    enriched = dict(analysis)
    raw_elements = enriched.get("elements")
    if not isinstance(raw_elements, list):
        return enriched

    box_ir = read_json(case_dir / "box_ir" / "box_ir.json", default={"boxes": []})
    request = read_json(
        case_dir / "reports" / "element_analysis_codex" / "element_analysis_request.json",
        default={"candidates": []},
    )
    source_boxes = {
        str(box.get("id")): box
        for box in box_ir.get("boxes", []) or []
        if isinstance(box, Mapping) and box.get("id")
    }
    request_candidates = {
        str(candidate.get("box_id")): candidate
        for candidate in request.get("candidates", []) or []
        if isinstance(candidate, Mapping) and candidate.get("box_id")
    }

    elements: list[dict[str, Any]] = []
    for index, raw_element in enumerate(raw_elements):
        if not isinstance(raw_element, Mapping):
            raise ValueError(f"element analysis record {index} must be an object")
        element = dict(raw_element)
        if is_removal_record(element):
            elements.append(element)
            continue
        source_ids = normalized_element_source_ids(element, source_boxes)
        mask_sources: list[tuple[str, Mapping[str, Any], dict[str, Any]]] = []
        polygon_sources: list[tuple[str, Mapping[str, Any], dict[str, Any]]] = []
        for source_id in source_ids:
            source = source_boxes.get(source_id)
            if not isinstance(source, Mapping):
                continue
            geometry = normalize_asset_geometry(source.get("geometry"), fallback_bbox=source.get("bbox"))
            if not geometry:
                continue
            if geometry.get("kind") == "mask":
                mask_sources.append((source_id, source, geometry))
            elif geometry.get("kind") == "polygon":
                polygon_sources.append((source_id, source, geometry))

        if len(mask_sources) == 1:
            source_id, _source, geometry = mask_sources[0]
            element["geometry"] = geometry
            element["geometry_kind"] = "mask"
            element["geometry_locked"] = True
            element["bbox"] = geometry["bbox"]
            preview = request_candidates.get(source_id, {}).get("geometry_preview")
            if isinstance(preview, str) and preview:
                element["geometry_preview_relative_path"] = preview
                element["mask_preview"] = preview
            element["reason"] = append_unique_sentence(
                str(element.get("reason") or ""),
                "Mask geometry is preserved from the source SAM region.",
            )
        elif len(polygon_sources) == 1 and not isinstance(element.get("geometry"), Mapping):
            source_id, _source, geometry = polygon_sources[0]
            element["geometry"] = geometry
            element["geometry_kind"] = "polygon"
            preview = request_candidates.get(source_id, {}).get("geometry_preview")
            if isinstance(preview, str) and preview:
                element["geometry_preview_relative_path"] = preview

        elements.append(element)

    enriched["elements"] = elements
    return enriched


def normalized_element_source_ids(
    element: Mapping[str, Any],
    source_boxes: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    raw_source_ids = element.get("source_candidate_ids")
    if isinstance(raw_source_ids, list):
        source_ids = [str(item) for item in raw_source_ids if str(item)]
    else:
        source_ids = []
    box_id = str(element.get("box_id") or "")
    if not source_ids and box_id in source_boxes:
        source_ids = [box_id]
    return source_ids


def is_removal_record(element: Mapping[str, Any]) -> bool:
    action = record_refinement_action(element)
    if action == "removed":
        return True
    if action != "merged":
        return False
    if "removed_source_candidate_ids" in element:
        return True
    return not has_retained_element_payload(element)


def record_refinement_action(record: Mapping[str, Any]) -> str:
    return str(record.get("refinement_action") or record.get("action") or "").strip()


def has_retained_element_payload(record: Mapping[str, Any]) -> bool:
    return any(record.get(key) not in (None, "", []) for key in ("category", "bbox", "element_type", "type", "geometry"))


def analysis_removal_records(analysis: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    elements = analysis.get("elements")
    if isinstance(elements, list):
        records.extend(element for element in elements if isinstance(element, Mapping) and is_removal_record(element))
    records.extend(top_level_removal_records(analysis))
    return records


def top_level_removal_records(analysis: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_records = analysis.get("removal_records", [])
    if raw_records is None:
        return []
    if not isinstance(raw_records, list):
        raise ValueError("element_analysis.json removal_records must be a list")
    records: list[Mapping[str, Any]] = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            raise ValueError(f"removal_records[{index}] must be an object")
        records.append(raw_record)
    return records


def backfill_omitted_candidates(
    analysis: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    enriched = dict(analysis)
    elements = enriched.get("elements")
    if not isinstance(elements, list):
        return enriched
    candidates = [
        candidate
        for candidate in request.get("candidates", [])
        if isinstance(candidate, Mapping) and candidate.get("box_id")
    ]
    expected_ids = {str(candidate.get("box_id")) for candidate in candidates}
    covered_ids: set[str] = set()
    for element in elements:
        if not isinstance(element, Mapping):
            continue
        source_ids = _analysis_record_source_ids(element, expected_ids)
        covered_ids.update(source_ids)
    for removal_record in analysis_removal_records(enriched):
        covered_ids.update(_analysis_record_source_ids(removal_record, expected_ids))
    missing_ids = expected_ids - covered_ids
    if not missing_ids:
        return enriched
    enriched["elements"] = [
        *elements,
        *[
            _backfilled_candidate_element(candidate)
            for candidate in candidates
            if str(candidate.get("box_id")) in missing_ids
        ],
    ]
    return enriched


def _analysis_record_source_ids(
    element: Mapping[str, Any],
    expected_ids: set[str],
) -> list[str]:
    raw_source_ids = element.get("source_candidate_ids")
    if isinstance(raw_source_ids, list):
        return [str(item) for item in raw_source_ids if str(item)]
    removed_source_ids = element.get("removed_source_candidate_ids")
    if isinstance(removed_source_ids, list):
        return [str(item) for item in removed_source_ids if str(item)]
    box_id = str(element.get("box_id") or "")
    return [box_id] if box_id in expected_ids else []


def _backfilled_candidate_element(candidate: Mapping[str, Any]) -> dict[str, Any]:
    box_id = str(candidate.get("box_id"))
    category = str(candidate.get("current_pipeline_method") or "")
    if category not in CATEGORIES:
        category = "svg_self_draw"
    bbox = normalize_bbox(candidate.get("bbox"), allow_line=True)
    if bbox is None:
        bbox = (0.0, 0.0, 1.0, 1.0)
    element: dict[str, Any] = {
        "box_id": box_id,
        "source_candidate_ids": [box_id],
        "refinement_action": "unchanged",
        "category": category,
        "confidence": "medium",
        "visual_role": str(candidate.get("visual_role") or candidate.get("type") or "unknown"),
        "reason": "Preserved automatically because the agent response omitted this source candidate.",
        "bbox": list(bbox),
        "type": str(candidate.get("type") or "unknown"),
    }
    geometry = candidate.get("geometry")
    if isinstance(geometry, Mapping):
        element["geometry"] = dict(geometry)
    for source_key, target_key in (
        ("geometry_kind", "geometry_kind"),
        ("geometry_locked", "geometry_locked"),
        ("geometry_preview", "geometry_preview_relative_path"),
    ):
        value = candidate.get(source_key)
        if value not in (None, ""):
            element[target_key] = value
    return element


def append_unique_sentence(text: str, sentence: str) -> str:
    text = text.strip()
    if sentence in text:
        return text
    return f"{text} {sentence}".strip()


def write_mask_preview_sheet(case_dir: Path, output_dir: Path, mask_previews: Sequence[Mapping[str, Any]]) -> str:
    previews = [preview for preview in mask_previews if isinstance(preview.get("preview_path"), str)]
    if not previews:
        return ""
    cell_width = 220
    cell_height = 190
    columns = min(4, max(1, len(previews)))
    rows = (len(previews) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#f8faf9")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, preview in enumerate(previews):
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        label = str(preview.get("box_id") or f"mask_{index + 1}")
        rel_path = Path(str(preview["preview_path"]))
        with Image.open(case_dir / rel_path) as image:
            crop = image.convert("RGBA")
        background = checkerboard(crop.size)
        background.alpha_composite(crop)
        background.thumbnail((cell_width - 24, cell_height - 44), Image.Resampling.LANCZOS)
        px = x + (cell_width - background.width) // 2
        py = y + 28 + (cell_height - 44 - background.height) // 2
        sheet.paste(background.convert("RGB"), (px, py))
        draw.rectangle([x + 8, y + 8, x + cell_width - 8, y + cell_height - 8], outline="#08784f", width=2)
        draw.text((x + 14, y + 12), label, fill="#0f172a", font=font)
        if preview.get("bbox"):
            draw.text((x + 14, y + cell_height - 24), bbox_text(preview.get("bbox")), fill="#475569", font=font)
    sheet_path = output_dir / "mask_previews" / "mask_preview_sheet.png"
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sheet_path)
    return sheet_path.relative_to(case_dir).as_posix()


def checkerboard(size: tuple[int, int], block: int = 12) -> Image.Image:
    image = Image.new("RGBA", size, "#ffffff")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2 == 0:
                draw.rectangle([x, y, x + block - 1, y + block - 1], fill="#e7ece8")
    return image


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def int_bbox(raw_bbox: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    bbox = normalize_bbox(raw_bbox)
    if bbox is None:
        return None
    width, height = image_size
    left = max(0, min(width, int(bbox[0])))
    top = max(0, min(height, int(bbox[1])))
    right = max(0, min(width, int(bbox[2] + 0.999999)))
    bottom = max(0, min(height, int(bbox[3] + 0.999999)))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def safe_token(value: str) -> str:
    token = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value).strip("._-")
    return token or "asset"


def bbox_text(raw_bbox: Any) -> str:
    bbox = normalize_bbox(raw_bbox)
    if bbox is None:
        return ""
    return ",".join(str(round(value)) for value in bbox)


def write_candidate_table(path: Path, request: Mapping[str, Any]) -> None:
    columns = (
        "box_id",
        "type",
        "bbox",
        "geometry_kind",
        "geometry_locked",
        "geometry_preview",
        "current_pipeline_method",
        "asset_id",
        "render_policy",
        "background_policy",
        "active_variant",
        "policy_reasons",
        "ocr_text",
    )
    lines = ["\t".join(columns)]
    for candidate in request.get("candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        policy = candidate.get("asset_policy") if isinstance(candidate.get("asset_policy"), Mapping) else {}
        manifest = candidate.get("asset_manifest") if isinstance(candidate.get("asset_manifest"), Mapping) else {}
        ocr_text = " | ".join(
            str(item.get("text", "")).replace("\t", " ").replace("\n", " ")
            for item in candidate.get("overlapping_ocr", [])
            if isinstance(item, Mapping) and item.get("text")
        )
        reasons = policy.get("reason_codes") if isinstance(policy.get("reason_codes"), list) else []
        values = (
            candidate.get("box_id", ""),
            candidate.get("type", ""),
            ",".join(str(item) for item in candidate.get("bbox", [])),
            candidate.get("geometry_kind", ""),
            candidate.get("geometry_locked", ""),
            candidate.get("geometry_preview", ""),
            candidate.get("current_pipeline_method", ""),
            candidate.get("asset_id", ""),
            policy.get("render_policy", ""),
            policy.get("background_policy", ""),
            manifest.get("active_variant", ""),
            "|".join(str(item) for item in reasons),
            ocr_text,
        )
        lines.append("\t".join(str(value).replace("\t", " ").replace("\n", " ") for value in values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_prompt(case_dir: Path, request_path: Path, candidate_table_path: Path, output_path: Path) -> str:
    output_dir_rel = output_path.parent.relative_to(case_dir)
    assets_visualization_script = REPO_ROOT / "scripts" / "assets_visualization.py"
    return f"""DrawAI asset post-processing and source analysis task.

We are performing an image vectorization task: a bitmap image will eventually be transformed into an editable representation. The whole process has three parts:
- Asset parsing: divide the image into independent assets. Each asset may be text, an icon, table, frame, arrow, and so on.
- Asset post-processing: refine the pre-parsed assets.
- Editable reconstruction: combine assets and finish the final visual result.

Some assets should become editable forms, such as text, frames, arrows, and simple vector graphics. Some assets should instead be cropped from the original image and pasted back into their original positions. We have already preprocessed the image with layout analysis and OCR methods. You need to use the preprocessing result as evidence and execute the second stage, "asset post-processing", to refine the result. The detailed task instructions are below.

Workspace/case root:
{case_dir}

Inputs:
- Original image: inputs/figure.png
- Current DrawAI asset-plan overlay: reports/assemble_debug/assets/08_asset_plan.png
- Mask preview sheet, when mask candidates exist: reports/element_analysis_codex/mask_previews/mask_preview_sheet.png
- Compact candidate table: {candidate_table_path.relative_to(case_dir)}
- Machine-readable request: {request_path.relative_to(case_dir)}
- The request lists final layout candidates, overlapping OCR text, current crop/native decisions, asset policy metrics, geometry_kind, geometry_preview paths, and any optional pre-existing asset hrefs. The final asset manifest is generated after this analysis, so do not assume local crop hrefs already exist.

You may read files under the case root, but this is a bounded analysis pass. Do not render SVG/PPT, do not spend time searching unrelated files, and do not print the full request JSON to the terminal. Start from the compact candidate table; use the full request JSON only for exact bbox/details when needed. Use the attached original image, the attached asset-plan overlay, and the request JSON as the factual sources. Do not use MCP tools, apps, web search, memories, skills, hooks, or multi-agent delegation.

Task 1: refine request.candidates into minimum independent assets.
Each output element should be the smallest independent visual part, such as one icon, image, frame, arrow, text line, chart mark, chart block, or diagram component.
- Split a candidate when one box contains multiple independent parts, for example several icons/images inside one block.
- Add a new element when an asset is visible in the original image but not covered by any current candidate.
- Adjust the bbox when the current position is wrong or misses part of a component, for example a complex image whose frame does not include all visible content.
- Preserve traceability. For an unchanged or adjusted element, set source_candidate_ids to the original candidate ID. For a split element, use a new stable ID such as B012_S01 and set source_candidate_ids to ["B012"]. For a newly added element, use a stable ID such as N001 and set source_candidate_ids to [].
- When an original candidate is removed as duplicate/noise or merged into another retained element, emit a removal record with box_id, source_candidate_ids, refinement_action set to removed or merged, and a concise reason. Removal records do not need category or bbox because they are not retained output elements.
- Bboxes must be visual extents in image pixels. For a straight line or divider, give at least 1 pixel of thickness so the bbox has positive width and height.
- Pay close attention to whether coordinates are correct and whether each bbox tightly contains the corresponding asset.
- Some candidates have geometry_kind="mask". For those candidates, use their mask_preview PNG and the mask preview sheet as visual evidence. Do not adjust or resize the mask region; preserve its bbox/geometry when keeping it. You may remove or merge a mask candidate only when it is clearly duplicate or noise, and the original candidate ID must still be represented through source_candidate_ids.
- Do not read or rely on raw mask files. Mask regions are intentionally exposed to you as cropped PNG previews, not as mask data.

Task 2: repeat the following refinement loop until you believe the asset parsing quality is perfect, all elements are reasonable assets, and all bbox coordinates are accurate. Run at most 3 visualization/refinement iterations.
1. Write the current refined assets JSON for the iteration to:
   {output_dir_rel}/refine_iteration_<N>.json
   where <N> starts at 1 and increases by one each time. The iteration JSON should contain at least schema, case_dir, refinement_summary, refinement_actions, and elements with box_id, source_candidate_ids, refinement_action, bbox, type, visual_role, and reason.
2. Run assets_visualization for that iteration:
   python {assets_visualization_script} --image inputs/figure.png --json {output_dir_rel}/refine_iteration_<N>.json --output {output_dir_rel}/assets_visualization_iteration_<N>.png --summary-output {output_dir_rel}/assets_visualization_iteration_<N>.summary.json --color-mode action --label-mode id_type --title "DrawAI assets refinement iteration <N>"
3. Inspect the visualization output at:
   {output_dir_rel}/assets_visualization_iteration_<N>.png
   Use it to correct Task 1 results. You may add assets, remove assets, split assets, merge accidental duplicates, and adjust bbox coordinates. One iteration may change any number of assets.
4. Repeat steps 1-3 until the assets are perfect, or until you have completed 3 iterations.
5. Save the final refined asset list used for classification to:
   {output_dir_rel}/refined_assets_final.json

Task 3: classify every final refined output element into exactly one of these three categories:
- svg_self_draw: use editable SVG primitives/text/paths directly. Use this for text, arrows, boxes, lines, charts, simple geometric diagrams, and visually simple icons that can be faithfully redrawn.
- crop: use a precise source-image crop with its local background preserved. Use this for screenshots, photographs, dense texture, heatmaps, complex small raster icons, or visual details whose background is coupled with the object.
- crop_nobg: use a precise crop after background removal/transparent subject extraction. Use this when the foreground object is separable and should sit over reconstructed SVG background.

Important:
- Treat SAM/OCR/current asset plan as evidence, not truth. You may disagree with current_pipeline_method if the image supports it.
- Do not skip candidates. Every original request.candidates item must be represented by at least one output element through source_candidate_ids, or by an unchanged output element with the same box_id.
- The type field must be a concrete DrawAI element type: text, icon, picture, table, chart, diagram, arrow, frame, grid, symbol, content_box, or unknown. For newly added elements, do not use a meta type such as added_asset; classify the visible object itself.
- New IDs are allowed only for split or added refined elements. Keep IDs short and stable.
- This task only classifies and explains; do not modify the main SVG/PPT outputs.
- If uncertain, choose the most faithful final-source strategy and mark confidence as low or medium.
- After Task 2 is complete, complete the Task 3 classification in one pass. Write the final JSON file first, then write the markdown note. Keep reasons concise.
- Do not run git commands, do not commit, and do not change repository code.

Write UTF-8 JSON to:
{output_path.relative_to(case_dir)}

The JSON file must have this shape:
{{
  "schema": "{SCHEMA_OUTPUT}",
  "case_dir": "{case_dir}",
  "source": "codex",
  "strategy_summary": "short paragraph",
  "refinement_summary": "short paragraph",
  "refinement_iterations": [
    {{"iteration": 1, "json_path": "{output_dir_rel}/refine_iteration_1.json", "visualization_path": "{output_dir_rel}/assets_visualization_iteration_1.png", "changes": "short summary"}}
  ],
  "categories": {{"svg_self_draw": 0, "crop": 0, "crop_nobg": 0}},
  "refinement_actions": {{"unchanged": 0, "adjusted": 0, "split": 0, "added": 0, "removed": 0, "merged": 0}},
  "elements": [
    {{
      "box_id": "B001",
      "source_candidate_ids": ["B001"],
      "refinement_action": "unchanged",
      "category": "svg_self_draw",
      "confidence": "high",
      "visual_role": "short label",
      "reason": "one or two sentences",
      "evidence": ["short evidence item"],
      "bbox": [0, 0, 10, 10],
      "type": "content_box",
      "current_pipeline_method": "svg_self_draw",
      "recommended_asset_source": "svg",
      "geometry_kind": "mask",
      "geometry_locked": true,
      "geometry_preview_relative_path": "reports/element_analysis_codex/mask_previews/B001_mask_preview.png"
    }}
  ],
  "notes": []
}}

Also write a concise markdown audit note to:
reports/element_analysis_codex/analysis_notes.md

Keep the final chat response to one sentence. The JSON file is the source of truth.
"""


def invoke_codex_element_analysis_cli(
    *,
    case_dir: Path,
    prompt: str,
    image_paths: Sequence[Path],
    output_dir: Path,
    trace_path: Path,
    model_name: str,
    reasoning_effort: str,
    timeout_seconds: float,
    config_overrides: Sequence[str],
    runtime_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    codex_bin = resolve_codex_executable()
    if codex_bin is None:
        raise RuntimeError(
            "codex executable was not found. Run `uv run drawai setup local`, or run this script through: "
            "uv run --with openai-codex --prerelease=allow python ..."
        )
    normalized_model = _normalize_codex_model_name(model_name)
    normalized_effort = _normalize_codex_reasoning_effort(reasoning_effort)
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "cli_events.jsonl"
    stderr_path = output_dir / "cli_stderr.txt"
    last_message_path = output_dir / "cli_last_message.txt"
    for path in (events_path, stderr_path, last_message_path):
        if path.exists():
            path.unlink()

    started_at = time.monotonic()
    with _isolated_codex_home(case_dir) as prepared_codex_home:
        command = [
            str(codex_bin),
            "exec",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--json",
            "-C",
            str(case_dir),
            "-s",
            "danger-full-access",
            "-o",
            str(last_message_path),
            *image_cli_args(image_paths),
            *cli_config_args(normalized_effort, config_overrides, runtime_config=runtime_config),
        ]
        if normalized_model is not None:
            command.extend(["-m", normalized_model])
        command.append("-")
        env = os.environ.copy()
        env.update(_codex_sdk_env(prepared_codex_home.codex_home, runtime_config=runtime_config))
        env["HOME"] = str(prepared_codex_home.codex_home)
        for key in ("DRAWAI_HOST_HOME", "DRAWAI_HOST_CODEX_HOME"):
            env.pop(key, None)
        with events_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                cwd=str(case_dir),
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=timeout_seconds,
                check=False,
            )
        archive = _archive_codex_session_logs(
            prepared_codex_home.codex_home,
            output_dir / "codex_session_log",
            task_name="drawai.element_analysis.cli.v1",
        )

    duration_ms = int((time.monotonic() - started_at) * 1000)
    stderr_text = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
    last_message = last_message_path.read_text(encoding="utf-8") if last_message_path.exists() else ""
    cli_error = codex_cli_error_excerpt(events_path)
    trace = {
        "schema": "drawai.codex_element_analysis_cli_trace.v1",
        "case_dir": str(case_dir),
        "command": redact_command(command),
        "returncode": completed.returncode,
        "model_name": normalized_model or "codex-default",
        "reasoning_effort": normalized_effort,
        "timeout_seconds": timeout_seconds,
        "duration_ms": duration_ms,
        "image_paths": [str(path) for path in image_paths],
        "events_path": str(events_path),
        "stderr_path": str(stderr_path),
        "last_message_path": str(last_message_path),
        "last_message_excerpt": last_message[:2000],
        "stderr_excerpt": stderr_text[:2000],
        "cli_error_excerpt": cli_error,
        "session_log_archive": archive,
    }
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")
    if completed.returncode != 0:
        error_detail = cli_error or stderr_text[-2000:]
        raise RuntimeError(
            f"codex exec failed with returncode={completed.returncode}. error: {error_detail}"
        )
    return {
        "invoker": "cli",
        "model_name": normalized_model or "codex-default",
        "reasoning_effort": normalized_effort,
        "duration_ms": duration_ms,
        "events_path": str(events_path),
        "last_message_path": str(last_message_path),
        "session_log_archive_path": str(output_dir / "codex_session_log"),
    }


def image_cli_args(image_paths: Sequence[Path]) -> list[str]:
    args: list[str] = []
    for image_path in image_paths:
        args.extend(["-i", str(image_path)])
    return args


def cli_config_args(
    reasoning_effort: str,
    extra_overrides: Sequence[str],
    *,
    runtime_config: Mapping[str, Any] | None = None,
) -> list[str]:
    overrides = controlled_codex_config_overrides(
        [f'model_reasoning_effort="{reasoning_effort}"', *[str(item) for item in extra_overrides]],
        runtime_config=runtime_config,
    )
    args: list[str] = []
    for override in overrides:
        args.extend(["-c", override])
    return args


def redact_command(command: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            redacted.append(item)
            skip_next = False
            continue
        redacted.append(item)
        if item in {"-i", "-C", "-o", "-m", "-s", "-c"}:
            skip_next = True
    return redacted


def codex_cli_error_excerpt(events_path: Path, *, max_chars: int = 2000) -> str:
    if not events_path.exists():
        return ""
    messages: list[str] = []
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping):
            continue
        if event.get("type") == "error":
            message = event.get("message")
            if isinstance(message, str) and message.strip():
                messages.append(message.strip())
        turn_error = event.get("error")
        if isinstance(turn_error, Mapping):
            message = turn_error.get("message")
            if isinstance(message, str) and message.strip():
                messages.append(message.strip())
    if not messages:
        return ""
    text = messages[-1]
    return text if len(text) <= max_chars else f"{text[:max_chars]}..."


def invoke_codex_element_analysis_sdk(
    *,
    case_dir: Path,
    prompt: str,
    image_paths: Sequence[Path],
    output_dir: Path,
    trace_path: Path,
    model_name: str,
    reasoning_effort: str,
    timeout_seconds: float,
    config_overrides: Sequence[str],
    runtime_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    sdk = _load_openai_codex_sdk()
    normalized_model = _normalize_codex_model_name(model_name)
    normalized_effort = _normalize_codex_reasoning_effort(reasoning_effort)
    output_dir.mkdir(parents=True, exist_ok=True)
    session_log_archive_dir = output_dir / "codex_session_log"
    started_at = time.monotonic()
    result = None
    with _isolated_codex_home(case_dir) as prepared_codex_home:
        with sdk.Codex(
            sdk.CodexConfig(
                cwd=str(case_dir),
                config_overrides=controlled_codex_config_overrides(
                    config_overrides, runtime_config=runtime_config
                ),
                env=_codex_sdk_env(prepared_codex_home.codex_home, runtime_config=runtime_config),
            )
        ) as codex:
            thread = codex.thread_start(
                approval_mode=sdk.ApprovalMode.deny_all,
                config={"model_reasoning_effort": normalized_effort},
                cwd=str(case_dir),
                developer_instructions=(
                    "Internal DrawAI element source analysis thread.\n"
                    f"Workspace root: {case_dir}\n"
                    "You may use shell commands to inspect files and write outputs inside this workspace. "
                    "Do not use MCP tools, apps, web search, memories, skills, hooks, or multi-agent delegation."
                ),
                ephemeral=True,
                model=normalized_model,
                sandbox=sdk.Sandbox.full_access,
            )
            run_input = [
                sdk.TextInput(prompt),
                *(sdk.LocalImageInput(path=str(image_path)) for image_path in image_paths),
            ]
            result = _run_thread_with_timeout(
                thread,
                run_input,
                timeout_seconds=timeout_seconds,
                approval_mode=sdk.ApprovalMode.deny_all,
                cwd=str(case_dir),
                effort=normalized_effort,
                model=normalized_model,
                sandbox=sdk.Sandbox.full_access,
            )
        archive = _archive_codex_session_logs(
            prepared_codex_home.codex_home,
            session_log_archive_dir,
            task_name="drawai.element_analysis.v1",
            sdk_turn_result=result,
        )

    trace = {
        "schema": "drawai.codex_element_analysis_trace.v1",
        "case_dir": str(case_dir),
        "model_name": normalized_model or "codex-default",
        "reasoning_effort": normalized_effort,
        "timeout_seconds": timeout_seconds,
        "image_paths": [str(path) for path in image_paths],
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "result": {
            "id": getattr(result, "id", None),
            "status": _codex_sdk_jsonable(getattr(result, "status", None)),
            "duration_ms": getattr(result, "duration_ms", None),
            "usage": _codex_sdk_jsonable(getattr(result, "usage", None)),
            "final_response": getattr(result, "final_response", None),
        },
        "session_log_archive": archive,
    }
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "model_name": normalized_model or "codex-default",
        "reasoning_effort": normalized_effort,
        "duration_ms": trace["duration_ms"],
        "session_log_archive_path": str(session_log_archive_dir),
        "usage": trace["result"]["usage"],
    }


def invoke_agent_cli_element_analysis(
    *,
    case_dir: Path,
    prompt: str,
    image_paths: Sequence[Path],
    output_dir: Path,
    trace_path: Path,
    model_name: str,
    timeout_seconds: float,
    agent: str,
    command: Sequence[str],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "element_analysis.json"
    request_path = output_dir / "element_analysis_request.json"
    preseeded = False
    if request_path.exists():
        request = read_json(request_path)
        if isinstance(request.get("candidates"), list):
            write_json(output_path, build_baseline_analysis(case_dir, request, source="agent_cli_baseline_review"))
            preseeded = True
    started_at = time.monotonic()
    runtime_config = {
        "provider": "agent-cli",
        "connection_id": f"drawai-{agent}-cli-element-analysis",
        "model_name": model_name,
        "timeout_seconds": timeout_seconds,
        "cli": {
            "agent": agent,
            "command": list(command),
        },
    }
    final_message = invoke_agent_cli_text(
        image_paths=image_paths,
        prompt=prompt,
        task_name=f"drawai.element_analysis.agent_cli.{agent}.v1",
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=case_dir,
    )
    if not output_path.exists():
        raise RuntimeError(f"Agent CLI element analysis did not write required output: {output_path}")
    review_path = output_dir / "agent_cli_review.json"
    if preseeded and review_path.exists():
        analysis = read_json(output_path)
        review = read_json(review_path)
        analysis["agent_cli_review"] = review
        if isinstance(review, Mapping) and review.get("strategy_summary"):
            analysis["strategy_summary"] = str(review["strategy_summary"])
        write_json(output_path, analysis)
    duration_ms = int((time.monotonic() - started_at) * 1000)
    trace = {
        "schema": "drawai.agent_cli_element_analysis_trace.v1",
        "invoker": "agent_cli",
        "agent": agent,
        "case_dir": str(case_dir),
        "model_name": model_name or f"{agent}-cli-default",
        "timeout_seconds": timeout_seconds,
        "image_paths": [str(path) for path in image_paths],
        "duration_ms": duration_ms,
        "output_path": str(output_path),
        "preseeded_baseline": preseeded,
        "review_path": str(review_path) if review_path.exists() else None,
        "final_message_excerpt": final_message[:2000],
    }
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "invoker": "agent_cli",
        "agent": agent,
        "model_name": model_name or f"{agent}-cli-default",
        "duration_ms": duration_ms,
        "output_path": str(output_path),
    }


def invoke_acp_agent_element_analysis(
    *,
    case_dir: Path,
    prompt: str,
    image_paths: Sequence[Path],
    output_dir: Path,
    trace_path: Path,
    model_name: str,
    timeout_seconds: float,
    agent: str,
    command: Sequence[str],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "element_analysis.json"
    request_path = output_dir / "element_analysis_request.json"
    preseeded = False
    if request_path.exists():
        request = read_json(request_path)
        if isinstance(request.get("candidates"), list):
            write_json(output_path, build_baseline_analysis(case_dir, request, source="acp_agent_baseline_review"))
            preseeded = True
    started_at = time.monotonic()
    runtime_config = {
        "provider": "acp-agent",
        "connection_id": f"drawai-{agent}-acp-element-analysis",
        "model_name": model_name,
        "timeout_seconds": timeout_seconds,
        "acp": {
            "agent": agent,
            "command": list(command),
        },
    }
    final_message = invoke_acp_agent_text(
        image_paths=image_paths,
        prompt=prompt,
        task_name=f"drawai.element_analysis.acp_agent.{agent}.v1",
        runtime_config=runtime_config,
        trace_path=trace_path,
        isolated_cwd=case_dir,
        additional_roots=(REPO_ROOT,),
    )
    if not output_path.exists():
        raise RuntimeError(f"ACP agent element analysis did not write required output: {output_path}")
    review_path = output_dir / "acp_agent_review.json"
    if preseeded and review_path.exists():
        analysis = read_json(output_path)
        review = read_json(review_path)
        analysis["acp_agent_review"] = review
        if isinstance(review, Mapping) and review.get("strategy_summary"):
            analysis["strategy_summary"] = str(review["strategy_summary"])
        write_json(output_path, analysis)
    duration_ms = int((time.monotonic() - started_at) * 1000)
    trace = {
        "schema": "drawai.acp_agent_element_analysis_trace.v1",
        "invoker": "acp_agent",
        "agent": agent,
        "case_dir": str(case_dir),
        "model_name": model_name or f"{agent}-acp-default",
        "timeout_seconds": timeout_seconds,
        "image_paths": [str(path) for path in image_paths],
        "duration_ms": duration_ms,
        "output_path": str(output_path),
        "preseeded_baseline": preseeded,
        "review_path": str(review_path) if review_path.exists() else None,
        "final_message_excerpt": final_message[:2000],
    }
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "invoker": "acp_agent",
        "agent": agent,
        "model_name": model_name or f"{agent}-acp-default",
        "duration_ms": duration_ms,
        "output_path": str(output_path),
    }


def build_agent_cli_review_prompt(case_dir: Path, request_path: Path, candidate_table_path: Path, output_path: Path) -> str:
    review_path = output_path.with_name("agent_cli_review.json")
    return f"""DrawAI agent CLI lightweight run0 asset review.

Workspace/case root:
{case_dir}

Python has already generated a complete baseline element analysis at:
{output_path.relative_to(case_dir)}

Your job is to inspect the attached original image and asset-plan overlay, then write only a concise review JSON. Do not regenerate the full element list, do not run visualization scripts, and do not print large JSON files.

Read these compact files only if needed:
- Candidate table: {candidate_table_path.relative_to(case_dir)}
- Baseline element analysis: {output_path.relative_to(case_dir)}
- Machine-readable request, only for exact bbox checks: {request_path.relative_to(case_dir)}

Write UTF-8 JSON to:
{review_path.relative_to(case_dir)}

The review JSON must have this shape:
{{
  "schema": "drawai.agent_cli_element_analysis_review.v1",
  "status": "ok",
  "strategy_summary": "short summary of whether the baseline asset source decisions are reasonable",
  "notable_adjustments": [
    {{"box_id": "B001", "suggestion": "optional short suggestion"}}
  ],
  "notes": []
}}

Keep the final chat response to one short sentence. The preseeded element_analysis.json remains the source of truth for this run.
"""


def build_acp_agent_review_prompt(case_dir: Path, request_path: Path, candidate_table_path: Path, output_path: Path) -> str:
    review_path = output_path.with_name("acp_agent_review.json")
    return f"""DrawAI ACP agent lightweight run0 asset review.

Workspace/case root:
{case_dir}

Python has already generated a complete baseline element analysis at:
{output_path.relative_to(case_dir)}

Your job is to inspect the attached original image and asset-plan overlay, then write only a concise review JSON. Do not regenerate the full element list, do not run visualization scripts, and do not print large JSON files.

Read these compact files only if needed:
- Candidate table: {candidate_table_path.relative_to(case_dir)}
- Baseline element analysis: {output_path.relative_to(case_dir)}
- Machine-readable request, only for exact bbox checks: {request_path.relative_to(case_dir)}

Write UTF-8 JSON to:
{review_path.relative_to(case_dir)}

The review JSON must have this shape:
{{
  "schema": "drawai.acp_agent_element_analysis_review.v1",
  "status": "ok",
  "strategy_summary": "short summary of whether the baseline asset source decisions are reasonable",
  "notable_adjustments": [
    {{"box_id": "B001", "suggestion": "optional short suggestion"}}
  ],
  "notes": []
}}
"""


def build_baseline_analysis(case_dir: Path, request: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    elements: list[dict[str, Any]] = []
    categories = {"svg_self_draw": 0, "crop": 0, "crop_nobg": 0}
    for index, candidate in enumerate(request.get("candidates", []) or [], start=1):
        if not isinstance(candidate, Mapping):
            continue
        box_id = str(candidate.get("box_id") or f"B{index:03d}")
        category = _baseline_category(candidate.get("current_pipeline_method"))
        categories[category] += 1
        bbox = candidate.get("bbox")
        elements.append(
            {
                "box_id": box_id,
                "source_candidate_ids": [box_id],
                "refinement_action": "unchanged",
                "category": category,
                "confidence": "medium",
                "visual_role": str(candidate.get("type") or "element"),
                "reason": "Baseline source decision reused for Kimi CLI lightweight run0.",
                "evidence": ["candidate_table", "deterministic_asset_plan"],
                "bbox": bbox,
                "type": str(candidate.get("type") or "unknown"),
                "current_pipeline_method": category,
                "recommended_asset_source": "svg" if category == "svg_self_draw" else category,
            }
        )
    return {
        "schema": SCHEMA_OUTPUT,
        "case_dir": str(case_dir),
        "source": source,
        "strategy_summary": "Baseline element analysis generated from deterministic DrawAI asset decisions for Kimi CLI lightweight review.",
        "refinement_summary": "No model-driven split/merge refinement was required before Kimi CLI review.",
        "refinement_iterations": [],
        "categories": categories,
        "refinement_actions": {
            "unchanged": len(elements),
            "adjusted": 0,
            "split": 0,
            "added": 0,
        },
        "elements": elements,
        "notes": [],
    }


def _baseline_category(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"crop_nobg", "crop_no_bg", "transparent_subject", "remove_background", "rmbg"}:
        return "crop_nobg"
    if normalized in {"crop", "crop_asset", "preserve_crop", "direct_crop"}:
        return "crop"
    return "svg_self_draw"


def analysis_images(case_dir: Path) -> list[Path]:
    candidates = [
        case_dir / "inputs" / "figure.png",
        case_dir / "reports" / "assemble_debug" / "assets" / "08_asset_plan.png",
        case_dir / "reports" / "element_analysis_codex" / "mask_previews" / "mask_preview_sheet.png",
    ]
    preview_dir = case_dir / "reports" / "element_analysis_codex" / "mask_previews"
    if preview_dir.is_dir():
        candidates.extend(sorted(preview_dir.glob("*_mask_preview.png"))[:24])
    return [path for path in candidates if path.exists()]


def validate_analysis(analysis: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    if analysis.get("schema") != SCHEMA_OUTPUT:
        raise ValueError(f"Unexpected element analysis schema: {analysis.get('schema')!r}")
    elements = analysis.get("elements")
    if not isinstance(elements, list):
        raise ValueError("element_analysis.json must contain an elements list")
    expected = {str(item.get("box_id")) for item in request.get("candidates", []) if isinstance(item, Mapping)}
    seen_output_ids: list[str] = []
    covered_source_ids: set[str] = set()
    added_ids: list[str] = []
    retained_elements: list[Mapping[str, Any]] = []
    removal_count = 0
    action_counts: Counter[str] = Counter()

    def validate_source_record(record: Mapping[str, Any], box_id: str) -> list[str]:
        raw_source_ids = record.get("source_candidate_ids")
        if isinstance(raw_source_ids, list):
            source_ids = validate_source_id_list(
                raw_source_ids,
                f"{box_id} source_candidate_ids",
                allow_empty=True,
            )
        elif isinstance(record.get("removed_source_candidate_ids"), list):
            source_ids = validate_source_id_list(
                record.get("removed_source_candidate_ids", []),
                f"{box_id} removed_source_candidate_ids",
                allow_empty=True,
            )
        else:
            source_ids = [box_id] if box_id in expected else []
        unexpected_source_ids = sorted(source_id for source_id in source_ids if source_id not in expected)
        if unexpected_source_ids:
            raise ValueError(f"Unexpected source_candidate_ids for {box_id}: {unexpected_source_ids[:20]}")
        return source_ids

    def validate_removal_record(record: Mapping[str, Any], box_id: str, action: str) -> None:
        nonlocal removal_count
        reason = str(record.get("removal_reason") or record.get("reason") or "").strip()
        if not reason:
            raise ValueError(f"{box_id} removal record must contain a reason")
        source_ids = validate_source_record(record, box_id)
        if not source_ids:
            raise ValueError(f"{box_id} removal record must contain source_candidate_ids")
        covered_source_ids.update(source_ids)
        action_counts[action] += 1
        removal_count += 1

    for element in elements:
        if not isinstance(element, Mapping):
            raise ValueError("Every element analysis record must be an object")
        box_id = str(element.get("box_id") or "")
        if not box_id:
            raise ValueError("Every element analysis record must contain box_id")
        action = record_refinement_action(element) or "unchanged"
        if action not in REFINEMENT_ACTIONS:
            raise ValueError(f"Unexpected refinement_action for {box_id}: {action}")
        source_ids = validate_source_record(element, box_id)
        if action == "added" and source_ids:
            raise ValueError(f"{box_id} added element must not include source_candidate_ids")
        if is_removal_record(element):
            validate_removal_record(element, box_id, action)
            continue
        category = str(element.get("category") or "")
        if category not in CATEGORIES:
            raise ValueError(f"Unexpected category for {box_id}: {category}")
        bbox = normalize_bbox(element.get("bbox"), allow_line=True)
        if bbox is None:
            raise ValueError(f"Invalid bbox for {box_id}: {element.get('bbox')!r}")
        if source_ids:
            covered_source_ids.update(source_ids)
        elif action != "added":
            raise ValueError(f"{box_id} has no source_candidate_ids but refinement_action is {action!r}")
        if box_id not in expected:
            added_ids.append(box_id)
        seen_output_ids.append(box_id)
        action_counts[action] += 1
        retained_elements.append(element)
    for removal_record in top_level_removal_records(analysis):
        box_id = str(removal_record.get("box_id") or "")
        if not box_id:
            raise ValueError("Every removal record must contain box_id")
        action = record_refinement_action(removal_record)
        if action not in {"removed", "merged"}:
            raise ValueError(f"Unexpected refinement_action for {box_id}: {action}")
        validate_removal_record(removal_record, box_id, action)
    duplicates = sorted(box_id for box_id, count in Counter(seen_output_ids).items() if count > 1)
    missing = sorted(expected - covered_source_ids)
    if duplicates or missing:
        raise ValueError(f"Invalid element coverage. missing={missing[:20]} duplicates={duplicates[:20]}")
    category_counts = dict(Counter(str(item.get("category")) for item in retained_elements))
    return {
        "schema": "drawai.codex_element_analysis_validation.v1",
        "candidate_count": len(expected),
        "element_count": len(retained_elements),
        "added_element_count": len(added_ids),
        "removal_count": removal_count,
        "category_counts": {category: int(category_counts.get(category, 0)) for category in CATEGORIES},
        "refinement_action_counts": {action: int(action_counts.get(action, 0)) for action in REFINEMENT_ACTIONS},
    }


def validate_source_id_list(
    raw_source_ids: Sequence[Any],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not raw_source_ids and not allow_empty:
        raise ValueError(f"{field_name} must contain non-empty strings")
    source_ids: list[str] = []
    for source_id in raw_source_ids:
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(f"{field_name} must contain non-empty strings")
        source_ids.append(source_id)
    return source_ids


def write_v2_element_plans_export(
    output_dir: Path,
    analysis: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    expected_candidate_ids = {
        str(candidate.get("box_id"))
        for candidate in request.get("candidates", [])
        if isinstance(candidate, Mapping) and candidate.get("box_id")
    }
    locked_geometry_by_candidate = {
        str(candidate.get("box_id")): candidate["geometry"]
        for candidate in request.get("candidates", [])
        if (
            isinstance(candidate, Mapping)
            and candidate.get("box_id")
            and candidate.get("geometry_locked") is True
            and isinstance(candidate.get("geometry"), Mapping)
        )
    }
    refiner = CodexElementRefiner(RefineConfig())
    plans = refiner.convert_analysis(
        analysis,
        expected_candidate_ids=expected_candidate_ids,
        locked_geometry_by_candidate=locked_geometry_by_candidate,
    )
    removals = codex_analysis_to_v2_removal_records(analysis)
    payload = {
        "schema": REFINED_ELEMENT_PLANS_EXPORT_SCHEMA,
        "source_schema": analysis.get("schema"),
        "provider": refiner.config.provider,
        "validation": {
            "candidate_count": len(expected_candidate_ids),
            "element_count": len(plans),
            "removal_count": len(removals),
        },
        "elements": [plan.to_dict() for plan in plans],
        "removals": [
            {
                "action": removal["action"],
                "source_candidate_ids": list(removal["source_candidate_ids"]),
                "reason": removal["reason"],
            }
            for removal in removals
        ],
    }
    write_json(output_dir / "element_plans.v2.json", payload)
    return payload


def current_pipeline_method(
    decision: Mapping[str, Any],
    initial: Mapping[str, Any],
    policy: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> str:
    if decision.get("decision") != "crop_asset":
        return "svg_self_draw"
    if (
        manifest.get("active_variant") == "without_background"
        or manifest.get("nobg_svg_href")
        or policy.get("background_policy") in {"transparent_subject", "split_backplate"}
    ):
        return "crop_nobg"
    if manifest.get("restore_strategy") == "component_assets" or manifest.get("insertable_components"):
        return "crop"
    return "crop"


def overlapping_ocr(bbox: Any, ocr_boxes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    target = normalize_bbox(bbox)
    if target is None:
        return []
    hits = []
    for box in ocr_boxes:
        other = normalize_bbox(box.get("bbox"))
        if other is None:
            continue
        overlap = intersection_area(target, other)
        if overlap <= 0:
            continue
        other_area = area(other)
        if other_area <= 0 or overlap / other_area < 0.2:
            continue
        hits.append(
            {
                "id": box.get("id", ""),
                "text": box.get("text", ""),
                "confidence": box.get("confidence", None),
                "bbox": box.get("bbox"),
            }
        )
    return hits[:12]


def asset_hrefs(manifest: Mapping[str, Any]) -> dict[str, str]:
    keys = (
        "svg_href",
        "source_svg_href",
        "nobg_svg_href",
        "source_png_href",
        "nobg_png_href",
        "href",
    )
    return {key: str(manifest.get(key)) for key in keys if manifest.get(key)}


def compact_mapping(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        return {}
    keep = (
        "asset_id",
        "box_id",
        "decision",
        "role",
        "render_policy",
        "background_policy",
        "split_policy",
        "confidence",
        "reason_codes",
        "active_variant",
        "restore_strategy",
        "should_run_rmbg",
        "bbox",
        "current_label",
        "svg_href",
        "source_svg_href",
        "nobg_svg_href",
    )
    result = {key: record[key] for key in keep if key in record}
    metrics = record.get("metrics")
    if isinstance(metrics, Mapping):
        result["metrics_summary"] = {
            key: metrics[key]
            for key in (
                "crop_width",
                "crop_height",
                "foreground_ratio",
                "edge_density",
                "thin_line_score",
                "color_complexity",
                "texture_score",
                "simple_geometry_score",
                "connected_component_count",
                "foreground_touches_sides",
            )
            if key in metrics
        }
    return result


def records_by_key(records: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        return {}
    result = {}
    for record in records:
        if isinstance(record, Mapping) and isinstance(record.get(key), str):
            result[str(record[key])] = dict(record)
    return result


def normalize_bbox(raw: Any, *, allow_line: bool = False) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    x1, y1, x2, y2 = [float(item) for item in raw]
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    if allow_line:
        if right == left:
            left -= 0.5
            right += 0.5
        if bottom == top:
            top -= 0.5
            bottom += 0.5
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def intersection_area(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    return max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(0.0, min(left[3], right[3]) - max(left[1], right[1]))


def area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
