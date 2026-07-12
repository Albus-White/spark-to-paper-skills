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

from drawai.slide_image_prompt import build_slide_image_generation_prompt  # noqa: E402


CASES: list[dict[str, Any]] = [
    {
        "id": "business_mckinsey_rag_decision",
        "label": "商务咨询 / RAG 上线决策",
        "category": "professional_business_consulting",
        "payload": {
            "prompt": "生成一页中文商务咨询风格 PPT 图像：企业知识库 RAG 项目是否应该进入试点上线，面向管理层，给出结论、判断依据、风险和推进路径。",
            "language": "zh",
            "template_id": "mckinsey_boardroom",
            "source_mode": "source_grounded",
            "text_density": "high",
            "visible_text_blocks": {
                "title": "企业 RAG 试点上线决策",
                "takeaway": "先限定高价值场景，再用评测、权限与灰度机制降低上线风险",
                "labels": ["结论先行", "业务价值", "数据权限", "答案评测", "灰度路线"],
            },
            "claims": [
                {"claim": "本页只做定性决策结构，不展示未提供来源的 ROI、成本节省或准确率数字。"},
                {"claim": "上线风险主要来自权限边界、检索质量、答案可追溯性和业务场景不清。"},
            ],
            "sources": [
                {
                    "title": "企业 RAG 项目复盘摘要",
                    "evidence": "Pilot should start from constrained workflows with measurable answer quality and permission controls.",
                }
            ],
            "visual_style": "董事会咨询单页，顶部一句结论，主体使用议题树、决策矩阵、风险栏和三阶段路线图；中文文字要充分，避免技术管线占满页面。",
        },
    },
    {
        "id": "tech_openai_agent_workflow",
        "label": "科技产品 / 多模态 Agent 工作流",
        "category": "tech_ai_product",
        "payload": {
            "prompt": "生成一页中文 AI 产品发布风格 PPT 图像：多模态 Agent 如何从用户目标、文档、截图和工具调用中形成可执行工作流。",
            "language": "zh",
            "template_id": "openai_minimal",
            "source_mode": "prompt_only",
            "text_density": "medium-high",
            "visible_text_blocks": {
                "title": "多模态 Agent 工作流",
                "takeaway": "把目标、上下文、工具和记忆组织成可追踪的任务闭环",
                "labels": ["用户目标", "多模态上下文", "计划分解", "工具调用", "结果校验", "任务记忆"],
            },
            "claims": [
                {"claim": "没有提供具体产品参数，因此不得展示真实模型排名、发布日期或 benchmark 分数。"},
            ],
            "visual_style": "极简 AI keynote，白底或深浅对比，中心是任务闭环图；要有完整中文标题、栏目和 3-5 条解释，不要只有空白布局。",
        },
    },
    {
        "id": "data_economist_inference_cost",
        "label": "数据媒体 / 推理成本杠杆",
        "category": "data_media",
        "payload": {
            "prompt": "生成一页中文数据媒体风格 PPT 图像：解释 AI 应用推理成本如何受缓存命中、批处理效率和模型路由影响；图表只使用提供的数据。",
            "language": "zh",
            "template_id": "economist_data_story",
            "source_mode": "data_driven",
            "text_density": "medium-high",
            "visible_text_blocks": {
                "title": "推理成本的三类杠杆",
                "takeaway": "缓存命中率、批处理效率与模型路由共同决定单位请求成本",
                "labels": ["缓存命中率", "批处理效率", "模型路由", "相对成本", "场景数据"],
            },
            "data_sources": {
                "note": "Synthetic scenario data supplied for visual validation; label as scenario data, not industry average.",
                "rows": [
                    {"scenario": "基线", "relative_cost": 1.0, "cache_hit": "0%", "batching": "低"},
                    {"scenario": "加入缓存", "relative_cost": 0.72, "cache_hit": "35%", "batching": "低"},
                    {"scenario": "缓存+批处理", "relative_cost": 0.55, "cache_hit": "35%", "batching": "中"},
                    {"scenario": "智能路由", "relative_cost": 0.41, "cache_hit": "35%", "batching": "中"},
                ],
            },
            "claims": [
                {"claim": "图表只展示用户提供的相对成本场景数据。"},
                {"claim": "不得把测试数据伪装成行业平均值或真实厂商数据。"},
            ],
            "visual_style": "财经数据报道风格，大图表为主，右侧用解释卡片；有清楚中文注释和来源说明，不要生成无来源排行。",
        },
    },
    {
        "id": "academic_nature_safety_briefing",
        "label": "学术教学 / 多模态安全论文导读",
        "category": "academic_teaching",
        "payload": {
            "prompt": "生成一页中文学术论文汇报 PPT 图像：从一篇关于多模态安全评测的论文做组会开场页，突出研究问题、方法框架、证据结构和讨论问题。",
            "language": "zh",
            "template_id": "nature_paper_briefing",
            "source_mode": "source_grounded",
            "text_density": "medium-high",
            "visible_text_blocks": {
                "title": "多模态安全评测：组会导读",
                "takeaway": "重点不是单一分数，而是风险场景、攻击路径与评测边界",
                "labels": ["研究问题", "方法框架", "风险场景", "证据片段", "讨论问题"],
            },
            "sources": [
                {
                    "title": "用户提供的论文笔记",
                    "evidence": "The paper studies multimodal safety evaluation with scenario prompts, attack surfaces, and limits of aggregate scores.",
                }
            ],
            "claims": [
                {"claim": "不得编造论文作者、会议名称、DOI 或引用编号。"},
            ],
            "visual_style": "高影响力论文 briefing，中心是 claim-method-evidence 结构，配泛化论文图、方法框架和讨论卡；中文解释要可读。",
        },
    },
    {
        "id": "trend_bento_drawai_pipeline",
        "label": "潮流视觉 / DrawAI 能力总览",
        "category": "trend_visual",
        "payload": {
            "prompt": "生成一页中文 Bento 网格风格 PPT 图像：介绍 DrawAI 从高质量 PPT 图像生成到可编辑重建的核心流程。",
            "language": "zh",
            "template_id": "bento_grid",
            "source_mode": "source_grounded",
            "text_density": "medium",
            "visible_text_blocks": {
                "title": "DrawAI：从图像到可编辑 PPT",
                "takeaway": "先追求首图质量，再用结构化重建获得可编辑性",
                "labels": ["PPT 图像生成", "OCR 识别", "元素分层", "布局重建", "人工校正", "质量检查"],
            },
            "claims": [
                {"claim": "当前第一阶段使用 baked_text 图像生成，后续由 DrawAI 做可编辑处理。"},
                {"claim": "不得承诺 100% 自动完美还原。"},
            ],
            "visual_style": "现代 bento grid，必须有一个主卡和多个功能卡，每个卡有中文标题和解释；不要做成只有图标的空白网格。",
        },
    },
    {
        "id": "cartoon_blue_robot_ai_learning",
        "label": "IP 安全卡通 / 蓝白机器人学习",
        "category": "ip_safe_cartoon",
        "payload": {
            "prompt": "生成一页中文儿童学习 PPT 图像：用一个原创蓝白圆润机器人老师讲解“AI 助手如何记住长期任务”。只体现蓝白圆润卡通、未来小道具和儿童学习氛围。",
            "language": "zh",
            "template_id": "blue_robot_learning",
            "source_mode": "prompt_only",
            "text_density": "medium",
            "visible_text_blocks": {
                "title": "AI 助手如何记住任务",
                "takeaway": "把目标、线索和下一步记录下来，才能连续完成长期任务",
                "labels": ["目标卡片", "线索收集", "任务记忆", "下一步", "复习检查"],
            },
            "must_avoid": [
                "不要生成哆啦A梦本体",
                "不要精确复刻任何受版权保护角色",
                "不要铃铛、魔法口袋、商标符号或相同脸部比例",
            ],
            "claims": [
                {"claim": "这是原创蓝白机器人学习风，不是任何现有角色。"},
            ],
            "visual_style": "原创蓝白圆润机器人老师，未来小道具，日式儿童漫画分镜氛围；中文教学文字清楚，不要英文标题。",
        },
    },
    {
        "id": "infra_cyberpunk_agent_stack",
        "label": "科技基础设施 / Agent 控制平面",
        "category": "tech_ai_product",
        "payload": {
            "prompt": "生成一页中文赛博基础设施风格 PPT 图像：解释 Agent 系统中的控制平面、工具网关、权限策略和执行日志如何协同。",
            "language": "zh",
            "template_id": "cyberpunk_infra",
            "source_mode": "prompt_only",
            "text_density": "medium-high",
            "visible_text_blocks": {
                "title": "Agent 控制平面",
                "takeaway": "权限、工具、日志和回滚机制决定 Agent 是否可控",
                "labels": ["控制平面", "工具网关", "权限策略", "执行日志", "回滚机制", "风险告警"],
            },
            "claims": [
                {"claim": "没有提供真实系统日志、IP 地址或安全事件，因此只使用抽象拓扑和泛化标签。"},
            ],
            "visual_style": "黑底霓虹基础设施拓扑，中心是控制平面，四周是工具网关、权限、日志、告警；中文标签高对比，不要伪终端垃圾文字。",
        },
    },
]


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

    selected_cases = CASES[: args.limit] if args.limit else CASES
    started_at = time.time()
    report: dict[str, Any] = {
        "schema": "drawai.codex_slide_imagegen_expanded_style_cases.v1",
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "case_count": len(selected_cases),
        "cases": [],
    }
    _write_json(output_dir / "summary.json", report)

    blocked_reason = ""
    for index, case in enumerate(selected_cases, start=1):
        case_dir = output_dir / f"{index:02d}_{case['id']}"
        record = None if args.force else _load_existing_record(case_dir)
        if record is None:
            record = _write_prompt_only_record(case, case_dir=case_dir, index=index)
            if not args.prompt_only and not blocked_reason:
                try:
                    record = _run_case(case, case_dir=case_dir, index=index, runtime_config=runtime_config)
                except Exception as exc:  # Keep prompts when quota/login/env fails.
                    blocked_reason = repr(exc)
                    record["status"] = "blocked"
                    record["blocked_reason"] = blocked_reason
                    _write_json(case_dir / "record.json", record)
            elif blocked_reason:
                record["status"] = "prompt_only"
                record["blocked_reason"] = blocked_reason
                _write_json(case_dir / "record.json", record)
        report["cases"].append(record)
        _write_json(output_dir / "summary.json", report)

    completed = [case for case in report["cases"] if _first_image_path(case) is not None]
    if completed:
        report["contact_sheet"] = str(_write_contact_sheet(output_dir, report["cases"]))
    if blocked_reason:
        report["status"] = "blocked" if completed else "prompt_only_blocked"
        report["blocked_reason"] = blocked_reason
    else:
        report["status"] = "ok"
    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_json(output_dir / "summary.json", report)
    _write_markdown_report(output_dir, report)
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 2 if blocked_reason and not completed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate small expanded-style Codex PPT image cases.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "codex_slide_imagegen_expanded_style_cases",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=420.0)
    parser.add_argument("--prompt-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _base_payload(case: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "size": "2048x1152",
        "quality": "high",
        "background": "opaque",
        "output_format": "png",
        "n": 1,
        "rendering_mode": "baked_text",
        "style_candidate_count": 3,
        "style_candidate_index": (index - 1) % 3 + 1,
        **case["payload"],
    }


def _write_prompt_only_record(case: dict[str, Any], *, case_dir: Path, index: int) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    payload = _base_payload(case, index=index)
    prompt = build_slide_image_generation_prompt(payload)
    _write_json(case_dir / "payload.json", payload)
    (case_dir / "improved_prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    record = {
        "id": case["id"],
        "label": case["label"],
        "category": case["category"],
        "template_id": payload["template_id"],
        "topic": payload["visible_text_blocks"]["title"],
        "source_mode": payload["source_mode"],
        "text_density": payload["text_density"],
        "status": "prompt_only",
        "case_dir": str(case_dir),
        "payload_path": str(case_dir / "payload.json"),
        "prompt_path": str(case_dir / "improved_prompt.txt"),
        "image_path": "",
        "generation": None,
        "quality_notes": [],
    }
    _write_json(case_dir / "record.json", record)
    return record


def _run_case(case: dict[str, Any], *, case_dir: Path, index: int, runtime_config: dict[str, object]) -> dict[str, Any]:
    from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_imagegen

    record = _write_prompt_only_record(case, case_dir=case_dir, index=index)
    prompt = (case_dir / "improved_prompt.txt").read_text(encoding="utf-8")
    result = invoke_codex_python_sdk_imagegen(
        prompt=prompt,
        output_dir=case_dir / "generated",
        task_name="drawai.experiment.codex_slide_expanded_style_cases.v1",
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
        if image.width < 1200 or image.height < 675:
            notes.append(f"lower than expected resolution: {image.width}x{image.height}")
        if image.width / max(1, image.height) < 1.5:
            notes.append("aspect ratio may not be 16:9 wide slide")
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
    direct = Path(str(record.get("image_path") or ""))
    if direct.is_file():
        return direct
    generation = record.get("generation") or {}
    for image in generation.get("images", []):
        path = Path(str(image.get("path") or ""))
        if path.is_file():
            return path
    return None


def _write_contact_sheet(output_dir: Path, records: list[dict[str, Any]]) -> Path:
    Image, ImageDraw, _ = _pil()
    thumb_w = 600
    thumb_h = 338
    label_h = 52
    margin = 18
    cols = 2
    rows = (len(records) + cols - 1) // cols
    width = margin * (cols + 1) + cols * thumb_w
    height = margin + rows * (label_h + thumb_h + margin)
    sheet = Image.new("RGB", (width, height), (246, 247, 249))
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    small = _font(14)
    for index, record in enumerate(records):
        row = index // cols
        col = index % cols
        x = margin + col * (thumb_w + margin)
        y = margin + row * (label_h + thumb_h + margin)
        draw.text((x, y), record["label"], fill=(15, 23, 42), font=font)
        draw.text((x, y + 24), f"{record['template_id']} / {record['status']}", fill=(71, 85, 105), font=small)
        _paste_thumb(sheet, _first_image_path(record), x, y + label_h, thumb_w, thumb_h)
    path = output_dir / "contact_sheet.jpg"
    sheet.save(path, quality=92)
    return path


def _paste_thumb(sheet: Image.Image, path: Path | None, x: int, y: int, width: int, height: int) -> None:
    Image, ImageDraw, _ = _pil()
    draw = ImageDraw.Draw(sheet)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=8, fill=(226, 232, 240), outline=(203, 213, 225))
    if path is None:
        draw.text((x + 20, y + 20), "prompt only / missing image", fill=(148, 27, 27), font=_font(18))
        return
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        ox = x + (width - image.width) // 2
        oy = y + (height - image.height) // 2
        sheet.paste(image, (ox, oy))


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


def _write_markdown_report(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Expanded Style Cases",
        "",
        f"- Status: {report.get('status')}",
        f"- Output dir: {report.get('output_dir')}",
        f"- Contact sheet: {report.get('contact_sheet', '')}",
        f"- Blocked reason: {report.get('blocked_reason', '')}",
        "",
        "| Case | Template | Topic | Status | Image | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in report.get("cases", []):
        notes = "; ".join(record.get("quality_notes") or [])
        lines.append(
            "| {label} | `{template}` | {topic} | {status} | {image} | {notes} |".format(
                label=record.get("label", ""),
                template=record.get("template_id", ""),
                topic=record.get("topic", ""),
                status=record.get("status", ""),
                image=record.get("image_path", ""),
                notes=notes,
            )
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "case_count": report.get("case_count"),
        "output_dir": report.get("output_dir"),
        "contact_sheet": report.get("contact_sheet", ""),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "blocked_reason": report.get("blocked_reason", ""),
        "ok_cases": sum(1 for case in report.get("cases", []) if case.get("status") == "ok"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
