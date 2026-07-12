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


def _slide(slide_id: str, title: str, takeaway: str, labels: list[str], body: list[str]) -> dict[str, Any]:
    return {
        "id": slide_id,
        "title": title,
        "takeaway": takeaway,
        "labels": labels,
        "body": body,
    }


DECKS: list[dict[str, Any]] = [
    {
        "id": "kimi_technical_roadmap",
        "label": "Kimi 系列模型技术与效果讲解",
        "template_id": "dark_tech",
        "source_mode": "source_grounded",
        "text_density": "medium-high",
        "intent": "technical",
        "audience": "AI 技术团队、产品负责人、研究生组会",
        "style": "暗色科技发布会风格，黑色背景、青绿/蓝色强调、中文标题醒目、架构流和能力模块贯穿全 deck。",
        "deck_context": "连续 10 页讲清 Kimi 系列模型：定位、架构、训练、长上下文、Agent、效果、限制、落地建议。不要编造 benchmark 分数。",
        "claims": [
            "Kimi/Kimi K2 相关事实必须来自用户提供的公开资料摘要；没有来源的参数、分数、日期和排名不要展示。",
            "Kimi K2 可作为 MoE 与 Agent 能力讲解案例；精确数值只在来源中明确提供时展示。",
        ],
        "sources": [
            {
                "title": "Kimi/Kimi K2 官方资料摘要",
                "url": "https://github.com/MoonshotAI/Kimi-K2",
                "evidence": "Use only supplied public-description facts; do not invent benchmark values or release claims.",
            }
        ],
        "slides": [
            _slide("01_title", "Kimi 系列模型全景", "从长上下文到 Agent 能力，Kimi 的主线是扩展上下文、提升推理与增强工具使用", ["定位", "演进", "能力地图"], ["用一页建立全 deck 的技术主线", "用模块地图而非排名榜表达能力"]),
            _slide("02_positioning", "模型定位与用户场景", "Kimi 的价值不只在聊天，而在长文档理解、复杂任务拆解和工具调用", ["长文档", "研究助理", "代码与工具", "Agent 工作流"], ["区分普通对话、知识处理和任务执行", "避免把未知场景包装成已验证能力"]),
            _slide("03_architecture", "MoE 架构与稀疏激活", "MoE 用总参数规模承载知识容量，用稀疏激活控制推理成本", ["专家路由", "稀疏激活", "容量扩展", "计算效率"], ["画模块化专家路由示意", "不展示未提供来源的具体专家数量或分数"]),
            _slide("04_training", "训练与优化路线", "训练优化关注稳定性、效率与长程能力，而不是单一指标冲刺", ["数据配比", "优化器", "稳定训练", "能力对齐"], ["用训练管线表达数据、优化、评测闭环", "不要编造训练 token 或硬件规模"]),
            _slide("05_context", "长上下文能力的产品意义", "长上下文把模型从短问答推进到资料阅读、上下文追踪和多步任务", ["资料载入", "上下文检索", "证据定位", "长程追踪"], ["强调输入压缩和证据定位", "用文档堆栈和上下文窗口视觉"]),
            _slide("06_agent", "Agent 与工具调用能力", "Agent 能力来自规划、工具使用、状态维护和结果校验的组合", ["任务规划", "工具调用", "状态记忆", "自检回路"], ["展示 Planner-Tool-State-Check 闭环", "不要画假终端日志"]),
            _slide("07_effects", "效果评估应该怎么看", "缺少来源时不展示分数；可用任务类型、能力边界和证据等级替代排名", ["任务覆盖", "证据等级", "边界条件", "对比维度"], ["用定性评估矩阵，不编 benchmark", "标注来源质量"]),
            _slide("08_risks", "风险与边界", "长上下文和 Agent 能力越强，越需要关注幻觉、权限、工具安全和成本", ["幻觉", "权限", "工具安全", "成本"], ["画风险雷达和控制点", "风险描述只基于通用工程事实"]),
            _slide("09_deployment", "企业落地架构", "企业接入应围绕资料治理、工具权限、评测集和审计链路设计", ["资料治理", "权限网关", "评测集", "审计日志"], ["用企业落地拓扑表达", "不画真实厂商 UI"]),
            _slide("10_summary", "结论：从模型能力到工作流能力", "Kimi 类模型的真正价值在于把模型能力组织成可靠任务工作流", ["主线回顾", "落地建议", "下一步"], ["收束为三条 takeaway", "保持暗色科技封面风格"]),
        ],
    },
    {
        "id": "enterprise_rag_decision",
        "label": "企业 RAG 上线决策与治理",
        "template_id": "consulting_report",
        "source_mode": "source_grounded",
        "text_density": "high",
        "intent": "business",
        "audience": "企业管理层、AI 项目负责人、数据治理团队",
        "style": "管理咨询报告风格，白底、深蓝强调、结论先行、矩阵/路线图/风险栏贯穿全 deck。",
        "deck_context": "连续 10 页解释企业知识库 RAG 是否应该上线：价值、场景、数据、评测、权限、风险、路线图和治理闭环。",
        "claims": [
            "RAG 上线风险主要来自场景不清、数据权限、检索质量、答案可追溯性和持续评测不足。",
            "没有提供 ROI 数字时，只做定性决策结构，不画具体收益数值。",
        ],
        "sources": [
            {
                "title": "企业 RAG 项目复盘摘要",
                "evidence": "Pilot should start from constrained workflows with measurable answer quality and permission controls.",
            }
        ],
        "slides": [
            _slide("01_exec", "RAG 上线决策总览", "先限定高价值场景，再用评测与权限治理降低上线风险", ["业务价值", "上线风险", "治理闭环"], ["给出是否推进的条件，而不是泛泛介绍技术"]),
            _slide("02_scenarios", "从场景而不是技术开始", "优先选择知识密集、答案可验证、权限边界清晰的流程", ["客服知识", "销售支持", "研发查询", "合规问答"], ["用场景筛选漏斗表达"]),
            _slide("03_value", "价值假设与衡量口径", "价值要绑定节省时间、减少错误、提升覆盖，而不是只看模型能力", ["时间节省", "覆盖率", "错误率", "满意度"], ["不编 ROI 数字，用指标口径表"]),
            _slide("04_data", "数据源与权限边界", "RAG 的第一风险不是生成，而是把不该看的资料检索出来", ["知识库", "权限", "敏感信息", "审计"], ["用权限分层和数据域地图表达"]),
            _slide("05_retrieval", "检索质量怎么评估", "检索评估应覆盖召回、排序、证据可读性和失败兜底", ["召回", "排序", "证据片段", "兜底"], ["用评测表而非复杂算法图"]),
            _slide("06_answer", "答案质量与可追溯性", "可信答案需要来源引用、置信提示和人工升级路径", ["来源引用", "置信提示", "升级路径", "反馈"], ["展示答案 QA 流程"]),
            _slide("07_risks", "上线风险矩阵", "把风险拆成数据、模型、流程、合规四类并指定控制手段", ["数据风险", "模型风险", "流程风险", "合规风险"], ["咨询矩阵结构"]),
            _slide("08_pilot", "灰度试点路线图", "先做小场景闭环，再扩展部门和知识域", ["试点", "评测", "灰度", "扩展"], ["画 4 阶段路线图"]),
            _slide("09_ops", "运营与持续治理", "RAG 不是一次性交付，需要知识更新、评测回归和反馈处理", ["知识更新", "回归评测", "反馈处理", "权限复核"], ["画治理闭环"]),
            _slide("10_decision", "上线条件与下一步", "满足场景、数据、评测、权限四个门槛后再进入规模化", ["上线门槛", "责任人", "下一步"], ["收束成决策清单"]),
        ],
    },
    {
        "id": "ai_inference_cost",
        "label": "AI 推理成本优化数据故事",
        "template_id": "data_journalism",
        "source_mode": "data_driven",
        "text_density": "medium-high",
        "intent": "data",
        "audience": "AI 应用负责人、平台工程团队、财务管理者",
        "style": "数据新闻/财经图表风格，白底、强图表、右侧解释卡片，所有数字只来自 data_sources。",
        "deck_context": "连续 10 页用同一组示例数据说明推理成本如何被缓存、批处理、模型路由和监控治理影响。",
        "claims": [
            "本 deck 使用合成测试数据，只能标注为情景示例，不能说成行业平均或真实厂商数据。",
            "所有图表数值只能来自 data_sources。",
        ],
        "data_sources": {
            "note": "Synthetic scenario data for image-generation validation; not real vendor data.",
            "cost_scenarios": [
                {"scenario": "Baseline", "relative_cost": 1.00, "cache_hit": 0, "batching": "low"},
                {"scenario": "Cache", "relative_cost": 0.72, "cache_hit": 35, "batching": "low"},
                {"scenario": "Cache+Batch", "relative_cost": 0.55, "cache_hit": 35, "batching": "medium"},
                {"scenario": "Routed", "relative_cost": 0.41, "cache_hit": 35, "batching": "medium"},
            ],
            "latency_scenarios": [
                {"scenario": "Baseline", "relative_latency": 1.00},
                {"scenario": "Batch", "relative_latency": 1.18},
                {"scenario": "Cache", "relative_latency": 0.83},
                {"scenario": "Routed", "relative_latency": 0.91},
            ],
        },
        "slides": [
            _slide("01_overview", "推理成本的三类杠杆", "缓存命中率、批处理效率和模型路由共同决定单位请求成本", ["缓存", "批处理", "模型路由"], ["展示 4 个成本场景的总览柱状图"]),
            _slide("02_unit", "单位请求成本拆解", "先拆成输入、生成、检索、工具调用，再决定优化顺序", ["输入", "生成", "检索", "工具"], ["用堆叠结构，不新增数值"]),
            _slide("03_cache", "缓存命中率的影响", "缓存场景在示例数据中把相对成本从 1.00 降到 0.72", ["Baseline", "Cache", "35% 命中"], ["只能用 data_sources 的 1.00 与 0.72"]),
            _slide("04_batch", "批处理的收益与代价", "批处理降低单位成本，但可能推高部分请求延迟", ["吞吐", "延迟", "批大小"], ["使用相对延迟情景数据"]),
            _slide("05_routing", "模型路由策略", "复杂任务走强模型，简单任务走轻模型，路由场景成本最低", ["任务分层", "强模型", "轻模型", "路由"], ["展示 Routed 0.41 但标注情景示例"]),
            _slide("06_quality", "成本不能脱离质量", "优化策略要同时监控答案质量、失败率和人工升级", ["质量", "失败率", "升级"], ["不编质量分数，只画监控框架"]),
            _slide("07_latency", "延迟与成本的取舍", "不同策略会改变成本曲线和延迟曲线，不能只看一条线", ["成本", "延迟", "体验"], ["用相对延迟数据做小图"]),
            _slide("08_observability", "监控指标体系", "把请求、缓存、路由、成本和质量指标放进同一看板", ["请求量", "缓存", "路由", "成本", "质量"], ["监控看板不要出现假数值"]),
            _slide("09_governance", "预算与策略治理", "成本优化要有预算阈值、策略变更审批和回滚机制", ["预算", "阈值", "审批", "回滚"], ["管理流程图"]),
            _slide("10_playbook", "成本优化 Playbook", "先量化基线，再逐步引入缓存、批处理、路由和监控", ["基线", "缓存", "批处理", "路由", "监控"], ["总结为行动清单"]),
        ],
    },
    {
        "id": "multimodal_safety_paper",
        "label": "多模态安全评测论文组会",
        "template_id": "notebooklm_briefing",
        "source_mode": "source_grounded",
        "text_density": "medium-high",
        "intent": "document",
        "audience": "组会听众、安全研究者、模型评测团队",
        "style": "NotebookLM 资料简报风格，纸张卡片、问题卡片、证据片段和方法框架贯穿全 deck。",
        "deck_context": "连续 10 页做一篇多模态安全评测论文的组会导读，突出研究问题、方法、结果阅读方式、局限和讨论问题。",
        "claims": [
            "本 deck 基于用户提供的论文笔记摘要；不要编造论文作者、会议、年份或引用编号。",
            "核心不是单一分数，而是风险场景、攻击路径、模型行为和评测边界。",
        ],
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
        "slides": [
            _slide("01_opening", "多模态安全评测：组会导读", "核心不是单一分数，而是风险场景、攻击路径与评测边界", ["研究问题", "方法", "风险"], ["开场页，建立阅读框架"]),
            _slide("02_question", "论文想回答什么问题", "多模态模型的风险来自图像、文本和跨模态组合", ["输入模态", "风险类别", "组合攻击"], ["问题卡片结构"]),
            _slide("03_method", "评测框架概览", "评测需要同时记录输入、风险、模型行为和证据链", ["输入", "风险", "行为", "证据"], ["方法流程图"]),
            _slide("04_scenarios", "风险场景怎么设计", "场景化提示比单一测试更接近真实使用边界", ["场景", "角色", "约束", "预期行为"], ["纸张卡片和场景栏"]),
            _slide("05_attack", "攻击路径与失败模式", "攻击路径可以来自视觉误导、文本诱导或跨模态冲突", ["视觉误导", "文本诱导", "冲突输入"], ["攻击路径图，不画危险细节"]),
            _slide("06_metrics", "为什么不能只看总分", "总分会隐藏类别差异、边界条件和失败样式", ["类别差异", "边界条件", "失败样式"], ["读分数的注意事项"]),
            _slide("07_evidence", "证据片段如何支撑结论", "每个判断应追溯到输入、输出和风险分类证据", ["输入证据", "输出行为", "风险标签"], ["证据卡片结构"]),
            _slide("08_limitations", "论文局限与外推边界", "评测集、场景覆盖和模型版本都会限制结论外推", ["覆盖范围", "模型版本", "场景偏差"], ["局限卡片"]),
            _slide("09_discussion", "组会讨论问题", "讨论重点放在评测可复现性、风险定义和企业落地", ["复现性", "风险定义", "落地"], ["Q&A 卡片"]),
            _slide("10_takeaway", "读完这篇论文应带走什么", "安全评测应从分数表升级为风险场景和证据链管理", ["结论", "启发", "下一步"], ["总结页"]),
        ],
    },
    {
        "id": "drawai_image_to_editable_ppt",
        "label": "DrawAI 图像到可编辑 PPT 产品流程",
        "template_id": "product_launch",
        "source_mode": "brand_template",
        "text_density": "medium",
        "intent": "product",
        "audience": "DrawAI 产品团队、用户、投资人演示",
        "style": "深色产品发布风格，青绿色强调，中心工作流和模块卡片贯穿全 deck，中文为主。",
        "deck_context": "连续 10 页介绍 DrawAI 的两阶段策略：先生成高质量 PPT 位图，再通过识别、分层和重建获得可编辑性。",
        "brand": {
            "name": "DrawAI",
            "palette": "深色基底、青绿色强调、清晰白色中文正文",
            "tone": "高级、工具型、可信赖，不做营销空话",
        },
        "claims": [
            "DrawAI 后续流程会处理可编辑重建，因此第一阶段允许 baked_text。",
            "不要承诺 100% 自动完美还原，保留人工校正和 QA。",
        ],
        "slides": [
            _slide("01_value", "DrawAI 图像到可编辑 PPT", "先追求首图质量，再用结构化重建获得可编辑性", ["首图质量", "结构化重建", "可编辑"], ["产品总览页"]),
            _slide("02_problem", "为什么不直接生成 PPTX", "直接生成可编辑 PPT 往往牺牲审美、布局和视觉完整度", ["审美", "布局", "可编辑性"], ["问题页"]),
            _slide("03_strategy", "两阶段策略", "第一阶段生成高质量位图，第二阶段做 OCR、分层和可编辑重建", ["生成", "识别", "分层", "重建"], ["核心流程"]),
            _slide("04_prompt", "第一阶段：高质量图像生成", "通过模板、风格、来源和文字约束提升 PPT 位图质量", ["模板", "风格", "来源", "文字"], ["突出 UI 策略入口"]),
            _slide("05_ocr", "第二阶段：文本识别", "OCR 找到标题、正文、标签和图表文字，为后续编辑定位", ["标题", "正文", "标签", "图表"], ["文本框高亮"]),
            _slide("06_assets", "元素分层与资产处理", "把图像拆成文本区、图形区、图表区和装饰资产", ["文本区", "图形区", "图表区", "装饰资产"], ["分层示意"]),
            _slide("07_rebuild", "可编辑重建", "将识别出的结构重建为可编辑形状、文本框和图片资产", ["形状", "文本框", "图片", "版式"], ["PPT 重建预览"]),
            _slide("08_review", "人工校正与 QA", "保留人工校正入口，处理错字、层级、对齐和缺失元素", ["错字", "层级", "对齐", "缺失"], ["QA 面板"]),
            _slide("09_workbench", "Workbench 里的用户工作流", "用户从生成图像开始，选择满意版本后进入可编辑处理", ["生成", "选择", "处理", "导出"], ["产品路径"]),
            _slide("10_summary", "产品结论", "DrawAI 把图像生成的审美优势和可编辑 PPT 的实用性连接起来", ["审美", "可编辑", "工作流"], ["发布总结"]),
        ],
    },
]


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_decks = DECKS[: args.deck_limit] if args.deck_limit else DECKS
    runtime_config: dict[str, object] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model

    started_at = time.time()
    report: dict[str, Any] = {
        "schema": "drawai.codex_slide_imagegen_deck_continuity_suite.v1",
        "status": "prompt_only" if args.prompt_only else "running",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "deck_count": len(selected_decks),
        "slides_per_deck": args.slides_per_deck,
        "prompt_only": args.prompt_only,
        "decks": [],
    }
    _write_json(output_dir / "deck_continuity_report.json", report)

    for deck_index, deck in enumerate(selected_decks, start=1):
        deck_dir = output_dir / f"{deck_index:02d}_{deck['id']}"
        deck_dir.mkdir(parents=True, exist_ok=True)
        deck_records: list[dict[str, Any]] = []
        selected_slides = deck["slides"][: args.slides_per_deck]
        for slide_index, slide in enumerate(selected_slides, start=1):
            slide_dir = deck_dir / f"{slide_index:02d}_{slide['id']}"
            record = None if args.force else _load_existing_record(slide_dir, allow_prompt_only=args.prompt_only)
            if record is None:
                try:
                    record = _prepare_or_generate_slide(
                        deck=deck,
                        deck_index=deck_index,
                        slide=slide,
                        slide_index=slide_index,
                        slide_count=len(selected_slides),
                        slide_dir=slide_dir,
                        prompt_only=args.prompt_only,
                        runtime_config=runtime_config,
                    )
                except CodexPythonSdkImageGenError as exc:
                    record = _blocked_record(deck, slide, slide_dir, slide_index, str(exc))
                    deck_records.append(record)
                    _write_json(slide_dir / "record.json", record)
                    _write_deck_report(deck_dir, deck, deck_records, status="blocked", error=str(exc))
                    report["status"] = "blocked"
                    report["blocked_reason"] = str(exc)
                    report["decks"].append(_deck_summary(deck, deck_dir, deck_records, "blocked", str(exc)))
                    _write_json(output_dir / "deck_continuity_report.json", report)
                    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
                    return 2
            deck_records.append(record)
            _write_deck_report(deck_dir, deck, deck_records, status="prompt_only" if args.prompt_only else "running")
        deck_sheet = _write_deck_contact_sheet(deck_dir, deck, deck_records)
        deck_status = "prompt_only" if args.prompt_only else _records_status(deck_records)
        _write_deck_report(deck_dir, deck, deck_records, status=deck_status, contact_sheet=deck_sheet)
        report["decks"].append(_deck_summary(deck, deck_dir, deck_records, deck_status, "", deck_sheet))
        _write_json(output_dir / "deck_continuity_report.json", report)

    overview = _write_overview_contact_sheet(output_dir, report["decks"])
    report["status"] = "prompt_only" if args.prompt_only else _decks_status(report["decks"])
    report["overview_contact_sheet"] = str(overview)
    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_json(output_dir / "deck_continuity_report.json", report)
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate 5 continuous 10-slide PPT image decks with Codex imageGeneration.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "outputs" / "codex_slide_imagegen_deck_continuity_5x10")
    parser.add_argument("--slides-per-deck", type=int, default=10)
    parser.add_argument("--deck-limit", type=int, default=0)
    parser.add_argument("--prompt-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=480.0)
    return parser.parse_args()


def _prepare_or_generate_slide(
    *,
    deck: dict[str, Any],
    deck_index: int,
    slide: dict[str, Any],
    slide_index: int,
    slide_count: int,
    slide_dir: Path,
    prompt_only: bool,
    runtime_config: dict[str, object],
) -> dict[str, Any]:
    slide_dir.mkdir(parents=True, exist_ok=True)
    payload = _payload(deck, deck_index, slide, slide_index, slide_count)
    prompt = build_slide_image_generation_prompt(payload)
    _write_json(slide_dir / "payload.json", payload)
    (slide_dir / "improved_prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    record: dict[str, Any] = {
        "deck_id": deck["id"],
        "deck_label": deck["label"],
        "slide_id": slide["id"],
        "slide_index": slide_index,
        "slide_count": slide_count,
        "title": slide["title"],
        "template_id": deck["template_id"],
        "source_mode": deck["source_mode"],
        "status": "prompt_only" if prompt_only else "pending",
        "slide_dir": str(slide_dir),
        "payload_path": str(slide_dir / "payload.json"),
        "prompt_path": str(slide_dir / "improved_prompt.txt"),
        "generation": {},
        "error": "",
    }
    if not prompt_only:
        result = invoke_codex_python_sdk_imagegen(
            prompt=prompt,
            output_dir=slide_dir / "generated",
            task_name="drawai.experiment.codex_slide_deck_continuity.v1",
            output_stem=f"{slide_index:02d}-{deck['id']}-{slide['id']}",
            runtime_config=runtime_config,
            trace_path=slide_dir / "trace.jsonl",
            isolated_cwd=slide_dir / "codex_cwd",
        )
        record["generation"] = result.to_dict()
        record["status"] = "ok" if _first_image_path(record) is not None else "missing_image"
    _write_json(slide_dir / "record.json", record)
    return record


def _payload(deck: dict[str, Any], deck_index: int, slide: dict[str, Any], slide_index: int, slide_count: int) -> dict[str, Any]:
    page_label = f"第 {slide_index}/{slide_count} 页"
    continuity = (
        f"这是连续 deck《{deck['label']}》的{page_label}。必须保持同一套模板、配色、中文语言策略、图标风格、"
        "信息层级和页脚/页码节奏；不要把它画成孤立单页。"
    )
    labels = [page_label, *slide["labels"]]
    claims = [{"claim": item, "source": "deck-level source context"} for item in deck.get("claims", [])]
    claims.extend({"claim": item, "source": "slide-level brief"} for item in slide.get("body", []))
    payload: dict[str, Any] = {
        "prompt": (
            f"{continuity}\n"
            f"本页标题：{slide['title']}。\n"
            f"本页目标：{slide['takeaway']}。\n"
            f"Deck 总目标：{deck['deck_context']}"
        ),
        "language": "zh",
        "output_language": "zh",
        "template_id": deck["template_id"],
        "source_mode": deck["source_mode"],
        "text_density": deck["text_density"],
        "intent": deck["intent"],
        "deck_type": "continuous 10-page PPT image deck",
        "slide_type": "continuous PPT slide image",
        "audience": deck["audience"],
        "tone": "专业、清晰、连续、适合汇报",
        "style": deck["style"],
        "visual_style": deck["style"],
        "size": "2048x1152",
        "quality": "high",
        "background": "opaque",
        "output_format": "png",
        "n": 1,
        "rendering_mode": "baked_text",
        "style_candidate_index": 1,
        "style_candidate_count": 3,
        "visible_text_blocks": {
            "title": slide["title"],
            "takeaway": slide["takeaway"],
            "labels": labels,
        },
        "locked_visible_text": [slide["title"], slide["takeaway"], *labels],
        "claims": claims,
        "composition_guidance": [
            continuity,
            f"全 deck 固定模板：{deck['template_id']}；本页只改变内容，不改变视觉系统。",
            "每页保留清晰页码、章节感和统一的信息结构。",
            "中文标题、栏目名、说明文字必须占主导；英文只保留模型名、API、标准术语或数据场景名。",
        ],
        "quality_gates": [
            "连续 deck 一致性优先：同一配色、字体层级、图标语言和布局节奏。",
            "每页必须是可读 PPT，不是空 layout，也不是互不相干的海报。",
            "不要编造未提供的数字、引用、排名、日期、公司 logo 或论文元信息。",
            "文字区域保持 OCR 友好，方便 DrawAI 后续重建。",
        ],
        "drawai_postprocess": [
            "保持文本块、图表、流程箭头、卡片和装饰资产边界清晰。",
            "避免复杂纹理压在文字下方。",
            "保留适合分层的几何区域。",
        ],
    }
    if deck.get("sources"):
        payload["sources"] = deck["sources"]
    if deck.get("data_sources"):
        payload["data_sources"] = deck["data_sources"]
    if deck.get("brand"):
        payload["brand"] = deck["brand"]
    return payload


def _blocked_record(deck: dict[str, Any], slide: dict[str, Any], slide_dir: Path, slide_index: int, error: str) -> dict[str, Any]:
    return {
        "deck_id": deck["id"],
        "deck_label": deck["label"],
        "slide_id": slide["id"],
        "slide_index": slide_index,
        "title": slide["title"],
        "template_id": deck["template_id"],
        "source_mode": deck["source_mode"],
        "status": "blocked",
        "slide_dir": str(slide_dir),
        "generation": {},
        "error": error,
    }


def _load_existing_record(slide_dir: Path, *, allow_prompt_only: bool) -> dict[str, Any] | None:
    path = slide_dir / "record.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    if allow_prompt_only and record.get("status") == "prompt_only":
        return record
    image_path = _first_image_path(record)
    if image_path is None or not image_path.is_file():
        return None
    return record


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


def _records_status(records: list[dict[str, Any]]) -> str:
    if any(record.get("status") == "blocked" for record in records):
        return "blocked"
    if all(_first_image_path(record) and _first_image_path(record).is_file() for record in records):
        return "ok"
    return "partial"


def _decks_status(decks: list[dict[str, Any]]) -> str:
    statuses = {deck.get("status") for deck in decks}
    if "blocked" in statuses:
        return "blocked"
    if "partial" in statuses:
        return "partial"
    return "ok"


def _deck_summary(
    deck: dict[str, Any],
    deck_dir: Path,
    records: list[dict[str, Any]],
    status: str,
    error: str = "",
    contact_sheet: Path | None = None,
) -> dict[str, Any]:
    return {
        "id": deck["id"],
        "label": deck["label"],
        "template_id": deck["template_id"],
        "source_mode": deck["source_mode"],
        "slides": len(records),
        "status": status,
        "deck_dir": str(deck_dir),
        "contact_sheet": str(contact_sheet) if contact_sheet else str(deck_dir / "deck_contact_sheet.jpg"),
        "error": error,
        "records": records,
    }


def _write_deck_report(
    deck_dir: Path,
    deck: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    status: str,
    error: str = "",
    contact_sheet: Path | None = None,
) -> None:
    _write_json(deck_dir / "deck_report.json", _deck_summary(deck, deck_dir, records, status, error, contact_sheet))


def _write_deck_contact_sheet(deck_dir: Path, deck: dict[str, Any], records: list[dict[str, Any]]) -> Path:
    thumb_w, thumb_h = 420, 236
    label_h, margin = 42, 18
    cols = 2
    rows = (len(records) + cols - 1) // cols
    header_h = 66
    width = margin * (cols + 1) + cols * thumb_w
    height = margin + header_h + rows * (label_h + thumb_h + margin)
    sheet = Image.new("RGB", (width, height), (246, 247, 249))
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, margin), deck["label"], fill=(15, 23, 42), font=_font(24))
    draw.text((margin, margin + 32), f"{deck['template_id']} / {deck['source_mode']} / 10-page continuity deck", fill=(71, 85, 105), font=_font(16))
    for index, record in enumerate(records):
        row, col = divmod(index, cols)
        x = margin + col * (thumb_w + margin)
        y = margin + header_h + row * (label_h + thumb_h + margin)
        draw.text((x, y), f"{record.get('slide_index', index + 1):02d}. {record.get('title', '')}", fill=(15, 23, 42), font=_font(15))
        _paste_thumb(sheet, _first_image_path(record), x, y + label_h, thumb_w, thumb_h)
    path = deck_dir / "deck_contact_sheet.jpg"
    sheet.save(path, quality=92)
    return path


def _write_overview_contact_sheet(output_dir: Path, deck_summaries: list[dict[str, Any]]) -> Path:
    thumb_w, thumb_h = 300, 169
    label_h, margin = 48, 18
    cols = 5
    max_rows = 2
    header_h = 64
    width = margin * (cols + 1) + cols * thumb_w
    height = margin + header_h + max_rows * (label_h + thumb_h + margin)
    sheet = Image.new("RGB", (width, height), (246, 247, 249))
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, margin), "5 组连续 10 页 PPT 图像生成总览", fill=(15, 23, 42), font=_font(24))
    draw.text((margin, margin + 32), "每列一个 deck，显示第 1 页与第 10 页，用于检查连续风格一致性", fill=(71, 85, 105), font=_font(16))
    for col, deck in enumerate(deck_summaries):
        records = deck.get("records", [])
        first = records[0] if records else {}
        last = records[-1] if records else {}
        for row, record in enumerate([first, last]):
            x = margin + col * (thumb_w + margin)
            y = margin + header_h + row * (label_h + thumb_h + margin)
            title = f"{deck.get('label', '')[:18]} / p{record.get('slide_index', '?')}"
            draw.text((x, y), title, fill=(15, 23, 42), font=_font(14))
            draw.text((x, y + 20), f"{deck.get('template_id')} / {deck.get('status')}", fill=(71, 85, 105), font=_font(12))
            _paste_thumb(sheet, _first_image_path(record), x, y + label_h, thumb_w, thumb_h)
    path = output_dir / "overview_contact_sheet.jpg"
    sheet.save(path, quality=92)
    return path


def _paste_thumb(sheet: Image.Image, path: Path | None, x: int, y: int, width: int, height: int) -> None:
    draw = ImageDraw.Draw(sheet)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=7, fill=(226, 232, 240), outline=(203, 213, 225))
    if path is None or not path.is_file():
        draw.text((x + 16, y + 16), "prompt only / missing", fill=(100, 116, 139), font=_font(14))
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
        "deck_count": report.get("deck_count"),
        "slides_per_deck": report.get("slides_per_deck"),
        "output_dir": report.get("output_dir"),
        "overview_contact_sheet": report.get("overview_contact_sheet", ""),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "blocked_reason": report.get("blocked_reason", ""),
        "deck_contact_sheets": [
            {"id": deck.get("id"), "status": deck.get("status"), "contact_sheet": deck.get("contact_sheet")}
            for deck in report.get("decks", [])
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
