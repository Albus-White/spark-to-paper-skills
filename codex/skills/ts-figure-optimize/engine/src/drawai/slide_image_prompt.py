from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .slide_template_library import get_template_card
from .slide_image_strategy import build_slide_image_strategy_manifest


SLIDE_IMAGE_PROMPT_SCHEMA = "drawai.slide_image_prompt.v1"
DEFAULT_SLIDE_CANVAS = "presentation-grade 16:9 slide image"
DEFAULT_DESIGN_PRINCIPLES = (
    "finished PPT explanation page, not a bare layout scaffold",
    "balanced narrative text and visuals",
    "factually restrained content based on the primary request",
    "clear hierarchy with readable body copy",
    "high visual ambition with a polished first-glance impact",
)

CODEX_IMAGEGEN_CONTEXT_FIELDS = {
    "audience",
    "brand",
    "design_system",
    "drawai_postprocess",
    "language",
    "must_avoid",
    "must_include",
    "negative_prompt",
    "quality_gates",
    "slide_mode",
    "slide_type",
    "template",
    "rendering_mode",
    "template_id",
    "template_card",
    "template_card_id",
    "tone",
    "output_language",
    "visual_richness_guidance",
}


def codex_imagegen_context_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return Codex-only prompt context fields without leaking them to the Images API path."""

    return {key: payload[key] for key in CODEX_IMAGEGEN_CONTEXT_FIELDS if key in payload}


def merge_codex_imagegen_context(
    normalized_payload: Mapping[str, Any],
    raw_payload: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(normalized_payload)
    merged.update(codex_imagegen_context_payload(raw_payload))
    return merged


def build_slide_image_generation_manifest(
    payload: Mapping[str, Any],
    *,
    variant_index: int = 1,
    variant_count: int = 1,
) -> dict[str, Any]:
    prompt = _clean_text(payload.get("prompt"))
    strategy = build_slide_image_strategy_manifest(payload)
    manifest: dict[str, Any] = {
        "schema": SLIDE_IMAGE_PROMPT_SCHEMA,
        "primary_request": prompt,
        "variant": {
            "index": int(variant_index),
            "count": int(variant_count),
        },
        "generation_settings": {
            "size": _clean_text(payload.get("size")) or "1024x1024",
            "quality": _clean_text(payload.get("quality")) or "auto",
            "background": _clean_text(payload.get("background")) or "auto",
            "output_format": _clean_text(payload.get("output_format")) or "png",
        },
        "slide_intent": {
            "mode": _clean_text(payload.get("slide_mode")) or "image_first_ppt_slide",
            "type": _clean_text(payload.get("slide_type")) or "single-slide visual",
            "audience": _clean_text(payload.get("audience")),
            "tone": _clean_text(payload.get("tone")),
            "brand": _jsonish(payload.get("brand")),
        },
        "design": {
            "template": _clean_text(payload.get("template")),
            "template_id": _clean_text(payload.get("template_id")),
            "template_card_id": _clean_text(payload.get("template_card_id")),
            "template_card": _template_card_manifest(payload),
            "design_system": _jsonish(payload.get("design_system")),
            "style_references": _jsonish(payload.get("style_references") or payload.get("style_reference")),
            "design_principles": list(DEFAULT_DESIGN_PRINCIPLES),
        },
        "strategy": strategy,
        "text": {
            "requested_language": _requested_language(payload),
            "policy": (
                "Render a normal PPT explanation page with readable in-image title, section labels, and concise "
                "body copy derived from the primary request. Preserve the user's language unless the user explicitly "
                "asks for another language."
            ),
        },
        "inclusion": {
            "must_include": _jsonish(payload.get("must_include")),
            "must_avoid": _jsonish(payload.get("must_avoid")),
            "negative_prompt": _clean_text(payload.get("negative_prompt")),
        },
        "quality_gates": _quality_gates(payload),
        "drawai_postprocess": _drawai_postprocess(payload),
    }
    return manifest


def build_legacy_workbench_image_generation_prompt(
    payload: Mapping[str, Any],
    *,
    variant_index: int = 1,
    variant_count: int = 1,
) -> str:
    """Reproduce the pre-grounding Workbench Codex image prompt for A/B tests."""

    lines = [
        "DrawAI image generation request.",
        f"Primary request: {_clean_text(payload.get('prompt'))}",
        "",
        "Generation settings selected in the DrawAI UI:",
        f"- Requested size/aspect: {payload.get('size')}",
        f"- Quality preference: {payload.get('quality')}",
        f"- Background preference: {payload.get('background')}",
        f"- Output format preference: {payload.get('output_format')}",
        f"- Requested image count: {variant_count}",
    ]
    if variant_count > 1:
        lines.append(
            f"- This tool call should produce image {variant_index} of {variant_count}; "
            "create a distinct useful variant without making a collage."
        )
    if _clean_text(payload.get("background")).lower() == "transparent":
        lines.append(
            "- Transparent background was requested. If true alpha is unavailable, keep the subject isolated on a clean removable background; do not draw a checkerboard pattern."
        )
    lines.extend(
        [
            "",
            "Use the built-in Codex image generation tool for exactly one output image.",
            "Do not render these settings as visible text unless the primary request explicitly asks for text.",
        ]
    )
    return "\n".join(lines)


def build_slide_image_generation_prompt(
    payload: Mapping[str, Any],
    *,
    variant_index: int = 1,
    variant_count: int = 1,
) -> str:
    manifest = build_slide_image_generation_manifest(
        payload,
        variant_index=variant_index,
        variant_count=variant_count,
    )

    lines = [
        "DrawAI high-quality PPT slide image request.",
        "",
        "Goal:",
        "- Produce one premium slide-ready bitmap image for a PPT workflow.",
        "- The image may be non-editable; it will later pass through DrawAI's editable reconstruction pipeline.",
        "- Optimize for visual quality, factual restraint, clear structure, OCR-readability, and downstream segmentation.",
        "- Default rendering mode is baked_text: render complete title, body copy, diagrams, charts, and visual structure directly inside the final bitmap.",
        "- Do not trade away presentation beauty for caution: keep the slide visually memorable, premium, and finished while staying faithful to the primary request.",
        "",
        "Mandatory tool behavior:",
        "- Use the built-in Codex image generation tool for exactly one output image.",
        "- Do not call OpenAI Images API manually.",
        "- Do not use shell commands, web search, MCP tools, or multi-agent delegation in this image-generation turn.",
        "",
        "Primary request:",
        manifest["primary_request"],
        "",
        "Generation settings:",
        *[f"- {key}: {value}" for key, value in manifest["generation_settings"].items()],
        "",
        "Slide intent:",
        *_render_mapping_lines(manifest["slide_intent"]),
        "",
        "Design direction:",
        *_render_mapping_lines(manifest["design"]),
        "",
        "Optional template:",
        *_optional_template_lines(manifest),
        "",
        "Baked text directive:",
        f"- rendering_mode: {manifest['strategy']['rendering_mode']}",
        "- Generate the final PPT slide as a complete bitmap with readable in-image text.",
        "- Do not leave empty placeholders assuming a later text overlay pass.",
        "- DrawAI may reconstruct/edit the generated bitmap later, but this generation step must already be useful to read as a slide.",
        "",
        "Content and text policy:",
        f"- {manifest['text']['policy']}",
        "- Do not infer a scientific domain from words like Nature-style, academic, or high-impact; those describe publication polish unless a domain is explicitly supplied.",
        "- Do not invent statistics, citations, dates, product UI, maps, charts, rankings, logos, or named-entity details.",
        "- Generated decorative visuals may be imaginative, but concrete factual content must come from the primary request.",
        *_language_policy_lines(manifest["text"]),
        "- Match the language of the primary request. If the request is Chinese, render Chinese slide copy; preserve model names, APIs, metrics, and technical terms in English only where they are proper nouns or standard terms.",
        "- Do not translate Chinese headings, bullets, or speaker-facing explanations into English unless the user explicitly requests English.",
        "- Minimum useful text: a clear title, subtitle or takeaway when supplied, readable section/module labels, and 3-6 concise explanatory bullets or callouts.",
        "- For medium-density technical PPT pages, use normal slide copy density: enough text to explain the idea at a glance while preserving spacing.",
        "- Body copy may paraphrase only the primary request.",
        "- Avoid tiny text, gibberish, pseudo-writing, watermark-like marks, signatures, random labels, and unreadable micro-captions.",
        "- If exact long text rendering is risky, split it into shorter readable bullets or callouts; never leave the slide textless.",
        "",
        "Quality gates to satisfy visually:",
        *_render_list_lines(manifest["quality_gates"]),
        "",
        "Visual richness guidance:",
        *_render_list_lines(_visual_richness_guidance(payload)),
        "",
        "DrawAI post-processing constraints:",
        *_render_list_lines(manifest["drawai_postprocess"]),
        "",
        "Variant instruction:",
        _variant_instruction(variant_index, variant_count),
        "",
        "Negative constraints:",
        _compact_json(manifest["inclusion"], limit=3000),
        "",
        'Final response contract: reply only {"generated": true}.',
    ]
    return "\n".join(line for line in lines if line is not None).strip()


def build_slide_image_api_generation_prompt(
    payload: Mapping[str, Any],
    *,
    variant_index: int = 1,
    variant_count: int = 1,
) -> str:
    manifest = build_slide_image_generation_manifest(
        payload,
        variant_index=variant_index,
        variant_count=variant_count,
    )
    lines = [
        "DrawAI high-quality slide image request for an Images API provider.",
        "",
        "Primary request:",
        manifest["primary_request"],
        "",
        "Generation settings:",
        *[f"- {key}: {value}" for key, value in manifest["generation_settings"].items()],
        "",
        "Slide intent:",
        *_render_mapping_lines(manifest["slide_intent"]),
        "",
        "Design direction:",
        *_render_mapping_lines(manifest["design"]),
        "",
        "Optional template:",
        *_optional_template_lines(manifest),
        "",
        "Content and text policy:",
        f"- {manifest['text']['policy']}",
        *_language_policy_lines(manifest["text"]),
        "- Render a complete, readable slide image when the request implies a PPT or explanation page.",
        "- Do not invent statistics, citations, dates, product UI, maps, rankings, logos, or named-entity details.",
        "- Body copy may paraphrase only the primary request.",
        "",
        "Quality gates to satisfy visually:",
        *_render_list_lines(manifest["quality_gates"]),
        "",
        "Visual richness guidance:",
        *_render_list_lines(_visual_richness_guidance(payload)),
        "",
        "DrawAI post-processing constraints:",
        *_render_list_lines(manifest["drawai_postprocess"]),
        "",
        "Variant instruction:",
        _variant_instruction(variant_index, variant_count),
        "",
        "Negative constraints:",
        _compact_json(manifest["inclusion"], limit=3000),
    ]
    return "\n".join(line for line in lines if line is not None).strip()


def build_slide_image_prompt_comparison(
    payload: Mapping[str, Any],
    *,
    variant_index: int = 1,
    variant_count: int = 1,
) -> dict[str, Any]:
    legacy_prompt = build_legacy_workbench_image_generation_prompt(
        payload,
        variant_index=variant_index,
        variant_count=variant_count,
    )
    improved_prompt = build_slide_image_generation_prompt(
        payload,
        variant_index=variant_index,
        variant_count=variant_count,
    )
    manifest = build_slide_image_generation_manifest(
        payload,
        variant_index=variant_index,
        variant_count=variant_count,
    )
    return {
        "schema": "drawai.slide_image_prompt_comparison.v1",
        "variant": {"index": variant_index, "count": variant_count},
        "legacy_prompt": legacy_prompt,
        "improved_prompt": improved_prompt,
        "improved_manifest": manifest,
        "diff_summary": _prompt_diff_summary(legacy_prompt, improved_prompt),
    }


def _quality_gates(payload: Mapping[str, Any]) -> list[str]:
    supplied = _string_list(payload.get("quality_gates"))
    defaults = [
        "single coherent slide, not a collage of unrelated panels",
        "use the full 16:9 canvas with balanced density; avoid large accidental empty regions",
        "presentation polish should be comparable to a manually designed high-impact academic overview slide",
        "contains enough readable explanatory text to be useful as a PPT slide: title, takeaway, section labels, and concise body copy",
        "must not look like a layout-only wireframe or unlabeled component scaffold",
        "clear focal hierarchy with generous margins and no overcrowding",
        "high contrast between foreground and background",
        "no overlapping text or visual elements",
        "no cropped important content near slide edges",
        "no unreadable microtext, mojibake, pseudo-letters, or random captions",
        "data-like visuals must stay abstract unless concrete values are present in the primary request",
        "when verified metrics are unavailable, use unlabeled abstract mini-charts or schematic indicators rather than fake numbers",
        "professional typography and spacing suitable for a 16:9 presentation",
    ]
    return _dedupe([*supplied, *defaults])


def _template_card_manifest(payload: Mapping[str, Any]) -> Any:
    supplied = payload.get("template_card")
    if _has_content(supplied):
        return _jsonish(supplied)
    card_id = _clean_text(payload.get("template_card_id"))
    if not card_id:
        return None
    try:
        card = get_template_card(card_id)
    except KeyError:
        return {"id": card_id, "status": "unknown"}
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "category": card.get("category"),
        "scenario_tags": card.get("scenario_tags"),
        "visual_tags": card.get("visual_tags"),
        "prompt_recipe": card.get("prompt_recipe"),
        "visual_keywords": card.get("visual_keywords"),
        "palette": card.get("palette"),
        "layout_archetypes": card.get("layout_archetypes"),
        "tests": card.get("tests"),
    }


def _template_card_lines(card: Any) -> list[str]:
    if not _has_content(card):
        return ["- no template card selected."]
    if not isinstance(card, Mapping):
        return [f"- {card}"]
    if card.get("status") == "unknown":
        return [f"- requested_template_card_id: {card.get('id')}", "- status: unknown card id; ignore this template card."]
    lines = [
        f"- Card: {card.get('id')} / {card.get('name')}",
        f"- Category: {card.get('category')}",
        f"- Scenario tags: {_compact_json(card.get('scenario_tags'), limit=900)}",
        f"- Visual tags: {_compact_json(card.get('visual_tags'), limit=900)}",
        f"- Prompt recipe: {card.get('prompt_recipe')}",
        f"- Visual keywords: {_compact_json(card.get('visual_keywords'), limit=900)}",
        f"- Palette: {_compact_json(card.get('palette'), limit=900)}",
        f"- Layout archetypes: {_compact_json(card.get('layout_archetypes'), limit=900)}",
    ]
    tests = card.get("tests")
    if _has_content(tests):
        lines.append(f"- Card QA tests: {_compact_json(tests, limit=900)}")
    return [line for line in lines if _has_content(line)]


def _requested_language(payload: Mapping[str, Any]) -> str:
    explicit = _clean_text(payload.get("language") or payload.get("output_language")).lower()
    if explicit in {"zh", "zh-cn", "chinese", "中文", "简体中文"}:
        return "zh"
    if explicit in {"en", "english", "英文"}:
        return "en"
    text = " ".join(
        _clean_text(payload.get(key))
        for key in ("prompt", "tone")
        if _clean_text(payload.get(key))
    )
    return "zh" if _contains_cjk(text) else "auto"


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _language_policy_lines(text_policy: Mapping[str, Any]) -> list[str]:
    if text_policy.get("requested_language") != "zh":
        return ["- main_language: follow the user's request."]
    return [
        "- main_language: Chinese. Use Chinese for the main title, subtitle, section headers, bullets, callouts, captions, warnings, and takeaway text.",
        "- Keep English only for model/product/API names, acronyms, code identifiers, benchmark names, and standard technical terms where Chinese translation would be unnatural.",
        "- Do not render generic English section headings. Use Chinese headings such as 核心结论、来源质量、威胁模型、记忆分层、状态表示、技术栈、风险边界.",
        "- A mixed Chinese/English technical slide is acceptable only when the Chinese text remains dominant and explanatory.",
    ]


def _drawai_postprocess(payload: Mapping[str, Any]) -> list[str]:
    supplied = _string_list(payload.get("drawai_postprocess"))
    defaults = [
        "use crisp object boundaries and clean layer separation where possible",
        "keep text regions high contrast and OCR-friendly if text appears",
        "avoid textured noise directly behind text or chart labels",
        "avoid excessive glow, blur, transparency, and low-contrast gradients over semantic content",
        "prefer simple geometric regions for tables, charts, cards, arrows, and panels",
        "leave enough spacing for DrawAI to segment text, icons, charts, and decorative assets",
    ]
    return _dedupe([*supplied, *defaults])


def _visual_richness_guidance(payload: Mapping[str, Any]) -> list[str]:
    supplied = _string_list(payload.get("visual_richness_guidance"))
    defaults = [
        "do not reduce the slide to five plain cards; add source-safe visual substance inside and around the pipeline",
        "synthetic thumbnails are allowed when they are clearly generic: microscopy-like panels, figure crops, mask overlays, charts, asset swatches, vector nodes, and editable-canvas previews",
        "unlabeled charts may show abstract trends, bars, or scatter patterns for visual metaphor only; do not add axis labels, numeric values, legends with unsupported method names, or performance claims",
        "avoid domain-specific imagery such as biomedical cells, molecules, organs, maps, hardware, company products, or clinical scenes unless provided by the source context",
        "for generic AI/pipeline topics, use neutral paper-figure thumbnails, document crops, layout grids, chart placeholders, mask overlays, UI-free vector diagrams, and editable-canvas previews",
        "show process transformation visually: raw figure -> detected text/regions -> separated assets -> native shapes -> editable slide output",
        "use varied panel scale, subtle shadows, thin rules, and accent color blocks to create depth and a finished editorial look",
        "include enough small visual detail to feel premium, while keeping semantic modules cleanly separable for DrawAI",
        "if a subtitle is useful, derive it only from the primary request and avoid unsupported claims",
    ]
    return _dedupe([*supplied, *defaults])


def _variant_instruction(variant_index: int, variant_count: int) -> str:
    if variant_count <= 1:
        return "Create the strongest single version; do not make a collage or compare alternatives inside the image."
    return (
        f"This is variant {variant_index} of {variant_count}. Keep the same factual content and constraints, "
        "but vary composition, visual metaphor, color balance, or spatial hierarchy. Do not make a collage."
    )


def _prompt_diff_summary(legacy_prompt: str, improved_prompt: str) -> dict[str, Any]:
    improved_checks = {
        "anti_hallucination": "Do not invent" in improved_prompt,
        "ocr_text_policy": "OCR" in improved_prompt or "mojibake" in improved_prompt,
        "drawai_postprocess": "DrawAI post-processing constraints" in improved_prompt,
        "quality_gates": "Quality gates" in improved_prompt,
        "baked_text": "Baked text directive" in improved_prompt,
    }
    legacy_checks = {
        "anti_hallucination": "Do not invent" in legacy_prompt,
        "ocr_text_policy": "OCR" in legacy_prompt or "mojibake" in legacy_prompt,
        "drawai_postprocess": "DrawAI post-processing constraints" in legacy_prompt,
        "quality_gates": "Quality gates" in legacy_prompt,
        "baked_text": "Baked text directive" in legacy_prompt,
    }
    return {
        "legacy_chars": len(legacy_prompt),
        "improved_chars": len(improved_prompt),
        "added_controls": [
            key for key, enabled in improved_checks.items() if enabled and not legacy_checks.get(key)
        ],
        "legacy_controls": [key for key, enabled in legacy_checks.items() if enabled],
        "improved_controls": [key for key, enabled in improved_checks.items() if enabled],
    }


def _render_mapping_lines(value: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, item in value.items():
        if _has_content(item):
            lines.append(f"- {key}: {_compact_json(item, limit=1400) if not isinstance(item, str) else item}")
    return lines or ["- default: premium, modern, presentation-ready visual design"]


def _render_list_lines(values: Sequence[str]) -> list[str]:
    return [f"- {item}" for item in values if item]


def _optional_template_lines(manifest: Mapping[str, Any]) -> list[str]:
    strategy = manifest.get("strategy")
    selected = strategy.get("selected_template") if isinstance(strategy, Mapping) else None
    card = manifest.get("design", {}).get("template_card") if isinstance(manifest.get("design"), Mapping) else None
    lines: list[str] = []
    if not isinstance(selected, Mapping):
        lines.append("- none selected.")
    else:
        lines.extend(
            [
                f"- Template: {selected.get('id')} / {selected.get('name')}",
                f"- Category: {selected.get('category')}",
                f"- Visual direction: {selected.get('visual_direction')}",
                f"- Palette: {selected.get('palette')}",
                f"- Typography: {selected.get('typography')}",
            ]
        )
        template_enforcement = selected.get("template_enforcement")
        if _has_content(template_enforcement):
            lines.append(f"- Template guidance: {template_enforcement}")
        archetypes = selected.get("layout_archetypes")
        if _has_content(archetypes):
            lines.append(f"- Layout options: {_compact_json(archetypes, limit=900)}")
    if _has_content(card):
        lines.extend(_template_card_lines(card))
    return [line for line in lines if _has_content(line)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_clean_text(item) for item in value if _clean_text(item)]
    return [_compact_json(value, limit=1000)]


def _jsonish(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonish(item) for key, item in value.items() if _has_content(item)}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_jsonish(item) for item in value if _has_content(item)]
    return value


def _compact_json(value: Any, *, limit: int) -> str:
    if not _has_content(value):
        return "none"
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return any(_has_content(item) for item in value)
    return True


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped
