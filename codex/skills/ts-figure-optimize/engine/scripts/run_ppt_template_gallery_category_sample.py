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

from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.codex_python_sdk_imagegen import (  # noqa: E402
    CodexPythonSdkImageGenError,
    invoke_codex_python_sdk_imagegen,
)
from drawai.slide_image_prompt import build_slide_image_generation_prompt  # noqa: E402
from drawai.slide_image_strategy import template_registry_summary  # noqa: E402


DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "ppt_template_gallery_category_sample"
USER_PROMPT = "生成《AI Agent 工作流如何接入企业文档体系》的PPT"


SELECTED_TEMPLATES: list[dict[str, str]] = [
    {
        "category": "专业商务/咨询",
        "template_id": "mckinsey_boardroom",
        "reason": "结论先行、管理层汇报、路线图/决策结构代表。",
    },
    {
        "category": "专业商务/咨询",
        "template_id": "bcg_strategy_map",
        "reason": "战略地图、能力分层、机会评估代表。",
    },
    {
        "category": "科技/AI 产品",
        "template_id": "openai_minimal",
        "reason": "AI 产品极简发布、能力概览代表。",
    },
    {
        "category": "科技/AI 产品",
        "template_id": "developer_docs",
        "reason": "架构说明、API/工作流上手代表。",
    },
    {
        "category": "数据/媒体",
        "template_id": "economist_data_story",
        "reason": "数据叙事、图表解释、证据页代表。",
    },
    {
        "category": "数据/媒体",
        "template_id": "infographic_dashboard",
        "reason": "指标看板、运营状态、信息图代表。",
    },
    {
        "category": "学术/教学",
        "template_id": "nature_paper_briefing",
        "reason": "论文/高质量学术汇报的结构化论证代表。",
    },
    {
        "category": "学术/教学",
        "template_id": "courseware_explainer",
        "reason": "课程讲解、概念拆解、学习路径代表。",
    },
    {
        "category": "潮流视觉",
        "template_id": "swiss_grid",
        "reason": "严谨网格、报告排版、现代主义代表。",
    },
    {
        "category": "潮流视觉",
        "template_id": "bento_grid",
        "reason": "能力总览、模块展示、产品感代表。",
    },
    {
        "category": "卡通/轻视觉",
        "template_id": "blue_robot_learning",
        "reason": "轻松学习、卡通教学、儿童/大众化解释代表。",
    },
    {
        "category": "卡通/轻视觉",
        "template_id": "comic_manga_classroom",
        "reason": "漫画课堂、分镜讲解、对话式教学代表。",
    },
]


DECK_PAGES: list[dict[str, Any]] = [
    {
        "page_id": "01_overview",
        "page_title": "接入总览",
        "slide_type": "overview",
        "visible_text_blocks": {
            "title": "AI Agent 工作流如何接入企业文档体系",
            "takeaway": "不是把文档丢给模型，而是把知识源、权限、检索和评估接成可控闭环。",
            "labels": ["文档接入", "知识治理", "权限边界", "Agent 编排", "持续评估"],
        },
        "page_brief": (
            "总览页：解释企业文档体系接入 Agent 的整体逻辑。重点展示从文档源到知识索引、"
            "再到 Agent 工作流和治理闭环的高层结构。"
        ),
    },
    {
        "page_id": "02_document_ingestion",
        "page_title": "文档接入流程",
        "slide_type": "process",
        "visible_text_blocks": {
            "title": "文档接入流程",
            "takeaway": "先把文档变成可检索、可追溯、可授权的知识单元，再交给 Agent 调用。",
            "labels": ["采集", "清洗分块", "元数据标注", "向量索引", "权限绑定", "质量检查"],
        },
        "page_brief": (
            "流程页：展示文档采集、清洗分块、元数据标注、向量索引、权限绑定和质量检查。"
            "可以使用横向流程、泳道图、节点链路或模板适配的等价结构。"
        ),
    },
    {
        "page_id": "03_agent_workflow",
        "page_title": "Agent 工作流架构",
        "slide_type": "architecture",
        "visible_text_blocks": {
            "title": "Agent 工作流架构",
            "takeaway": "Agent 需要在意图识别、检索增强、工具调用和引用回溯之间保持状态。",
            "labels": ["用户问题", "意图识别", "检索增强", "工具调用", "答案生成", "引用回溯", "人工反馈"],
        },
        "page_brief": (
            "架构页：展示用户问题如何经过意图识别、RAG 检索、工具调用、答案生成、引用回溯和反馈。"
            "结构要能看出工作流，不要只做抽象装饰。"
        ),
    },
    {
        "page_id": "04_governance",
        "page_title": "治理与上线闭环",
        "slide_type": "governance",
        "visible_text_blocks": {
            "title": "治理与上线闭环",
            "takeaway": "上线后要持续监控来源可信、权限越界、风险回答和失败样例。",
            "labels": ["来源可信", "权限控制", "风险拦截", "效果评估", "灰度上线", "反馈复盘"],
        },
        "page_brief": (
            "治理页：展示权限控制、来源可信、风险拦截、效果评估、灰度上线和反馈复盘。"
            "可以做路线图、控制矩阵、闭环图或总结页。"
        ),
    },
]


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    templates = SELECTED_TEMPLATES[: args.template_limit] if args.template_limit else SELECTED_TEMPLATES
    pages = DECK_PAGES[: args.pages_per_template]
    registry_by_id = {item["id"]: item for item in template_registry_summary()}

    runtime_config: dict[str, object] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model

    report: dict[str, Any] = {
        "schema": "drawai.ppt_template_gallery_category_sample.v1",
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "user_prompt": USER_PROMPT,
        "template_count": len(templates),
        "pages_per_template": len(pages),
        "prompt_only": bool(args.prompt_only),
        "openai_api_key_used": False,
        "templates": [],
    }
    _write_json(output_dir / "summary.json", report)

    started_at = time.time()
    blocked_reason = ""
    for template_index, template in enumerate(templates, start=1):
        template_id = template["template_id"]
        template_meta = registry_by_id.get(template_id, {})
        template_dir = output_dir / f"{template_index:02d}_{template_id}"
        template_dir.mkdir(parents=True, exist_ok=True)
        template_record: dict[str, Any] = {
            "template_id": template_id,
            "template_name": template_meta.get("name") or template_id,
            "category": template["category"],
            "reason": template["reason"],
            "template_dir": str(template_dir),
            "pages": [],
        }

        for page_index, page in enumerate(pages, start=1):
            page_dir = template_dir / f"{page_index:02d}_{page['page_id']}"
            existing = None if args.force else _load_existing_record(page_dir)
            if existing is not None:
                template_record["pages"].append(existing)
                continue

            record = _write_prompt_only_record(
                output_dir=output_dir,
                template=template,
                template_meta=template_meta,
                page=page,
                page_dir=page_dir,
                page_index=page_index,
                page_count=len(pages),
            )
            if args.prompt_only:
                template_record["pages"].append(record)
                continue
            if blocked_reason:
                record["status"] = "prompt_only_after_blocker"
                record["blocked_reason"] = blocked_reason
                _write_json(page_dir / "record.json", record)
                template_record["pages"].append(record)
                continue
            try:
                record = _generate_page(
                    record=record,
                    page_dir=page_dir,
                    runtime_config=runtime_config,
                )
            except Exception as exc:  # noqa: BLE001 - preserve partial outputs for long gallery runs.
                blocked_reason = f"{type(exc).__name__}: {exc}"
                record["status"] = "blocked"
                record["blocked_reason"] = blocked_reason
                _write_json(page_dir / "record.json", record)
            template_record["pages"].append(record)
            _write_json(output_dir / "summary.json", {**report, "templates": [*report["templates"], template_record]})

        template_images = [_first_image_path(page_record) for page_record in template_record["pages"]]
        template_images = [path for path in template_images if path is not None]
        if template_images:
            template_record["contact_sheet_path"] = str(_write_contact_sheet(
                template_dir / "contact_sheet.jpg",
                template_record["pages"],
                title=f"{template_id} / {template['category']}",
                columns=2,
            ))
        report["templates"].append(template_record)
        _write_json(output_dir / "summary.json", report)

    image_records = [page for template in report["templates"] for page in template["pages"] if _first_image_path(page)]
    if image_records:
        report["contact_sheet_path"] = str(_write_contact_sheet(
            output_dir / "contact_sheet.jpg",
            image_records,
            title="PPT template gallery category sample",
            columns=4,
        ))
    if blocked_reason:
        report["status"] = "blocked_partial" if image_records else "blocked"
        report["blocked_reason"] = blocked_reason
    else:
        report["status"] = "prompt_only" if args.prompt_only else "ok"
    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_json(output_dir / "summary.json", report)
    _write_markdown_report(output_dir, report)
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 2 if report["status"] == "blocked" else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a category-sampled PPT template gallery.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--pages-per-template", type=int, default=4)
    parser.add_argument("--template-limit", type=int, default=0)
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=480.0)
    parser.add_argument("--prompt-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _base_payload(
    *,
    template: dict[str, str],
    template_meta: dict[str, Any],
    page: dict[str, Any],
    page_index: int,
    page_count: int,
) -> dict[str, Any]:
    template_id = template["template_id"]
    visible_text = page["visible_text_blocks"]
    prompt = (
        f"用户输入：{USER_PROMPT}\n"
        f"请生成第 {page_index}/{page_count} 页：{page['page_title']}。\n"
        f"{page['page_brief']}\n"
        f"页面标题：{visible_text['title']}\n"
        f"核心结论：{visible_text['takeaway']}\n"
        f"栏目标签：{'、'.join(visible_text['labels'])}\n"
        f"使用模板 {template_id} 的视觉系统。该模板用途：{template_meta.get('best_for') or 'PPT presentation'}。"
        f"视觉方向：{template_meta.get('visual_direction') or 'template-specific slide design'}。"
        f"本页是连续 deck 的第 {page_index}/{page_count} 页，必须与同模板其他页面保持色彩、字体层级、图形语言和边距一致。"
    )
    return {
        "prompt": prompt,
        "size": "2048x1152",
        "quality": "high",
        "background": "opaque",
        "output_format": "png",
        "n": 1,
        "template_id": template_id,
        "rendering_mode": "baked_text",
        "slide_type": page["slide_type"],
        "audience": "企业管理层、知识管理团队、AI 产品与技术团队",
        "drawai_postprocess": [
            "文本区域保持高对比，方便 OCR 识别。",
            "模块边界清晰，方便 SAM/DrawAI 后续可编辑重建。",
            "避免将语义文字压在复杂纹理、强噪声或低对比渐变上。",
        ],
        "quality_gates": [
            "必须能看出这是连续 deck 的一页。",
            "必须包含标题、核心结论/说明、结构化内容区。",
            "不要编造公司名、真实客户案例、市场规模、年份、benchmark 或未给定数字。",
        ],
    }


def _write_prompt_only_record(
    *,
    output_dir: Path,
    template: dict[str, str],
    template_meta: dict[str, Any],
    page: dict[str, Any],
    page_dir: Path,
    page_index: int,
    page_count: int,
) -> dict[str, Any]:
    page_dir.mkdir(parents=True, exist_ok=True)
    payload = _base_payload(
        template=template,
        template_meta=template_meta,
        page=page,
        page_index=page_index,
        page_count=page_count,
    )
    prompt = build_slide_image_generation_prompt(payload)
    payload_path = page_dir / "payload.json"
    prompt_path = page_dir / "prompt.txt"
    _write_json(payload_path, payload)
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    record = {
        "schema": "drawai.ppt_template_gallery_category_sample.record.v1",
        "status": "prompt_only",
        "operation": "generate",
        "openai_api_key_used": False,
        "template_id": template["template_id"],
        "category": template["category"],
        "page_id": page["page_id"],
        "page_title": page["page_title"],
        "page_index": page_index,
        "page_count": page_count,
        "user_prompt": USER_PROMPT,
        "output_dir": str(output_dir),
        "case_dir": str(page_dir),
        "payload_path": str(payload_path),
        "prompt_path": str(prompt_path),
        "image_path": "",
        "generation": None,
        "quality_notes": [],
    }
    _write_json(page_dir / "record.json", record)
    return record


def _generate_page(
    *,
    record: dict[str, Any],
    page_dir: Path,
    runtime_config: dict[str, object],
) -> dict[str, Any]:
    prompt = Path(record["prompt_path"]).read_text(encoding="utf-8")
    result = invoke_codex_python_sdk_imagegen(
        prompt=prompt,
        output_dir=page_dir / "generated",
        task_name="drawai.experiment.ppt_template_gallery_category_sample.v1",
        output_stem=f"{record['page_index']:02d}-{record['page_id']}-{record['template_id']}",
        runtime_config=runtime_config,
        trace_path=page_dir / "trace.jsonl",
        isolated_cwd=page_dir / "codex_cwd",
    )
    if not result.images:
        raise CodexPythonSdkImageGenError("Codex image generation returned no images")
    source = result.images[0].path
    target = page_dir / f"{record['page_id']}.png"
    shutil.copy2(source, target)
    record.update(
        {
            "status": "ok",
            "image_path": str(target),
            "generation": result.to_dict(),
            "quality_notes": _basic_image_notes(target),
        }
    )
    _write_json(page_dir / "record.json", record)
    return record


def _basic_image_notes(path: Path) -> list[str]:
    notes: list[str] = []
    try:
        with Image.open(path) as image:
            width, height = image.size
            if width < 1200 or height < 650:
                notes.append(f"low_resolution:{width}x{height}")
            ratio = width / max(1, height)
            if not (1.65 <= ratio <= 1.86):
                notes.append(f"unexpected_aspect_ratio:{ratio:.3f}")
    except OSError as exc:
        notes.append(f"image_open_error:{exc}")
    return notes


def _write_contact_sheet(
    path: Path,
    records: list[dict[str, Any]],
    *,
    title: str,
    columns: int,
) -> Path:
    image_records = [record for record in records if _first_image_path(record)]
    if not image_records:
        raise ValueError("no images for contact sheet")
    thumb_w, thumb_h = 360, 203
    label_h = 54
    gap = 18
    margin = 24
    header_h = 56
    rows = (len(image_records) + columns - 1) // columns
    sheet_w = margin * 2 + columns * thumb_w + (columns - 1) * gap
    sheet_h = margin * 2 + header_h + rows * (thumb_h + label_h) + (rows - 1) * gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    title_font = _font(24)
    small_font = _font(13)
    draw.text((margin, margin), title, fill=(15, 23, 42), font=title_font)
    for index, record in enumerate(image_records):
        row = index // columns
        col = index % columns
        x = margin + col * (thumb_w + gap)
        y = margin + header_h + row * (thumb_h + label_h + gap)
        image_path = _first_image_path(record)
        assert image_path is not None
        try:
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                bg = Image.new("RGB", (thumb_w, thumb_h), (246, 248, 251))
                bg.paste(image, ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2))
                sheet.paste(bg, (x, y))
        except OSError:
            draw.rectangle((x, y, x + thumb_w, y + thumb_h), fill=(254, 226, 226), outline=(220, 38, 38))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline=(203, 213, 225), width=1)
        label = f"{record.get('template_id')} / {record.get('page_title')}"
        status = str(record.get("status") or "")
        draw.text((x, y + thumb_h + 8), label[:46], fill=(15, 23, 42), font=small_font)
        draw.text((x, y + thumb_h + 28), f"{record.get('category')} / {status}", fill=(71, 85, 105), font=small_font)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)
    return path


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _write_markdown_report(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# PPT Template Gallery Category Sample",
        "",
        f"- status: {report.get('status')}",
        f"- user_prompt: {report.get('user_prompt')}",
        f"- output_dir: {report.get('output_dir')}",
        f"- contact_sheet: {report.get('contact_sheet_path', '')}",
        f"- templates: {report.get('template_count')} x {report.get('pages_per_template')} pages",
        f"- openai_api_key_used: {report.get('openai_api_key_used')}",
        "",
        "## Templates",
    ]
    for template in report.get("templates", []):
        ok_count = len([page for page in template.get("pages", []) if page.get("status") == "ok"])
        lines.extend(
            [
                "",
                f"### {template.get('template_id')} / {template.get('category')}",
                f"- reason: {template.get('reason')}",
                f"- pages: {ok_count}/{len(template.get('pages', []))}",
                f"- contact_sheet: {template.get('contact_sheet_path', '')}",
            ]
        )
        for page in template.get("pages", []):
            lines.append(
                f"- {page.get('page_index')}. {page.get('page_title')} [{page.get('status')}]: {page.get('image_path', '')}"
            )
    if report.get("blocked_reason"):
        lines.extend(["", "## Blocker", str(report["blocked_reason"])])
    (output_dir / "summary.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _load_existing_record(page_dir: Path) -> dict[str, Any] | None:
    record_path = page_dir / "record.json"
    if not record_path.exists():
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if record.get("status") == "ok" and _first_image_path(record):
        return record
    if record.get("status") == "prompt_only":
        return None
    return None


def _first_image_path(record: dict[str, Any]) -> Path | None:
    raw = str(record.get("image_path") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    pages = [page for template in report.get("templates", []) for page in template.get("pages", [])]
    return {
        "status": report.get("status"),
        "output_dir": report.get("output_dir"),
        "template_count": report.get("template_count"),
        "page_count": len(pages),
        "ok_count": len([page for page in pages if page.get("status") == "ok"]),
        "contact_sheet_path": report.get("contact_sheet_path"),
        "blocked_reason": report.get("blocked_reason", ""),
    }


if __name__ == "__main__":
    raise SystemExit(main())
