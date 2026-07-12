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
from drawai.slide_image_strategy import template_registry_summary  # noqa: E402
from drawai.slide_template_library import (  # noqa: E402
    build_prompt_from_template_card,
    list_template_cards,
    recommend_template_cards,
)


SHOWCASE_SCHEMA = "drawai.codex_slide_feature_showcase_cases.v1"
TOPIC = "AI Agent 工作流如何落地企业知识库"

PREVIOUS_TEMPLATE_EXP = REPO_ROOT / "outputs" / "codex_slide_template_library_experiment"
PREVIOUS_EXPANDED = REPO_ROOT / "outputs" / "codex_slide_imagegen_expanded_style_cases"

REUSED_IMAGES = {
    "swiss_international": PREVIOUS_TEMPLATE_EXP / "02_swiss_international" / "swiss_international.png",
    "aurora_ui": PREVIOUS_TEMPLATE_EXP / "03_aurora_ui" / "aurora_ui.png",
    "manga_safe_learning": PREVIOUS_TEMPLATE_EXP / "04_manga_safe_learning" / "manga_safe_learning.png",
    "business_source_grounded": PREVIOUS_EXPANDED / "01_business_mckinsey_rag_decision" / "business_mckinsey_rag_decision.png",
    "tech_chinese_first": PREVIOUS_EXPANDED / "02_tech_openai_agent_workflow" / "tech_openai_agent_workflow.png",
    "data_driven": PREVIOUS_EXPANDED / "03_data_economist_inference_cost" / "data_economist_inference_cost.png",
    "blue_robot_safe": PREVIOUS_EXPANDED / "06_cartoon_blue_robot_ai_learning" / "cartoon_blue_robot_ai_learning.png",
}


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve(strict=False)
    if args.force and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = time.time()
    registry = template_registry_summary()
    cards = list_template_cards()
    report: dict[str, Any] = {
        "schema": SHOWCASE_SCHEMA,
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "template_registry_count": len(registry),
        "template_card_count": len(cards),
        "cases": [],
    }
    _write_json(output_dir / "summary.json", report)
    _write_feature_inventory(output_dir, registry=registry, cards=cards)

    cases: list[dict[str, Any]] = []
    cases.append(_case_workbench_strategy_controls(output_dir))
    cases.append(_case_template_recommendation(output_dir))
    cases.append(_case_template_gallery(output_dir, cards=cards))
    cases.append(_case_multi_template_compare(output_dir))
    cases.append(_case_source_grounded(output_dir))
    cases.append(_case_data_driven(output_dir))
    cases.append(_case_chinese_first(output_dir))
    cases.append(_case_safe_ip(output_dir))
    cases.append(_case_reference_image_edit(output_dir, skip_real=args.skip_reference_edit, runtime_config=_runtime_config(args)))
    cases.append(_case_drawai_handoff(output_dir))

    report["cases"] = cases
    report["contact_sheet"] = str(_write_contact_sheet(output_dir, cases))
    report["status"] = "ok" if not any(case.get("status") == "blocked" for case in cases) else "partial"
    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_json(output_dir / "summary.json", report)
    _write_summary_md(output_dir, report)
    print(json.dumps(_compact_report(report), ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a user-visible showcase of current Codex PPT image capabilities.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "codex_slide_feature_showcase_cases",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-reference-edit", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=420.0)
    return parser.parse_args()


def _runtime_config(args: argparse.Namespace) -> dict[str, Any]:
    runtime_config: dict[str, Any] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model
    return runtime_config


def _case_workbench_strategy_controls(output_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "01_workbench_strategy_controls")
    payload = {
        "prompt": "生成一页中文 PPT：企业知识库 Agent 从试点到规模化落地的决策页",
        "size": "2048x1152",
        "quality": "high",
        "background": "opaque",
        "output_format": "png",
        "language": "zh",
        "output_language": "zh",
        "template_id": "mckinsey_boardroom",
        "source_mode": "source_grounded",
        "text_density": "high",
        "style_candidate_count": 3,
        "style_candidate_index": 2,
        "visible_text_blocks": {
            "title": "企业知识库 Agent 落地决策",
            "takeaway": "先从高价值、低权限风险的流程试点，再逐步扩展到跨部门协同",
            "labels": ["决策结论", "试点边界", "权限治理", "评估指标", "推广路线"],
        },
        "sources": [
            {"title": "内部试点纪要", "evidence": "Pilot should start with constrained workflows and permission controls."}
        ],
        "claims": [
            {"claim": "没有提供 ROI、准确率或成本数字，因此页面只做定性决策框架。"},
            {"claim": "上线风险主要来自权限边界、检索质量、答案可追溯和场景边界。"},
        ],
        "data_sources": {"note": "No numeric table supplied; do not render quantified charts."},
        "visual_style": "董事会咨询页；结论先行；议题树、风险栏、三阶段路线图；中文文字充分。",
        "must_include": ["中文标题", "3-5 条决策依据", "来源约束说明"],
    }
    prompt = build_slide_image_generation_prompt(payload)
    return _write_case_record(
        case_dir,
        feature="Workbench Codex PPT 图像策略入口",
        status="prompt_only",
        capability_state="已可用",
        payload=payload,
        prompt=prompt,
        observations=[
            "覆盖模板选择、来源模式、语言、文字密度、候选风格、必须出现文字、事实来源、claims、data_sources、风格备注。",
            "本 case 只展示 prompt 组装，不触发真实生成。",
        ],
    )


def _case_template_recommendation(output_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "02_template_recommendation")
    recommendations = recommend_template_cards(TOPIC, limit=6)
    payload = {
        "user_input": TOPIC,
        "limit": 6,
        "recommended_template_card_ids": [item["id"] for item in recommendations],
        "recommendations": [
            {
                "id": item["id"],
                "name": item["name"],
                "category": item["category"],
                "scenario_tags": item["scenario_tags"],
                "visual_tags": item["visual_tags"],
            }
            for item in recommendations
        ],
    }
    prompt = "用户输入 PPT 类型/主题后，系统推荐多个 TemplateCard：\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    _write_json(case_dir / "recommendations.json", payload)
    return _write_case_record(
        case_dir,
        feature="用户输入 PPT 类型 -> 推荐模板卡",
        status="ok",
        capability_state="已可用",
        payload=payload,
        prompt=prompt,
        observations=["当前是启发式推荐，已能返回多张 TemplateCard；后续需要接入前端 gallery。"],
    )


def _case_template_gallery(output_dir: Path, *, cards: list[dict[str, Any]]) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "03_template_gallery_cards")
    selected_ids = [
        "modern_newspaper",
        "swiss_international",
        "aurora_ui",
        "manga_safe_learning",
        "corporate_strategy_cinematic",
        "weekly_kanban",
        "sales_architectural",
        "light_glassmorphism",
    ]
    selected = [card for card in cards if card["id"] in selected_ids]
    payload = {
        "gallery_card_count": len(cards),
        "shown_card_ids": [card["id"] for card in selected],
        "cards": selected,
    }
    _write_json(case_dir / "gallery_cards.json", payload)
    prompt = "模板 gallery / template card 信息展示：\n" + json.dumps(
        [
            {
                "id": card["id"],
                "name": card["name"],
                "category": card["category"],
                "palette": card["palette"],
                "layout_archetypes": card["layout_archetypes"],
                "source_policy": card["source_policy"],
                "ip_safety": card.get("ip_safety", ""),
            }
            for card in selected
        ],
        ensure_ascii=False,
        indent=2,
    )
    return _write_case_record(
        case_dir,
        feature="模板 gallery / TemplateCard 元数据",
        status="ok",
        capability_state="部分可用",
        payload=payload,
        prompt=prompt,
        observations=[
            "后端 TemplateCard seed 已有分类、标签、prompt recipe、色板、布局、来源/IP 策略。",
            "Workbench 前端 gallery cards 还未正式接入。",
        ],
    )


def _case_multi_template_compare(output_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "04_multi_template_effect_compare")
    image_specs = [
        ("swiss_international", REUSED_IMAGES["swiss_international"]),
        ("aurora_ui", REUSED_IMAGES["aurora_ui"]),
        ("business_source_grounded", REUSED_IMAGES["business_source_grounded"]),
        ("manga_safe_learning", REUSED_IMAGES["manga_safe_learning"]),
    ]
    images = _copy_reused_images(case_dir, image_specs)
    payload = {
        "topic": TOPIC,
        "purpose": "同一主题/相近主题下，对比多个模板/风格真实效果",
        "reused_from": [image["reused_from"] for image in images],
        "template_styles": [image["label"] for image in images],
    }
    return _write_case_record(
        case_dir,
        feature="同一主题多模板效果对比",
        status="ok",
        capability_state="已可用",
        payload=payload,
        prompt="复用已有真实生成图，合成总览 contact sheet，展示多模板视觉差异。",
        images=images,
        observations=[
            "已能用 contact sheet 对比不同模板效果。",
            "下一步应由 UI 直接从 gallery 卡触发多模板 preview generation。",
        ],
    )


def _case_source_grounded(output_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "05_source_grounded_business")
    payload = {
        "prompt": "生成一页中文商务咨询 PPT：企业 RAG 试点是否进入上线",
        "template_id": "mckinsey_boardroom",
        "source_mode": "source_grounded",
        "language": "zh",
        "text_density": "high",
        "visible_text_blocks": {
            "title": "企业 RAG 试点上线决策",
            "labels": ["结论先行", "业务价值", "数据权限", "答案评估", "灰度路线"],
        },
        "sources": [{"title": "项目复盘摘要", "evidence": "Pilot should start from constrained workflows."}],
        "claims": [
            {"claim": "只展示定性决策结构，不展示未提供来源的 ROI、成本节省或准确率数字。"}
        ],
    }
    prompt = build_slide_image_generation_prompt(payload)
    images = _copy_reused_images(case_dir, [("source_grounded_business", REUSED_IMAGES["business_source_grounded"])])
    return _write_case_record(
        case_dir,
        feature="source_grounded：事实来源/claims 约束",
        status="ok",
        capability_state="已可用",
        payload=payload,
        prompt=prompt,
        images=images,
        observations=["复用图展示商务咨询风格；prompt 明确禁止编造 ROI、成本节省、准确率等未提供数字。"],
    )


def _case_data_driven(output_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "06_data_driven_chart")
    payload = {
        "prompt": "生成一页中文数据媒体 PPT：AI 应用推理成本的三类杠杆",
        "template_id": "economist_data_story",
        "source_mode": "data_driven",
        "language": "zh",
        "text_density": "medium-high",
        "visible_text_blocks": {
            "title": "推理成本的三类杠杆",
            "labels": ["缓存命中率", "批处理效率", "模型路由", "相对成本", "场景数据"],
        },
        "data_sources": {
            "note": "Synthetic scenario data supplied for visual validation; label as scenario data, not industry average.",
            "rows": [
                {"scenario": "基线", "relative_cost": 1.0},
                {"scenario": "加入缓存", "relative_cost": 0.72},
                {"scenario": "缓存+批处理", "relative_cost": 0.55},
                {"scenario": "智能路由", "relative_cost": 0.41},
            ],
        },
        "claims": [{"claim": "图表只能展示用户给定的相对成本场景数据。"}],
    }
    prompt = build_slide_image_generation_prompt(payload)
    images = _copy_reused_images(case_dir, [("data_driven", REUSED_IMAGES["data_driven"])])
    return _write_case_record(
        case_dir,
        feature="data_driven：数据源约束图表页",
        status="ok",
        capability_state="已可用",
        payload=payload,
        prompt=prompt,
        images=images,
        observations=["复用图展示数据媒体风格；payload 带明确 data_sources，禁止把测试数据伪装成行业平均。"],
    )


def _case_chinese_first(output_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "07_chinese_first_visible_text")
    payload = {
        "prompt": "生成中文 AI 产品发布风格 PPT：多模态 Agent 工作流",
        "template_id": "openai_minimal",
        "source_mode": "prompt_only",
        "language": "zh",
        "visible_text_blocks": {
            "title": "多模态 Agent 工作流",
            "takeaway": "把目标、上下文、工具和记忆组织成可追踪的任务闭环",
            "labels": ["用户目标", "多模态上下文", "计划分解", "工具调用", "结果校验", "任务记忆"],
        },
    }
    prompt = build_slide_image_generation_prompt(payload)
    images = _copy_reused_images(case_dir, [("chinese_first", REUSED_IMAGES["tech_chinese_first"])])
    return _write_case_record(
        case_dir,
        feature="Chinese-first visible text：中文标题/栏目",
        status="ok",
        capability_state="已可用",
        payload=payload,
        prompt=prompt,
        images=images,
        observations=["复用图中文标题和栏目可读；当前 prompt policy 明确禁止把中文请求改成英文标题。"],
    )


def _case_safe_ip(output_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "08_safe_ip_cartoon")
    payload = {
        "prompt": "生成儿童学习 PPT：用原创蓝白圆润机器人讲 AI 助手如何记住长期任务",
        "template_id": "blue_robot_learning",
        "source_mode": "prompt_only",
        "language": "zh",
        "must_avoid": [
            "不要生成哆啦A梦本体",
            "不要精确复刻任何受版权保护角色",
            "不要铃铛、魔法口袋、商标符号或相同脸部比例",
        ],
    }
    prompt = build_slide_image_generation_prompt(payload)
    images = _copy_reused_images(case_dir, [("blue_robot_safe", REUSED_IMAGES["blue_robot_safe"])])
    return _write_case_record(
        case_dir,
        feature="safe IP/cartoon：蓝白机器人但不复刻哆啦A梦",
        status="ok",
        capability_state="已可用",
        payload=payload,
        prompt=prompt,
        images=images,
        observations=["复用图体现蓝白圆润学习氛围；prompt 和模板策略都加入 no Doraemon likeness / no trademarked symbols。"],
    )


def _case_reference_image_edit(output_dir: Path, *, skip_real: bool, runtime_config: dict[str, Any]) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "09_reference_image_local_input")
    source_image = REUSED_IMAGES["swiss_international"].resolve(strict=False)
    prompt = build_prompt_from_template_card(
        "light_glassmorphism",
        "参考图支持：用已有 PPT 图像作为风格/布局输入，生成企业知识库 Agent 的中文展示页",
        language="zh",
        reference_image_paths=[str(source_image)],
    )
    prompt = (
        prompt
        + "\n\nExecution note for this showcase: this case should call Codex image edit with the source image as a real LocalImageInput, not only write the path in text. Use the supplied image as style/layout input; do not copy exact text."
    )
    payload = {
        "operation": "codex_image_edit",
        "source_image_path": str(source_image),
        "template_card_id": "light_glassmorphism",
        "reference_support_level": "true LocalImageInput if status=ok; prompt-only if skipped/blocked",
    }
    images: list[dict[str, Any]] = []
    status = "prompt_only" if skip_real else "running"
    observations = [
        "此 case 用现有样例图作为 source_image_path，目标是验证 Codex edit / LocalImageInput 底层路径。",
        "Workbench 图像生成 UI 还没有完整 reference gallery 入口。",
    ]
    blocked_reason = ""
    if not skip_real:
        try:
            from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_image_edit

            result = invoke_codex_python_sdk_image_edit(
                source_image_path=source_image,
                prompt=prompt,
                output_dir=case_dir / "generated",
                task_name="drawai.experiment.slide_feature_showcase.reference_edit.v1",
                output_stem="reference-localinput-edit",
                runtime_config=runtime_config,
                trace_path=case_dir / "trace.jsonl",
                isolated_cwd=case_dir / "codex_cwd",
            )
            first = result.images[0] if result.images else None
            if first is not None:
                target = _copy_image(Path(first.path), case_dir / "reference_localinput_edit.png")
                images.append(
                    {
                        "label": "reference_localinput_edit",
                        "path": str(target),
                        "reused_from": "",
                        "operation": "codex_image_edit",
                        "source_image_path": str(source_image),
                    }
                )
                payload["generation"] = result.to_dict()
                status = "ok"
                observations.append("真实 edit 成功，记录中包含 source_image_path 和 operation=edit。")
            else:
                status = "blocked"
                blocked_reason = "Codex edit returned no image"
        except Exception as exc:  # noqa: BLE001 - showcase should preserve blocker record.
            status = "blocked"
            blocked_reason = repr(exc)
            observations.append(f"真实 edit 失败：{blocked_reason}")
    return _write_case_record(
        case_dir,
        feature="reference image support：prompt 字段 + Codex edit/LocalImageInput",
        status=status,
        capability_state="部分可用",
        payload=payload,
        prompt=prompt,
        images=images,
        observations=observations,
        blocked_reason=blocked_reason,
    )


def _case_drawai_handoff(output_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(output_dir, "10_drawai_batch_handoff")
    source = _copy_image(REUSED_IMAGES["aurora_ui"], case_dir / "selected_generated_image.png")
    payload: dict[str, Any] = {
        "purpose": "验证生成后的 PPT 图像可以进入 DrawAI Workbench batch/case 层",
        "source_image_path": str(source),
        "mode": "store_dry_run_no_analysis",
    }
    observations = [
        "已有 Workbench 上传/生成图提交路径；本 case 在独立 showcase workspace 创建 batch/case，不跑 OCR/SAM/SVG。",
        "模板 gallery 到一键创建 DrawAI batch 的产品化 UI 仍属于后续 Phase。",
    ]
    status = "ok"
    blocked_reason = ""
    try:
        from drawai.workbench.runner import create_case_config
        from drawai.workbench.store import WorkbenchStore

        workspace = case_dir / "workbench_dryrun"
        store = WorkbenchStore(workspace)
        base_config = REPO_ROOT / "configs" / "drawai" / "config.yaml"
        batch = store.create_batch(
            name="Feature showcase generated PPT image",
            input_mode="upload",
            max_concurrent_cases=1,
            auto_run_svg_after_analysis=False,
            config_path=base_config,
        )
        case = store.create_case(
            batch_id=batch.batch_id,
            name=source.name,
            source_image_path=source,
            config_path=base_config,
        )
        config_path = create_case_config(
            base_config_path=base_config,
            source_image=source,
            output_dir=case.run_root,
            target_path=Path(case.run_root) / "drawai.config.yaml",
        )
        store.update_case_config_path(case.case_id, config_path)
        refreshed = store.get_case(case.case_id)
        payload["batch"] = batch.to_api(case_counts=store.case_counts(batch.batch_id))
        payload["case"] = refreshed.to_api()
    except Exception as exc:  # noqa: BLE001
        status = "blocked"
        blocked_reason = repr(exc)
        observations.append(f"Dry-run 创建失败：{blocked_reason}")
    images = [
        {
            "label": "drawai_batch_source",
            "path": str(source),
            "reused_from": str(REUSED_IMAGES["aurora_ui"]),
            "operation": "dryrun_source",
        }
    ]
    return _write_case_record(
        case_dir,
        feature="生成后进入 DrawAI batch/case 的衔接",
        status=status,
        capability_state="部分可用",
        payload=payload,
        prompt="将已生成图片作为 DrawAI Workbench source image 创建 batch/case；本展示不执行重建流水线。",
        images=images,
        observations=observations,
        blocked_reason=blocked_reason,
    )


def _write_feature_inventory(output_dir: Path, *, registry: list[dict[str, Any]], cards: list[dict[str, Any]]) -> None:
    lines = [
        "# PPT 图像生成功能清单",
        "",
        "## 已可用",
        "",
        "- Workbench Codex PPT 图像策略入口：`ImageGenStudio.tsx` 已能向 `/api/imagegen/generations` 传入 `provider=codex`, `template_id`, `source_mode`, `language`, `text_density`, `style_candidate_count`, `style_candidate_index`, `visible_text_blocks`, `sources`, `claims`, `data_sources`, `visual_style` 等字段。",
        f"- 扩展模板注册表：`slide_image_strategy.TEMPLATE_REGISTRY` 当前暴露 {len(registry)} 个 template_id，可通过 `template_registry_summary()` 查看。",
        f"- Prompt/TemplateCard seed 库：`slide_template_library` 当前有 {len(cards)} 张 TemplateCard，支持 `list_template_cards()`, `recommend_template_cards()`, `build_prompt_from_template_card()`。",
        "- 真实图像生成：`invoke_codex_python_sdk_imagegen()` 已可生成 PPT 图像并落盘；已有 expanded style、deck continuity、template library 等 contact sheet/report 产物。",
        "- 中文与 baked_text 策略：当前 prompt builder 默认要求生成完整可读 PPT 位图，不允许空 layout 或英文占主导。",
        "- IP 安全策略：`blue_robot_learning` / `manga_safe_learning` 等模板包含 no copyrighted character / no Doraemon likeness / no trademarked symbols 等约束。",
        "",
        "## 部分可用",
        "",
        "- 参考图：`build_prompt_from_template_card(..., reference_image_paths=...)` 可把参考图路径和复制限制写入 prompt；`invoke_codex_python_sdk_image_edit(source_image_path=...)` 底层可通过 Codex SDK `LocalImageInput` 传本地图片。",
        "- Workbench `/api/imagegen/edits` 已存在 Codex edit endpoint，但图像生成 UI 还没有完整 reference image/style gallery 入口。",
        "- 生成图进入 DrawAI：Workbench 已有上传/生成图提交到 batch/case 的路径，本展示可创建 store dry-run case；但 template gallery 到重建流程的一键产品化入口还未完成。",
        "",
        "## 规划中",
        "",
        "- 最终产品 gallery：卡片缩略图、样例效果、标签、色板、参考图、prompt recipe、风险提示、推荐理由。",
        "- `scenario_id + visual_style_id` 二层组合，而不是把场景和视觉风格都塞进单个 `template_id`。",
        "- 多模板 preview generation API、reference gallery upload/register API、生成后评价与回写样例库。",
        "- 从选中的 TemplateCard/preview 一键创建 DrawAI batch 并继续运行可编辑重建。",
    ]
    (output_dir / "feature_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _copy_reused_images(case_dir: Path, specs: list[tuple[str, Path]]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for label, source in specs:
        target = _copy_image(source, case_dir / f"{label}.png")
        images.append(
            {
                "label": label,
                "path": str(target),
                "reused_from": str(source),
                "operation": "reused",
            }
        )
    return images


def _copy_image(source: Path, target: Path) -> Path:
    source = source.expanduser().resolve(strict=False)
    if not source.is_file():
        raise FileNotFoundError(f"missing image for showcase: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".png":
        shutil.copy2(source, target)
        return target
    Image, _, _ = _pil()
    with Image.open(source) as image:
        image.save(target)
    return target


def _write_case_record(
    case_dir: Path,
    *,
    feature: str,
    status: str,
    capability_state: str,
    payload: dict[str, Any],
    prompt: str,
    images: list[dict[str, Any]] | None = None,
    observations: list[str] | None = None,
    blocked_reason: str = "",
) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    _write_json(case_dir / "payload.json", payload)
    (case_dir / "prompt.txt").write_text(prompt.strip() + "\n", encoding="utf-8")
    record = {
        "id": case_dir.name,
        "feature": feature,
        "status": status,
        "capability_state": capability_state,
        "case_dir": str(case_dir),
        "payload_path": str(case_dir / "payload.json"),
        "prompt_path": str(case_dir / "prompt.txt"),
        "images": images or [],
        "observations": observations or [],
        "blocked_reason": blocked_reason,
    }
    _write_json(case_dir / "record.json", record)
    return record


def _write_contact_sheet(output_dir: Path, cases: list[dict[str, Any]]) -> Path:
    cells: list[dict[str, str]] = []
    for case in cases:
        for image in case.get("images", []):
            path = Path(str(image.get("path") or ""))
            if path.is_file():
                cells.append(
                    {
                        "feature": str(case.get("feature") or ""),
                        "label": str(image.get("label") or ""),
                        "status": str(case.get("status") or ""),
                        "path": str(path),
                        "reused_from": str(image.get("reused_from") or ""),
                    }
                )
    Image, ImageDraw, _ = _pil()
    thumb_w = 520
    thumb_h = 293
    label_h = 72
    margin = 18
    cols = 2
    rows = max(1, (len(cells) + cols - 1) // cols)
    width = margin * (cols + 1) + cols * thumb_w
    height = margin + rows * (label_h + thumb_h + margin)
    sheet = Image.new("RGB", (width, height), (247, 248, 250))
    draw = ImageDraw.Draw(sheet)
    font = _font(16)
    small = _font(12)
    if not cells:
        draw.text((margin, margin), "No generated or reused images", fill=(15, 23, 42), font=font)
    for index, cell in enumerate(cells):
        row = index // cols
        col = index % cols
        x = margin + col * (thumb_w + margin)
        y = margin + row * (label_h + thumb_h + margin)
        draw.text((x, y), _truncate(cell["label"], 46), fill=(15, 23, 42), font=font)
        draw.text((x, y + 22), _truncate(cell["feature"], 58), fill=(51, 65, 85), font=small)
        source = "reused" if cell["reused_from"] else "new"
        draw.text((x, y + 42), f"{source} / {cell['status']}", fill=(100, 116, 139), font=small)
        _paste_thumb(sheet, Path(cell["path"]), x, y + label_h, thumb_w, thumb_h)
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


def _write_summary_md(output_dir: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Codex PPT 图像功能展示用例",
        "",
        f"- 状态：{report.get('status')}",
        f"- 输出目录：{report.get('output_dir')}",
        f"- Contact sheet：{report.get('contact_sheet')}",
        f"- template_id 数量：{report.get('template_registry_count')}",
        f"- TemplateCard 数量：{report.get('template_card_count')}",
        "",
        "| Case | 功能点 | 状态 | 能力层级 | 图片 | 观察 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in report.get("cases", []):
        images = "<br>".join(str(image.get("path", "")) for image in case.get("images", []))
        observations = "<br>".join(case.get("observations", []))
        lines.append(
            f"| `{case['id']}` | {case['feature']} | {case['status']} | {case['capability_state']} | {images} | {observations} |"
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _case_dir(output_dir: Path, name: str) -> Path:
    return output_dir / name


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pil() -> tuple[Any, Any, Any]:
    from PIL import Image, ImageDraw, ImageFont

    return Image, ImageDraw, ImageFont


def _font(size: int) -> Any:
    _, _, ImageFont = _pil()
    for candidate in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/arial.ttf"):
        path = Path(candidate)
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _truncate(value: str, limit: int) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "output_dir": report.get("output_dir"),
        "contact_sheet": report.get("contact_sheet"),
        "case_count": len(report.get("cases", [])),
        "ok_cases": sum(1 for case in report.get("cases", []) if case.get("status") == "ok"),
        "blocked_cases": [case["id"] for case in report.get("cases", []) if case.get("status") == "blocked"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
