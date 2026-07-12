#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.slide_template_library import build_prompt_from_template_card  # noqa: E402


TOPIC = "AI Agent 工作流如何落地企业知识库"

REFERENCE_IMAGE = (
    REPO_ROOT
    / "outputs"
    / "codex_slide_imagegen_expanded_style_cases"
    / "02_tech_openai_agent_workflow"
    / "tech_openai_agent_workflow.png"
)

CASES: list[dict[str, Any]] = [
    {
        "id": "modern_newspaper",
        "title": TOPIC,
        "mode": "prompt_only",
        "notes": "editorial briefing prompt-only",
        "reference_image_paths": [],
    },
    {
        "id": "swiss_international",
        "title": TOPIC,
        "mode": "generate",
        "notes": "serious report grid",
        "reference_image_paths": [],
    },
    {
        "id": "aurora_ui",
        "title": TOPIC,
        "mode": "generate",
        "notes": "AI product workflow",
        "reference_image_paths": [],
    },
    {
        "id": "manga_safe_learning",
        "title": "用儿童学习 PPT 讲清楚 AI Agent 如何记住企业知识库任务",
        "mode": "generate",
        "notes": "IP-safe learning atmosphere; no protected character likeness",
        "reference_image_paths": [],
    },
    {
        "id": "corporate_strategy_cinematic",
        "title": TOPIC,
        "mode": "prompt_only",
        "notes": "corporate strategy board-level framing",
        "reference_image_paths": [],
    },
    {
        "id": "light_glassmorphism",
        "title": TOPIC,
        "mode": "prompt_only_reference",
        "notes": "prompt-only reference-image policy demo",
        "reference_image_paths": [str(REFERENCE_IMAGE)],
    },
]


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve(strict=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_config: dict[str, Any] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model

    started_at = time.time()
    report: dict[str, Any] = {
        "schema": "drawai.slide_template_library_experiment.v1",
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "topic": TOPIC,
        "output_dir": str(output_dir),
        "case_count": len(CASES),
        "cases": [],
    }
    _write_json(output_dir / "summary.json", report)

    blocked_reason = ""
    generated_count = 0
    for index, case in enumerate(CASES, start=1):
        case_dir = output_dir / f"{index:02d}_{case['id']}"
        record = None if args.force else _load_existing_record(case_dir)
        if record is None:
            record = _write_prompt_only_record(case, case_dir=case_dir, index=index)
            should_generate = (
                not args.prompt_only
                and case["mode"] == "generate"
                and generated_count < args.real_limit
                and not blocked_reason
            )
            if should_generate:
                try:
                    record = _run_generation(case, case_dir=case_dir, index=index, runtime_config=runtime_config)
                    generated_count += 1 if record.get("status") == "ok" else 0
                except Exception as exc:  # Keep prompt-only artifacts if login/quota/tooling fails.
                    blocked_reason = repr(exc)
                    record["status"] = "blocked"
                    record["blocked_reason"] = blocked_reason
                    _write_json(case_dir / "record.json", record)
        report["cases"].append(record)
        _write_json(output_dir / "summary.json", report)

    report["contact_sheet"] = str(_write_contact_sheet(output_dir, report["cases"]))
    report["status"] = "blocked" if blocked_reason else "ok"
    if blocked_reason:
        report["blocked_reason"] = blocked_reason
    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_json(output_dir / "summary.json", report)
    _write_markdown_report(output_dir, report)
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 2 if blocked_reason and not any(case.get("status") == "ok" for case in report["cases"]) else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small prompt/template-card PPT imagegen experiment.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "codex_slide_template_library_experiment",
    )
    parser.add_argument("--real-limit", type=int, default=3, help="Maximum real Codex generations to run.")
    parser.add_argument("--prompt-only", action="store_true", help="Only write prompts and records.")
    parser.add_argument("--force", action="store_true", help="Regenerate prompt records and images.")
    parser.add_argument("--model", default="", help="Optional Codex model override.")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=420.0)
    return parser.parse_args()


def _write_prompt_only_record(case: dict[str, Any], *, case_dir: Path, index: int) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    refs = _existing_reference_paths(case.get("reference_image_paths") or [])
    prompt = build_prompt_from_template_card(
        case["id"],
        case["title"],
        language="zh",
        reference_image_paths=refs,
    )
    payload = {
        "schema": "drawai.slide_template_library_experiment_case.v1",
        "case_id": case["id"],
        "topic": case["title"],
        "language": "zh",
        "template_card_id": case["id"],
        "reference_image_paths": refs,
        "size": "2048x1152",
        "quality": "high",
        "mode": case["mode"],
        "notes": case["notes"],
    }
    _write_json(case_dir / "payload.json", payload)
    (case_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    record = {
        "id": case["id"],
        "template_card_id": case["id"],
        "topic": case["title"],
        "mode": case["mode"],
        "status": "prompt_only",
        "case_dir": str(case_dir),
        "payload_path": str(case_dir / "payload.json"),
        "prompt_path": str(case_dir / "prompt.txt"),
        "reference_image_paths": refs,
        "image_path": "",
        "generation": None,
        "quality_notes": [],
    }
    _write_json(case_dir / "record.json", record)
    return record


def _run_generation(case: dict[str, Any], *, case_dir: Path, index: int, runtime_config: dict[str, Any]) -> dict[str, Any]:
    from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_imagegen

    record = _write_prompt_only_record(case, case_dir=case_dir, index=index)
    prompt = (case_dir / "prompt.txt").read_text(encoding="utf-8")
    result = invoke_codex_python_sdk_imagegen(
        prompt=prompt,
        output_dir=case_dir / "generated",
        task_name="drawai.experiment.slide_template_library.v1",
        output_stem=f"{index:02d}-{case['id']}",
        runtime_config=runtime_config,
        trace_path=case_dir / "trace.jsonl",
        isolated_cwd=case_dir / "codex_cwd",
    )
    first = result.images[0] if result.images else None
    image_path = ""
    quality_notes: list[str] = []
    if first is not None:
        image_path = str(_copy_preview_png(Path(first.path), case_dir / f"{case['id']}.png"))
        quality_notes = _basic_image_notes(Path(image_path))
    record.update(
        {
            "status": "ok" if image_path else "missing_image",
            "image_path": image_path,
            "generation": result.to_dict(),
            "quality_notes": quality_notes,
        }
    )
    _write_json(case_dir / "record.json", record)
    return record


def _existing_reference_paths(values: list[str]) -> list[str]:
    paths: list[str] = []
    for value in values:
        path = Path(value).expanduser().resolve(strict=False)
        if path.is_file():
            paths.append(str(path))
        else:
            paths.append(str(path))
    return paths


def _copy_preview_png(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".png":
        shutil.copy2(source, target)
        return target
    Image, _, _ = _pil()
    with Image.open(source) as image:
        image.save(target)
    return target


def _basic_image_notes(path: Path) -> list[str]:
    notes: list[str] = []
    if not path.is_file():
        return ["missing PNG preview"]
    Image, _, _ = _pil()
    with Image.open(path) as image:
        ratio = image.width / max(1, image.height)
        if image.width < 1200 or image.height < 675:
            notes.append(f"lower than expected resolution: {image.width}x{image.height}")
        if ratio < 1.5 or ratio > 1.9:
            notes.append(f"aspect ratio may not be 16:9: {image.width}x{image.height}")
    return notes


def _load_existing_record(case_dir: Path) -> dict[str, Any] | None:
    path = case_dir / "record.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _first_image_path(record: dict[str, Any]) -> Path | None:
    path = Path(str(record.get("image_path") or ""))
    if path.is_file():
        return path
    generation = record.get("generation") or {}
    for image in generation.get("images", []):
        candidate = Path(str(image.get("path") or ""))
        if candidate.is_file():
            return candidate
    return None


def _write_contact_sheet(output_dir: Path, records: list[dict[str, Any]]) -> Path:
    Image, ImageDraw, _ = _pil()
    thumb_w = 560
    thumb_h = 315
    label_h = 66
    margin = 18
    cols = 2
    rows = (len(records) + cols - 1) // cols
    width = margin * (cols + 1) + cols * thumb_w
    height = margin + rows * (label_h + thumb_h + margin)
    sheet = Image.new("RGB", (width, height), (247, 248, 250))
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    small = _font(13)
    for index, record in enumerate(records):
        row = index // cols
        col = index % cols
        x = margin + col * (thumb_w + margin)
        y = margin + row * (label_h + thumb_h + margin)
        draw.text((x, y), record["template_card_id"], fill=(15, 23, 42), font=font)
        status = f"{record['mode']} / {record['status']}"
        draw.text((x, y + 24), status, fill=(71, 85, 105), font=small)
        if record.get("reference_image_paths"):
            draw.text((x, y + 42), "reference prompt policy included", fill=(100, 116, 139), font=small)
        _paste_thumb(sheet, _first_image_path(record), x, y + label_h, thumb_w, thumb_h)
    path = output_dir / "contact_sheet.jpg"
    sheet.save(path, quality=92)
    return path


def _paste_thumb(sheet: Any, path: Path | None, x: int, y: int, width: int, height: int) -> None:
    Image, ImageDraw, _ = _pil()
    draw = ImageDraw.Draw(sheet)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=8, fill=(226, 232, 240), outline=(203, 213, 225))
    if path is None:
        draw.text((x + 18, y + 18), "prompt-only / no image", fill=(100, 116, 139), font=_font(18))
        return
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        ox = x + (width - image.width) // 2
        oy = y + (height - image.height) // 2
        sheet.paste(image, (ox, oy))


def _write_markdown_report(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Slide Template Library Experiment",
        "",
        f"- Status: {report.get('status')}",
        f"- Topic: {report.get('topic')}",
        f"- Output dir: {report.get('output_dir')}",
        f"- Contact sheet: {report.get('contact_sheet', '')}",
        f"- Blocked reason: {report.get('blocked_reason', '')}",
        "",
        "| Case | Mode | Status | Prompt | Image | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in report.get("cases", []):
        notes = "; ".join(record.get("quality_notes") or [])
        if record.get("reference_image_paths"):
            notes = (notes + "; " if notes else "") + "reference prompt policy included"
        lines.append(
            "| `{case}` | {mode} | {status} | {prompt} | {image} | {notes} |".format(
                case=record.get("template_card_id", ""),
                mode=record.get("mode", ""),
                status=record.get("status", ""),
                prompt=record.get("prompt_path", ""),
                image=record.get("image_path", ""),
                notes=notes,
            )
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _font(size: int) -> Any:
    _, _, ImageFont = _pil()
    for candidate in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        path = Path(candidate)
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _pil() -> tuple[Any, Any, Any]:
    from PIL import Image, ImageDraw, ImageFont

    return Image, ImageDraw, ImageFont


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "case_count": report.get("case_count"),
        "output_dir": report.get("output_dir"),
        "contact_sheet": report.get("contact_sheet"),
        "ok_cases": sum(1 for case in report.get("cases", []) if case.get("status") == "ok"),
        "blocked_reason": report.get("blocked_reason", ""),
    }


if __name__ == "__main__":
    raise SystemExit(main())
