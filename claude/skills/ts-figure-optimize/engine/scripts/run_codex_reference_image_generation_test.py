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

from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_image_edit  # noqa: E402
from drawai.slide_template_assets import load_slide_template_asset  # noqa: E402


DEFAULT_SOURCE_IMAGE = Path(r"C:\Users\yanrupeng\AppData\Local\hermes\image_cache\img_3801f9a210be.jpg")


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve(strict=False)
    if args.force and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_image = args.source_image.expanduser().resolve(strict=False)
    if not source_image.is_file():
        raise FileNotFoundError(f"source image does not exist: {source_image}")
    source_copy = _copy_source(source_image, output_dir / "source_reference.jpg")
    template = load_slide_template_asset("prisma_flow_diagram")
    prompt = _build_prompt(source_copy=source_copy, template=template)
    payload = {
        "schema": "drawai.codex_reference_image_generation_test.request.v1",
        "operation": "edit",
        "source_image_path": str(source_copy),
        "original_source_image_path": str(source_image),
        "template_id": template["id"],
        "topic": "DrawAI PPT 图像生成能力验证流程",
        "size": "2048x1152",
        "quality": "high",
        "output_format": "png",
        "uses_local_image_input": True,
    }
    _write_json(output_dir / "payload.json", payload)
    (output_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")

    runtime_config: dict[str, Any] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model

    started_at = time.time()
    record: dict[str, Any] = {
        "schema": "drawai.codex_reference_image_generation_test.record.v1",
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "operation": "edit",
        "source_image_path": str(source_copy),
        "original_source_image_path": str(source_image),
        "prompt_path": str(output_dir / "prompt.txt"),
        "payload_path": str(output_dir / "payload.json"),
        "image_path": "",
        "uses_local_image_input": True,
    }
    _write_json(output_dir / "record.json", record)

    try:
        result = invoke_codex_python_sdk_image_edit(
            source_image_path=source_copy,
            prompt=prompt,
            output_dir=output_dir / "generated",
            task_name="drawai.experiment.reference_image_prisma_flow.v1",
            output_stem="prisma-reference-flow-edit",
            runtime_config=runtime_config,
            trace_path=output_dir / "trace.jsonl",
            isolated_cwd=output_dir / "codex_cwd",
        )
        first = result.images[0] if result.images else None
        if first is None:
            raise RuntimeError("Codex edit returned no image")
        image_path = _copy_png(Path(first.path), output_dir / "reference_image_generated.png")
        record.update(
            {
                "status": "ok",
                "image_path": str(image_path),
                "generation": result.to_dict(),
                "operation": result.operation,
                "source_image_path": str(result.source_image_path),
                "elapsed_seconds": round(time.time() - started_at, 3),
            }
        )
    except Exception as exc:  # noqa: BLE001 - preserve prompt/payload on blocker.
        record.update(
            {
                "status": "blocked",
                "blocked_reason": repr(exc),
                "elapsed_seconds": round(time.time() - started_at, 3),
            }
        )
    _write_json(output_dir / "record.json", record)
    summary = _write_summary(output_dir, record)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if record["status"] == "ok" else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a PPT image from a real local PRISMA reference image.")
    parser.add_argument("--source-image", type=Path, default=DEFAULT_SOURCE_IMAGE)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "codex_reference_image_generation_test",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=420.0)
    return parser.parse_args()


def _build_prompt(*, source_copy: Path, template: dict[str, Any]) -> str:
    return f"""DrawAI reference-image PPT generation request.

Execution:
- Use the supplied local image as a real Codex LocalImageInput through image edit.
- operation: edit
- source_image_path: {source_copy}
- This is not prompt-only. The reference image must influence layout, colors, box rhythm, and arrow structure.

Template asset:
{json.dumps(template, ensure_ascii=False, indent=2)}

Task:
Generate one Chinese 16:9 PPT page titled "DrawAI PPT 图像生成能力验证流程".

Reference image adaptation:
- Follow the supplied PRISMA/systematic-review flow layout: yellow top header bars, white rectangular boxes with thin black borders, black arrows, pale-blue vertical stage labels on the left, two-column flow rhythm.
- Replace all original study/review content. Do not copy the original records, counts, English labels, Scopus text, citation-searching text, or exclusion reasons.
- Keep the visual grammar only: top headers, box hierarchy, arrows, stage labels, and clean systematic-review chart structure.

Visible Chinese text:
- Yellow header 1: "能力输入与模板来源"
- Yellow header 2: "参考图与结果验证"
- Left vertical stage labels: "输入", "筛选", "生成", "验证", "重建"
- Main boxes:
  1. "用户输入需求：PPT 类型、主题、语言、文字密度"
  2. "模板资产读取：design_tokens、slot_schema、reference_images"
  3. "候选策略筛选：template_id、source_mode、style lock"
  4. "参考图输入：LocalImageInput / Codex edit"
  5. "PPT 图像生成：中文标题、流程框、箭头与说明"
  6. "质量检查：文字可读、事实不编造、布局不混乱"
  7. "进入 DrawAI：元素识别、分层、可编辑重建"
  8. "输出记录：payload、prompt、record、contact sheet"
- Side exclusion/check boxes:
  - "禁止：复制原图研究数字"
  - "禁止：伪造来源或指标"
  - "禁止：只画空 layout"
  - "检查：operation=edit"

Design constraints:
- Chinese text must be readable and dominant.
- Keep white background and thin black flowchart lines.
- Keep the yellow top bars visually similar to the reference, but do not copy exact wording.
- Use arrows to show a clear screening/evaluation pipeline.
- Do not use fake logos, citations, watermarks, random English filler, or tiny unreadable text.
- The result should look like a polished PPT workflow page, not a raw screenshot crop.

Final response contract: reply only {{"edited": true}}."""


def _copy_source(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _copy_png(source: Path, target: Path) -> Path:
    Image, _, _ = _pil()
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".png":
        shutil.copy2(source, target)
        return target
    with Image.open(source) as image:
        image.save(target)
    return target


def _write_summary(output_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    contact_sheet = _write_contact_sheet(output_dir, record)
    summary = {
        "schema": "drawai.codex_reference_image_generation_test.summary.v1",
        "status": record["status"],
        "output_dir": str(output_dir),
        "source_copy": str(output_dir / "source_reference.jpg"),
        "original_source_image_path": str(_original_source_image_path(output_dir)),
        "prompt_path": str(output_dir / "prompt.txt"),
        "payload_path": str(output_dir / "payload.json"),
        "record_path": str(output_dir / "record.json"),
        "image_path": record.get("image_path", ""),
        "contact_sheet": str(contact_sheet),
        "operation": record.get("operation"),
        "source_image_path": record.get("source_image_path"),
        "uses_local_image_input": record.get("uses_local_image_input"),
        "blocked_reason": record.get("blocked_reason", ""),
    }
    _write_json(output_dir / "summary.json", summary)
    lines = [
        "# Codex 参考图真实生成测试",
        "",
        f"- 状态：{summary['status']}",
        f"- 输出目录：{summary['output_dir']}",
        f"- 源图副本：{summary['source_copy']}",
        f"- 生成图：{summary['image_path']}",
        f"- Contact sheet：{summary['contact_sheet']}",
        f"- operation：{summary['operation']}",
        f"- source_image_path：{summary['source_image_path']}",
        f"- original_source_image_path：{summary['original_source_image_path']}",
        f"- uses_local_image_input：{summary['uses_local_image_input']}",
        f"- blocked_reason：{summary['blocked_reason']}",
        "",
        "本测试通过 `invoke_codex_python_sdk_image_edit(source_image_path=...)` 运行，目标是证明这不是 prompt-only，而是真实 LocalImageInput/edit 路径。",
    ]
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def _write_contact_sheet(output_dir: Path, record: dict[str, Any]) -> Path:
    Image, ImageDraw, _ = _pil()
    source = output_dir / "source_reference.jpg"
    generated = Path(str(record.get("image_path") or ""))
    thumb_w = 520
    thumb_h = 293
    label_h = 48
    margin = 18
    sheet = Image.new("RGB", (margin * 3 + thumb_w * 2, margin * 2 + label_h + thumb_h), (247, 248, 250))
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, margin), "source reference / LocalImageInput", fill=(15, 23, 42), font=_font(16))
    draw.text((margin * 2 + thumb_w, margin), f"generated / {record['status']}", fill=(15, 23, 42), font=_font(16))
    _paste_thumb(sheet, source, margin, margin + label_h, thumb_w, thumb_h)
    if generated.is_file():
        _paste_thumb(sheet, generated, margin * 2 + thumb_w, margin + label_h, thumb_w, thumb_h)
    else:
        draw.rounded_rectangle(
            (margin * 2 + thumb_w, margin + label_h, margin * 2 + thumb_w * 2, margin + label_h + thumb_h),
            radius=8,
            fill=(226, 232, 240),
            outline=(203, 213, 225),
        )
        draw.text((margin * 2 + thumb_w + 16, margin + label_h + 18), "missing generated image", fill=(148, 27, 27), font=_font(16))
    path = output_dir / "contact_sheet.jpg"
    sheet.save(path, quality=92)
    return path


def _paste_thumb(sheet: Any, path: Path, x: int, y: int, width: int, height: int) -> None:
    Image, ImageDraw, _ = _pil()
    draw = ImageDraw.Draw(sheet)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=8, fill=(226, 232, 240), outline=(203, 213, 225))
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        ox = x + (width - image.width) // 2
        oy = y + (height - image.height) // 2
        sheet.paste(image, (ox, oy))


def _font(size: int) -> Any:
    _, _, ImageFont = _pil()
    for candidate in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/arial.ttf"):
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


def _original_source_image_path(output_dir: Path) -> str:
    payload_path = output_dir / "payload.json"
    if not payload_path.is_file():
        return ""
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str(payload.get("original_source_image_path") or "")


if __name__ == "__main__":
    raise SystemExit(main())
