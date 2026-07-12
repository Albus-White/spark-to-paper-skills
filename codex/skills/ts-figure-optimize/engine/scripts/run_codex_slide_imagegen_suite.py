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

from drawai.codex_python_sdk_imagegen import CodexPythonSdkImageGenError  # noqa: E402
from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_imagegen  # noqa: E402
from drawai.slide_image_prompt import (  # noqa: E402
    build_legacy_workbench_image_generation_prompt,
    build_slide_image_generation_prompt,
    build_slide_image_prompt_comparison,
)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = _selected_groups(args.groups)
    slides = [
        (group_id, slide)
        for group_id, group in groups.items()
        for slide in group[: args.max_slides_per_group]
    ]
    if args.limit:
        slides = slides[: args.limit]
    if not slides:
        raise SystemExit("No slides selected.")

    runtime_config: dict[str, object] = {
        "timeout_seconds": args.timeout_seconds,
        "reasoning_effort": args.reasoning_effort,
    }
    if args.model:
        runtime_config["model_name"] = args.model

    started_at = time.time()
    report: dict[str, Any] = {
        "schema": "drawai.codex_slide_imagegen_suite_report.v1",
        "status": "running" if args.generate else "prompt_only",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "generate": args.generate,
        "modes": args.modes,
        "slide_count": len(slides),
        "groups": list(groups.keys()),
        "slides": [],
    }
    _write_json(output_dir / "suite_report.json", report)

    generated_pairs: list[dict[str, Any]] = []
    for slide_index, (group_id, slide) in enumerate(slides, start=1):
        slide_dir = output_dir / f"{slide_index:02d}_{group_id}_{_safe_stem(slide['id'])}"
        slide_dir.mkdir(parents=True, exist_ok=True)
        payload = _slide_payload(group_id, slide, args)
        legacy_prompt = build_legacy_workbench_image_generation_prompt(payload)
        improved_prompt = build_slide_image_generation_prompt(payload)
        comparison = build_slide_image_prompt_comparison(payload)
        (slide_dir / "payload.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (slide_dir / "legacy_prompt.txt").write_text(legacy_prompt + "\n", encoding="utf-8")
        (slide_dir / "improved_prompt.txt").write_text(improved_prompt + "\n", encoding="utf-8")

        slide_record: dict[str, Any] = {
            "index": slide_index,
            "group": group_id,
            "slide_id": slide["id"],
            "title": slide["title"],
            "slide_dir": str(slide_dir),
            "legacy_prompt_path": str(slide_dir / "legacy_prompt.txt"),
            "improved_prompt_path": str(slide_dir / "improved_prompt.txt"),
            "diff_summary": comparison["diff_summary"],
            "generation": {},
        }

        if args.generate and not args.force:
            existing = _load_existing_slide_record(slide_dir)
            if existing is not None:
                slide_record.update(existing)
                slide_record.setdefault("generation", {})
                if _record_satisfies_modes(slide_record, modes=args.modes):
                    generated_pairs.append(slide_record)
                    report["slides"].append(slide_record)
                    _write_json(output_dir / "suite_report.json", report)
                    continue

        if args.generate:
            try:
                if args.modes in {"both", "legacy"} and (args.force or _first_image_path(slide_record["generation"].get("legacy")) is None):
                    legacy_result = invoke_codex_python_sdk_imagegen(
                        prompt=legacy_prompt,
                        output_dir=slide_dir / "legacy",
                        task_name="drawai.experiment.codex_slide_suite.legacy.v1",
                        output_stem=f"{slide_index:02d}-legacy",
                        runtime_config=runtime_config,
                        trace_path=slide_dir / "legacy_trace.jsonl",
                        isolated_cwd=slide_dir / "legacy_cwd",
                    )
                    slide_record["generation"]["legacy"] = legacy_result.to_dict()
                    _write_json(slide_dir / "record.json", slide_record)
                if args.modes in {"both", "improved"} and (args.force or _first_image_path(slide_record["generation"].get("improved")) is None):
                    improved_result = invoke_codex_python_sdk_imagegen(
                        prompt=improved_prompt,
                        output_dir=slide_dir / "improved",
                        task_name="drawai.experiment.codex_slide_suite.improved.v1",
                        output_stem=f"{slide_index:02d}-improved",
                        runtime_config=runtime_config,
                        trace_path=slide_dir / "improved_trace.jsonl",
                        isolated_cwd=slide_dir / "improved_cwd",
                    )
                    slide_record["generation"]["improved"] = improved_result.to_dict()
                    _write_json(slide_dir / "record.json", slide_record)
            except CodexPythonSdkImageGenError as exc:
                slide_record["error"] = str(exc)
                slide_record["status"] = "blocked"
                generated_pairs.append(slide_record)
                report["slides"].append(slide_record)
                report["status"] = "blocked"
                report["blocked_reason"] = str(exc)
                contact_sheet = _write_contact_sheet(output_dir, generated_pairs)
                report["contact_sheet"] = str(contact_sheet) if contact_sheet is not None else ""
                report["elapsed_seconds"] = round(time.time() - started_at, 3)
                _write_json(slide_dir / "record.json", slide_record)
                _write_json(output_dir / "suite_report.json", report)
                print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
                return 2
            generated_pairs.append(slide_record)
            _write_json(slide_dir / "record.json", slide_record)

        report["slides"].append(slide_record)
        _write_json(output_dir / "suite_report.json", report)

    if args.generate:
        report["status"] = "ok"
        contact_sheet = _write_contact_sheet(output_dir, generated_pairs)
        report["contact_sheet"] = str(contact_sheet) if contact_sheet is not None else ""
    report["elapsed_seconds"] = round(time.time() - started_at, 3)
    _write_json(output_dir / "suite_report.json", report)
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a multi-group academic PPT slide image A/B suite for legacy vs improved Codex image prompts."
    )
    parser.add_argument(
        "--groups",
        default="all",
        help=(
            "Comma-separated group ids, or all. Built-ins: drawai, spatial, battery, weather, singlecell, imaging, "
            "kimi, agent_memory, research_rag, multimodal_safety, world_model, ai_infra_cost."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "outputs" / "codex_slide_imagegen_suite")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--modes", choices=["both", "legacy", "improved"], default="both")
    parser.add_argument("--max-slides-per-group", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0, help="Global slide limit. Use 5-10 for a controlled visual sample.")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="low", choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--timeout-seconds", type=float, default=360.0)
    parser.add_argument("--strategy", default="auto", help="Deck intent/strategy, e.g. auto, academic, business, data, product, teaching, document.")
    parser.add_argument("--template", default="", help="Template id to force, e.g. academic_technical, consulting_report, data_journalism.")
    parser.add_argument("--source-mode", default="", help="Optional source mode override: prompt_only, source_grounded, data_driven, brand_template, web_research.")
    parser.add_argument("--style-candidate-index", type=int, default=1, help="Which candidate template direction to use for improved prompts.")
    parser.add_argument("--style-candidate-count", type=int, default=3, help="How many template directions to expose in strategy context.")
    parser.add_argument("--force", action="store_true", help="Regenerate even when a per-slide record already exists.")
    return parser.parse_args()


def _selected_groups(value: str) -> dict[str, list[dict[str, Any]]]:
    all_groups = _suite_groups()
    raw = str(value or "all").strip().lower()
    if raw == "all":
        return all_groups
    selected: dict[str, list[dict[str, Any]]] = {}
    for group_id in [item.strip() for item in raw.split(",") if item.strip()]:
        if group_id not in all_groups:
            raise SystemExit(f"Unknown group: {group_id}")
        selected[group_id] = all_groups[group_id]
    return selected


def _suite_groups() -> dict[str, list[dict[str, Any]]]:
    return {
        "drawai": _drawai_slides(),
        "spatial": _spatial_slides(),
        "battery": _battery_slides(),
        "weather": _weather_slides(),
        "singlecell": _singlecell_slides(),
        "imaging": _imaging_slides(),
        "kimi": _kimi_slides(),
        "agent_memory": _agent_memory_slides(),
        "research_rag": _research_rag_slides(),
        "multimodal_safety": _multimodal_safety_slides(),
        "world_model": _world_model_slides(),
        "ai_infra_cost": _ai_infra_cost_slides(),
    }


def _base_slide(
    *,
    slide_id: str,
    title: str,
    request: str,
    labels: list[str],
    claims: list[str],
    subtitle: str | None = None,
    key_message: str | None = None,
    visual_style: str = "Swiss editorial academic slide, premium but restrained",
    forbidden: list[str] | None = None,
) -> dict[str, Any]:
    resolved_subtitle = subtitle or _default_subtitle(request)
    resolved_key_message = key_message or (claims[0] if claims else "")
    visible_text = _dedupe([title, resolved_subtitle, resolved_key_message, *labels])
    return {
        "id": slide_id,
        "title": title,
        "subtitle": resolved_subtitle,
        "key_message": resolved_key_message,
        "prompt": request,
        "locked_visible_text": visible_text,
        "visible_text_blocks": {
            "title": title,
            "subtitle": resolved_subtitle,
            "takeaway": resolved_key_message,
            "labels": labels,
        },
        "text_density": "medium",
        "claims": [{"claim": claim, "source": "user-supplied academic deck brief"} for claim in claims],
        "research_context": {
            "source_basis": "synthetic user-supplied academic deck brief for prompt-suite evaluation",
            "forbidden": forbidden
            or [
                "invented benchmark numbers",
                "fake citation callouts",
                "fake dataset names",
                "unsupported institution logos",
                "random axis labels",
            ],
        },
        "style": visual_style,
        "size": "2048x1152",
        "quality": "high",
        "background": "opaque",
        "output_format": "png",
        "slide_type": "academic PPT slide image",
        "audience": "researchers and technical reviewers",
        "tone": "rigorous, clear, visually polished",
        "quality_gates": [
            "must look like a finished academic PPT slide, not a template placeholder",
            "visible text must be readable, source-grounded, and sufficient for explanation",
            "no invented metrics, citations, logos, dates, or dataset names",
        ],
    }


def _default_subtitle(request: str) -> str:
    text = request.strip()
    if ":" in text:
        text = text.split(":", 1)[-1].strip()
    text = text.replace("Create slide 1", "").replace("Create slide 2", "").replace("Create slide 3", "")
    text = text.replace("Create slide 4", "").replace("Create slide 5", "").strip(" .")
    words = text.split()
    return " ".join(words[:12]).strip() or "Source-grounded academic overview"


def _drawai_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(
            slide_id="01_overview",
            title="DrawAI Overview",
            request="Create slide 1 of a continuous academic deck introducing DrawAI: figure-to-editable-PPT reconstruction with OCR grounding, segmentation masks, asset selection, and native SVG/PPT rebuild.",
            labels=["DrawAI", "Figure-to-Editable-PPT", "OCR", "Masks", "Assets", "SVG/PPT"],
            claims=["DrawAI reconstructs figures into editable SVG/PPT artifacts using OCR, masks, asset selection, and native rebuild."],
        ),
        _base_slide(
            slide_id="02_problem",
            title="Problem",
            request="Create slide 2 explaining why direct image-to-PPT generation fails: text instability, layout drift, and non-editable output.",
            labels=["Problem", "Text instability", "Layout drift", "Non-editable output"],
            claims=["Direct generated PPT images can suffer from text instability, layout drift, and non-editable artifacts."],
        ),
        _base_slide(
            slide_id="03_pipeline",
            title="Pipeline",
            request="Create slide 3 showing the DrawAI pipeline as a polished left-to-right methods diagram.",
            labels=["Pipeline", "Normalize", "OCR", "Segment", "Select", "Rebuild", "Export"],
            claims=["The pipeline normalizes input, grounds text, segments regions, selects assets, rebuilds native shapes, and exports."],
        ),
        _base_slide(
            slide_id="04_quality_control",
            title="Quality Control",
            request="Create slide 4 explaining visual QA gates for OCR, layout, segmentation, and editable reconstruction.",
            labels=["Quality control", "OCR check", "Layout check", "Asset check", "PPT check"],
            claims=["Quality control checks OCR readability, layout coherence, asset separation, and PPT reconstruction suitability."],
        ),
        _base_slide(
            slide_id="05_takeaway",
            title="Takeaway",
            request="Create slide 5 summarizing the key takeaway: generate high-quality slide images first, then convert through DrawAI to editable artifacts.",
            labels=["Takeaway", "High-quality image first", "Editable reconstruction next"],
            claims=["A high-quality image-first stage can be followed by DrawAI reconstruction for editable artifacts."],
        ),
    ]


def _spatial_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="Spatial Omics Goal", request="Create slide 1 for a spatial transcriptomics atlas deck about integrating tissue image tiles, spot-level expression, and region annotations.", labels=["Spatial atlas", "Tissue image", "Expression", "Regions"], claims=["The atlas concept integrates tissue image tiles, spot-level expression, and region annotations."]),
        _base_slide(slide_id="02_data", title="Data Model", request="Create slide 2 showing a data model with image tiles, spots, embeddings, and annotations; do not invent gene names or numeric counts.", labels=["Data model", "Tiles", "Spots", "Embeddings", "Annotations"], claims=["The data model connects image tiles, spatial spots, embeddings, and annotations."]),
        _base_slide(slide_id="03_method", title="Method", request="Create slide 3 showing a source-safe pipeline for feature extraction, neighborhood aggregation, and atlas visualization.", labels=["Method", "Features", "Neighborhoods", "Atlas view"], claims=["The method concept uses feature extraction, neighborhood aggregation, and atlas visualization."]),
        _base_slide(slide_id="04_validation", title="Validation", request="Create slide 4 showing validation checks with unlabeled schematic charts only; avoid fake metrics and gene labels.", labels=["Validation", "Consistency", "Region match", "Review"], claims=["Validation is framed as consistency checks and region review without supplied metrics."]),
        _base_slide(slide_id="05_summary", title="Summary", request="Create slide 5 summarizing a spatial atlas workflow with neutral diagrams and no biomedical claims beyond the brief.", labels=["Summary", "Integrate", "Explore", "Review"], claims=["The workflow supports integration, exploration, and review of spatial atlas data."]),
    ]


def _battery_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="Materials Discovery Goal", request="Create slide 1 for an academic deck on AI-assisted battery materials discovery using literature features, structure descriptors, and screening loops.", labels=["Materials discovery", "Literature", "Descriptors", "Screening"], claims=["The deck concept combines literature features, structure descriptors, and screening loops."]),
        _base_slide(slide_id="02_problem", title="Search Space", request="Create slide 2 showing the challenge of large materials search spaces with abstract lattice/cards, no chemical formulas or unsupported properties.", labels=["Search space", "Candidates", "Constraints", "Prioritization"], claims=["Large search spaces require candidate prioritization and constraint handling."]),
        _base_slide(slide_id="03_pipeline", title="Screening Pipeline", request="Create slide 3 showing an AI screening pipeline with featurization, surrogate modeling, uncertainty, and candidate review.", labels=["Pipeline", "Featurize", "Model", "Uncertainty", "Review"], claims=["The screening pipeline uses featurization, surrogate modeling, uncertainty, and review."]),
        _base_slide(slide_id="04_decision", title="Decision View", request="Create slide 4 showing a decision dashboard with unlabeled abstract charts and candidate cards; no fake performance values.", labels=["Decision view", "Trade-offs", "Candidates", "Next tests"], claims=["A decision view can organize trade-offs, candidate cards, and next-test planning."]),
        _base_slide(slide_id="05_takeaway", title="Takeaway", request="Create slide 5 summarizing a human-in-the-loop AI discovery process for battery materials.", labels=["Takeaway", "Human-in-the-loop", "Screen", "Validate"], claims=["Human-in-the-loop screening and validation are central to the discovery process."], forbidden=["invented chemical formulas", "fake conductivity values", "unsupported phase names"]),
    ]


def _weather_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="Weather Nowcasting Goal", request="Create slide 1 for a weather nowcasting foundation model deck with radar frames, temporal context, and forecast maps.", labels=["Nowcasting", "Radar frames", "Temporal context", "Forecast"], claims=["The nowcasting concept uses radar frames, temporal context, and forecast outputs."]),
        _base_slide(slide_id="02_input", title="Input Sequence", request="Create slide 2 showing input sequence encoding with stacked abstract radar frames and time arrows; no real map labels.", labels=["Input sequence", "Frames", "Encoding", "Time"], claims=["Input sequence encoding stacks radar-like frames and temporal context."]),
        _base_slide(slide_id="03_model", title="Model", request="Create slide 3 showing a transformer-style temporal model with attention blocks and forecast head.", labels=["Model", "Attention", "Temporal model", "Forecast head"], claims=["The model concept includes temporal attention blocks and a forecast head."]),
        _base_slide(slide_id="04_evaluation", title="Evaluation", request="Create slide 4 showing evaluation views with abstract forecast-vs-observed panels; no fake scores or geography.", labels=["Evaluation", "Observed", "Forecast", "Uncertainty"], claims=["Evaluation compares observed and forecast panels and represents uncertainty without supplied scores."]),
        _base_slide(slide_id="05_summary", title="Summary", request="Create slide 5 summarizing a nowcasting workflow from radar frames to forecast review.", labels=["Summary", "Encode", "Predict", "Review"], claims=["The workflow encodes frames, predicts forecast views, and supports review."], forbidden=["real city names", "fake weather warnings", "real maps", "invented scores"]),
    ]


def _singlecell_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="Perturbation Screening Goal", request="Create slide 1 for a single-cell perturbation screening deck with cells represented only as abstract dots and matrices.", labels=["Perturbation screen", "Cells", "Perturbations", "Readout"], claims=["The screening concept connects perturbations, cells, and readouts."]),
        _base_slide(slide_id="02_design", title="Experimental Design", request="Create slide 2 showing a generic experimental design grid; no gene names, drug names, or numeric counts.", labels=["Design", "Perturb", "Measure", "Compare"], claims=["The design concept perturbs, measures, and compares readouts."]),
        _base_slide(slide_id="03_model", title="Modeling", request="Create slide 3 showing embedding and response modeling with abstract matrices and vector fields.", labels=["Modeling", "Embedding", "Response", "Prediction"], claims=["Modeling uses embeddings and response prediction concepts."]),
        _base_slide(slide_id="04_interpretation", title="Interpretation", request="Create slide 4 showing source-safe interpretation views: clusters, arrows, and rank-like cards with no numbers.", labels=["Interpretation", "Clusters", "Effects", "Review"], claims=["Interpretation views organize clusters, effects, and review without supplied quantitative claims."]),
        _base_slide(slide_id="05_takeaway", title="Takeaway", request="Create slide 5 summarizing perturbation screening as a loop from design to model to review.", labels=["Takeaway", "Design", "Model", "Review"], claims=["The loop runs from design to modeling to review."], forbidden=["gene names", "drug names", "invented effect sizes", "fake cell types"]),
    ]


def _imaging_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="Medical Imaging AI Goal", request="Create slide 1 for a medical imaging foundation model validation deck with generic image panels only, no disease claims.", labels=["Imaging AI", "Images", "Model", "Validation"], claims=["The validation concept connects image inputs, model processing, and review."], forbidden=["disease names", "diagnosis claims", "patient data", "fake metrics"]),
        _base_slide(slide_id="02_data", title="Data Handling", request="Create slide 2 showing privacy-preserving data handling with generic scans and metadata cards; no patient identifiers.", labels=["Data handling", "De-identify", "Curate", "Review"], claims=["Data handling includes de-identification, curation, and review."]),
        _base_slide(slide_id="03_model", title="Model Pipeline", request="Create slide 3 showing a model pipeline from image patches to embeddings to validation views.", labels=["Pipeline", "Patches", "Embeddings", "Validation"], claims=["The model pipeline connects image patches, embeddings, and validation views."]),
        _base_slide(slide_id="04_safety", title="Safety Checks", request="Create slide 4 showing safety and robustness checks with unlabeled abstract charts; no fake sensitivity or specificity.", labels=["Safety checks", "Robustness", "Review", "Escalate"], claims=["Safety checks include robustness, review, and escalation concepts."]),
        _base_slide(slide_id="05_summary", title="Summary", request="Create slide 5 summarizing imaging AI validation as a cautious review workflow.", labels=["Summary", "Validate", "Review", "Report"], claims=["Validation is framed as cautious review and reporting without supplied performance claims."]),
    ]


def _kimi_slides() -> list[dict[str, Any]]:
    kimi_sources = [
        {
            "title": "Moonshot AI official site",
            "url": "https://www.moonshot.ai/",
            "evidence": "Moonshot AI lists Kimi K2-series research, including Kimi K2.6 on 2026-04-20.",
        },
        {
            "title": "MoonshotAI/Kimi-K2 GitHub",
            "url": "https://github.com/MoonshotAI/Kimi-K2",
            "evidence": "Kimi K2 is described as a Mixture-of-Experts model with 1T total parameters and 32B activated parameters, trained with the Muon optimizer and optimized for agentic capabilities.",
        },
        {
            "title": "Kimi k1.5 arXiv",
            "url": "https://arxiv.org/abs/2501.12599",
            "evidence": "Kimi k1.5 reports reinforcement-learning scaling, long-context scaling, multimodal recipes, and long2short methods.",
        },
        {
            "title": "Kimi API Platform model list",
            "url": "https://platform.kimi.ai/docs/models",
            "evidence": "The platform docs list Kimi K2.7 Code, Kimi K2.6, and Kimi K2.5 image-preview models, and state older kimi-k2 series models were discontinued on May 25, 2026 with kimi-k2.6 recommended for continued support.",
        },
        {
            "title": "MoonshotAI/Kimi-K2.5 GitHub",
            "url": "https://github.com/MoonshotAI/Kimi-K2.5",
            "evidence": "Kimi K2.5 is described as an open-source native multimodal agentic model built through continual pretraining on approximately 15T mixed visual and text tokens atop Kimi-K2-Base.",
        },
    ]

    def slide(slide_id: str, title: str, request: str, labels: list[str], claims: list[str], key_message: str) -> dict[str, Any]:
        item = _base_slide(
            slide_id=slide_id,
            title=title,
            request=request,
            labels=labels,
            claims=claims,
            subtitle="Kimi 系列模型的技术路线与效果讲解",
            key_message=key_message,
            visual_style="中文技术汇报 PPT，保留必要英文模型名和术语，前沿模型分析风格，信息密度高但可读",
            forbidden=["fake leaderboard ranks", "unsupported benchmark values", "invented release dates", "fake logos", "unsupported model names"],
        )
        item["research_context"]["sources"] = kimi_sources
        item["sources"] = kimi_sources
        item["text_density"] = "medium-high"
        return item

    return [
        slide(
            "01_lineup",
            "Kimi 系列总览",
            "生成KIMI系列模型的技术和效果讲解PPT，第1页：梳理 Kimi k1.5、Kimi K2、Kimi K2.5、Kimi K2.6、Kimi K2.7 Code 的定位演进，强调只使用来源中提供的信息。",
            ["Kimi k1.5", "Kimi K2", "Kimi K2.5", "Kimi K2.6", "Kimi K2.7 Code", "模型演进"],
            ["Kimi k1.5 与强化学习扩展相关。", "Kimi K2 被描述为 MoE 模型，包含 1T 总参数和 32B 激活参数。", "Kimi API Platform 文档当前列出 Kimi K2.7 Code 和 Kimi K2.6。"],
            "从 RL 扩展走向 agentic 多模态与代码方向模型",
        ),
        slide(
            "02_architecture",
            "技术架构",
            "第2页：讲解 Kimi K2 系列的 MoE、activated parameters、Muon optimizer、agentic capability 等技术结构，避免展示不确定 benchmark 数值。",
            ["MoE 架构", "1T 总参数", "32B 激活参数", "Muon optimizer", "Agentic 能力"],
            ["Kimi K2 被描述为 Mixture-of-Experts 模型，包含 1T 总参数和 32B 激活参数。", "Kimi K2 被描述为使用 Muon optimizer 训练，并面向 agentic 能力优化。"],
            "Kimi K2 的主线是稀疏 MoE 扩展与面向 Agent 的优化",
        ),
        slide(
            "03_rl_reasoning",
            "推理训练",
            "第3页：解释 Kimi k1.5 的强化学习扩展、long-CoT、long2short、多模态训练配方，不画无来源具体排行榜。",
            ["RL scaling", "Long-CoT", "Long2short", "多模态配方"],
            ["Kimi k1.5 报告了强化学习扩展、长上下文扩展、多模态训练配方和 long2short 方法。"],
            "Kimi k1.5 将 RL 作为推理能力扩展轴",
        ),
        slide(
            "04_agentic_effect",
            "Agentic 效果",
            "第4页：用技术效果视角解释 coding、tool use、agentic workflows、vision-language inputs 的工作流价值，并标出 Kimi K2.7 Code 作为代码方向模型，不编具体分数。",
            ["代码能力", "工具调用", "视觉语言", "工作流", "K2.7 Code"],
            ["Kimi K2 面向 agentic 能力优化。", "Kimi K2.5 被描述为结合视觉语言理解与 agentic 范式的原生多模态 agentic 模型。", "Kimi API Platform 文档将 Kimi K2.7 Code 列为当前模型选项。"],
            "效果重点是工作流编排，而不只是聊天质量",
        ),
        slide(
            "05_takeaways",
            "总结与边界",
            "第5页：总结 Kimi 系列的技术主线、适用场景和风险边界，明确旧 K2 系列、K2.6 与 K2.7 Code 的平台模型关系。",
            ["技术主线", "适用场景", "K2.6", "K2.7 Code", "风险边界"],
            ["Kimi API Platform 文档说明旧 kimi-k2 系列模型已于 2026-05-25 停用。", "平台文档建议旧 kimi-k2 迁移场景继续使用 kimi-k2.6。", "Kimi API Platform 文档将 Kimi K2.7 Code 列为当前模型选项。"],
            "模型名称必须来源可查，避免无依据性能结论",
        ),
    ]


def _agent_memory_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="Agent 记忆系统", request="生成一个更难的技术PPT：Agent Memory 系统如何支持长期任务、工具调用和跨会话个性化，第1页讲总体目标。", labels=["Agent 记忆", "长期任务", "工具调用", "个性化"], claims=["Agent 记忆系统可以组织长期任务、工具状态和跨会话个性化概念。"], key_message="记忆让一次性 Agent 变成可持续工作流"),
        _base_slide(slide_id="02_layers", title="记忆分层", request="第2页讲 short-term state、episodic memory、semantic memory、tool traces 的分层，不引入具体产品指标。", labels=["短期状态", "情节记忆", "语义记忆", "工具轨迹"], claims=["记忆架构可以拆分短期状态、情节记录、语义知识和工具轨迹。"], key_message="分层记忆减少上下文拥挤"),
        _base_slide(slide_id="03_retrieval", title="检索策略", request="第3页讲 memory retrieval policy：query routing、freshness、privacy、conflict handling。", labels=["检索", "新鲜度", "隐私", "冲突处理"], claims=["检索策略需要平衡相关性、新鲜度、隐私和冲突处理。"], key_message="检索策略是记忆系统的控制平面"),
        _base_slide(slide_id="04_evaluation", title="记忆评估", request="第4页讲 memory 系统评估：task success、staleness、leakage、latency，用抽象图不要编数值。", labels=["评估", "任务成功", "过期风险", "泄露风险", "延迟"], claims=["记忆评估可以关注任务成功、过期风险、泄露风险和延迟，但不展示未提供数值。"], key_message="记忆质量是多目标权衡"),
        _base_slide(slide_id="05_risks", title="风险边界", request="第5页讲风险边界：错误记忆、隐私泄露、不可解释检索、用户控制。", labels=["风险", "错误记忆", "隐私", "用户控制"], claims=["记忆系统需要围绕错误记忆、隐私泄露、可解释性和用户控制建立约束。"], key_message="持久记忆需要持久治理"),
    ]


def _research_rag_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="引用支撑科研写作 RAG", request="生成一个更难的学术PPT：从网页/论文检索到引用支撑的科研写作 RAG，第1页讲总体架构。", labels=["科研 RAG", "检索", "抽取", "引用"], claims=["科研写作 RAG 连接检索、抽取、综合写作和引用控制。"], key_message="RAG 质量从生成前开始"),
        _base_slide(slide_id="02_sources", title="来源质量", request="第2页讲 source quality：primary source、recency、domain authority、duplicate removal。", labels=["来源质量", "一手来源", "时效性", "权威性", "去重"], claims=["来源质量可以从一手来源、时效性、领域权威和去重四个维度组织。"], key_message="低质来源会产生精致幻觉"),
        _base_slide(slide_id="03_claims", title="结论台账", request="第3页讲 claim ledger：每条结论绑定 source_id、evidence、confidence、freshness。", labels=["结论台账", "source_id", "证据", "新鲜度"], claims=["结论台账可以把结论绑定到来源标识、证据、置信度和新鲜度。"], key_message="每条结论都需要证据轨迹"),
        _base_slide(slide_id="04_synthesis", title="综合写作", request="第4页讲 synthesis：conflict resolution、quote limits、paraphrase、uncertainty labeling。", labels=["综合", "冲突处理", "转述", "不确定性"], claims=["综合写作需要处理证据冲突、转述来源证据并标注不确定性。"], key_message="综合是受控转换，不是自由发挥"),
        _base_slide(slide_id="05_qa", title="质量审查闭环", request="第5页讲 QA loop：citation coverage、unsupported claims、stale facts、visual audit。", labels=["QA 闭环", "引用覆盖", "无支撑结论", "过期事实"], claims=["QA 可以检查引用覆盖率、无支撑结论、过期事实和视觉审查结果。"], key_message="可信度取决于审查强度"),
    ]


def _multimodal_safety_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="多模态安全评估", request="生成一个更难的PPT：多模态模型安全评估体系，第1页讲文本、图像、视频、工具调用的综合风险。", labels=["多模态安全", "文本", "图像", "视频", "工具"], claims=["多模态安全评估关注文本、图像、视频和工具调用风险。"], key_message="安全必须覆盖模态与行动"),
        _base_slide(slide_id="02_threats", title="威胁模型", request="第2页讲 threat model：prompt injection、visual spoofing、unsafe tool use、privacy leakage。", labels=["威胁模型", "注入攻击", "视觉伪装", "工具风险", "隐私"], claims=["威胁建模可以包含注入攻击、视觉伪装、工具风险和隐私泄露。"], key_message="攻击面是多模态的"),
        _base_slide(slide_id="03_tests", title="测试矩阵", request="第3页讲 test matrix：输入类型、任务类型、policy dimension、severity。", labels=["测试矩阵", "输入", "任务", "策略维度", "严重性"], claims=["测试矩阵可以组织输入类型、任务类型、策略维度和严重性。"], key_message="覆盖率需要结构化"),
        _base_slide(slide_id="04_redteam", title="红队闭环", request="第4页讲 red-team loop：case generation、review、mitigation、regression tracking。", labels=["红队闭环", "生成样例", "复核", "缓解", "追踪"], claims=["红队闭环可以生成样例、复核失败、缓解风险并追踪回归。"], key_message="安全改进来自闭环复核"),
        _base_slide(slide_id="05_dashboard", title="安全看板", request="第5页讲 safety dashboard：风险分布、失败样例、版本对比，不编具体分数。", labels=["看板", "风险图", "失败样例", "版本对比"], claims=["安全看板可以展示风险分布、失败样例和版本对比，但不展示未提供分数。"], key_message="报告证据，不编分数"),
    ]


def _world_model_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="世界模型技术栈", request="生成一个更难的PPT：具身智能世界模型技术栈，第1页讲感知、状态、预测、规划闭环。", labels=["世界模型", "感知", "状态", "预测", "规划"], claims=["世界模型技术栈可以连接感知、状态估计、预测和规划。"], key_message="世界模型把交互压缩为可预测状态"),
        _base_slide(slide_id="02_state", title="状态表示", request="第2页讲 state representation：latent state、scene graph、object tokens、uncertainty。", labels=["状态", "潜变量", "场景图", "对象 token", "不确定性"], claims=["状态表示可以包含潜变量、场景图、对象 token 和不确定性。"], key_message="状态是系统瓶颈"),
        _base_slide(slide_id="03_prediction", title="预测模块", request="第3页讲 prediction：future frames、contact dynamics、reward model、failure modes。", labels=["预测", "未来状态", "动力学", "奖励", "失败模式"], claims=["预测可以覆盖未来状态、动力学、奖励和失败模式。"], key_message="预测支撑规划"),
        _base_slide(slide_id="04_planning", title="规划闭环", request="第4页讲 planning loop：simulate、score、select、act、observe。", labels=["规划", "模拟", "评分", "选择", "行动"], claims=["规划闭环可以模拟、评分、选择、行动和观察。"], key_message="规划把系统闭环"),
        _base_slide(slide_id="05_eval", title="具身评估", request="第5页讲 embodied eval：task success、generalization、safety margin、sample efficiency，不编数值。", labels=["评估", "任务成功", "泛化", "安全边界", "样本效率"], claims=["具身评估可以关注任务成功、泛化、安全边界和样本效率。"], key_message="具身评估是多维度问题"),
    ]


def _ai_infra_cost_slides() -> list[dict[str, Any]]:
    return [
        _base_slide(slide_id="01_goal", title="AI Infra Cost Model", request="生成一个更难的PPT：大模型推理成本和服务架构，第1页讲 token、KV cache、batching、latency 的关系。", labels=["AI infra cost", "Tokens", "KV cache", "Batching", "Latency"], claims=["Inference cost can be organized around tokens, KV cache, batching, and latency."], key_message="Cost is a systems problem"),
        _base_slide(slide_id="02_pipeline", title="Serving Pipeline", request="第2页讲 serving pipeline：router、prefill、decode、cache、scheduler。", labels=["Serving", "Router", "Prefill", "Decode", "Cache", "Scheduler"], claims=["A serving pipeline can include routing, prefill, decode, cache, and scheduling."], key_message="Serving separates prefill and decode bottlenecks"),
        _base_slide(slide_id="03_tradeoff", title="Trade-off Space", request="第3页讲 trade-off：throughput、latency、quality、cost、context length，不编价格。", labels=["Trade-offs", "Throughput", "Latency", "Quality", "Cost", "Context"], claims=["Serving design balances throughput, latency, quality, cost, and context length."], key_message="No single knob optimizes all objectives"),
        _base_slide(slide_id="04_optimization", title="Optimization", request="第4页讲 optimization：quantization、speculative decoding、prefix cache、load balancing。", labels=["Optimization", "Quantization", "Spec decode", "Prefix cache", "Balance"], claims=["Optimization concepts include quantization, speculative decoding, prefix caching, and load balancing."], key_message="Optimization is layered"),
        _base_slide(slide_id="05_observability", title="Observability", request="第5页讲 observability：token trace、queue time、cache hit、cost attribution。", labels=["Observability", "Token trace", "Queue time", "Cache hit", "Attribution"], claims=["Observability can track token traces, queue time, cache hits, and cost attribution."], key_message="Measure before optimizing"),
    ]


def _slide_payload(group_id: str, slide: dict[str, Any], args: argparse.Namespace | None = None) -> dict[str, Any]:
    payload = dict(slide)
    payload["prompt"] = f"[Deck group: {group_id}] {slide['prompt']}"
    if args is not None:
        if args.strategy and args.strategy != "auto":
            payload["strategy"] = args.strategy
        if args.template:
            payload["template_id"] = args.template
        if args.source_mode:
            payload["source_mode"] = args.source_mode
        payload["style_candidate_index"] = args.style_candidate_index
        payload["style_candidate_count"] = args.style_candidate_count
        payload["rendering_mode"] = "baked_text"
    return payload


def _load_existing_slide_record(slide_dir: Path) -> dict[str, Any] | None:
    record_path = slide_dir / "record.json"
    if not record_path.exists():
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    generation = record.get("generation")
    if not isinstance(generation, dict):
        return None
    return record


def _record_satisfies_modes(record: Mapping[str, Any], *, modes: str) -> bool:
    generation = record.get("generation")
    if not isinstance(generation, Mapping):
        return False
    required_modes = ("legacy", "improved") if modes == "both" else (modes,)
    return all(_first_image_path(generation.get(mode)) is not None for mode in required_modes)


def _write_contact_sheet(output_dir: Path, records: list[dict[str, Any]]) -> Path | None:
    rows: list[tuple[str, Path | None, Path | None]] = []
    for record in records:
        generation = record.get("generation", {})
        legacy = _first_image_path(generation.get("legacy"))
        improved = _first_image_path(generation.get("improved"))
        if legacy is not None or improved is not None:
            rows.append((f"{record['index']:02d} {record['group']} / {record['title']}", legacy, improved))
    if not rows:
        return None

    thumb_w = 620
    thumb_h = 350
    label_h = 34
    margin = 18
    width = margin * 3 + thumb_w * 2
    height = margin + len(rows) * (thumb_h + label_h + margin)
    sheet = Image.new("RGB", (width, height), (245, 246, 248))
    draw = ImageDraw.Draw(sheet)
    font = _font(18)
    small_font = _font(15)
    for i, (title, legacy, improved) in enumerate(rows):
        y = margin + i * (thumb_h + label_h + margin)
        draw.text((margin, y), f"{title}", fill=(16, 24, 40), font=font)
        draw.text((margin, y + 20), "legacy", fill=(100, 116, 139), font=small_font)
        draw.text((margin * 2 + thumb_w, y + 20), "improved", fill=(100, 116, 139), font=small_font)
        _paste_thumb(sheet, legacy, margin, y + label_h, thumb_w, thumb_h)
        _paste_thumb(sheet, improved, margin * 2 + thumb_w, y + label_h, thumb_w, thumb_h)
    path = output_dir / "contact_sheet.jpg"
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


def _first_image_path(result: Any) -> Path | None:
    if not isinstance(result, dict):
        return None
    images = result.get("images")
    if not isinstance(images, list) or not images:
        return None
    first = images[0]
    if not isinstance(first, dict) or not first.get("path"):
        return None
    return Path(str(first["path"]))


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "output_dir": report.get("output_dir"),
        "slide_count": report.get("slide_count"),
        "groups": report.get("groups"),
        "contact_sheet": report.get("contact_sheet", ""),
        "report_path": str(Path(str(report["output_dir"])) / "suite_report.json"),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_stem(value: str) -> str:
    keep = [ch if ch.isalnum() or ch in "-_." else "_" for ch in value]
    stem = "".join(keep).strip("._")
    return stem or "slide"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


if __name__ == "__main__":
    raise SystemExit(main())
