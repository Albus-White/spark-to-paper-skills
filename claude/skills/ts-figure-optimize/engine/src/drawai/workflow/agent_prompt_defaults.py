from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

RUN0_ELEMENT_REFINE_TASK = """DrawAI asset post-processing and element-plans task.

We are performing an image vectorization task: a bitmap image will eventually be transformed into an editable representation. The whole process has three parts:
- Asset parsing: divide the image into independent assets. Each asset may be text, an icon, table, frame, arrow, and so on.
- Asset post-processing: refine the pre-parsed assets.
- Editable reconstruction: combine assets and finish the final visual result.

Some assets should become editable forms, such as text, frames, arrows, and simple vector graphics. Some assets should instead be cropped from the original image and pasted back into their original positions. The parser/OCR/fusion outputs are evidence, not truth. Execute the second stage, asset post-processing, and produce refined DrawAI element plans that later asset materialization and SVG generation will consume.

Required evidence:
- Original image from the connected input, when available.
- Current DrawAI asset-plan overlay or parser/fusion visualization, when connected.
- Compact candidate table or element candidate JSON.
- Machine-readable request / element candidates / element plans from connected parser or fusion nodes.
- OCR text boxes when visible text content, grouping, or bbox needs confirmation.
- Mask preview sheet and individual mask previews when mask candidates exist.

Task 1: refine the connected candidates into minimum independent assets.
Each output element should be the smallest independent visual part, such as one icon, image, frame, arrow, text line, chart mark, chart block, or diagram component.
- Split a candidate when one box contains multiple independent parts, for example several icons/images inside one block.
- Add a new element when an asset is visible in the original image but not covered by any current candidate.
- Adjust the bbox when the current position is wrong or misses part of a component.
- Remove or merge a candidate only when it is clearly duplicate, noise, or wholly represented by another retained element.
- Preserve traceability. For unchanged or adjusted elements, keep source_candidate_ids pointing to the original candidate ID. For split elements, use stable IDs like B012_S01 with source_candidate_ids ["B012"]. For newly added elements, use stable IDs like N001 with source_candidate_ids [].
- Bboxes must be visual extents in image pixels. For straight lines or dividers, give at least 1 pixel of thickness so width and height are positive.
- Pay close attention to coordinate accuracy and whether each bbox tightly contains the corresponding asset.
- For geometry_kind="mask", use mask_preview PNGs and the mask preview sheet as visual evidence. Do not adjust or resize the mask region; preserve its bbox/geometry when keeping it. Remove or merge a mask candidate only when it is clearly duplicate or noise. Do not read or rely on raw mask files.

Task 2: repeat a bounded visualization/refinement loop until the asset parsing quality is good enough, all elements are reasonable assets, and bbox coordinates are accurate. Run at most 3 iterations.
1. Write the current element-plans JSON for the iteration to reports/element_plans_codex/refine_iteration_<N>.json, where <N> starts at 1.
2. Run assets_visualization.py with the original image and that iteration JSON, using color-mode action and label-mode id_type.
3. Inspect reports/element_plans_codex/assets_visualization_iteration_<N>.png.
4. Correct Task 1 results from the visualization. You may add assets, remove assets, split assets, merge accidental duplicates, and adjust bbox coordinates. One iteration may change any number of assets.
5. Repeat until the assets are correct or 3 iterations have completed.
6. Save the final refined element-plans JSON to the declared output path, normally output/elements.json.

Task 3: classify every final retained output element into exactly one processing intent.
- svg_self_draw: use editable SVG primitives/text/paths directly. Use this for text, arrows, boxes, lines, charts, simple geometric diagrams, and visually simple icons that can be faithfully redrawn.
- crop: use a precise source-image crop with local background preserved. Use this for screenshots, photographs, dense texture, heatmaps, complex small raster icons, or visual details whose background is coupled with the object.
- crop_nobg: use a precise crop after background removal/transparent subject extraction. Use this when the foreground object is separable and should sit over reconstructed SVG background.

Important classification and coverage rules:
- Treat SAM/OCR/current asset plan as evidence, not truth. You may disagree with current_pipeline_method if the image supports it.
- Output only retained final element plans. Do not output removal_records, strategy_summary, refinement_summary, categories, notes, or old element_analysis fields.
- Do not skip real visual assets. Every retained or merged original candidate should appear in source_candidate_ids on at least one output element. Clearly duplicate/noise candidates may be omitted.
- The element_type field must be a concrete DrawAI element type: text, icon, picture, table, chart, diagram, arrow, frame, grid, symbol, content_box, or unknown. For newly added elements, do not use a meta type such as added_asset.
- New IDs are allowed only for split or added refined elements. Keep IDs short and stable.
- If uncertain, choose the most faithful final-source strategy and mark confidence as low or medium.
- After the visualization loop, complete classification in one pass. Write the final JSON file first. Keep change_reason concise.

The final JSON must use format drawai.element_plans.v1 and contain:
- top-level schema="drawai.element_plans.v1"
- elements: array of retained element plans only

Each element plan must contain:
- schema="drawai.element_plan.v1"
- element_id: stable short ID
- source_candidate_ids: list of source candidate IDs; [] only for newly added visual assets
- element_type: text|icon|picture|table|chart|diagram|arrow|frame|grid|symbol|content_box|unknown
- bbox: [x, y, width, height] in image pixels, with positive width and height
- geometry: object; for ordinary boxes use {"kind":"bbox","bbox":[x,y,width,height],"coordinate_system":"figure_image_pixels"}
- z_order: integer, lower values behind higher values
- confidence: low|medium|high
- processing_intent: {"object_type": element_type or a more specific object name, "processing_type": svg_self_draw|crop|crop_nobg, "parameters": {}}
- review_status: agent_refined
- created_by_stage: refine_elements
- change_reason: concise explanation of keep/split/merge/add/bbox/source decision

The declared output JSON file is the source of truth."""

RUN0_ELEMENT_REFINE_CONSTRAINTS = (
    "Use only the connected input files listed in this prompt and explicitly declared built-in script files.",
    "Do not render final SVG/PPT and do not modify repository code. This node only refines/classifies assets.",
    "Do not use MCP tools, apps, web search, memories, skills, hooks, or multi-agent delegation.",
    "Do not print full request JSON to the terminal or logs; start from compact candidate tables and read exact details only when needed.",
    "Output only drawai.element_plans.v1 JSON; do not output codex element analysis, summaries, notes, or removal records.",
    "Write the declared output files exactly, in UTF-8 JSON or markdown according to the output declaration.",
)


@dataclass(frozen=True)
class PageSpecProcessingOperation:
    processing_type: str
    meaning: str
    choose_when: str
    avoid_when: str


PAGE_SPEC_PROCESSING_OPERATIONS = {
    "no_process": PageSpecProcessingOperation(
        processing_type="no_process",
        meaning=(
            "Do not materialize this element in the processing stage. Keep it as PageSpec structure for "
            "downstream SVG Compose to draw from its text, style, geometry, coordinates, and semantics."
        ),
        choose_when=(
            "Choose for text, lines, arrows, shapes, tables, ordinary chart structure, simple vector icons, "
            "background panels, diagrams that should remain structural, and any element that does not need "
            "an independent processed asset."
        ),
        avoid_when=(
            "Do not choose for photos, screenshots, textures, complex raster regions, foreground objects that "
            "need background removal, tiny raster thumbnails, conceptual illustration icons, future-state preview "
            "images, low-quality semantic thumbnails, or elements that require a dedicated processor before SVG Compose."
        ),
    ),
    "crop": PageSpecProcessingOperation(
        processing_type="crop",
        meaning=(
            "Crop the element region from the original image and preserve source pixels, local background, "
            "and raster detail as an independent asset."
        ),
        choose_when=(
            "Choose for photos, screenshots, heatmaps, complex textures, dense raster tiles, small complex "
            "raster icons that must preserve exact source pixels, and regions whose subject is visually coupled "
            "to its local background. Use crop for low-resolution thumbnails only when exact source-pixel "
            "preservation is visibly more important than cleanup or regeneration."
        ),
        avoid_when=(
            "Do not choose for editable text, lines, arrows, simple shapes, ordinary table structure, "
            "transparent foreground objects, elements that SVG Compose can draw directly, or low-resolution "
            "conceptual icons/thumbnails that should be cleaned by image_edit or regenerated by image_generate. "
            "Do not default source-grounded conceptual preview thumbnails to crop when image_edit or "
            "image_generate is enabled and a cleaner asset would preserve the intended visual role better."
        ),
    ),
    "crop_nobg": PageSpecProcessingOperation(
        processing_type="crop_nobg",
        meaning=(
            "Crop the element region and remove its background, producing a transparent foreground asset."
        ),
        choose_when=(
            "Choose for logos, products, people, standalone objects, foreground illustrations, transparent "
            "icons, and visually separable subjects with clear boundaries."
        ),
        avoid_when=(
            "Do not choose for screenshots, heatmaps, textures, software UI, photos whose background must "
            "remain attached, editable structures, or objects whose boundary is too ambiguous for background removal."
        ),
    ),
    "chart_rebuild_reserved": PageSpecProcessingOperation(
        processing_type="chart_rebuild_reserved",
        meaning=(
            "Reserve the element as a future structured chart-rebuild target. It does not produce an asset in "
            "the current processing stage."
        ),
        choose_when="Choose only for chart elements that clearly need future structured chart reconstruction.",
        avoid_when=(
            "Do not choose for non-chart elements, ordinary chart structures that SVG Compose can draw, or "
            "chart screenshots that should be preserved with a crop."
        ),
    ),
    "svg_self_draw": PageSpecProcessingOperation(
        processing_type="svg_self_draw",
        meaning=(
            "Use an SVG processor to generate an independent SVG asset for this element during the processing stage."
        ),
        choose_when=(
            "Choose for complex vector elements that must be generated as standalone SVG assets before final composition."
        ),
        avoid_when=(
            "Do not choose for ordinary text, lines, shapes, tables, or elements that can be drawn by downstream "
            "SVG Compose without an independent asset."
        ),
    ),
    "image_generate": PageSpecProcessingOperation(
        processing_type="image_generate",
        meaning=(
            "Generate a new raster image asset from the element's semantic role, nearby labels, "
            "page context, and target box size. The result will be scaled back into the original PageSpec box."
        ),
        choose_when=(
            "Choose for image-like conceptual graphics, illustrative icons, predicted/future representation "
            "thumbnails, missing or low-quality visual assets, and regions where copying source pixels would "
            "preserve noise rather than a clean representation. Prefer image_generate when the source crop is "
            "missing, too tiny, too noisy, or semantically clear enough to synthesize from labels and surrounding "
            "context. Keep the classifier selective: not every image-like element should be generated if crop, "
            "crop_nobg, image_edit, or no_process is the more faithful operation."
        ),
        avoid_when=(
            "Do not choose for editable text, lines, simple shapes, tables, charts, source pixels that are already "
            "acceptable as crops and must remain pixel-identical, or foreground objects that only need background removal."
        ),
    ),
    "image_edit": PageSpecProcessingOperation(
        processing_type="image_edit",
        meaning=(
            "Crop the source element and edit it into a cleaner raster asset while preserving its original composition, "
            "visual role, colors, aspect, and placement constraints."
        ),
        choose_when=(
            "Choose when the source crop already contains the target object but needs cleanup, redraw, deblurring, "
            "background adjustment, style harmonization, higher-quality reconstruction, or readable preservation "
            "of a tiny conceptual icon. Prefer image_edit over crop for source-grounded thumbnails, previews, "
            "and illustrative icons when the crop is visibly low-resolution but the original composition should "
            "stay recognizable. Keep the classifier selective: use crop/crop_nobg/no_process when source-pixel "
            "preservation, transparent extraction, or structural reconstruction is more faithful."
        ),
        avoid_when=(
            "Do not choose for elements that should remain structural, direct crops that are already good enough "
            "and must remain pixel-identical, fully missing assets better suited to image_generate, or standalone "
            "foreground objects where crop_nobg is sufficient."
        ),
    ),
}

DEFAULT_PAGE_SPEC_REFINE_PROCESSING_TYPES = (
    "no_process",
    "crop",
    "crop_nobg",
    "image_edit",
)


def normalize_page_spec_processing_types(
    processing_types: Sequence[str] | None = None,
    operation_catalog: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    raw_types = (
        DEFAULT_PAGE_SPEC_REFINE_PROCESSING_TYPES
        if processing_types is None
        else processing_types
    )
    if isinstance(raw_types, str):
        raise ValueError("PageSpec processing types must be an array of strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_type in enumerate(raw_types):
        if not isinstance(raw_type, str):
            raise ValueError(f"page_spec_processing_types[{index}] must be a string")
        processing_type = raw_type.strip()
        if not processing_type:
            continue
        if processing_type not in PAGE_SPEC_PROCESSING_OPERATIONS and (
            operation_catalog is None or processing_type not in operation_catalog
        ):
            raise ValueError(f"unsupported PageSpec processing type: {processing_type}")
        if processing_type in seen:
            continue
        normalized.append(processing_type)
        seen.add(processing_type)
    if not normalized:
        raise ValueError("at least one PageSpec processing type must be enabled")
    return tuple(normalized)


def render_page_spec_processing_operations(
    processing_types: Sequence[str] | None = None,
    operation_catalog: Mapping[str, Any] | None = None,
) -> str:
    sections: list[str] = ["## Available Processing Operations"]
    for processing_type in normalize_page_spec_processing_types(
        processing_types,
        operation_catalog=operation_catalog,
    ):
        operation = _page_spec_processing_operation(processing_type, operation_catalog)
        sections.append(
            "\n".join(
                (
                    f"### {operation.processing_type}",
                    "",
                    f"Meaning: {operation.meaning}",
                    "",
                    f"Choose when: {operation.choose_when}",
                    "",
                    f"Do not choose when: {operation.avoid_when}",
                )
            )
        )
    return "\n\n".join(sections)


def _page_spec_processing_operation(
    processing_type: str,
    operation_catalog: Mapping[str, Any] | None,
) -> PageSpecProcessingOperation:
    if operation_catalog is not None and processing_type in operation_catalog:
        raw = operation_catalog[processing_type]
        if isinstance(raw, PageSpecProcessingOperation):
            return raw
        if not isinstance(raw, Mapping):
            raise ValueError(f"page_spec_processing_operations.{processing_type} must be an object")
        return PageSpecProcessingOperation(
            processing_type=processing_type,
            meaning=_operation_text(raw, "meaning", processing_type),
            choose_when=_operation_text(raw, "choose_when", processing_type),
            avoid_when=_operation_text(raw, "avoid_when", processing_type),
        )
    if processing_type not in PAGE_SPEC_PROCESSING_OPERATIONS:
        raise ValueError(f"unsupported PageSpec processing type: {processing_type}")
    return PAGE_SPEC_PROCESSING_OPERATIONS[processing_type]


def _operation_text(raw: Mapping[str, Any], field_name: str, processing_type: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"page_spec_processing_operations.{processing_type}.{field_name} must be a non-empty string")
    return value.strip()


PAGE_SPEC_REFINE_TASK_PREFIX = """DrawAI PageSpec refinement task.

You are operating on one page. The connected PageSpec is the only structured page model for this node. The refined PageSpec elements array is the handoff to every downstream node.

DrawAI's overall task is to vectorize an input image. This node is in the visual element parsing and correction stage. Your job is to refine the previous PageSpec result against the original page image.

Goal: read the original page image and the connected drawai.page_spec.v1 file, then write the refined drawai.page_spec.v1 file to the declared output path. The refinement must correct all page elements: add missing elements, delete redundant elements, split or merge elements, adjust kind, role, coordinates, z-order, text, style, and processing operation.

Required operations:
- Treat the original image as visual truth and the connected PageSpec as evidence.
- Do not inspect DrawAI repository source code, import internal DrawAI modules, or call internal Python APIs to learn schema behavior. Use the declared DrawAI CLI tools, especially `format describe` and `format validate`, for format contracts and validation.
- Keep the PageSpec top-level model page-level only: schema, page_id, source, canvas, background, elements, and metadata.
- Check for redundant and missing elements. Add elements that are visible in the page but missing from the input PageSpec. Remove elements that are duplicate, noise, false positives, or fully represented by another retained element.
- Deletions must be actual deletions from elements. Do not keep deleted elements with a removed flag.
- Check for elements that should be split or merged. Split an element when one box contains multiple independent visual parts that should not share one processing operation. Keep the original id for one dominant split child when appropriate, and create new ids for split-out parts.
- Merge elements when multiple boxes describe the same visual object. Keep the clearest existing id, delete redundant boxes, and adjust the kept element's type, bbox, and processing operation.
- Do not merge elements that require different processing operations. If one element contains parts that require different operations, split it.
- For every retained or new element, set build.processing_type. Use only the processing operations provided in this task prompt. Do not invent or use unavailable operations.
- If an element does not need an independent processed asset, use the processing operation that means no processing/materialization.
- Preserve useful source_refs from upstream PageSpec evidence. For adjusted/new/split/merged elements, add element metadata.refine_action with one of adjusted, added, split_child, or merged_result; add metadata.refine_reason as a short reason; and add metadata.refine_source_ids when the element came from previous element ids.
- Preserve stable ids. Keep the original id for retained or adjusted elements. Do not globally renumber. For added visual elements, continue the existing id style with the next unused E### when possible. For splits, keep the source id on the dominant child if it still represents that child, and create new ids only for the additional children. For merges, keep the clearest existing source id.
- Record a compact top-level metadata.refine_changes object with this shape:
  {"adjusted":[{"id":"E001","fields":["box_px"],"reason":"..."}],"added":[{"id":"E200","reason":"..."}],"split":[{"source_id":"E010","new_ids":["E010","E201"],"reason":"..."}],"merged":[{"source_ids":["E011","E012"],"kept_id":"E011","reason":"..."}],"deleted":[{"id":"E013","reason":"..."}]}
  Use empty arrays when a category has no changes. This is an audit trail only; the refined elements array is the source of truth.

Element field guide:
- id: stable unique element id.
- kind: one of text, shape, image, diagram, connector, table, chart, formula, or unknown.
- role: a more specific semantic role such as title, body_text, logo, photo, icon, axis, legend, diagram, or background_panel.
- box_px: [x, y, width, height] in source image pixels. Width and height must be positive.
- points_px: key points for lines, arrows, or connectors when useful.
- polygon_px: polygon points for non-rectangular regions when useful.
- z_index: visual layer; larger values appear above smaller values.
- text: visible text for text elements only.
- geometry: more precise geometry such as bbox, mask, polygon, or connector endpoints.
- style: visual style such as color, font, size, stroke, fill, opacity, and alignment when known.
- measurement: OCR confidence, text measurement, size estimates, and compact visual evidence.
- source_refs: upstream evidence references. Preserve useful references.
- build.mode: construction mode, such as editable_text, vector, asset_ref, or structured.
- build.processing_type: processing operation. It must be one of the available operations in this prompt.
- build.asset_id: required when the selected processing operation produces an independent asset.
- materialization: generated by a later processing node. Do not write or fake it in this refine node.
- metadata: compact refinement audit fields such as refine_action, refine_reason, and refine_source_ids.

Field updates:
- When adjusting an element, update only fields supported by visual evidence: box_px, geometry, points_px, polygon_px, kind, role, text, z_index, build.mode, build.processing_type, build.asset_id, style, measurement, source_refs, and metadata.
- When adding an element, include id, kind, role, box_px, z_index, source_refs, build.mode, build.processing_type, metadata.refine_action="added", and metadata.refine_reason. Include text for text elements. Include build.asset_id when the operation produces an independent asset.
- When deleting an element, remove it from elements and record the deletion in metadata.refine_changes.deleted.
- When splitting an element, every split child must have its own box_px, kind, role, and build.processing_type. Each split child should preserve source_refs to the source element or source evidence.
- When merging elements, keep one stable id, expand box_px to cover the complete object, merge source_refs without duplicates, delete the redundant elements, and record metadata.refine_action="merged_result".

JSON examples:

Adjusted element:
```json
{
  "id": "E001",
  "kind": "image",
  "role": "logo",
  "box_px": [120, 40, 88, 32],
  "z_index": 20,
  "source_refs": [{"kind": "page_spec_element", "id": "E001"}],
  "build": {"mode": "asset_ref", "processing_type": "crop_nobg", "asset_id": "A001"},
  "metadata": {
    "refine_action": "adjusted",
    "refine_reason": "original bbox missed the right edge of the logo",
    "refine_source_ids": ["E001"]
  }
}
```

Added text element:
```json
{
  "id": "E203",
  "kind": "text",
  "role": "axis_label",
  "box_px": [88, 512, 140, 24],
  "z_index": 15,
  "text": "Accuracy",
  "source_refs": [],
  "build": {"mode": "editable_text", "processing_type": "no_process"},
  "measurement": {"text": "Accuracy", "confidence": "medium"},
  "metadata": {
    "refine_action": "added",
    "refine_reason": "visible axis label was missing from the input PageSpec"
  }
}
```

Top-level audit shape:
```json
{
  "metadata": {
    "refine_changes": {
      "adjusted": [{"id": "E001", "fields": ["box_px", "build.processing_type"], "reason": "..."}],
      "added": [{"id": "E203", "reason": "..."}],
      "split": [{"source_id": "E010", "new_ids": ["E010", "E201"], "reason": "..."}],
      "merged": [{"source_ids": ["E011", "E012"], "kept_id": "E011", "reason": "..."}],
      "deleted": [{"id": "E013", "reason": "..."}]
    }
  }
}
```

"""

PAGE_SPEC_REFINE_TASK_SUFFIX = """Output requirements:

- Write exactly one JSON object with schema drawai.page_spec.v1.
- The output PageSpec must validate under drawai.page_spec.v1.
- Before finishing, run the DrawAI format tool against the declared output path: format validate --format-id drawai.page_spec.v1 --path <declared PageSpec output path>. Finish only after validation reports ok.
- Do not write a sidecar planning or analysis file for this node. Put the final decisions directly in PageSpec elements and metadata.
- Do not embed any other full schema, upstream payload, or compatibility artifact inside metadata; metadata should stay compact and audit-oriented."""


def render_page_spec_refine_task(
    processing_types: Sequence[str] | None = None,
    operation_catalog: Mapping[str, Any] | None = None,
) -> str:
    processing_operations = render_page_spec_processing_operations(
        processing_types,
        operation_catalog=operation_catalog,
    )
    return "\n\n".join(
        (
            PAGE_SPEC_REFINE_TASK_PREFIX.strip(),
            processing_operations,
            PAGE_SPEC_REFINE_TASK_SUFFIX.strip(),
        )
    )


PAGE_SPEC_REFINE_TASK = render_page_spec_refine_task()

PAGE_SPEC_REFINE_TASK_PREFIX_ZH = """DrawAI PageSpec 精修任务。

你正在处理单页图像。连接进来的 PageSpec 是此节点唯一的结构化页面模型。精修后的 PageSpec elements 数组会交给所有下游节点使用。

DrawAI 的整体任务是把输入图像向量化。本节点处于视觉元素解析和校正阶段。你的工作是对照原始页面图像，精修上游 PageSpec 结果。

目标：读取原始页面图像和连接进来的 drawai.page_spec.v1 文件，然后把精修后的 drawai.page_spec.v1 文件写到声明的输出路径。精修必须校正所有页面元素：补充缺失元素、删除冗余元素、拆分或合并元素、调整 kind、role、坐标、z-order、文本、样式和 processing operation。

必须执行的操作：
- 把原始图像当成视觉真值，把连接进来的 PageSpec 当成证据。
- 不要检查 DrawAI 仓库源码、不要导入内部 DrawAI 模块、不要调用内部 Python API 来学习 schema 行为。使用声明的 DrawAI CLI 工具，尤其是 `format describe` 和 `format validate`，来获取格式契约和做校验。
- PageSpec 顶层模型只保留页面级字段：schema、page_id、source、canvas、background、elements 和 metadata。
- 检查冗余和缺失元素。对页面中可见但输入 PageSpec 缺失的元素要新增；对重复、噪声、误检或已经被另一个保留元素完整表示的元素要删除。
- 删除必须是真正从 elements 中删除。不要保留带 removed 标记的 deleted element。
- 检查是否有需要拆分或合并的元素。当一个 box 内包含多个独立视觉部分，且它们不应共享同一个 processing operation 时，要拆分该元素。合适时保留原 id 给主导 split child，并给拆出的其他部分创建新 id。
- 当多个 box 描述同一个视觉对象时要合并。保留最清晰的现有 id，删除冗余 box，并调整保留元素的类型、bbox 和 processing operation。
- 不要合并需要不同 processing operation 的元素。如果一个元素包含需要不同 operation 的部分，应拆分它。
- 对每个保留或新增元素，都设置 build.processing_type。只能使用本 task prompt 中提供的 processing operations。不要发明或使用不可用的 operation。
- 如果某个元素不需要独立处理资产，就使用表示不处理/不 materialize 的 processing operation。
- 保留来自上游 PageSpec 证据中有用的 source_refs。对 adjusted/new/split/merged 元素，在 element metadata 中加入 metadata.refine_action，取值为 adjusted、added、split_child 或 merged_result；加入简短的 metadata.refine_reason；当元素来自之前的 element id 时加入 metadata.refine_source_ids。
- 保持 id 稳定。保留或调整元素时保留原 id。不要全局重编号。对新增视觉元素，尽量沿用现有 id 风格并使用下一个未使用的 E###。拆分时，如果 source id 仍代表主导 child，就保留给它；只给额外 child 创建新 id。合并时保留最清晰的 source id。
- 在顶层 metadata.refine_changes 中记录紧凑变更，形状如下：
  {"adjusted":[{"id":"E001","fields":["box_px"],"reason":"..."}],"added":[{"id":"E200","reason":"..."}],"split":[{"source_id":"E010","new_ids":["E010","E201"],"reason":"..."}],"merged":[{"source_ids":["E011","E012"],"kept_id":"E011","reason":"..."}],"deleted":[{"id":"E013","reason":"..."}]}
  某类没有变更时使用空数组。这只是审计日志；精修后的 elements 数组才是事实来源。

元素字段指南：
- id：稳定且唯一的元素 id。
- kind：text、shape、image、diagram、connector、table、chart、formula 或 unknown 之一。
- role：更具体的语义角色，例如 title、body_text、logo、photo、icon、axis、legend、diagram 或 background_panel。
- box_px：源图像像素坐标中的 [x, y, width, height]。宽高必须为正。
- points_px：对线、箭头或 connector 有帮助时记录关键点。
- polygon_px：对非矩形区域有帮助时记录 polygon points。
- z_index：视觉层级；数值越大越靠上。
- text：仅 text 元素使用的可见文本。
- geometry：更精确的几何，例如 bbox、mask、polygon 或 connector endpoints。
- style：视觉样式，例如 color、font、size、stroke、fill、opacity 和 alignment。
- measurement：OCR confidence、文本测量、尺寸估计和紧凑视觉证据。
- source_refs：上游证据引用。保留有用引用。
- build.mode：构造模式，例如 editable_text、vector、asset_ref 或 structured。
- build.processing_type：processing operation。必须是本 prompt 中可用的 operation 之一。
- build.asset_id：当选择的 processing operation 会产生独立 asset 时必填。
- materialization：由后续 processing node 生成。不要在 refine 节点中写入或伪造。
- metadata：紧凑的 refinement 审计字段，例如 refine_action、refine_reason 和 refine_source_ids。

字段更新：
- 调整元素时，只更新视觉证据支持的字段：box_px、geometry、points_px、polygon_px、kind、role、text、z_index、build.mode、build.processing_type、build.asset_id、style、measurement、source_refs 和 metadata。
- 新增元素时，包含 id、kind、role、box_px、z_index、source_refs、build.mode、build.processing_type、metadata.refine_action="added" 和 metadata.refine_reason。text 元素要包含 text。当 operation 会产生独立 asset 时包含 build.asset_id。
- 删除元素时，从 elements 中移除它，并在 metadata.refine_changes.deleted 中记录删除。
- 拆分元素时，每个 split child 都必须有自己的 box_px、kind、role 和 build.processing_type。每个 split child 应保留指向 source element 或 source evidence 的 source_refs。
- 合并元素时，保留一个稳定 id，扩展 box_px 覆盖完整对象，去重合并 source_refs，删除冗余元素，并记录 metadata.refine_action="merged_result"。

JSON 示例：

Adjusted element:
```json
{
  "id": "E001",
  "kind": "image",
  "role": "logo",
  "box_px": [120, 40, 88, 32],
  "z_index": 20,
  "source_refs": [{"kind": "page_spec_element", "id": "E001"}],
  "build": {"mode": "asset_ref", "processing_type": "crop_nobg", "asset_id": "A001"},
  "metadata": {
    "refine_action": "adjusted",
    "refine_reason": "original bbox missed the right edge of the logo",
    "refine_source_ids": ["E001"]
  }
}
```

Added text element:
```json
{
  "id": "E203",
  "kind": "text",
  "role": "axis_label",
  "box_px": [88, 512, 140, 24],
  "z_index": 15,
  "text": "Accuracy",
  "source_refs": [],
  "build": {"mode": "editable_text", "processing_type": "no_process"},
  "measurement": {"text": "Accuracy", "confidence": "medium"},
  "metadata": {
    "refine_action": "added",
    "refine_reason": "visible axis label was missing from the input PageSpec"
  }
}
```

Top-level audit shape:
```json
{
  "metadata": {
    "refine_changes": {
      "adjusted": [{"id": "E001", "fields": ["box_px", "build.processing_type"], "reason": "..."}],
      "added": [{"id": "E203", "reason": "..."}],
      "split": [{"source_id": "E010", "new_ids": ["E010", "E201"], "reason": "..."}],
      "merged": [{"source_ids": ["E011", "E012"], "kept_id": "E011", "reason": "..."}],
      "deleted": [{"id": "E013", "reason": "..."}]
    }
  }
}
```

"""

PAGE_SPEC_REFINE_TASK_SUFFIX_ZH = """输出要求：

- 只写一个 schema 为 drawai.page_spec.v1 的 JSON object。
- 输出 PageSpec 必须通过 drawai.page_spec.v1 校验。
- 结束前，对声明的输出路径运行 DrawAI format 工具：format validate --format-id drawai.page_spec.v1 --path <declared PageSpec output path>。只有 validation reports ok 后才能结束。
- 不要为此节点写 sidecar planning 或 analysis 文件。把最终决策直接写进 PageSpec elements 和 metadata。
- 不要在 metadata 中嵌入其他完整 schema、上游 payload 或兼容性 artifact；metadata 应保持紧凑并只用于审计。"""


def render_page_spec_refine_task_zh(
    processing_types: Sequence[str] | None = None,
    operation_catalog: Mapping[str, Any] | None = None,
) -> str:
    processing_operations = render_page_spec_processing_operations(
        processing_types,
        operation_catalog=operation_catalog,
    )
    return "\n\n".join(
        (
            PAGE_SPEC_REFINE_TASK_PREFIX_ZH.strip(),
            processing_operations,
            PAGE_SPEC_REFINE_TASK_SUFFIX_ZH.strip(),
        )
    )


PAGE_SPEC_REFINE_TASK_ZH = render_page_spec_refine_task_zh()

PAGE_SPEC_REFINE_CONSTRAINTS = (
    "Use only connected input files listed in this prompt and explicitly declared built-in script files.",
    "Do not inspect repository source code, import internal DrawAI modules, or call internal DrawAI APIs; use declared DrawAI CLI tools for schema/tool contracts.",
    "Do not render final SVG/PPT. This node only refines one PageSpec page.",
    "Do not use MCP tools, apps, web search, memories, skills, hooks, or multi-agent delegation.",
    "Deleted elements must be absent from the output elements array; record deletion only in metadata.refine_changes.",
    "Write the declared PageSpec output exactly as UTF-8 JSON.",
)

SVG_GENERATION_TASK = """IMAGE VECTORIZATION TASK
Goal: convert one bitmap figure into an editable, PPT-stable SVG.

OVERALL DRAWAI PIPELINE
The full DrawAI task is split into three conceptual stages:
1. Asset parsing: SAM/OCR produce PageSpec element evidence for one page.
2. PageSpec refinement and asset preparation: refine the PageSpec elements, adjust bboxes, split/merge elements, add missing elements, decide build.processing_type for each element, and materialize crop/crop_nobg outputs into element.materialization inside the PageSpec bundle.
3. Image editabilization: reconstruct the whole figure as an editable SVG/PPT representation by combining editable SVG primitives/text with allowed raster crop assets.

The current Agent node executes stage 3 only. Do not redo parsing, refinement, or asset preparation. Use the connected original image as visual truth. If the connected input list includes no PageSpec, treat this as the direct-image path from the start. When a materialized PageSpec input is connected, use it as the structured plan and use only its element.materialization outputs as raster asset sources. Your job is to create one complete first-pass SVG, run validation, make the bounded refinement rounds described below, and always finish with the declared final SVG and logs before the agent timeout.

EXECUTION MODEL
- The DrawAI runner prepares the node work directory and connected input files. You must read those files yourself.
- You may use ordinary shell utilities or short local scripts to inspect connected files and write node-local outputs. For DrawAI-specific behavior, do not inspect repository source code, import internal DrawAI modules, or call internal Python APIs; use only the declared DrawAI CLI tools and their `help` / `format describe` contracts.
- The declared SVG output is the semantic output consumed by downstream nodes. This task also intentionally writes auxiliary SVG/render/report/log files inside the same node output directory; those auxiliary files are allowed task artifacts, not additional downstream outputs.
- You must create intermediate SVGs, inspect them, revise them, and finish with the declared final SVG and logs. In PageSpec-connected runs, also create the requested renders/reports with svg-validate.
- Run1 and every refine round may use allowed local raster image hrefs produced from PageSpec element.materialization when the element source is crop or crop_nobg.
- If this node is used in an image-only DAG with no PageSpec input, reconstruct directly from the image, use editable SVG for all structure, do not call page-spec-assets, and validate the final SVG with the format tool instead of PageSpec-backed svg-validate.
- Finalization has higher priority than another refinement round. If the latest SVG validates and is broadly faithful, finalize it immediately.

AVAILABLE FILES AND READING LOGIC
Primary files for this stage:
- Original/current reference image. Use it as the visual truth for layout, color, text placement, arrows, icons, images, tables, axes, and spacing.
- Materialized PageSpec JSON, when connected. Use it as the main structured plan: element ids, kind, role, bbox, z_index, text, style, measurement, grouping, build.processing_type, and materialization outputs.
- PageSpec materialized assets, when connected. Use the declared DrawAI page-spec-assets tool to compute allowed local raster hrefs from the materialized PageSpec for crop/crop_nobg elements.
- SVG validation. In PageSpec-connected runs, use the declared DrawAI svg-validate tool for each SVG/render/report pair. In image-only runs, use format validate for the final SVG and record the validation command in iteration_log.md.

Reading sequence:
1. Start from the original image and the connected materialized PageSpec when present. These sources define what the stage is trying to reproduce.
2. When a PageSpec input is connected, before inserting any raster image href, compute it with the page-spec-assets tool from the connected PageSpec. Use --svg-dir svg so hrefs resolve after the final SVG is mirrored to svg/semantic.svg for preview and PPT export. In image-only runs, skip this step entirely.
3. Do not look for unconnected OCR, template, layout, request, or parser files. OCR/SAM evidence has already been fused into PageSpec when PageSpec is connected.
4. Keep request JSON compact in reasoning. Do not print full JSON files to terminal or logs.

PATH MODEL
- The Agent process cwd is the workflow run root.
- The declared output path shown below is the node-local final SVG, for example nodes/svg_compose/runs/001/output/semantic.svg.
- For PageSpec-connected runs, write every auxiliary file next to that declared output in the same node output directory: semantic_0.svg, rendered_0.png, validation_report_0.json, semantic_1.svg, rendered_1.png, validation_report_1.json, optional semantic_2.svg, optional rendered_2.png, optional validation_report_2.json, rendered.png, validation_report_final.json, iteration_log.md, and iteration_log.jsonl.
- For image-only runs, write semantic_0.svg, semantic_1.svg when a refinement round is used, optional semantic_2.svg only when validation failed, semantic.svg, validation_report_final.json, iteration_log.md, and iteration_log.jsonl. rendered*.png files are optional in image-only runs.
- After this node succeeds, DrawAI mirrors the declared final SVG to svg/semantic.svg for preview and PPT export. You do not write the mirror yourself.
- When a PageSpec input is connected, the mirrored SVG lives under svg/semantic.svg; compute PageSpec asset hrefs with page-spec-assets --svg-dir svg and use those hrefs in every SVG you write. Validate PageSpec-connected SVGs with svg-validate --href-base-dir svg so validation uses the same canonical href base.

SOURCE POLICY
- svg_self_draw: use editable SVG primitives/text for text, formulas, arrows, frames, tables, axes, borders, simple charts, simple icons, and simple diagram components.
- crop: use an exact local crop image for screenshots, photos, dense raster texture, heatmaps, complex small icons, or details that are not worth or not possible to faithfully redraw as SVG.
- crop_nobg: use a no-background crop image when the foreground object is separable and should sit on top of reconstructed editable SVG background.
- Use PageSpec build.processing_type labels as the default. Override only in the SVG source choice when the original image and current render clearly show that another source strategy is more faithful. Record the reason in the iteration log.
- Insert only hrefs returned by the page-spec-assets tool for PageSpec materialization outputs. Do not invent image paths, external URLs, file:// URLs, absolute paths, or base64 images.
- Do not use raster images to cover text, arrows, panels, tables, formulas, axes, or other structure that should remain editable.

RUN1 / COMPLETE FIRST PASS
- Write semantic_0.svg.
- It must be a complete whole-figure SVG, not a placeholder map, skeleton, gray-box map, or list of asset boxes.
- Cover the whole canvas.
- Use SVG/text for svg_self_draw elements.
- Use PageSpec materialization image hrefs for crop/crop_nobg elements when available.
- When a PageSpec input is connected, compute those hrefs with page-spec-assets --svg-dir svg. Even though the declared SVG output is written under this node attempt directory, the hrefs must be valid for the final mirrored SVG under svg/semantic.svg. In image-only runs, do not use image hrefs unless they are already connected as declared inputs.
- Preserve PageSpec bboxes unless visible evidence shows they need adjustment.
- Keep major objects separated and editable where appropriate.
- Avoid overfitting tiny details before the whole figure layout is coherent.
- In PageSpec-connected runs, render/validate semantic_0.svg to rendered_0.png and validation_report_0.json using the svg-validate tool with --href-base-dir svg.
- In image-only runs, skip PageSpec-backed rendering only if no PageSpec input is connected; record that in iteration_log.md and still run format validate --format-id drawai.semantic_svg.v1 --path <declared SVG output path> before finishing.
- Record Run1 in iteration_log.md and iteration_log.jsonl, including what was created, obvious issues, and any crop/crop_nobg regions that still need source decisions.

REFINE LOOP / DEFAULT 1 ROUND, MAX 2 ROUNDS
At the start of each round:
1. Use the latest SVG as input.
2. In PageSpec-connected runs, render it with svg-validate. In image-only runs, render only if a renderer is available through declared tools; otherwise inspect the SVG structure and compare against the original image directly.
3. Compare the render or SVG structure against the original image.
4. First inspect the whole figure, then inspect local regions.
5. Decide the highest-impact fixes yourself.

Refinement budget:
- Default: run exactly one refinement round after Run1, then finalize.
- Skip the refinement round only when Run1 already validates and the whole-figure match is clearly acceptable.
- Run a second refinement round only if the latest validator failed, the render is blank/broken, required raster hrefs are invalid, or one clearly fixable high-impact structure issue would block a useful PPT.
- Do not run a third refinement round in this workflow. Preserve time for finalization.
- For image-only DAGs, never run more than one refinement round unless validation failed. Image-only runs lack PageSpec assets, so prioritize a coherent editable SVG over exhaustive pixel matching.

In each round, consider:
- Whole-figure layout mismatch: canvas scale, panel positions, major blocks, relative spacing, z-order.
- Text mismatch: missing text, wrong content, wrong grouping, wrong size, wrong baseline, wrong color.
- Connector/arrow mismatch: missing arrows, wrong direction, wrong endpoint, wrong arrowhead, wrong layering.
- Shape/table/axis mismatch: wrong borders, grids, ticks, legends, blocks, fills, strokes.
- Asset source mismatch: crop/crop_nobg region redrawn badly, missing PageSpec materialization href, wrong crop/no-background choice, image placed at the wrong bbox.
- Editability regression: text/arrow/table/panel became raster when it should be editable.
- PPT stability issue: unsupported SVG feature, unsafe href, invalid image reference, bad structure for SVG-to-PPT conversion.
- Validator issue: parse error, blank render, asset_href_not_in_manifest, blocked feature, viewBox mismatch, or failed report.

Allowed refine actions:
- Edit SVG shapes, text, groups, arrow geometry, fills, strokes, transforms, z-order, and object IDs.
- Add or remove SVG elements when the original image supports it.
- Insert allowed PageSpec materialization hrefs for crop/crop_nobg regions.
- Replace an unfaithful SVG approximation with an allowed crop/crop_nobg image.
- Replace a crop with editable SVG only when the region is visually simple and the SVG version is faithful.
- Adjust materialized image placement/size to match refined bboxes or visible evidence.
- Correct text from the connected image and PageSpec text fields.

Round outputs:
- In PageSpec-connected runs, Round 1 writes semantic_1.svg, rendered_1.png, and validation_report_1.json.
- In PageSpec-connected runs, optional Round 2 writes semantic_2.svg, rendered_2.png, and validation_report_2.json.
- In image-only runs, Round 1 writes semantic_1.svg when used, and optional Round 2 writes semantic_2.svg only when validation failed. Rendered PNGs and per-round validation reports are optional in image-only runs; validation_report_final.json remains required.

After each round, write to iteration_log.md and iteration_log.jsonl: round number, input SVG, output SVG/render/report, issues found, changes made, asset source changes if any, validation status, and stop or continue decision.

Stop after Run1 or Round 1 when all of these are true:
- The latest validator report is status=\"ok\" for the validation mode available to this DAG.
- The whole-figure render is coherent and broadly close to the original under the current constraints.
- Text, arrows, panels, tables, axes, images, and icons are not obviously missing or broken.
- crop/crop_nobg regions use allowed PageSpec materialization sources, or any exception is explicitly logged.
- Editable structures remain editable.
- Another round would likely improve only small details.

FINALIZATION
- Choose the latest acceptable SVG as the final result.
- Write the accepted final SVG to output/semantic.svg, the declared node-output path.
- In PageSpec-connected runs, render/validate semantic.svg to rendered.png and validation_report_final.json with --href-base-dir svg. Finish only after validation_report_final.json reports status=\"ok\".
- In image-only runs, run format validate --format-id drawai.semantic_svg.v1 --path <declared SVG output path>, write validation_report_final.json with the command result and status, and explain in iteration_log.md that no PageSpec-backed raster validation was available.
- If validation is already ok and time is being spent on minor visual tweaks, stop tweaking and finalize. A complete valid final SVG is better than an unfinished extra refinement.

OVERALL SVG/PPT PROFILE
Target the DrawAI Scientific SVG Profile v1 for editable PPT conversion. Treat the input as an editable scientific structure diagram, not as a bitmap tracing task. Infer the visual language: background, major modules, arrows/connectors, annotations, legends, stroke weights, rounded corners, palette, gradients, typography, and flow direction.
- Use rect for panels/modules/boxes, circle/ellipse for simple nodes/badges/dots, line/polyline for straight or orthogonal connectors, path only when curves/brackets/custom geometry are really needed, polygon for arrowheads or simple closed geometry, text/tspan for all visible text and formulas, and g for stable grouping.
- Use defs only for simple reusable markers or supported gradients. Prefer solid fills for core semantic objects.
- Use image elements only for explicit local raster assets from PageSpec materialization.
- Do not output CSS style blocks, filters, masks, clipPath, foreignObject, textPath, pattern fills, base64 images, external image URLs, absolute paths, symbol, or use.
- Prefer direct SVG presentation attributes over CSS classes for fill, stroke, font-size, opacity, and dash styling.
- Use stable semantic groups with ids prefixed module-, flow-, annotation-, legend-, panel-, connector-, label-, node-, image-, decorative-, or background-.
- For numbered/lettered badges, use a simple circle/ellipse plus centered editable text.
- Prefer orthogonal connector geometry when the source uses horizontal/vertical flows. Route connectors to module edges and avoid crossing text or panel centers.
- Filled or thick block arrows should be one closed shape. Thin connectors should keep shaft and arrowhead together after SVG-to-PPT conversion.
- Render connector arrows after background panels/modules and before raster image assets.
- Preserve editable text with text/tspan. For formulas, render a visible SVG fallback with Unicode math characters and tspan superscript/subscript, and also keep the original LaTeX source on the formula group for PPT export.
- A formula includes standalone mathematical variables or symbols with subscripts, superscripts, accents, Greek letters, operators, or relation signs. Mark these as formula groups even when they are short labels, legends, or isolated variables.
- Do not flatten formula structure into plain text such as alphai, xi2, yhat, or theta0. Use LaTeX for the source and use tspan baseline-shift in the visible fallback for subscripts and superscripts.
- Formula groups must use data-pb-role="formula", data-pb-editable="true", a stable id, data-pb-formula-bbox="x y width height" in SVG viewBox coordinates, and data-pb-formula-latex-b64 with UTF-8 base64 LaTeX. Use data-pb-formula-latex only when the LaTeX is fully XML-escaped.
- Do not display raw LaTeX in the visible SVG text layer. The visible layer is only the SVG fallback; svg_to_ppt reads the hidden LaTeX metadata and exports it as editable Office Math when possible.
- Formula SVG example:
  <g id="label-formula-example" data-pb-role="formula" data-pb-editable="true" data-pb-formula-bbox="100 112 220 40" data-pb-formula-latex-b64="XGFscGhhX2leMitcYmV0YV9pPWNfaQ==">
    <text id="label-formula-example-fallback" x="100" y="140" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="700" fill="#111" text-anchor="start" data-pb-role="formula" data-pb-editable="true" data-pb-text-source="visual_inferred" data-pb-orientation="horizontal">&#945;<tspan baseline-shift="sub" font-size="18">i</tspan><tspan baseline-shift="super" font-size="18">2</tspan> + &#946;<tspan baseline-shift="sub" font-size="18">i</tspan> = c<tspan baseline-shift="sub" font-size="18">i</tspan></text>
    <desc>LaTeX: \\alpha_i^2+\\beta_i=c_i</desc>
  </g>
- Mark non-editable raster assets with data-pb-editable=\"false\" and editable vectors/text with data-pb-editable=\"true\".

FINAL CHECK BEFORE ENDING THIS RUN
- semantic_0.svg exists. In PageSpec-connected runs it also has render/validation output.
- 0-2 refine rounds were run. If 0 rounds were run, explain why Run1 already met the stop condition. If 2 rounds were run, explain the validator failure or high-impact issue that justified it.
- semantic.svg is the accepted final SVG output. In PageSpec-connected runs, rendered.png is the accepted final render output; in image-only runs, rendered.png is optional but validation_report_final.json is required.
- validation_report_final.json is status=\"ok\" for the validation mode available to this DAG.
- iteration_log.md and iteration_log.jsonl explain every round and stop/continue decision.
- Keep the final chat response short; files are the source of truth."""

SVG_GENERATION_TASK_ZH = """任务
你需要完成位图矢量化任务。

目标：把输入的位图图形转换成可编辑 SVG，并且要尽可能还原输入图像的视觉效果。前面的阶段已经使用一些解析方法解析了输入位图，形成大量元素，并封装成 PageSpec 数据格式。这一阶段要基于原图、PageSpec，以及部分已经提前处理好的元素，组合成最终 SVG。

输入原则
1. 原始图像是视觉真值，用来判断 layout、颜色、文字位置、插图、装饰、panel、虚线框、标题和局部修复。要尽可能用 SVG 还原原图的所有视觉效果。
2. PageSpec 是结构计划，用来获取 element id、kind、role、bbox、z_index、text、style、build.processing_type、materialization。
3. 有部分元素已经经过提前处理，不需要用 SVG 重新绘制，而是需要通过贴图方式拼到 SVG 中。
4. 如果 PageSpec 没有表达某个可见元素，需要在脚本的 spec-external section 里补出来。
5. PageSpec 可能出错，包括缺失、冗余、位置错误、类型错误、文字错误等。你需要根据原始图像判断，以还原原始图像为最终目标。PageSpec 只是一个可参考的结构化文件，不是最终视觉真值。

SVG 组合流程
你必须通过修改 Agent 运行上下文中列出的 SVG 生成脚本 run-root path 来生成 SVG。

不要直接手改 semantic_*.svg。

脚本采用 element-id registry 模式：

```python
ELEMENT_RENDERERS = {
    "E001": "draw_svg_e001",
    "E002": ("draw_shape", {"layer": "underlay"}),
    "E012": ("draw_asset", {"href_key": "active", "preserve_aspect_ratio": "xMidYMid meet"}),
    "E053": ("draw_text", {"font_size": 28, "fill": "#111827"}),
    "E006": ("draw_svg_e006", {"bar_color": "#60a5fa"}),
    "E099": ("skip", {"reason": "duplicate/merged/removed"}),
}
```

要求：
1. PageSpec 中每个 element 都必须有一个 ELEMENT_RENDERERS entry。
2. 简单文字可以共用 draw_text 或 draw_text_auto，但仍要通过 element id 显式登记，并通过参数控制字体大小、颜色、粗细、位置偏移等。
3. 已提前处理好的图片、插图、复杂装饰、照片、crop、crop_nobg 元素，可以共用 draw_asset，但只能使用 page-spec-assets 返回的 href。
4. 简单矩形、背景 panel、虚线框、圆角框、普通线条可以共用 draw_shape / draw_connector，并通过参数控制 layer、fill、stroke、rx、stroke_dasharray 等。
5. 复杂 chart、icon、标题 ribbon、特殊装饰、复杂 diagram、非通用结构，必须写 draw_svg_<element_id_lower>() 这种 case-specific 函数，例如 draw_svg_e006()。
6. 确认要删除的 element 用 skip，不要省略 registry entry。省略表示漏处理。
7. 从多个 PageSpec elements 推导出来的背景、分组、横线、整体装饰，放到 draw_derived_from_spec()。
8. PageSpec 里完全没有的视觉元素，放到 draw_extra_outside_spec()。

任务流程
1. 每一轮都修改同一个 build_semantic_svg.py，并把 ROUND_INDEX 递增。
2. 第一轮中，根据真实图像和 PageSpec 填写 ELEMENT_RENDERERS、通用参数和必要的 draw_svg_<element_id>() 函数。
3. 从第二轮开始，根据真实图像和上一轮的 rendered_<last_round_index>.png 修改 build_semantic_svg.py。根据两者不一致的地方，可以增加、删除、移动、重画、改色、改层级、改贴图、改文字、改字体、改虚线、改圆角、改 panel、改装饰。
4. 每一轮修改完成后运行脚本。脚本会生成：
   - semantic_<ROUND_INDEX>.svg
   - rendered_<ROUND_INDEX>.png
   - validation_report_<ROUND_INDEX>.json
   - build_semantic_svg_<ROUND_INDEX>.py
5. 继续执行第 3 步进行迭代。总共最多进行 5 轮迭代。
6. 如果你认为当前可编辑 SVG 的渲染图已经能够尽可能完整地复原输入原始图像，可以提前终止迭代。
7. 只有在你认为新的迭代已经无法进一步提升视觉效果时，才允许提前结束。
8. 以最后一轮生成并通过校验的 semantic_<ROUND_INDEX>.svg 作为 accepted SVG。把这个文件复制到当前 DAG 声明的最终 SVG 路径，供下游节点使用。

校验和停止条件
每一轮都必须使用 svg-validate 生成对应的 render 和 validation report。

如果 validation 失败，需要先修复失败原因，再继续下一轮或结束。不能在最终 validation 失败时结束。

最终结束前必须满足：
1. 最新一轮 validation_report_<ROUND_INDEX>.json 的 status 是 ok。
2. 最新一轮 rendered_<ROUND_INDEX>.png 与原始图像在整体视觉上尽可能一致。
3. 主要文字、插图、背景、panel、标题、装饰、虚线框、答案框、价格标签、图标、局部元素没有明显缺失或错位。
4. 已提前处理好的元素使用允许的 asset href。
5. 可编辑结构仍保持可编辑，不能把整页或主要结构 rasterize。
6. 最终 accepted SVG 已复制到声明的最终 SVG 路径。

SVG/PPT 结构约束
1. 用 SVG primitives/text 表达 text、formula、panel、arrow、table、axis、simple chart、simple icon。
2. 只对已经提前处理好的元素、crop、crop_nobg，或视觉复杂且不适合重画的区域使用 raster asset。
3. 不要 rasterize 整页、文字、箭头、表格、公式、坐标轴或主要结构。
4. 使用稳定 id，例如 shape-E001、label-E053、image-E188、custom-E183。
5. SVG 内避免 CSS style block、filter、mask、clipPath、foreignObject、textPath、pattern、base64、external image URL、absolute path、symbol、use。
6. 优先使用 presentation attributes，例如 fill、stroke、font-size、opacity、stroke-dasharray。
7. 非编辑 raster 标记 data-pb-editable="false"；可编辑 SVG/text 标记 data-pb-editable="true"。
8. 公式使用可见 SVG fallback，并标记 data-pb-role="formula"；不要把公式变成不可编辑图片。

运行命令
从 workflow run root 执行脚本。脚本内部需要使用已声明的 DrawAI CLI tools：page-spec-assets 和 svg-validate。不要 import DrawAI 内部 Python API 来替代这些 tools。

结束前最终检查
- 每个 PageSpec element 都有 ELEMENT_RENDERERS entry，或者明确 skip。
- 每轮运行都保存 build_semantic_svg_<ROUND_INDEX>.py 快照。
- 最新一轮 semantic_<ROUND_INDEX>.svg、rendered_<ROUND_INDEX>.png、validation_report_<ROUND_INDEX>.json 存在。
- validation_report_<ROUND_INDEX>.json 的 status 是 ok。
- accepted SVG 已复制到当前 DAG 声明的最终 SVG 路径。
- iteration_log.md 和 iteration_log.jsonl 简要记录每轮状态和停止原因。
- 最终回复保持简短；文件才是事实来源。"""

SVG_GENERATION_CONSTRAINTS = (
    "只使用本 prompt 中列出的 connected input files、Agent 运行上下文列出的 SVG 生成脚本，以及显式声明的其它脚本文件。",
    "不要检查 repository source code，不要 import internal DrawAI modules，不要调用 internal DrawAI APIs；DrawAI-specific 行为只能使用声明的 DrawAI CLI tools。",
    "不要重做 parsing 或 PageSpec refinement；消费连接进来的 materialized PageSpec 和原始图像。",
    "不要使用 MCP tools、apps、web search、memories、skills、hooks 或 multi-agent delegation。",
    "不要发明 image href、external URL、file:// URL、absolute path 或 base64 image。",
    "不要 rasterize panels、arrows、text、formulas、grids、tables、axes 或整页主要结构。",
    "必须通过 Agent 运行上下文列出的 build_semantic_svg.py 生成 SVG，并让最终 SVG 可由该脚本复现。",
    "每轮运行都要保存脚本快照 build_semantic_svg_<ROUND_INDEX>.py。",
    "最终回复保持简短；文件才是事实来源。",
)

CUSTOM_AGENT_TASK = """Use the connected input files as context and produce exactly the output files declared by this node configuration.

This is a configurable DrawAI Agent node. The node editor controls the task, input inclusion, input descriptions, output declarations, provider, model/profile/reasoning settings, timeout, and runtime constraints. Read the connected files listed in the prompt, follow the declared output formats, and write only the declared outputs."""

CUSTOM_AGENT_CONSTRAINTS = (
    "Treat every connected input file as explicit node context.",
    "Honor the configured output declarations over node defaults.",
    "Write only the declared output paths inside this node work directory.",
)
