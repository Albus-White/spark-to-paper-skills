from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Mapping

from .document import normalize_box_type

SAME_TYPE_SMALLER_OVERLAP_AREA_SIMILARITY_THRESHOLD = 0.75
SAME_TYPE_NESTED_SMALLER_OVERLAP_TYPES = frozenset({"content_box", "icon"})
CROSS_TYPE_DUPLICATE_IOU_THRESHOLD = 0.90
CROSS_TYPE_DUPLICATE_SMALLER_OVERLAP_THRESHOLD = 0.98
CROSS_TYPE_DUPLICATE_AREA_SIMILARITY_THRESHOLD = 0.85
CONTAINER_CONTEXT_CHILD_AREA_RATIO_THRESHOLD = 0.65
VISUAL_ASSET_CHILD_MAX_AREA_RATIO = 0.90
VISUAL_ASSET_TYPES = frozenset({"icon", "picture"})
KEEP_TRACE_SAMPLE_LIMIT = 8
CONTAINER_PRIORITY = {
    "grid": 0,
    "content_box": 1,
    "border": 2,
    "picture": 3,
    "icon": 4,
    "symbol": 5,
    "arrow": 6,
    "unknown": 99,
}
LEAF_PRIORITY = {
    "arrow": 0,
    "picture": 1,
    "content_box": 2,
    "icon": 3,
    "symbol": 4,
    "grid": 5,
    "border": 6,
    "unknown": 99,
}


def merge_box_ir(
    raw_box_ir: dict[str, Any],
    duplicate_iou_threshold: float = 0.85,
    duplicate_smaller_overlap_threshold: float = 0.92,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_boxes = [deepcopy(box) for box in raw_box_ir.get("boxes", []) if isinstance(box, Mapping)]
    trace: dict[str, Any] = {
        "schema": "drawai.box_ir.merge_trace.v1",
        "duplicate_iou_threshold": duplicate_iou_threshold,
        "duplicate_smaller_overlap_threshold": duplicate_smaller_overlap_threshold,
        "same_type_smaller_overlap_area_similarity_threshold": (
            SAME_TYPE_SMALLER_OVERLAP_AREA_SIMILARITY_THRESHOLD
        ),
        "cross_type_duplicate_iou_threshold": CROSS_TYPE_DUPLICATE_IOU_THRESHOLD,
        "cross_type_duplicate_smaller_overlap_threshold": CROSS_TYPE_DUPLICATE_SMALLER_OVERLAP_THRESHOLD,
        "cross_type_duplicate_area_similarity_threshold": CROSS_TYPE_DUPLICATE_AREA_SIMILARITY_THRESHOLD,
        "container_context_child_area_ratio_threshold": CONTAINER_CONTEXT_CHILD_AREA_RATIO_THRESHOLD,
        "decisions": [],
        "keep_summary": {
            "different_type": 0,
            "overlap_below_duplicate_threshold": 0,
            "samples": [],
        },
    }
    merged_document = deepcopy(raw_box_ir)

    if not source_boxes:
        merged_document["boxes"] = []
        merged_document["merge_trace"] = trace
        return merged_document, trace

    parents = list(range(len(source_boxes)))
    merge_decisions: list[dict[str, Any]] = []

    for left_index in range(len(source_boxes)):
        for right_index in range(left_index + 1, len(source_boxes)):
            left = source_boxes[left_index]
            right = source_boxes[right_index]
            reason = _duplicate_reason(
                left,
                right,
                duplicate_iou_threshold,
                duplicate_smaller_overlap_threshold,
            )
            if reason is not None:
                _union(parents, left_index, right_index)
                merge_decisions.append(
                    {
                        "action": "merge",
                        "box_ids": [_box_id(left, left_index), _box_id(right, right_index)],
                        "reason": reason,
                    }
                )
            else:
                _record_keep(trace["keep_summary"], left, right, left_index, right_index)

    clusters: dict[int, list[int]] = {}
    for index in range(len(source_boxes)):
        root = _find(parents, index)
        clusters.setdefault(root, []).append(index)

    result_boxes: list[dict[str, Any]] = []
    for indexes in clusters.values():
        merged_box = _merge_cluster(source_boxes, indexes, source_boxes)
        result_boxes.append(merged_box)
        visual_child = _preserved_visual_asset_child(source_boxes, indexes, merged_box)
        if visual_child is not None:
            result_boxes.append(visual_child)
    result_boxes.sort(key=_result_reading_order_key)

    old_to_new_id: dict[str, str] = {}
    for index, box in enumerate(result_boxes, start=1):
        result_id = f"B{index:03d}"
        box["id"] = result_id
        box["parent_ids"] = []
        box["child_ids"] = []
        for old_id in box["source_box_ids"]:
            old_to_new_id.setdefault(old_id, result_id)

    for decision in merge_decisions:
        result_ids = {old_to_new_id.get(box_id) for box_id in decision["box_ids"]}
        result_ids.discard(None)
        if len(result_ids) == 1:
            decision["result_box_id"] = next(iter(result_ids))
        trace["decisions"].append(decision)

    for box in result_boxes:
        action = "merge" if len(box["source_box_ids"]) > 1 else "keep"
        reason = "duplicate_cluster_bounding_rect" if action == "merge" else "no_duplicate_match"
        if box.get("_preserved_visual_asset_child"):
            reason = "preserve_visual_asset_child"
        trace["decisions"].append(
            {
                "action": action,
                "box_ids": list(box["source_box_ids"]),
                "reason": reason,
                "result_box_id": box["id"],
            }
        )

    _apply_containment(result_boxes, trace)
    for box in result_boxes:
        box.pop("_source_order", None)
        box.pop("_preserved_visual_asset_child", None)

    merged_document["boxes"] = result_boxes
    merged_document["merge_trace"] = trace
    return merged_document, trace


def _merge_cluster(
    source_boxes: list[dict[str, Any]],
    indexes: list[int],
    all_source_boxes: list[dict[str, Any]],
) -> dict[str, Any]:
    boxes = [source_boxes[index] for index in indexes]
    selected = _select_cluster_representative(boxes, indexes, all_source_boxes)
    bbox = [
        min(box["bbox"][0] for box in boxes),
        min(box["bbox"][1] for box in boxes),
        max(box["bbox"][2] for box in boxes),
        max(box["bbox"][3] for box in boxes),
    ]
    merged: dict[str, Any] = {
        "id": "",
        "type": selected.get("type", "unknown"),
        "bbox": bbox,
        "parent_ids": [],
        "child_ids": [],
        "source_box_ids": [_box_id(box, index) for box, index in zip(boxes, indexes, strict=True)],
        "_source_order": min(int(box.get("source_region_index", index)) for box, index in zip(boxes, indexes, strict=True)),
    }

    scores = [float(box["score"]) for box in boxes if isinstance(box.get("score"), (int, float))]
    if scores:
        merged["score"] = max(scores)
    source_prompts = [
        _canonical_source_prompt(box["source_prompt"])
        for box in boxes
        if "source_prompt" in box and box["source_prompt"] not in (None, "")
    ]
    canonical_prompts = _dedupe_json_stable(source_prompts)
    if canonical_prompts:
        merged["source_prompt"] = _singular_source_prompt(merged["type"], canonical_prompts)
        merged["source_prompts"] = canonical_prompts
    _copy_geometry_when_safe(merged, selected, boxes, bbox)
    return merged


def _select_cluster_representative(
    boxes: list[dict[str, Any]],
    indexes: list[int],
    all_source_boxes: list[dict[str, Any]],
) -> dict[str, Any]:
    priority = CONTAINER_PRIORITY if _cluster_has_external_child(indexes, all_source_boxes) else LEAF_PRIORITY

    def sort_key(item: tuple[dict[str, Any], int]) -> tuple[int, float, int]:
        box, index = item
        box_type = normalize_box_type(box.get("type"))
        score = float(box["score"]) if isinstance(box.get("score"), (int, float)) else 0.0
        source_order = int(box.get("source_region_index", index))
        return (priority.get(box_type, priority["unknown"]), -score, source_order)

    return sorted(zip(boxes, indexes, strict=True), key=sort_key)[0][0]


def _preserved_visual_asset_child(
    source_boxes: list[dict[str, Any]],
    indexes: list[int],
    merged_box: Mapping[str, Any],
) -> dict[str, Any] | None:
    if normalize_box_type(merged_box.get("type")) != "content_box":
        return None
    cluster_area = _area(merged_box["bbox"])
    if cluster_area <= 0:
        return None

    candidates: list[tuple[float, float, int, dict[str, Any]]] = []
    for index in indexes:
        box = source_boxes[index]
        box_type = normalize_box_type(box.get("type"))
        if box_type not in VISUAL_ASSET_TYPES:
            continue
        box_area = _area(box["bbox"])
        if box_area <= 0:
            continue
        area_ratio = box_area / cluster_area
        if area_ratio >= VISUAL_ASSET_CHILD_MAX_AREA_RATIO:
            continue
        if not _contains(merged_box["bbox"], box["bbox"]):
            continue
        score = float(box["score"]) if isinstance(box.get("score"), (int, float)) else 0.0
        candidates.append((box_area, score, index, box))
    if not candidates:
        return None

    _, _, selected_index, selected = sorted(candidates, key=lambda item: (-item[0], -item[1], item[2]))[0]
    preserved: dict[str, Any] = {
        "id": "",
        "type": normalize_box_type(selected.get("type")),
        "bbox": list(selected["bbox"]),
        "parent_ids": [],
        "child_ids": [],
        "source_box_ids": [_box_id(selected, selected_index)],
        "_source_order": int(selected.get("source_region_index", selected_index)),
        "_preserved_visual_asset_child": True,
    }
    if isinstance(selected.get("score"), (int, float)):
        preserved["score"] = float(selected["score"])
    if "source_prompt" in selected and selected["source_prompt"] not in (None, ""):
        prompt = _canonical_source_prompt(selected["source_prompt"])
        preserved["source_prompt"] = prompt
        preserved["source_prompts"] = [prompt]
    if isinstance(selected.get("geometry"), Mapping):
        preserved["geometry"] = deepcopy(selected["geometry"])
    if isinstance(selected.get("mask_path"), str) and selected["mask_path"]:
        preserved["mask_path"] = selected["mask_path"]
    return preserved


def _copy_geometry_when_safe(
    merged: dict[str, Any],
    selected: Mapping[str, Any],
    boxes: list[Mapping[str, Any]],
    merged_bbox: list[float],
) -> None:
    geometry = selected.get("geometry")
    if not isinstance(geometry, Mapping):
        return
    if len(boxes) == 1 or _same_bbox(selected.get("bbox"), merged_bbox):
        merged["geometry"] = deepcopy(geometry)
        if isinstance(selected.get("mask_path"), str) and selected["mask_path"]:
            merged["mask_path"] = selected["mask_path"]
        return
    source_geometries = []
    for box in boxes:
        if isinstance(box.get("geometry"), Mapping):
            source_geometries.append(
                {
                    "source_box_id": box.get("id", ""),
                    "geometry": deepcopy(box["geometry"]),
                }
            )
    if source_geometries:
        merged["source_geometries"] = source_geometries


def _same_bbox(first: Any, second: Any, *, tolerance: float = 1e-6) -> bool:
    if not isinstance(first, (list, tuple)) or not isinstance(second, (list, tuple)):
        return False
    if len(first) != 4 or len(second) != 4:
        return False
    return all(abs(float(left) - float(right)) <= tolerance for left, right in zip(first, second, strict=True))


def _cluster_has_external_child(indexes: list[int], all_source_boxes: list[dict[str, Any]]) -> bool:
    index_set = set(indexes)
    cluster_boxes = [all_source_boxes[index] for index in indexes]
    cluster_bbox = [
        min(box["bbox"][0] for box in cluster_boxes),
        min(box["bbox"][1] for box in cluster_boxes),
        max(box["bbox"][2] for box in cluster_boxes),
        max(box["bbox"][3] for box in cluster_boxes),
    ]
    cluster_area = _area(cluster_bbox)
    if cluster_area <= 0:
        return False
    for index, box in enumerate(all_source_boxes):
        if index in index_set:
            continue
        box_area = _area(box["bbox"])
        if box_area <= 0 or box_area >= cluster_area * CONTAINER_CONTEXT_CHILD_AREA_RATIO_THRESHOLD:
            continue
        if _contains(cluster_bbox, box["bbox"]):
            return True
    return False


def _duplicate_reason(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    duplicate_iou_threshold: float,
    duplicate_smaller_overlap_threshold: float,
) -> str | None:
    left_area = _area(left["bbox"])
    right_area = _area(right["bbox"])
    if left_area <= 0 or right_area <= 0:
        return None
    intersection = _intersection_area(left["bbox"], right["bbox"])
    if intersection <= 0:
        return None
    union = left_area + right_area - intersection
    iou = intersection / union if union > 0 else 0.0
    smaller_overlap = intersection / min(left_area, right_area)
    area_similarity = min(left_area, right_area) / max(left_area, right_area)
    left_type = normalize_box_type(left.get("type"))
    right_type = normalize_box_type(right.get("type"))
    if left_type != right_type:
        if iou >= CROSS_TYPE_DUPLICATE_IOU_THRESHOLD:
            return "cross_type_geometric_duplicate"
        if (
            smaller_overlap >= CROSS_TYPE_DUPLICATE_SMALLER_OVERLAP_THRESHOLD
            and area_similarity >= CROSS_TYPE_DUPLICATE_AREA_SIMILARITY_THRESHOLD
        ):
            return "cross_type_geometric_duplicate"
        return None
    if (
        left_type in SAME_TYPE_NESTED_SMALLER_OVERLAP_TYPES
        and smaller_overlap >= duplicate_smaller_overlap_threshold
    ):
        return f"same_type_nested_{left_type}"
    if iou >= duplicate_iou_threshold:
        return "same_type_iou"
    if (
        smaller_overlap >= duplicate_smaller_overlap_threshold
        and area_similarity >= SAME_TYPE_SMALLER_OVERLAP_AREA_SIMILARITY_THRESHOLD
    ):
        return "same_type_smaller_overlap"
    return None


def _record_keep(
    keep_summary: dict[str, Any],
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    left_index: int,
    right_index: int,
) -> None:
    reason = _keep_reason(left, right)
    keep_summary[reason] = int(keep_summary.get(reason, 0)) + 1
    samples = keep_summary.setdefault("samples", [])
    if len(samples) < KEEP_TRACE_SAMPLE_LIMIT:
        samples.append(
            {
                "action": "keep",
                "box_ids": [_box_id(left, left_index), _box_id(right, right_index)],
                "reason": reason,
            }
        )


def _keep_reason(left: Mapping[str, Any], right: Mapping[str, Any]) -> str:
    if left.get("type") != right.get("type"):
        return "different_type"
    return "overlap_below_duplicate_threshold"


def _dedupe_json_stable(values: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = _json_stable_key(value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _canonical_source_prompt(raw: Any) -> str:
    prompt_type = normalize_box_type(raw)
    if prompt_type != "unknown":
        return prompt_type
    if isinstance(raw, Mapping):
        for field_name in ("id", "type", "label", "text", "class", "class_name", "category", "name"):
            prompt_type = normalize_box_type(raw.get(field_name))
            if prompt_type != "unknown":
                return prompt_type
    if isinstance(raw, str):
        return raw.strip()
    return _json_stable_key(raw)


def _json_stable_key(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(value)


def _singular_source_prompt(box_type: Any, prompts: list[Any]) -> Any:
    if len(prompts) == 1:
        return prompts[0]
    if isinstance(box_type, str) and box_type:
        return box_type
    return prompts[0]


def _apply_containment(boxes: list[dict[str, Any]], trace: dict[str, Any]) -> None:
    for outer in boxes:
        for inner in boxes:
            if outer is inner:
                continue
            if _contains(outer["bbox"], inner["bbox"]) and _area(outer["bbox"]) > _area(inner["bbox"]):
                if outer["id"] not in inner["parent_ids"]:
                    inner["parent_ids"].append(outer["id"])
                if inner["id"] not in outer["child_ids"]:
                    outer["child_ids"].append(inner["id"])
                trace["decisions"].append(
                    {
                        "action": "relate",
                        "box_ids": [outer["id"], inner["id"]],
                        "reason": "spatial_containment",
                    }
                )


def _contains(outer: list[float], inner: list[float]) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _intersection_area(left: list[float], right: list[float]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


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
    if isinstance(raw_id, str) and raw_id:
        return raw_id
    return f"B{fallback_index + 1:03d}"


def _result_reading_order_key(box: Mapping[str, Any]) -> tuple[float, float, float, float, int]:
    bbox = box["bbox"]
    return (bbox[1], bbox[0], bbox[3], bbox[2], int(box.get("_source_order", 0)))
