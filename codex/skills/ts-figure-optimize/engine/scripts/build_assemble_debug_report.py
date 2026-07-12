from __future__ import annotations

import argparse
import html
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.domain.box_ir.merge import (  # noqa: E402
    CROSS_TYPE_DUPLICATE_AREA_SIMILARITY_THRESHOLD,
    CROSS_TYPE_DUPLICATE_IOU_THRESHOLD,
    CROSS_TYPE_DUPLICATE_SMALLER_OVERLAP_THRESHOLD,
    SAME_TYPE_SMALLER_OVERLAP_AREA_SIMILARITY_THRESHOLD,
    _cluster_has_external_child,
    _duplicate_reason,
    _preserved_visual_asset_child,
    _select_cluster_representative,
)


TYPE_COLORS = {
    "arrow": "#e76f51",
    "border": "#6d6875",
    "content_box": "#2a9d8f",
    "grid": "#9b5de5",
    "icon": "#f4a261",
    "picture": "#457b9d",
    "symbol": "#f15bb5",
    "text": "#118ab2",
    "unknown": "#8d99ae",
    "ocr": "#d62828",
}

METHOD_COLORS = {
    "svg_self_draw": "#13a563",
    "crop": "#f59e0b",
    "crop_nobg": "#2563eb",
    "crop_component": "#9333ea",
    "imagegen": "#d946ef",
    "unknown": "#64748b",
}

CODEX_METHOD_LABELS = {
    "svg_self_draw": "SVG 自绘",
    "crop": "直接抠图",
    "crop_nobg": "抠图去背景",
    "imagegen": "ImageGen",
    "unknown": "未知",
}

CLUSTER_COLORS = [
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#3b82f6",
    "#8b5cf6",
    "#ec4899",
    "#06b6d4",
    "#84cc16",
]


@dataclass(frozen=True)
class ClusterReplay:
    clusters: list[list[int]]
    pair_decisions: list[dict[str, Any]]
    keep_samples: list[dict[str, Any]]
    merged_candidates: list[dict[str, Any]]
    preserved_children: list[dict[str, Any]]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    case_dirs = [Path(item).expanduser().resolve(strict=False) for item in args.case_dirs]
    outputs: list[Path] = []
    for case_dir in case_dirs:
        output_dir = Path(args.output_dir).expanduser().resolve(strict=False) if args.output_dir else case_dir / "reports" / "assemble_debug"
        if len(case_dirs) > 1 and args.output_dir:
            output_dir = output_dir / case_dir.name
        outputs.append(build_report(case_dir, output_dir=output_dir, max_boxes=args.max_boxes))
    for output in outputs:
        print(output)
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an interactive DrawAI assemble/asset-plan debug report.")
    parser.add_argument("case_dirs", nargs="+", help="One or more DrawAI case output directories.")
    parser.add_argument("--output-dir", default="", help="Optional output directory. Defaults to CASE/reports/assemble_debug.")
    parser.add_argument("--max-boxes", type=int, default=600, help="Maximum boxes to render as interactive HTML overlays.")
    return parser.parse_args(argv)


def build_report(case_dir: Path, *, output_dir: Path, max_boxes: int) -> Path:
    paths = _case_paths(case_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    figure = Image.open(paths["figure"]).convert("RGB")
    width, height = figure.size
    raw_box_ir = _read_json(paths["raw_box_ir"])
    merged_box_ir = _read_json(paths["merged_box_ir"])
    final_box_ir = _read_json(paths["final_box_ir"])
    merge_trace = _read_json(paths["merge_trace"])
    raw_regions = _read_json(paths["raw_regions"], default=[])
    ocr_payload = _read_json(paths["ocr"], default={"ocr_text_boxes": []})
    initial_decisions = _read_json(paths["initial_asset_decisions"], default={"decisions": []})
    asset_decisions = _read_json(paths["asset_decisions"], default={"decisions": []})
    asset_policy = _read_json(paths["asset_policy_report"], default={"assets": []})
    asset_manifest = _read_json(paths["asset_manifest"], default={"assets": []})
    codex_element_analysis = _read_json(paths["codex_element_analysis"], default={})

    raw_boxes = _box_list(raw_box_ir.get("boxes"))
    merged_boxes = _box_list(merged_box_ir.get("boxes"))
    final_boxes = _box_list(final_box_ir.get("boxes"))
    ocr_boxes = _box_list(ocr_payload.get("ocr_text_boxes"))
    replay = _replay_merge(raw_boxes)
    asset_methods = _asset_methods(final_boxes, initial_decisions, asset_decisions, asset_policy, asset_manifest)
    codex_element_methods = _codex_element_methods(final_boxes, codex_element_analysis)

    static_images = {
        "01_raw_sam_all": _save_overlay(
            figure,
            assets_dir / "01_raw_sam_all.png",
            [_overlay_box(box, TYPE_COLORS.get(str(box.get("type")), TYPE_COLORS["unknown"]), _box_label(box)) for box in raw_boxes],
            title="Raw SAM boxes after normalization",
        ),
        "02_duplicate_pairs": _save_duplicate_pairs(figure, assets_dir / "02_duplicate_pairs.png", raw_boxes, replay.pair_decisions),
        "03_merge_clusters": _save_cluster_overlay(figure, assets_dir / "03_merge_clusters.png", raw_boxes, replay),
        "04_merged_sam": _save_overlay(
            figure,
            assets_dir / "04_merged_sam.png",
            [_overlay_box(box, TYPE_COLORS.get(str(box.get("type")), TYPE_COLORS["unknown"]), _box_label(box)) for box in merged_boxes],
            title="Merged SAM structure boxes",
        ),
        "05_containment": _save_containment(figure, assets_dir / "05_containment.png", merged_boxes),
        "06_ocr": _save_overlay(
            figure,
            assets_dir / "06_ocr.png",
            [_overlay_box(box, TYPE_COLORS["ocr"], _ocr_label(box)) for box in ocr_boxes],
            title="OCR boxes",
        ),
        "07_final_boxir_plus_ocr": _save_final_overlay(figure, assets_dir / "07_final_boxir_plus_ocr.png", final_boxes, ocr_boxes),
        "08_asset_plan": _save_asset_plan_overlay(figure, assets_dir / "08_asset_plan.png", final_boxes, asset_methods),
    }
    if codex_element_methods:
        static_images["09_codex_element_distribution"] = _save_codex_element_overlay(
            figure,
            assets_dir / "09_codex_element_distribution.png",
            codex_element_methods,
        )

    copied_figure = assets_dir / "figure.png"
    figure.save(copied_figure)

    manifest = {
        "schema": "drawai.assemble_debug_report.v1",
        "case_dir": str(case_dir),
        "output_dir": str(output_dir),
        "canvas": {"width": width, "height": height},
        "counts": _counts(
            raw_regions,
            raw_boxes,
            merged_boxes,
            final_boxes,
            ocr_boxes,
            replay,
            asset_methods,
            codex_element_methods,
        ),
        "images": static_images,
        "asset_methods": asset_methods,
        "codex_element_methods": codex_element_methods,
        "merge_replay": {
            "pair_decision_count": len(replay.pair_decisions),
            "cluster_count": len(replay.clusters),
            "merged_cluster_count": sum(1 for cluster in replay.clusters if len(cluster) > 1),
            "preserved_visual_child_count": len(replay.preserved_children),
        },
    }
    _write_json(output_dir / "assemble_debug_manifest.json", manifest)

    html_path = output_dir / "assemble_debug_report.html"
    html_path.write_text(
        _html_report(
            case_dir=case_dir,
            width=width,
            height=height,
            figure_rel="assets/figure.png",
            static_images=static_images,
            raw_regions=raw_regions,
            raw_boxes=raw_boxes,
            merged_boxes=merged_boxes,
            final_boxes=final_boxes,
            ocr_boxes=ocr_boxes,
            replay=replay,
            merge_trace=merge_trace,
            asset_methods=asset_methods,
            codex_element_analysis=codex_element_analysis,
            codex_element_methods=codex_element_methods,
            asset_policy=asset_policy,
            asset_manifest=asset_manifest,
            max_boxes=max_boxes,
        ),
        encoding="utf-8",
    )
    return html_path


def _case_paths(case_dir: Path) -> dict[str, Path]:
    paths = {
        "figure": case_dir / "inputs" / "figure.png",
        "raw_regions": case_dir / "sam3" / "raw_regions.json",
        "ocr": case_dir / "ocr" / "ocr_boxes.json",
        "raw_box_ir": case_dir / "box_ir" / "box_ir.raw.json",
        "merged_box_ir": case_dir / "box_ir" / "box_ir.merged.json",
        "final_box_ir": case_dir / "box_ir" / "box_ir.json",
        "merge_trace": case_dir / "box_ir" / "merge_trace.json",
        "initial_asset_decisions": case_dir / "svg_to_ppt" / "assets" / "initial_asset_decisions.json",
        "asset_decisions": case_dir / "svg_to_ppt" / "assets" / "asset_decisions.json",
        "asset_policy_report": case_dir / "svg_to_ppt" / "assets" / "asset_policy_report.json",
        "asset_manifest": case_dir / "svg_to_ppt" / "assets" / "asset_manifest.json",
        "codex_element_analysis": case_dir / "reports" / "element_analysis_codex" / "element_analysis.json",
    }
    missing = [str(path) for key, path in paths.items() if key in {"figure", "raw_box_ir", "merged_box_ir", "final_box_ir"} and not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required assemble artifacts:\n" + "\n".join(missing))
    return paths


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _box_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping) and _bbox(item.get("bbox")) is not None]


def _bbox(raw: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(item) for item in raw]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in (x1, y1, x2, y2)):
        return None
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _replay_merge(raw_boxes: list[dict[str, Any]]) -> ClusterReplay:
    parents = list(range(len(raw_boxes)))
    pair_decisions: list[dict[str, Any]] = []
    keep_samples: list[dict[str, Any]] = []
    for left_index in range(len(raw_boxes)):
        for right_index in range(left_index + 1, len(raw_boxes)):
            reason = _duplicate_reason(raw_boxes[left_index], raw_boxes[right_index], 0.85, 0.92)
            if reason is not None:
                _union(parents, left_index, right_index)
                pair_decisions.append(
                    {
                        "left_index": left_index,
                        "right_index": right_index,
                        "box_ids": [_box_id(raw_boxes[left_index], left_index), _box_id(raw_boxes[right_index], right_index)],
                        "reason": reason,
                        "metrics": _overlap_metrics(raw_boxes[left_index], raw_boxes[right_index]),
                    }
                )
            elif len(keep_samples) < 12:
                keep_samples.append(
                    {
                        "left_index": left_index,
                        "right_index": right_index,
                        "box_ids": [_box_id(raw_boxes[left_index], left_index), _box_id(raw_boxes[right_index], right_index)],
                        "reason": "different_type" if raw_boxes[left_index].get("type") != raw_boxes[right_index].get("type") else "overlap_below_duplicate_threshold",
                    }
                )
    cluster_by_root: dict[int, list[int]] = {}
    for index in range(len(raw_boxes)):
        cluster_by_root.setdefault(_find(parents, index), []).append(index)
    clusters = list(cluster_by_root.values())
    merged_candidates: list[dict[str, Any]] = []
    preserved_children: list[dict[str, Any]] = []
    for cluster in clusters:
        boxes = [raw_boxes[index] for index in cluster]
        representative = _select_cluster_representative(boxes, cluster, raw_boxes)
        bbox = [
            min(_bbox(box["bbox"])[0] for box in boxes if _bbox(box.get("bbox"))),
            min(_bbox(box["bbox"])[1] for box in boxes if _bbox(box.get("bbox"))),
            max(_bbox(box["bbox"])[2] for box in boxes if _bbox(box.get("bbox"))),
            max(_bbox(box["bbox"])[3] for box in boxes if _bbox(box.get("bbox"))),
        ]
        merged = {
            "type": representative.get("type", "unknown"),
            "bbox": bbox,
            "source_box_ids": [_box_id(raw_boxes[index], index) for index in cluster],
            "cluster_indexes": list(cluster),
            "has_external_child": _cluster_has_external_child(cluster, raw_boxes),
        }
        merged_candidates.append(merged)
        visual_child = _preserved_visual_asset_child(raw_boxes, cluster, merged)
        if visual_child is not None:
            visual_child["cluster_indexes"] = list(cluster)
            preserved_children.append(visual_child)
    return ClusterReplay(
        clusters=clusters,
        pair_decisions=pair_decisions,
        keep_samples=keep_samples,
        merged_candidates=merged_candidates,
        preserved_children=preserved_children,
    )


def _find(parents: list[int], index: int) -> int:
    while parents[index] != index:
        parents[index] = parents[parents[index]]
        index = parents[index]
    return index


def _union(parents: list[int], left: int, right: int) -> None:
    left_root = _find(parents, left)
    right_root = _find(parents, right)
    if left_root != right_root:
        parents[right_root] = left_root


def _box_id(box: Mapping[str, Any], fallback_index: int) -> str:
    raw_id = box.get("id")
    return raw_id if isinstance(raw_id, str) and raw_id else f"B{fallback_index + 1:03d}"


def _overlap_metrics(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, float]:
    left_bbox = _bbox(left.get("bbox"))
    right_bbox = _bbox(right.get("bbox"))
    if left_bbox is None or right_bbox is None:
        return {}
    intersection = _intersection(left_bbox, right_bbox)
    left_area = _area(left_bbox)
    right_area = _area(right_bbox)
    if intersection <= 0 or left_area <= 0 or right_area <= 0:
        return {"iou": 0.0, "smaller_overlap": 0.0, "area_similarity": 0.0}
    union = left_area + right_area - intersection
    return {
        "iou": round(intersection / union if union else 0.0, 4),
        "smaller_overlap": round(intersection / min(left_area, right_area), 4),
        "area_similarity": round(min(left_area, right_area) / max(left_area, right_area), 4),
    }


def _intersection(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> float:
    return max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(0.0, min(left[3], right[3]) - max(left[1], right[1]))


def _area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _asset_methods(
    boxes: list[dict[str, Any]],
    initial_decisions: Mapping[str, Any],
    asset_decisions: Mapping[str, Any],
    asset_policy: Mapping[str, Any],
    asset_manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    initial_by_box = _records_by_key(initial_decisions.get("decisions"), "box_id")
    decision_by_box = _records_by_key(asset_decisions.get("decisions"), "box_id")
    policy_by_asset = _records_by_key(asset_policy.get("assets"), "asset_id")
    manifest_by_asset = _records_by_key(asset_manifest.get("assets"), "asset_id")
    result: dict[str, dict[str, Any]] = {}
    for box in boxes:
        box_id = str(box.get("id") or "")
        decision = decision_by_box.get(box_id, {})
        initial = initial_by_box.get(box_id, {})
        asset_id = str(decision.get("asset_id") or initial.get("asset_id") or decision.get("recovered_asset_id") or "")
        policy = policy_by_asset.get(asset_id, {})
        manifest = manifest_by_asset.get(asset_id, {})
        method = "svg_self_draw"
        label = "SVG 自绘"
        detail = "最终 asset decision 是 native_svg，进入 Codex 后由 SVG primitives/text 绘制。"
        if decision.get("decision") == "crop_asset":
            if manifest.get("restore_strategy") == "component_assets" or manifest.get("insertable_components"):
                method = "crop_component"
                label = "抠图组件"
                detail = "该区域保留为组件化 raster asset；Codex 只能按 manifest 引用组件。"
            elif (
                manifest.get("active_variant") == "without_background"
                or manifest.get("nobg_svg_href")
                or policy.get("background_policy") in {"transparent_subject", "split_backplate"}
            ):
                method = "crop_nobg"
                label = "抠图去背景"
                detail = "该区域裁剪后使用 RMBG/透明主体版本，最终 SVG 引用去背景 PNG。"
            else:
                method = "crop"
                label = "直接抠图"
                detail = "该区域保留原始 crop PNG，最终 SVG 引用带背景 raster asset。"
        elif initial.get("decision") == "crop_asset" and decision.get("decision") == "native_svg":
            detail = "初始是 crop_asset，但 asset policy 判定为可恢复，因此改为 SVG 自绘。"
        result[box_id] = {
            "method": method,
            "label": label,
            "detail": detail,
            "asset_id": asset_id,
            "decision": decision,
            "initial_decision": initial,
            "policy": policy,
            "manifest": manifest,
        }
    return result


def _codex_element_methods(
    boxes: list[dict[str, Any]],
    codex_element_analysis: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    elements = codex_element_analysis.get("elements")
    if not isinstance(elements, list):
        return {}
    boxes_by_id = {str(box.get("id") or ""): box for box in boxes}
    result: dict[str, dict[str, Any]] = {}
    for element in elements:
        if not isinstance(element, Mapping):
            continue
        box_id = str(element.get("box_id") or element.get("element_id") or element.get("id") or "")
        if not box_id:
            continue
        fallback_box = boxes_by_id.get(box_id)
        bbox = _codex_bbox(element.get("bbox"))
        if bbox is None and fallback_box is not None:
            bbox = _bbox(fallback_box.get("bbox"))
        if bbox is None:
            continue
        method = _normalize_codex_category(element.get("category") or element.get("class") or element.get("method"))
        source_candidate_ids = element.get("source_candidate_ids")
        if not isinstance(source_candidate_ids, list):
            source_candidate_ids = [box_id] if box_id in boxes_by_id else []
        source_candidate_ids = [str(item) for item in source_candidate_ids if str(item)]
        element_type = str(element.get("type") or (fallback_box or {}).get("type") or "")
        result[box_id] = {
            "id": box_id,
            "bbox": list(bbox),
            "type": element_type,
            "method": method,
            "label": CODEX_METHOD_LABELS.get(method, CODEX_METHOD_LABELS["unknown"]),
            "detail": str(element.get("reason") or element.get("detail") or element.get("explanation") or ""),
            "confidence": str(element.get("confidence") or ""),
            "visual_role": str(element.get("visual_role") or element.get("role") or ""),
            "recommended_asset_source": str(element.get("recommended_asset_source") or ""),
            "source_candidate_ids": source_candidate_ids,
            "refinement_action": str(element.get("refinement_action") or "unchanged"),
            "evidence": element.get("evidence") if isinstance(element.get("evidence"), list) else [],
            "raw": dict(element),
        }
    return result


def _codex_element_boxes(codex_element_methods: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    for box_id, method in codex_element_methods.items():
        bbox = _codex_bbox(method.get("bbox"))
        if bbox is None:
            continue
        boxes.append(
            {
                "id": str(method.get("id") or box_id),
                "type": str(method.get("type") or ""),
                "bbox": list(bbox),
                "codex_method": method,
            }
        )
    return boxes


def _normalize_codex_category(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "native_svg": "svg_self_draw",
        "svg": "svg_self_draw",
        "svg_direct": "svg_self_draw",
        "self_draw": "svg_self_draw",
        "crop_asset": "crop",
        "direct_crop": "crop",
        "preserve_crop": "crop",
        "crop_no_bg": "crop_nobg",
        "crop_without_background": "crop_nobg",
        "without_background": "crop_nobg",
        "remove_background": "crop_nobg",
        "rmbg": "crop_nobg",
        "image_gen": "imagegen",
        "image_generation": "imagegen",
        "generated_image": "imagegen",
    }
    text = aliases.get(text, text)
    return text if text in CODEX_METHOD_LABELS else "unknown"


def _records_by_key(records: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if isinstance(record, Mapping) and isinstance(record.get(key), str):
            result[str(record[key])] = dict(record)
    return result


def _save_overlay(image: Image.Image, path: Path, boxes: list[dict[str, Any]], *, title: str) -> str:
    canvas = image.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(18)
    for box in boxes:
        _draw_box(draw, box["bbox"], box["color"], box.get("label", ""), font=font)
    canvas = Image.alpha_composite(canvas, overlay)
    _draw_title(canvas, title)
    canvas.convert("RGB").save(path)
    return path.name if path.parent.name != "assets" else f"assets/{path.name}"


def _save_duplicate_pairs(image: Image.Image, path: Path, raw_boxes: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> str:
    canvas = image.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(16)
    shown_indexes: set[int] = set()
    for decision in decisions:
        left = raw_boxes[decision["left_index"]]
        right = raw_boxes[decision["right_index"]]
        shown_indexes.update((decision["left_index"], decision["right_index"]))
        left_center = _center(_bbox(left["bbox"]))
        right_center = _center(_bbox(right["bbox"]))
        draw.line([left_center, right_center], fill=(255, 255, 255, 170), width=3)
    for index in sorted(shown_indexes):
        box = raw_boxes[index]
        color = TYPE_COLORS.get(str(box.get("type")), TYPE_COLORS["unknown"])
        _draw_box(draw, _bbox(box["bbox"]), color, _box_label(box), font=font)
    canvas = Image.alpha_composite(canvas, overlay)
    _draw_title(canvas, f"Duplicate pair decisions: {len(decisions)}")
    canvas.convert("RGB").save(path)
    return f"assets/{path.name}"


def _save_cluster_overlay(image: Image.Image, path: Path, raw_boxes: list[dict[str, Any]], replay: ClusterReplay) -> str:
    canvas = image.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(16)
    for cluster_index, cluster in enumerate(replay.clusters):
        color = CLUSTER_COLORS[cluster_index % len(CLUSTER_COLORS)]
        for index in cluster:
            box = raw_boxes[index]
            _draw_box(draw, _bbox(box["bbox"]), color, _box_label(box), font=font, width=3, fill_alpha=32)
    canvas = Image.alpha_composite(canvas, overlay)
    _draw_title(canvas, f"Merge clusters: {len(replay.clusters)} total, {sum(1 for c in replay.clusters if len(c) > 1)} merged")
    canvas.convert("RGB").save(path)
    return f"assets/{path.name}"


def _save_containment(image: Image.Image, path: Path, boxes: list[dict[str, Any]]) -> str:
    canvas = image.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(16)
    by_id = {box.get("id"): box for box in boxes}
    for box in boxes:
        color = TYPE_COLORS.get(str(box.get("type")), TYPE_COLORS["unknown"])
        _draw_box(draw, _bbox(box["bbox"]), color, _box_label(box), font=font, width=3)
    for box in boxes:
        child_ids = box.get("child_ids") if isinstance(box.get("child_ids"), list) else []
        for child_id in child_ids:
            child = by_id.get(child_id)
            if child is None:
                continue
            draw.line([_center(_bbox(box["bbox"])), _center(_bbox(child["bbox"]))], fill=(255, 255, 255, 180), width=2)
    canvas = Image.alpha_composite(canvas, overlay)
    _draw_title(canvas, "Containment relations: parent -> child")
    canvas.convert("RGB").save(path)
    return f"assets/{path.name}"


def _save_final_overlay(image: Image.Image, path: Path, boxes: list[dict[str, Any]], ocr_boxes: list[dict[str, Any]]) -> str:
    overlays = [_overlay_box(box, TYPE_COLORS.get(str(box.get("type")), TYPE_COLORS["unknown"]), _box_label(box)) for box in boxes]
    overlays.extend(_overlay_box(box, TYPE_COLORS["ocr"], _ocr_label(box)) for box in ocr_boxes)
    return _save_overlay(image, path, overlays, title="final layout IR: merged SAM structure + OCR text layer")


def _save_asset_plan_overlay(image: Image.Image, path: Path, boxes: list[dict[str, Any]], asset_methods: Mapping[str, Mapping[str, Any]]) -> str:
    overlays: list[dict[str, Any]] = []
    for box in boxes:
        box_id = str(box.get("id") or "")
        method = asset_methods.get(box_id, {}).get("method", "unknown")
        color = METHOD_COLORS.get(str(method), METHOD_COLORS["unknown"])
        label = f"{box_id} {asset_methods.get(box_id, {}).get('label', method)}"
        overlays.append(_overlay_box(box, color, label))
    return _save_overlay(image, path, overlays, title="Asset plan before Codex: SVG self-draw vs crop assets")


def _save_codex_element_overlay(
    image: Image.Image,
    path: Path,
    codex_element_methods: Mapping[str, Mapping[str, Any]],
) -> str:
    overlays: list[dict[str, Any]] = []
    for box_id, record in codex_element_methods.items():
        method = record.get("method", "unknown")
        color = METHOD_COLORS.get(str(method), METHOD_COLORS["unknown"])
        label = f"{box_id} {record.get('label', method)}"
        overlays.append({"bbox": _codex_bbox(record.get("bbox")), "color": color, "label": label})
    return _save_overlay(image, path, overlays, title="Codex element source analysis: SVG / crop / no-bg / ImageGen")


def _overlay_box(box: Mapping[str, Any], color: str, label: str) -> dict[str, Any]:
    return {"bbox": _bbox(box.get("bbox")), "color": color, "label": label}


def _codex_bbox(raw: Any) -> tuple[float, float, float, float] | None:
    bbox = _bbox(raw)
    if bbox is not None:
        return bbox
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(item) for item in raw]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in (x1, y1, x2, y2)):
        return None
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    if right == left:
        left -= 0.5
        right += 0.5
    if bottom == top:
        top -= 0.5
        bottom += 0.5
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _draw_box(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[float, float, float, float] | None,
    color: str,
    label: str,
    *,
    font: ImageFont.ImageFont,
    width: int = 4,
    fill_alpha: int = 44,
) -> None:
    if bbox is None:
        return
    rgba = _hex_to_rgba(color, 235)
    fill = _hex_to_rgba(color, fill_alpha)
    xy = [int(round(item)) for item in bbox]
    draw.rectangle(xy, outline=rgba, width=width, fill=fill)
    if label:
        text_bbox = draw.textbbox((xy[0] + 3, xy[1] + 3), label, font=font)
        draw.rectangle([text_bbox[0] - 2, text_bbox[1] - 2, text_bbox[2] + 2, text_bbox[3] + 2], fill=(0, 0, 0, 170))
        draw.text((xy[0] + 3, xy[1] + 3), label, fill=(255, 255, 255, 255), font=font)


def _draw_title(image: Image.Image, title: str) -> None:
    draw = ImageDraw.Draw(image)
    font = _font(28)
    margin = 16
    bbox = draw.textbbox((margin, margin), title, font=font)
    draw.rectangle([bbox[0] - 8, bbox[1] - 8, bbox[2] + 8, bbox[3] + 8], fill=(0, 0, 0, 190))
    draw.text((margin, margin), title, fill=(255, 255, 255, 255), font=font)


def _hex_to_rgba(value: str, alpha: int) -> tuple[int, int, int, int]:
    value = value.strip().lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ):
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _box_label(box: Mapping[str, Any]) -> str:
    return f"{box.get('id', '')} {box.get('type', '')}".strip()


def _ocr_label(box: Mapping[str, Any]) -> str:
    text = str(box.get("text") or box.get("value") or "").strip()
    if len(text) > 10:
        text = text[:10] + "..."
    return f"OCR {text}".strip()


def _center(bbox: tuple[float, float, float, float] | None) -> tuple[int, int]:
    if bbox is None:
        return 0, 0
    return int(round((bbox[0] + bbox[2]) / 2)), int(round((bbox[1] + bbox[3]) / 2))


def _counts(
    raw_regions: Any,
    raw_boxes: list[dict[str, Any]],
    merged_boxes: list[dict[str, Any]],
    final_boxes: list[dict[str, Any]],
    ocr_boxes: list[dict[str, Any]],
    replay: ClusterReplay,
    asset_methods: Mapping[str, Mapping[str, Any]],
    codex_element_methods: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    method_counts = Counter(str(item.get("method", "unknown")) for item in asset_methods.values())
    codex_method_counts = Counter(
        str(item.get("method", "unknown")) for item in (codex_element_methods or {}).values()
    )
    codex_refinement_counts = Counter(
        str(item.get("refinement_action", "unknown")) for item in (codex_element_methods or {}).values()
    )
    raw_region_count = len(raw_regions) if isinstance(raw_regions, list) else 0
    return {
        "raw_regions": raw_region_count,
        "raw_sam_boxes": len(raw_boxes),
        "dropped_raw_regions": max(0, raw_region_count - len(raw_boxes)),
        "duplicate_pairs": len(replay.pair_decisions),
        "merge_clusters": len(replay.clusters),
        "merged_clusters": sum(1 for cluster in replay.clusters if len(cluster) > 1),
        "merged_sam_boxes": len(merged_boxes),
        "final_structure_boxes": len(final_boxes),
        "ocr_boxes": len(ocr_boxes),
        "preserved_visual_children": len(replay.preserved_children),
        "asset_method_counts": dict(sorted(method_counts.items())),
        "codex_element_count": len(codex_element_methods or {}),
        "codex_element_method_counts": dict(sorted(codex_method_counts.items())),
        "codex_refinement_action_counts": dict(sorted(codex_refinement_counts.items())),
    }


def _html_report(
    *,
    case_dir: Path,
    width: int,
    height: int,
    figure_rel: str,
    static_images: Mapping[str, str],
    raw_regions: Any,
    raw_boxes: list[dict[str, Any]],
    merged_boxes: list[dict[str, Any]],
    final_boxes: list[dict[str, Any]],
    ocr_boxes: list[dict[str, Any]],
    replay: ClusterReplay,
    merge_trace: Mapping[str, Any],
    asset_methods: Mapping[str, Mapping[str, Any]],
    codex_element_analysis: Mapping[str, Any],
    codex_element_methods: Mapping[str, Mapping[str, Any]],
    asset_policy: Mapping[str, Any],
    asset_manifest: Mapping[str, Any],
    max_boxes: int,
) -> str:
    counts = _counts(
        raw_regions,
        raw_boxes,
        merged_boxes,
        final_boxes,
        ocr_boxes,
        replay,
        asset_methods,
        codex_element_methods,
    )
    method_counts = counts["asset_method_counts"]
    codex_method_counts = counts["codex_element_method_counts"]
    codex_refinement_counts = counts["codex_refinement_action_counts"]
    codex_boxes = _codex_element_boxes(codex_element_methods)
    duplicate_rows = "\n".join(_duplicate_row(item) for item in replay.pair_decisions[:300])
    cluster_rows = "\n".join(_cluster_row(index, cluster, raw_boxes, replay) for index, cluster in enumerate(replay.clusters, start=1))
    policy_rows = "\n".join(_asset_policy_row(item) for item in asset_policy.get("assets", []) if isinstance(item, Mapping))
    manifest_rows = "\n".join(_asset_manifest_row(item) for item in asset_manifest.get("assets", []) if isinstance(item, Mapping))
    codex_rows = "\n".join(_codex_element_row(record) for record in codex_element_methods.values())
    interactive_layers = {
        "raw": _interactive_boxes(raw_boxes[:max_boxes], width, height, lambda box: TYPE_COLORS.get(str(box.get("type")), TYPE_COLORS["unknown"]), _raw_tooltip),
        "merged": _interactive_boxes(merged_boxes[:max_boxes], width, height, lambda box: TYPE_COLORS.get(str(box.get("type")), TYPE_COLORS["unknown"]), _merged_tooltip),
        "ocr": _interactive_boxes(ocr_boxes[:max_boxes], width, height, lambda _box: TYPE_COLORS["ocr"], _ocr_tooltip),
        "asset": _interactive_boxes(
            final_boxes[:max_boxes],
            width,
            height,
            lambda box: METHOD_COLORS.get(str(asset_methods.get(str(box.get("id") or ""), {}).get("method", "unknown")), METHOD_COLORS["unknown"]),
            lambda box: _asset_tooltip(box, asset_methods.get(str(box.get("id") or ""), {})),
            labeler=lambda box: str(asset_methods.get(str(box.get("id") or ""), {}).get("label") or box.get("id") or ""),
        ),
    }
    if codex_element_methods:
        interactive_layers["codex"] = _interactive_boxes(
            codex_boxes[:max_boxes],
            width,
            height,
            lambda box: METHOD_COLORS.get(str(box.get("codex_method", {}).get("method", "unknown")), METHOD_COLORS["unknown"]),
            lambda box: _codex_element_tooltip(box, box.get("codex_method", {})),
            labeler=lambda box: f"{box.get('id', '')} {box.get('codex_method', {}).get('label', '')}".strip(),
        )
    codex_stats = ""
    if codex_element_methods:
        codex_stats = (
            f'{_stat("Codex refined elements", counts.get("codex_element_count", 0))}'
            f'{_stat("Codex SVG 自绘", codex_method_counts.get("svg_self_draw", 0))}'
            f'{_stat("Codex 直接抠图", codex_method_counts.get("crop", 0))}'
            f'{_stat("Codex 抠图去背景", codex_method_counts.get("crop_nobg", 0))}'
            f'{_stat("Codex ImageGen", codex_method_counts.get("imagegen", 0))}'
            f'{_stat("Codex split", codex_refinement_counts.get("split", 0))}'
            f'{_stat("Codex added", codex_refinement_counts.get("added", 0))}'
        )
    codex_tab = '<button data-layer="codex">Codex analysis</button>' if codex_element_methods else ""
    codex_layer = _layer("codex", figure_rel, interactive_layers.get("codex", "")) if codex_element_methods else ""
    codex_details = ""
    if codex_element_methods:
        codex_details = f"""
  <details open>
    <summary>Codex 元素来源分析</summary>
    <p>{html.escape(str(codex_element_analysis.get("strategy_summary") or "Codex 读取 SAM/OCR/layout IR/asset plan 后，先 refine candidates，再判断每个 refined element 的最终来源策略。"))}</p>
    <table><thead><tr><th>element</th><th>source candidates</th><th>refine</th><th>type</th><th>Codex 分类</th><th>confidence</th><th>role</th><th>current method</th><th>reason</th></tr></thead><tbody>{codex_rows}</tbody></table>
  </details>
"""
    image_sections = "\n".join(
        f'<figure><figcaption>{html.escape(_image_caption(name))}</figcaption><img src="{html.escape(src)}" alt="{html.escape(name)}"></figure>'
        for name, src in static_images.items()
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DrawAI Assemble Debug Report</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; color:#17202a; background:#f6f7f9; }}
header {{ padding:24px 28px; background:#fff; border-bottom:1px solid #d0d5dd; position:sticky; top:0; z-index:5; }}
h1 {{ margin:0 0 8px; font-size:24px; letter-spacing:0; }}
p {{ line-height:1.55; }}
main {{ max-width:1500px; margin:0 auto; padding:22px; }}
.path {{ color:#667085; overflow-wrap:anywhere; font-size:13px; }}
.summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin:16px 0; }}
.stat {{ background:#fff; border:1px solid #d0d5dd; border-radius:8px; padding:12px; }}
.stat b {{ display:block; font-size:22px; }}
section {{ background:#fff; border:1px solid #d0d5dd; border-radius:8px; padding:16px; margin:16px 0; }}
h2 {{ margin:0 0 10px; font-size:18px; }}
.steps {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:10px; }}
.step {{ border:1px solid #e4e7ec; border-radius:8px; padding:12px; background:#fcfcfd; }}
.step strong {{ display:block; margin-bottom:4px; }}
.gallery {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(460px,1fr)); gap:14px; }}
figure {{ margin:0; border:1px solid #d0d5dd; border-radius:8px; background:#fff; overflow:hidden; }}
figcaption {{ padding:8px 10px; font-size:13px; color:#475467; background:#f9fafb; border-bottom:1px solid #d0d5dd; }}
img {{ display:block; width:100%; height:auto; background:#fff; }}
.interactive-wrap {{ overflow:auto; border:1px solid #d0d5dd; border-radius:8px; background:#111827; padding:10px; }}
.stage-view {{ position:relative; width:min(100%, {width}px); min-width:min({width}px, 100%); margin:auto; }}
.stage-view > img {{ width:100%; height:auto; display:block; }}
.ibox {{ position:absolute; border:2px solid var(--c); background:color-mix(in srgb, var(--c) 16%, transparent); }}
.ibox .label {{ position:absolute; left:2px; top:2px; max-width:96%; padding:1px 4px; color:#fff; background:rgba(0,0,0,.70); font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.ibox:hover {{ z-index:10; border-width:3px; background:color-mix(in srgb, var(--c) 28%, transparent); }}
.ibox:hover::after {{ content:attr(data-tip); position:absolute; left:0; top:100%; width:max-content; max-width:360px; white-space:pre-wrap; padding:8px 10px; color:#fff; background:rgba(17,24,39,.96); border:1px solid #fff; border-radius:6px; font-size:12px; line-height:1.45; box-shadow:0 8px 24px rgba(0,0,0,.25); }}
.tabs {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }}
.tabs button {{ border:1px solid #d0d5dd; border-radius:6px; background:#fff; padding:7px 10px; cursor:pointer; }}
.tabs button.active {{ background:#17202a; color:#fff; border-color:#17202a; }}
.layer {{ display:none; }}
.layer.active {{ display:block; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ border-top:1px solid #e4e7ec; padding:7px 8px; text-align:left; vertical-align:top; }}
th {{ background:#f9fafb; color:#475467; }}
details {{ border:1px solid #d0d5dd; border-radius:8px; margin:10px 0; }}
summary {{ cursor:pointer; padding:10px 12px; font-weight:600; }}
.legend {{ display:flex; flex-wrap:wrap; gap:10px; margin:10px 0; }}
.legend span {{ display:inline-flex; align-items:center; gap:5px; font-size:13px; }}
.swatch {{ width:14px; height:14px; border-radius:3px; display:inline-block; }}
code {{ background:#f2f4f7; padding:1px 4px; border-radius:4px; }}
</style>
</head>
<body>
<header>
  <h1>DrawAI Assemble / Asset Plan Debug Report</h1>
  <div class="path">{html.escape(str(case_dir))}</div>
</header>
<main>
  <section>
    <h2>总览</h2>
    <div class="summary">
      {_stat("raw regions", counts["raw_regions"])}
      {_stat("raw SAM boxes", counts["raw_sam_boxes"])}
      {_stat("dropped regions", counts["dropped_raw_regions"])}
      {_stat("duplicate pairs", counts["duplicate_pairs"])}
      {_stat("merged clusters", counts["merged_clusters"])}
      {_stat("merged boxes", counts["merged_sam_boxes"])}
      {_stat("OCR boxes", counts["ocr_boxes"])}
      {_stat("SVG 自绘", method_counts.get("svg_self_draw", 0))}
      {_stat("直接抠图", method_counts.get("crop", 0))}
      {_stat("抠图去背景", method_counts.get("crop_nobg", 0))}
      {_stat("抠图组件", method_counts.get("crop_component", 0))}
      {codex_stats}
    </div>
  </section>

  <section>
    <h2>这一步实际发生了什么</h2>
    <div class="steps">
      <div class="step"><strong>1. SAM raw region 清洗</strong>读取 SAM 输出，解析 bbox，裁到画布内，丢掉无效框；然后按阅读顺序重排。</div>
      <div class="step"><strong>2. SAM-SAM 去重</strong>两两计算 IoU、smaller-overlap、面积相似度；达到阈值就 union 到同一个 duplicate cluster。</div>
      <div class="step"><strong>3. Cluster 合并</strong>每个 cluster 生成一个外接矩形，类型由代表框选择规则决定：容器上下文偏 content/grid，叶子上下文偏 arrow/picture/icon。</div>
      <div class="step"><strong>4. 视觉资产保护</strong>如果 content_box 吞掉内部 icon/picture，且该视觉资产足够独立，会额外保留为 child。</div>
      <div class="step"><strong>5. 包含关系</strong>根据完全包含关系建立 parent/child；这一步不是去重，只是补层级。</div>
      <div class="step"><strong>6. OCR 挂载</strong>OCR 框只做边界裁剪和无效过滤；当前不参与 SAM merge，而是作为文字层进入最终 layout IR。</div>
      <div class="step"><strong>7. Asset plan</strong>根据 final boxes 决定 Codex 前的处理方式：SVG 自绘、直接抠图、抠图去背景、组件化抠图。</div>
    </div>
  </section>

  <section>
    <h2>可交互查看</h2>
    <div class="legend">
      {_legend(METHOD_COLORS["svg_self_draw"], "SVG 自绘")}
      {_legend(METHOD_COLORS["crop"], "直接抠图")}
      {_legend(METHOD_COLORS["crop_nobg"], "抠图去背景")}
      {_legend(METHOD_COLORS["crop_component"], "抠图组件")}
      {_legend(METHOD_COLORS["imagegen"], "ImageGen")}
      {_legend(TYPE_COLORS["ocr"], "OCR")}
    </div>
    <div class="tabs">
      <button class="active" data-layer="asset">Asset plan</button>
      {codex_tab}
      <button data-layer="raw">Raw SAM</button>
      <button data-layer="merged">Merged SAM</button>
      <button data-layer="ocr">OCR</button>
    </div>
    <div class="interactive-wrap">
      {_layer("asset", figure_rel, interactive_layers["asset"], active=True)}
      {codex_layer}
      {_layer("raw", figure_rel, interactive_layers["raw"])}
      {_layer("merged", figure_rel, interactive_layers["merged"])}
      {_layer("ocr", figure_rel, interactive_layers["ocr"])}
    </div>
  </section>

  <section>
    <h2>静态步骤图</h2>
    <div class="gallery">{image_sections}</div>
  </section>

  <section>
    <h2>Duplicate pair 决策</h2>
    <p>这里只展示前 300 条。判断阈值：同类 IoU ≥ 0.85；同类 smaller-overlap ≥ 0.92 且面积相似度 ≥ {SAME_TYPE_SMALLER_OVERLAP_AREA_SIMILARITY_THRESHOLD}; 跨类型 IoU ≥ {CROSS_TYPE_DUPLICATE_IOU_THRESHOLD} 或 smaller-overlap ≥ {CROSS_TYPE_DUPLICATE_SMALLER_OVERLAP_THRESHOLD} 且面积相似度 ≥ {CROSS_TYPE_DUPLICATE_AREA_SIMILARITY_THRESHOLD}。</p>
    <table><thead><tr><th>#</th><th>boxes</th><th>reason</th><th>metrics</th></tr></thead><tbody>{duplicate_rows}</tbody></table>
  </section>

  <section>
    <h2>Merge clusters</h2>
    <table><thead><tr><th>#</th><th>source boxes</th><th>selected type</th><th>context</th></tr></thead><tbody>{cluster_rows}</tbody></table>
  </section>

  <details>
    <summary>Asset policy 明细</summary>
    <table><thead><tr><th>asset</th><th>box</th><th>label</th><th>render</th><th>background</th><th>split</th><th>reasons</th></tr></thead><tbody>{policy_rows}</tbody></table>
  </details>

  <details>
    <summary>Materialized asset manifest</summary>
    <table><thead><tr><th>asset</th><th>box</th><th>variant</th><th>href</th><th>policy</th></tr></thead><tbody>{manifest_rows}</tbody></table>
  </details>

  {codex_details}

  <details>
    <summary>Merge trace 原始统计</summary>
    <pre>{html.escape(json.dumps(_trace_summary(merge_trace), ensure_ascii=False, indent=2))}</pre>
  </details>
</main>
<script>
document.querySelectorAll('.tabs button').forEach((button) => {{
  button.addEventListener('click', () => {{
    document.querySelectorAll('.tabs button').forEach((item) => item.classList.remove('active'));
    document.querySelectorAll('.layer').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    document.querySelector('.layer[data-layer="' + button.dataset.layer + '"]').classList.add('active');
  }});
}});
</script>
</body>
</html>
"""


def _stat(label: str, value: Any) -> str:
    return f'<div class="stat"><b>{html.escape(str(value))}</b>{html.escape(label)}</div>'


def _legend(color: str, label: str) -> str:
    return f'<span><i class="swatch" style="background:{html.escape(color)}"></i>{html.escape(label)}</span>'


def _layer(name: str, image_src: str, boxes_html: str, *, active: bool = False) -> str:
    active_class = " active" if active else ""
    return f'<div class="layer{active_class}" data-layer="{html.escape(name)}"><div class="stage-view"><img src="{html.escape(image_src)}" alt="{html.escape(name)}">{boxes_html}</div></div>'


def _interactive_boxes(
    boxes: list[dict[str, Any]],
    width: int,
    height: int,
    colorer,
    tooltiper,
    *,
    labeler=None,
) -> str:
    items: list[str] = []
    for box in boxes:
        bbox = _bbox(box.get("bbox"))
        if bbox is None:
            continue
        left = bbox[0] / width * 100
        top = bbox[1] / height * 100
        box_width = (bbox[2] - bbox[0]) / width * 100
        box_height = (bbox[3] - bbox[1]) / height * 100
        label = labeler(box) if labeler is not None else _box_label(box)
        tip = tooltiper(box)
        color = colorer(box)
        items.append(
            '<div class="ibox" '
            f'style="--c:{html.escape(color)};left:{left:.4f}%;top:{top:.4f}%;width:{box_width:.4f}%;height:{box_height:.4f}%;" '
            f'data-tip="{html.escape(tip)}"><span class="label">{html.escape(str(label))}</span></div>'
        )
    return "\n".join(items)


def _raw_tooltip(box: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"id: {box.get('id', '')}",
            f"type: {box.get('type', '')}",
            f"source_prompt: {box.get('source_prompt', '')}",
            f"score: {box.get('score', '')}",
            f"bbox: {_round_bbox(box.get('bbox'))}",
            "stage: raw SAM normalized box",
        ]
    )


def _merged_tooltip(box: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"id: {box.get('id', '')}",
            f"type: {box.get('type', '')}",
            f"source_box_ids: {box.get('source_box_ids', [])}",
            f"parents: {box.get('parent_ids', [])}",
            f"children: {box.get('child_ids', [])}",
            f"bbox: {_round_bbox(box.get('bbox'))}",
            "stage: merged SAM structure box",
        ]
    )


def _ocr_tooltip(box: Mapping[str, Any]) -> str:
    text = str(box.get("text") or box.get("value") or "")
    return "\n".join([f"text: {text}", f"bbox: {_round_bbox(box.get('bbox'))}", "stage: OCR text layer"])


def _asset_tooltip(box: Mapping[str, Any], method: Mapping[str, Any]) -> str:
    policy = method.get("policy") if isinstance(method.get("policy"), Mapping) else {}
    manifest = method.get("manifest") if isinstance(method.get("manifest"), Mapping) else {}
    return "\n".join(
        [
            f"box: {box.get('id', '')}",
            f"type: {box.get('type', '')}",
            f"处理办法: {method.get('label', '')}",
            f"asset_id: {method.get('asset_id', '')}",
            f"说明: {method.get('detail', '')}",
            f"render_policy: {policy.get('render_policy', '')}",
            f"background_policy: {policy.get('background_policy', '')}",
            f"active_variant: {manifest.get('active_variant', '')}",
            f"href: {manifest.get('svg_href') or manifest.get('source_svg_href') or ''}",
            f"bbox: {_round_bbox(box.get('bbox'))}",
        ]
    )


def _codex_element_tooltip(box: Mapping[str, Any], method: Mapping[str, Any]) -> str:
    evidence = method.get("evidence") if isinstance(method.get("evidence"), list) else []
    current = method.get("raw", {}).get("current_pipeline_method") if isinstance(method.get("raw"), Mapping) else ""
    source_candidate_ids = method.get("source_candidate_ids") if isinstance(method.get("source_candidate_ids"), list) else []
    return "\n".join(
        [
            f"box: {box.get('id', '')}",
            f"type: {box.get('type', '')}",
            f"refinement_action: {method.get('refinement_action', '')}",
            f"source_candidate_ids: {', '.join(str(item) for item in source_candidate_ids)}",
            f"Codex 分类: {method.get('label', '')}",
            f"confidence: {method.get('confidence', '')}",
            f"visual_role: {method.get('visual_role', '')}",
            f"current_pipeline_method: {current}",
            f"recommended_asset_source: {method.get('recommended_asset_source', '')}",
            f"reason: {method.get('detail', '')}",
            f"evidence: {', '.join(str(item) for item in evidence)}",
            f"bbox: {_round_bbox(method.get('bbox') or box.get('bbox'))}",
        ]
    )


def _round_bbox(raw: Any) -> str:
    bbox = _bbox(raw)
    if bbox is None:
        return ""
    return "[" + ", ".join(str(round(item, 1)) for item in bbox) + "]"


def _duplicate_row(item: Mapping[str, Any]) -> str:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), Mapping) else {}
    return (
        "<tr>"
        f"<td>{html.escape(str(item.get('left_index')))}-{html.escape(str(item.get('right_index')))}</td>"
        f"<td>{html.escape(', '.join(str(x) for x in item.get('box_ids', [])))}</td>"
        f"<td>{html.escape(str(item.get('reason', '')))}</td>"
        f"<td>{html.escape(json.dumps(metrics, ensure_ascii=False))}</td>"
        "</tr>"
    )


def _cluster_row(index: int, cluster: list[int], raw_boxes: list[dict[str, Any]], replay: ClusterReplay) -> str:
    merged = replay.merged_candidates[index - 1] if index - 1 < len(replay.merged_candidates) else {}
    source_labels = []
    for raw_index in cluster:
        box = raw_boxes[raw_index]
        source_labels.append(f"{_box_id(box, raw_index)}:{box.get('type', '')}")
    context = "container context" if merged.get("has_external_child") else "leaf context"
    return (
        "<tr>"
        f"<td>{index}</td>"
        f"<td>{html.escape(', '.join(source_labels))}</td>"
        f"<td>{html.escape(str(merged.get('type', '')))}</td>"
        f"<td>{html.escape(context)}</td>"
        "</tr>"
    )


def _asset_policy_row(item: Mapping[str, Any]) -> str:
    reasons = item.get("reason_codes") if isinstance(item.get("reason_codes"), list) else []
    return (
        "<tr>"
        f"<td>{html.escape(str(item.get('asset_id', '')))}</td>"
        f"<td>{html.escape(str(item.get('box_id', '')))}</td>"
        f"<td>{html.escape(str(item.get('current_label', '')))}</td>"
        f"<td>{html.escape(str(item.get('render_policy', '')))}</td>"
        f"<td>{html.escape(str(item.get('background_policy', '')))}</td>"
        f"<td>{html.escape(str(item.get('split_policy', '')))}</td>"
        f"<td>{html.escape(', '.join(str(x) for x in reasons))}</td>"
        "</tr>"
    )


def _asset_manifest_row(item: Mapping[str, Any]) -> str:
    policy_bits = [str(item.get(key, "")) for key in ("render_policy", "background_policy", "split_policy") if item.get(key)]
    href = item.get("svg_href") or item.get("source_svg_href") or ""
    return (
        "<tr>"
        f"<td>{html.escape(str(item.get('asset_id', '')))}</td>"
        f"<td>{html.escape(str(item.get('box_id', '')))}</td>"
        f"<td>{html.escape(str(item.get('active_variant', '')))}</td>"
        f"<td>{html.escape(str(href))}</td>"
        f"<td>{html.escape(' / '.join(policy_bits))}</td>"
        "</tr>"
    )


def _codex_element_row(method: Mapping[str, Any]) -> str:
    raw = method.get("raw") if isinstance(method.get("raw"), Mapping) else {}
    source_candidate_ids = method.get("source_candidate_ids") if isinstance(method.get("source_candidate_ids"), list) else []
    return (
        "<tr>"
        f"<td>{html.escape(str(method.get('id', '')))}</td>"
        f"<td>{html.escape(', '.join(str(item) for item in source_candidate_ids))}</td>"
        f"<td>{html.escape(str(method.get('refinement_action', '')))}</td>"
        f"<td>{html.escape(str(method.get('type', '')))}</td>"
        f"<td>{html.escape(str(method.get('label', '')))}</td>"
        f"<td>{html.escape(str(method.get('confidence', '')))}</td>"
        f"<td>{html.escape(str(method.get('visual_role', '')))}</td>"
        f"<td>{html.escape(str(raw.get('current_pipeline_method', '')))}</td>"
        f"<td>{html.escape(str(method.get('detail', '')))}</td>"
        "</tr>"
    )


def _trace_summary(merge_trace: Mapping[str, Any]) -> dict[str, Any]:
    decisions = merge_trace.get("decisions") if isinstance(merge_trace.get("decisions"), list) else []
    return {
        "decision_count": len(decisions),
        "reasons": dict(sorted(Counter(str(item.get("reason", "unknown")) for item in decisions if isinstance(item, Mapping)).items())),
        "keep_summary": merge_trace.get("keep_summary", {}),
    }


def _image_caption(name: str) -> str:
    return {
        "01_raw_sam_all": "1. 清洗后的 Raw SAM boxes",
        "02_duplicate_pairs": "2. 被判定为重复的 pair",
        "03_merge_clusters": "3. Union 后的 merge clusters",
        "04_merged_sam": "4. 合并后的 SAM 结构框",
        "05_containment": "5. Parent/child containment",
        "06_ocr": "6. OCR 文本框",
        "07_final_boxir_plus_ocr": "7. 最终 layout IR + OCR",
        "08_asset_plan": "8. Codex 前的 asset plan",
        "09_codex_element_distribution": "9. Codex 元素来源分布",
    }.get(name, name)


if __name__ == "__main__":
    raise SystemExit(main())
