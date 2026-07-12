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
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from drawai.codex_python_sdk_imagegen import CodexPythonSdkImageGenError  # noqa: E402
from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_imagegen  # noqa: E402
from drawai.slide_image_prompt import build_slide_image_generation_prompt  # noqa: E402


CASES: list[dict[str, Any]] = [
    {
        "id": "kimi_dark_tech_source_grounded",
        "label": "01 Kimi / 暗色科技 / 资料约束",
        "payload": {
            "prompt": "生成一页中文技术PPT图像：Kimi 系列模型的技术路线与效果讲解，重点讲 MoE 扩展、训练优化、长上下文和 Agent 能力；不要编造 benchmark 分数。",
            "language": "zh",
            "template_id": "dark_tech",
            "source_mode": "source_grounded",
            "text_density": "medium-high",
            "visible_text_blocks": {
                "title": "Kimi 系列模型技术路线",
                "takeaway": "MoE 扩展、训练优化与 Agent 能力是主线",
                "labels": ["MoE 架构", "长上下文", "训练优化", "工具调用", "Agent 能力"],
            },
            "claims": [
                {"claim": "Kimi K2 被公开描述为 MoE 模型。", "source": "用户提供的官方资料摘要"},
                {"claim": "本页不展示未提供来源的 benchmark 分数。", "source": "测试约束"},
            ],
            "sources": [
                {
                    "title": "Kimi K2 官方资料摘要",
                    "url": "https://github.com/MoonshotAI/Kimi-K2",
                    "evidence": "Kimi K2 is described as a Mixture-of-Experts model; exact metrics should only be shown when supplied.",
                }
            ],
            "visual_style": "黑色科技发布会风格，中文标题突出，使用架构流、能力雷达和模块分层，不要出现英文通用标题。",
        },
    },
    {
        "id": "rag_consulting_report_source_grounded",
        "label": "02 RAG / 咨询报告 / 决策页",
        "payload": {
            "prompt": "生成一页中文咨询报告风格PPT图像：企业知识库 RAG 项目是否应该上线，面向管理层，给出决策结构、风险和推进建议。",
            "language": "zh",
            "template_id": "consulting_report",
            "source_mode": "source_grounded",
            "text_density": "high",
            "visible_text_blocks": {
                "title": "企业 RAG 上线决策",
                "takeaway": "先限定高价值场景，再用评测与权限治理降低上线风险",
                "labels": ["业务价值", "数据权限", "答案评测", "灰度上线", "治理闭环"],
            },
            "claims": [
                {"claim": "RAG 上线风险主要来自权限边界、检索质量、答案可追溯性和业务场景不清。", "source": "用户输入的项目经验摘要"},
                {"claim": "没有提供 ROI 数字，因此页面只做定性决策结构，不画具体收益数值。", "source": "测试约束"},
            ],
            "sources": [
                {
                    "title": "企业 RAG 项目复盘摘要",
                    "evidence": "Pilot should start from constrained workflows with measurable answer quality and permission controls.",
                }
            ],
            "visual_style": "管理咨询单页，顶部一句结论，下面用决策矩阵、风险栏、推进路线图表达；避免技术管线占满页面。",
        },
    },
    {
        "id": "ai_infra_data_journalism_data_driven",
        "label": "03 AI 成本 / 数据新闻 / 数据驱动",
        "payload": {
            "prompt": "生成一页中文数据新闻风格PPT图像：说明 AI 应用推理成本如何被缓存、批处理和模型路由影响。图表只能使用提供的数据。",
            "language": "zh",
            "template_id": "data_journalism",
            "source_mode": "data_driven",
            "text_density": "medium-high",
            "visible_text_blocks": {
                "title": "推理成本的三类杠杆",
                "takeaway": "缓存命中率、批处理效率和模型路由共同决定单位请求成本",
                "labels": ["缓存命中率", "批处理效率", "模型路由", "单位请求成本"],
            },
            "data_sources": {
                "note": "Synthetic test data supplied by user for chart rendering; values are illustrative and should be labeled as scenario data.",
                "rows": [
                    {"scenario": "Baseline", "relative_cost": 1.0, "cache_hit": "0%", "batching": "low"},
                    {"scenario": "Cache", "relative_cost": 0.72, "cache_hit": "35%", "batching": "low"},
                    {"scenario": "Cache+Batch", "relative_cost": 0.55, "cache_hit": "35%", "batching": "medium"},
                    {"scenario": "Routed", "relative_cost": 0.41, "cache_hit": "35%", "batching": "medium"},
                ],
            },
            "claims": [
                {"claim": "本页图表只展示用户提供的相对成本场景数据。", "source": "测试数据源"},
                {"claim": "不要把测试数据伪装成行业平均值或真实厂商数据。", "source": "测试约束"},
            ],
            "visual_style": "像高质量财经数据报道：大图表为主，右侧用解释卡片，不要生成无来源的轴标签或排行榜。",
        },
    },
    {
        "id": "paper_notebooklm_briefing",
        "label": "04 论文汇报 / 资料简报",
        "payload": {
            "prompt": "生成一页中文学术论文汇报PPT图像：从一篇关于多模态安全评测的论文做组会开场页，突出研究问题、方法框架和评测风险。",
            "language": "zh",
            "template_id": "notebooklm_briefing",
            "source_mode": "source_grounded",
            "text_density": "medium-high",
            "visible_text_blocks": {
                "title": "多模态安全评测：组会导读",
                "takeaway": "核心不是单一分数，而是风险场景、攻击路径与评测边界",
                "labels": ["研究问题", "评测框架", "风险场景", "证据片段", "讨论问题"],
            },
            "sources": [
                {
                    "title": "用户提供的论文笔记",
                    "evidence": "The paper studies multimodal safety evaluation with scenario-based prompts, attack surfaces, and limitations of aggregate scores.",
                },
                {
                    "title": "用户提供的 figure legend 摘要",
                    "evidence": "The method compares input modality, risk category, model behavior, and evidence traceability.",
                },
            ],
            "claims": [
                {"claim": "该页应呈现论文导读结构，而不是编造论文作者、会议或引用编号。", "source": "测试约束"},
            ],
            "visual_style": "NotebookLM 资料简报风格，像文档卡片和问题卡片的合成页，保留学术感但不要过白过素。",
        },
    },
    {
        "id": "drawai_product_launch_brand_template",
        "label": "05 DrawAI / 产品发布 / 品牌模板",
        "payload": {
            "prompt": "生成一页中文产品发布PPT图像：介绍 DrawAI 从 PPT 图像生成到可编辑重建的工作流，强调先生成高质量位图，再进行可编辑元素处理。",
            "language": "zh",
            "template_id": "product_launch",
            "source_mode": "brand_template",
            "text_density": "medium",
            "visible_text_blocks": {
                "title": "DrawAI 图像到可编辑 PPT",
                "takeaway": "先追求首图质量，再用结构化重建获得可编辑性",
                "labels": ["高质量位图", "文本识别", "元素分层", "可编辑重建", "人工校正"],
            },
            "brand": {
                "name": "DrawAI",
                "palette": "深色基底、青绿色强调、清晰白色中文正文",
                "tone": "高级、工具型、可信赖，不做营销空话",
            },
            "claims": [
                {"claim": "DrawAI 后续流程会处理可编辑重建，因此第一阶段允许 baked_text。", "source": "当前产品方案"},
                {"claim": "不要承诺 100% 自动完美还原，保留人工校正和 QA。", "source": "测试约束"},
            ],
            "visual_style": "产品发布单页，有一个清晰中心工作流：Prompt -> PPT 图像 -> OCR/分层 -> 可编辑 PPT；视觉要比普通流程图更高级。",
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
        "schema": "drawai.codex_slide_imagegen_ui_strategy_cases.v1",
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "case_count": len(selected_cases),
        "cases": [],
    }
    _write_json(output_dir / "ui_strategy_cases_report.json", report)

    for index, case in enumerate(selected_cases, start=1):
        case_dir = output_dir / f"{index:02d}_{case['id']}"
        record = None if args.force else _load_existing_record(case_dir)
        if record is None:
            try:
                record = _run_case(case, case_dir=case_dir, index=index, runtime_config=runtime_config)
            except CodexPythonSdkImageGenError as exc:
                report["status"] = "blocked"
                report["blocked_reason"] = str(exc)
                _write_json(output_dir / "ui_strategy_cases_report.json", report)
                print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
                return 2
        report["cases"].append(record)
        _write_json(output_dir / "ui_strategy_cases_report.json", report)

    report["status"] = "ok"
    report["contact_sheet"] = str(_write_contact_sheet(output_dir, report["cases"]))
    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_json(output_dir / "ui_strategy_cases_report.json", report)
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate five UI-strategy PPT image cases with Codex imageGeneration.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "outputs" / "codex_slide_imagegen_ui_strategy_cases")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=420.0)
    return parser.parse_args()


def _run_case(case: dict[str, Any], *, case_dir: Path, index: int, runtime_config: dict[str, object]) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    payload = {
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
    prompt = build_slide_image_generation_prompt(payload)
    _write_json(case_dir / "payload.json", payload)
    (case_dir / "improved_prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    result = invoke_codex_python_sdk_imagegen(
        prompt=prompt,
        output_dir=case_dir / "generated",
        task_name="drawai.experiment.codex_slide_ui_strategy_cases.v1",
        output_stem=f"{index:02d}-{case['id']}",
        runtime_config=runtime_config,
        trace_path=case_dir / "trace.jsonl",
        isolated_cwd=case_dir / "codex_cwd",
    )
    record = {
        "id": case["id"],
        "label": case["label"],
        "template_id": payload["template_id"],
        "source_mode": payload["source_mode"],
        "text_density": payload["text_density"],
        "case_dir": str(case_dir),
        "payload_path": str(case_dir / "payload.json"),
        "prompt_path": str(case_dir / "improved_prompt.txt"),
        "generation": result.to_dict(),
    }
    _write_json(case_dir / "record.json", record)
    return record


def _load_existing_record(case_dir: Path) -> dict[str, Any] | None:
    path = case_dir / "record.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return record if _first_image_path(record) is not None else None


def _first_image_path(record: dict[str, Any]) -> Path | None:
    for image in record.get("generation", {}).get("images", []):
        path = Path(str(image.get("path") or ""))
        if path.is_file():
            return path
    return None


def _write_contact_sheet(output_dir: Path, records: list[dict[str, Any]]) -> Path:
    thumb_w = 600
    thumb_h = 338
    label_h = 38
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
        draw.text((x, y + 22), f"{record['template_id']} / {record['source_mode']}", fill=(71, 85, 105), font=small)
        _paste_thumb(sheet, _first_image_path(record), x, y + label_h, thumb_w, thumb_h)
    path = output_dir / "contact_sheet.jpg"
    sheet.save(path, quality=92)
    return path


def _paste_thumb(sheet: Image.Image, path: Path | None, x: int, y: int, width: int, height: int) -> None:
    draw = ImageDraw.Draw(sheet)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=8, fill=(226, 232, 240), outline=(203, 213, 225))
    if path is None:
        draw.text((x + 20, y + 20), "missing image", fill=(148, 27, 27), font=_font(18))
        return
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        ox = x + (width - image.width) // 2
        oy = y + (height - image.height) // 2
        sheet.paste(image, (ox, oy))


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        path = Path(candidate)
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "case_count": report.get("case_count"),
        "output_dir": report.get("output_dir"),
        "contact_sheet": report.get("contact_sheet", ""),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "blocked_reason": report.get("blocked_reason", ""),
    }


if __name__ == "__main__":
    raise SystemExit(main())
