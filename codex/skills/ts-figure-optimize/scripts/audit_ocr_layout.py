#!/usr/bin/env python3
"""Detect severe text-box overlap, duplication, clipping, and tiny labels from DrawAI OCR."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _boxes(payload):
    if isinstance(payload, list):
        return payload
    for key in ("ocr_text_boxes", "boxes", "text_boxes"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def _canvas(box_ir, boxes):
    canvas = box_ir.get("canvas") if isinstance(box_ir, dict) else {}
    width, height = float((canvas or {}).get("width") or 0), float((canvas or {}).get("height") or 0)
    if width and height:
        return width, height
    coords = [item.get("bbox") for item in boxes if isinstance(item, dict) and item.get("bbox")]
    return (max((float(box[2]) for box in coords), default=0),
            max((float(box[3]) for box in coords), default=0))


def audit(ocr_path: Path, box_ir_path: Path, overlap_threshold: float = 0.35,
          min_height_ratio: float = 0.012) -> dict:
    payload = json.loads(ocr_path.read_text(encoding="utf-8"))
    box_ir = json.loads(box_ir_path.read_text(encoding="utf-8")) if box_ir_path.is_file() else {}
    raw_boxes = _boxes(payload)
    width, height = _canvas(box_ir, raw_boxes)
    errors, warnings, boxes = [], [], []
    for index, item in enumerate(raw_boxes):
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") or item.get("box")
        if not isinstance(bbox, list) or len(bbox) < 4:
            warnings.append(f"ocr[{index}] missing bbox")
            continue
        try:
            x0, y0, x1, y1 = map(float, bbox[:4])
        except (TypeError, ValueError):
            warnings.append(f"ocr[{index}] invalid bbox")
            continue
        x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1))
        text = str(item.get("text") or "").strip()
        if x1 <= x0 or y1 <= y0 or not text:
            continue
        ident = str(item.get("id") or f"ocr[{index}]")
        boxes.append((ident, text, (x0, y0, x1, y1)))
        if width and height and (x0 < 0 or y0 < 0 or x1 > width or y1 > height):
            errors.append(f"{ident} text bbox is clipped outside the canvas")
        if height and (y1 - y0) / height < min_height_ratio:
            warnings.append(f"{ident} label may be too small at paper scale ({(y1-y0)/height:.3%} canvas height)")

    collisions = []
    for index, (left_id, left_text, left) in enumerate(boxes):
        lx0, ly0, lx1, ly1 = left
        left_area = (lx1 - lx0) * (ly1 - ly0)
        for right_id, right_text, right in boxes[index + 1:]:
            rx0, ry0, rx1, ry1 = right
            overlap = max(0.0, min(lx1, rx1) - max(lx0, rx0)) * max(0.0, min(ly1, ry1) - max(ly0, ry0))
            if not overlap:
                continue
            right_area = (rx1 - rx0) * (ry1 - ry0)
            ratio = overlap / min(left_area, right_area)
            if ratio >= overlap_threshold:
                collision = {"left": left_id, "left_text": left_text, "right": right_id,
                             "right_text": right_text, "overlap_ratio": round(ratio, 6)}
                collisions.append(collision)
                errors.append(f"{left_id}/{right_id} text boxes overlap by {ratio:.0%}")

    return {"ok": not errors, "canvas": [width, height], "text_box_count": len(boxes),
            "collisions": collisions, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr", required=True)
    parser.add_argument("--box-ir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overlap-threshold", type=float, default=0.35)
    parser.add_argument("--min-height-ratio", type=float, default=0.012)
    args = parser.parse_args()
    report = audit(Path(args.ocr), Path(args.box_ir), args.overlap_threshold, args.min_height_ratio)
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
