#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
SCRIPT_ROOT = REPO_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_imagegen  # noqa: E402
from drawai.codex_python_sdk_imagegen import CodexPythonSdkImageGenError  # noqa: E402
from drawai.slide_image_prompt import build_slide_image_generation_prompt  # noqa: E402
from run_codex_slide_imagegen_suite import _kimi_slides  # noqa: E402


DEFAULT_CANDIDATES = (
    ("dark_tech", "dark_tech"),
    ("academic_technical", "academic_technical"),
    ("product_launch", "product_launch"),
)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_config: dict[str, object] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model

    slides = _kimi_slides()
    started_at = time.time()
    report: dict[str, Any] = {
        "schema": "drawai.codex_slide_imagegen_strategy_test.v1",
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "prompt_group": "kimi",
        "rendering_mode": "baked_text",
        "candidate_templates": [item[0] for item in DEFAULT_CANDIDATES],
        "candidates": [],
        "deck": [],
    }
    _write_json(output_dir / "strategy_test_report.json", report)

    if not args.skip_candidates:
        for index, (template_id, label) in enumerate(DEFAULT_CANDIDATES, start=1):
            candidate_dir = output_dir / "candidates" / f"{index:02d}_{template_id}"
            existing = _load_existing_record(candidate_dir)
            if existing is not None:
                report["candidates"].append(existing)
                _write_json(output_dir / "strategy_test_report.json", report)
                continue
            try:
                record = _generate_slide(
                    slide=slides[0],
                    group_id="kimi",
                    output_dir=candidate_dir,
                    output_stem=f"candidate-{index:02d}-{template_id}",
                    template_id=template_id,
                    strategy=args.strategy,
                    style_candidate_index=index,
                    style_candidate_count=len(DEFAULT_CANDIDATES),
                    runtime_config=runtime_config,
                    label=label,
                    timeout_seconds=args.timeout_seconds,
                )
            except CodexPythonSdkImageGenError as exc:
                report["status"] = "blocked"
                report["blocked_reason"] = str(exc)
                _write_json(output_dir / "strategy_test_report.json", report)
                if report["candidates"]:
                    report["candidate_contact_sheet"] = str(_write_candidate_sheet(output_dir, report["candidates"]))
                    _write_json(output_dir / "strategy_test_report.json", report)
                print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
                return 2
            except Exception as exc:
                report["status"] = "failed"
                report["error"] = repr(exc)
                _write_json(output_dir / "strategy_test_report.json", report)
                raise
            else:
                report["candidates"].append(record)
                _write_json(output_dir / "strategy_test_report.json", report)
        report["candidate_contact_sheet"] = str(_write_candidate_sheet(output_dir, report["candidates"]))

    if not args.skip_deck:
        for index, slide in enumerate(slides[: args.deck_slides], start=1):
            deck_dir = output_dir / "deck" / f"{index:02d}_{slide['id']}"
            existing = _load_existing_record(deck_dir)
            if existing is not None:
                report["deck"].append(existing)
                _write_json(output_dir / "strategy_test_report.json", report)
                continue
            try:
                record = _generate_slide(
                    slide=slide,
                    group_id="kimi",
                    output_dir=deck_dir,
                    output_stem=f"deck-{index:02d}-{args.deck_template}",
                    template_id=args.deck_template,
                    strategy=args.strategy,
                    style_candidate_index=1,
                    style_candidate_count=len(DEFAULT_CANDIDATES),
                    runtime_config=runtime_config,
                    label=f"{index:02d} {slide['title']}",
                    timeout_seconds=args.timeout_seconds,
                )
            except CodexPythonSdkImageGenError as exc:
                report["status"] = "blocked"
                report["blocked_reason"] = str(exc)
                _write_json(output_dir / "strategy_test_report.json", report)
                if report["deck"]:
                    report["deck_contact_sheet"] = str(_write_deck_sheet(output_dir, report["deck"]))
                    _write_json(output_dir / "strategy_test_report.json", report)
                print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
                return 2
            except Exception as exc:
                report["status"] = "failed"
                report["error"] = repr(exc)
                _write_json(output_dir / "strategy_test_report.json", report)
                raise
            else:
                report["deck"].append(record)
                _write_json(output_dir / "strategy_test_report.json", report)
        report["deck_contact_sheet"] = str(_write_deck_sheet(output_dir, report["deck"]))

    report["status"] = "ok"
    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_json(output_dir / "strategy_test_report.json", report)
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a complete baked-text strategy test for Kimi PPT image generation.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "codex_slide_imagegen_strategy_test" / "kimi_complete",
    )
    parser.add_argument("--strategy", default="technical")
    parser.add_argument("--deck-template", default="academic_technical")
    parser.add_argument("--deck-slides", type=int, default=5)
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=420.0)
    parser.add_argument("--skip-candidates", action="store_true")
    parser.add_argument("--skip-deck", action="store_true")
    return parser.parse_args()


def _generate_slide(
    *,
    slide: dict[str, Any],
    group_id: str,
    output_dir: Path,
    output_stem: str,
    template_id: str,
    strategy: str,
    style_candidate_index: int,
    style_candidate_count: int,
    runtime_config: dict[str, object],
    label: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(slide)
    payload.update(
        {
            "prompt": f"[Deck group: {group_id}] {slide['prompt']}",
            "strategy": strategy,
            "template_id": template_id,
            "style_candidate_index": style_candidate_index,
            "style_candidate_count": style_candidate_count,
            "rendering_mode": "baked_text",
        }
    )
    prompt = build_slide_image_generation_prompt(payload)
    _write_json(output_dir / "payload.json", payload)
    (output_dir / "improved_prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    result = invoke_codex_python_sdk_imagegen(
        prompt=prompt,
        output_dir=output_dir / "generated",
        task_name="drawai.experiment.codex_slide_strategy_test.improved.v1",
        output_stem=output_stem,
        runtime_config={**runtime_config, "timeout_seconds": timeout_seconds},
        trace_path=output_dir / "trace.jsonl",
        isolated_cwd=output_dir / "codex_cwd",
    )
    record = {
        "label": label,
        "slide_id": slide["id"],
        "title": slide["title"],
        "template_id": template_id,
        "output_dir": str(output_dir),
        "prompt_path": str(output_dir / "improved_prompt.txt"),
        "generation": result.to_dict(),
    }
    _write_json(output_dir / "record.json", record)
    return record


def _write_candidate_sheet(output_dir: Path, records: list[dict[str, Any]]) -> Path:
    rows = [(record["label"], _first_image_path(record)) for record in records]
    thumb_w = 520
    thumb_h = 293
    label_h = 34
    margin = 20
    width = margin * (len(rows) + 1) + thumb_w * len(rows)
    height = margin * 2 + label_h + thumb_h
    sheet = Image.new("RGB", (width, height), (245, 246, 248))
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for i, (label, path) in enumerate(rows):
        x = margin + i * (thumb_w + margin)
        draw.text((x, margin), label, fill=(16, 24, 40), font=font)
        _paste_thumb(sheet, path, x, margin + label_h, thumb_w, thumb_h)
    path = output_dir / "candidate_contact_sheet.jpg"
    sheet.save(path, quality=92)
    return path


def _write_deck_sheet(output_dir: Path, records: list[dict[str, Any]]) -> Path:
    rows = [(record["label"], _first_image_path(record)) for record in records]
    thumb_w = 620
    thumb_h = 349
    label_h = 34
    margin = 18
    width = margin * 2 + thumb_w
    height = margin + len(rows) * (label_h + thumb_h + margin)
    sheet = Image.new("RGB", (width, height), (245, 246, 248))
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    for i, (label, path) in enumerate(rows):
        y = margin + i * (label_h + thumb_h + margin)
        draw.text((margin, y), label, fill=(16, 24, 40), font=font)
        _paste_thumb(sheet, path, margin, y + label_h, thumb_w, thumb_h)
    path = output_dir / "deck_contact_sheet.jpg"
    sheet.save(path, quality=92)
    return path


def _paste_thumb(sheet: Image.Image, path: Path | None, x: int, y: int, w: int, h: int) -> None:
    draw = ImageDraw.Draw(sheet)
    draw.rectangle([x, y, x + w, y + h], fill=(255, 255, 255), outline=(203, 213, 225))
    if path is None or not path.exists():
        draw.text((x + 20, y + 20), "not generated", fill=(100, 116, 139), font=_font(18))
        return
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((w - 10, h - 10))
        px = x + (w - image.width) // 2
        py = y + (h - image.height) // 2
        sheet.paste(image, (px, py))


def _first_image_path(record: dict[str, Any]) -> Path | None:
    generation = record.get("generation")
    if not isinstance(generation, dict):
        return None
    images = generation.get("images")
    if not isinstance(images, list) or not images:
        return None
    first = images[0]
    if not isinstance(first, dict) or not first.get("path"):
        return None
    return Path(str(first["path"]))


def _load_existing_record(output_dir: Path) -> dict[str, Any] | None:
    record_path = output_dir / "record.json"
    if not record_path.exists():
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    image_path = _first_image_path(record)
    if image_path is None or not image_path.exists():
        return None
    return record


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "output_dir": report.get("output_dir"),
        "candidate_contact_sheet": report.get("candidate_contact_sheet", ""),
        "deck_contact_sheet": report.get("deck_contact_sheet", ""),
        "candidate_count": len(report.get("candidates", [])),
        "deck_slide_count": len(report.get("deck", [])),
        "report_path": str(Path(str(report["output_dir"])) / "strategy_test_report.json"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
