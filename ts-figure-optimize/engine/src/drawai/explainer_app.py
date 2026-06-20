from __future__ import annotations

import argparse
import html
import json
import mimetypes
import sys
import urllib.parse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from PIL import Image


CASE_SCHEMA = "drawai.output_explainer_case.v1"
REPORT_FILENAME = "drawai_explainer.generated.html"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
JSON_EXTENSIONS = {".json", ".jsonl"}
SVG_ATTEMPT_INPUT_FIELDS: tuple[tuple[str, str], ...] = (
    ("figure_path", "figure_path"),
    ("reference_image_path", "reference_image_path"),
    ("input_template_svg", "input_template_svg"),
)


KNOWN_ARTIFACTS: tuple[tuple[str, str, str], ...] = (
    ("original_image", "inputs/original.png", "原始输入图"),
    ("figure_image", "inputs/figure.png", "归一化工作图"),
    ("source_metadata", "inputs/source_metadata.json", "输入元数据"),
    ("raw_regions", "sam3/raw_regions.json", "SAM3 汇总 regions"),
    ("sam_boxes_by_prompt", "sam3/sam_boxes_by_prompt.json", "SAM3 prompt 汇总"),
    ("box_ir_raw", "box_ir/box_ir.raw.json", "raw layout IR"),
    ("box_ir_merged", "box_ir/box_ir.merged.json", "合并后 layout IR"),
    ("box_ir", "box_ir/box_ir.json", "最终 layout IR"),
    ("merge_trace", "box_ir/merge_trace.json", "Box 合并 trace"),
    ("box_merge_diagnostics", "box_ir/box_merge_diagnostics.json", "Box 合并诊断"),
    ("semantic_overlay", "box_ir/semantic_overlay.png", "语义 overlay"),
    ("semantic_overlay_legend", "box_ir/semantic_overlay_legend.png", "语义 overlay 图例"),
    ("final_semantic_overlay", "box_ir/final_semantic_overlay.png", "最终 overlay"),
    ("final_semantic_overlay_legend", "box_ir/final_semantic_overlay_legend.png", "最终 overlay 图例"),
    ("ocr_boxes", "ocr/ocr_boxes.json", "OCR 文本框"),
    ("initial_asset_decisions", "svg_to_ppt/assets/initial_asset_decisions.json", "初始资产决策"),
    ("svg_recoverable_assets", "svg_to_ppt/assets/svg_recoverable_assets.json", "可恢复资产列表"),
    ("asset_decisions", "svg_to_ppt/assets/asset_decisions.json", "最终资产决策"),
    ("element_analysis", "reports/element_analysis_codex/element_analysis.json", "run0 元素分析"),
    ("element_analysis_request", "reports/element_analysis_codex/element_analysis_request.json", "run0 元素分析请求"),
    ("element_analysis_validation", "reports/element_analysis_codex/validation.json", "run0 元素分析校验"),
    ("element_analysis_status", "reports/element_analysis_codex/run_status.json", "run0 元素分析状态"),
    ("element_analysis_prompt", "reports/element_analysis_codex/prompt.txt", "run0 元素分析 prompt"),
    ("element_analysis_trace", "reports/element_analysis_codex/codex_element_analysis_trace.jsonl", "run0 元素分析 trace"),
    ("asset_manifest", "svg_to_ppt/assets/asset_manifest.json", "资产 manifest"),
    ("asset_policy_report", "svg_to_ppt/assets/asset_policy_report.json", "资产策略报告"),
    ("asset_recovery_reference", "svg/asset_recovery_reference.png", "资产选择参考图"),
    ("asset_recovery_reference_legend", "svg/asset_recovery_reference_legend.png", "资产选择图例"),
    ("svg_generation_reference", "svg/svg_generation_reference.png", "SVG 生成灰盒参考图"),
    ("svg_generation_reference_legend", "svg/svg_generation_reference_legend.png", "SVG 生成图例"),
    ("visual_template_reference", "svg/template_reference.png", "模板参考图"),
    ("visual_template_reference_legend", "svg/template_reference_legend.png", "模板参考图例"),
    ("svg_template_ir", "svg/svg_template_ir.json", "SVG template IR"),
    ("template_svg", "svg/template.svg", "模板 SVG"),
    ("template_rendered_png", "svg/template_rendered.png", "模板渲染 PNG"),
    ("semantic_svg", "svg/semantic.svg", "最终 semantic SVG"),
    ("rendered_png", "svg/rendered.png", "最终渲染 PNG"),
    ("svg_validation_report", "reports/svg_validation_report.json", "SVG 校验报告"),
    ("svg_to_ppt_export_report", "reports/svg_to_ppt_export_report.json", "PPTX export 报告"),
    ("ppt_optimized", "ppt_optimization/boxir-direct-ppt-optimized.pptx", "直接优化后 PPTX"),
    ("ppt_before_after", "ppt_optimization/boxir-direct-ppt-before-after.pptx", "优化前后对比 PPTX"),
    ("ppt_optimization_manifest", "ppt_optimization/direct-ppt-optimization-manifest.json", "PPT 优化 manifest"),
    ("ppt_optimized_preview", "ppt_optimization/preview/optimized-slide-01.png", "优化后 PPT 预览"),
    ("ppt_before_preview", "ppt_optimization/preview/before-after-slide-01.png", "优化前 PPT 预览"),
    ("ppt_after_preview", "ppt_optimization/preview/before-after-slide-02.png", "优化后 PPT 对比页预览"),
    ("stage_status", "reports/stage_status.json", "阶段状态"),
    ("stage_io_manifest", "reports/stage_io_manifest.json", "阶段 I/O manifest"),
    ("pipeline_summary", "reports/pipeline_summary.json", "Pipeline summary"),
    ("svg_generation_model_trace", "trace/svg_generation_model.jsonl", "Codex/SVG 模型调用 trace"),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve or generate a DrawAI output explainer frontend.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the local frontend server.")
    parser.add_argument("--port", type=int, default=8765, help="Port for the local frontend server.")
    parser.add_argument("--case-dir", help="Default outputs/case_* directory to load.")
    parser.add_argument("--write-html", help="Write a static explainer HTML for this outputs/case_* directory and exit.")
    args = parser.parse_args(argv)

    if args.write_html:
        output_path = write_static_report(Path(args.write_html))
        print(output_path)
        return 0

    server = ExplainerServer((args.host, args.port), _handler_factory(default_case_dir=args.case_dir))
    print(f"DrawAI explainer frontend: http://{args.host}:{args.port}/")
    if args.case_dir:
        query = urllib.parse.urlencode({"path": str(Path(args.case_dir).expanduser().resolve(strict=False))})
        print(f"Default case: http://{args.host}:{args.port}/?{query}")
    server.serve_forever()
    return 0


def load_case_data(case_dir: str | Path) -> dict[str, Any]:
    root = Path(case_dir).expanduser().resolve(strict=False)
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise NotADirectoryError(root)

    artifacts = {key: _artifact(root, key, rel, label) for key, rel, label in KNOWN_ARTIFACTS}
    pipeline_summary = _read_json_if_exists(root / "reports/pipeline_summary.json")
    stage_io = _read_json_if_exists(root / "reports/stage_io_manifest.json")
    compact_stage_io = _append_ppt_optimization_stage_io(_compact_stage_io(stage_io), artifacts)
    stage_status = _read_json_if_exists(root / "reports/stage_status.json")
    source_metadata = _read_json_if_exists(root / "inputs/source_metadata.json")

    prompt_runs = _load_sam_prompt_runs(root)
    boxir_summary = _load_boxir_summary(root)
    ocr_summary = _load_ocr_summary(root)
    asset_summary = _load_asset_summary(root)
    svg_summary = _load_svg_summary(root)
    pptx_summary = _load_pptx_summary(root)
    ppt_optimization_summary = _load_ppt_optimization_summary(root, artifacts)
    codex_rounds = _load_codex_rounds(root)
    svg_attempts = _load_svg_attempts(root)
    svg_runs = _group_svg_runs(svg_attempts)

    return {
        "schema": CASE_SCHEMA,
        "case_dir": str(root),
        "case_name": root.name,
        "run_dir": str(_infer_run_dir(root)),
        "artifacts": artifacts,
        "pipeline_summary": _compact_json(pipeline_summary),
        "stage_io": compact_stage_io,
        "stage_status": _compact_json(stage_status),
        "source_metadata": _compact_json(source_metadata),
        "sam3": {
            "prompt_runs": prompt_runs,
            "prompt_count": len(prompt_runs),
            "total_regions": sum(int(run.get("region_count", 0)) for run in prompt_runs),
        },
        "boxir": boxir_summary,
        "ocr": ocr_summary,
        "assets": asset_summary,
        "svg": svg_summary,
        "pptx": pptx_summary,
        "ppt_optimization": ppt_optimization_summary,
        "codex_rounds": codex_rounds,
        "svg_attempts": svg_attempts,
        "svg_runs": svg_runs,
    }


def write_static_report(case_dir: str | Path, output_path: str | Path | None = None) -> Path:
    root = Path(case_dir).expanduser().resolve(strict=False)
    data = load_case_data(root)
    target = Path(output_path) if output_path is not None else root / "reports" / REPORT_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_full_page(data, mode="static"), encoding="utf-8")
    return target


def render_full_page(data: Mapping[str, Any] | None = None, *, mode: str, default_case_dir: str | None = None) -> str:
    title = "DrawAI 图片转可编辑 SVG/PPTX 全流程解释"
    controls = ""
    report = ""
    body_class = "has-report" if data else "landing"
    if mode == "server":
        default_path = default_case_dir or ""
        controls = f"""
        <section class="loader panel">
          <div>
            <h2>加载 output 目录</h2>
            <p class="muted">读取已经落盘的 case 目录，生成阶段图、输入输出、SAM3 全 prompt、Codex 调用和 PPTX 结果。</p>
          </div>
          <div class="loader-row">
            <input id="case-path" value="{_esc(default_path)}" spellcheck="false" placeholder="/.../outputs/case_001_..." />
            <button id="load-case" type="button">加载</button>
            <button id="load-latest" type="button">最新 case</button>
            <button id="write-static" type="button">生成静态 HTML</button>
          </div>
          <p id="app-status" class="status-line"></p>
        </section>
        """
        report = '<div id="report-root"></div>'
    elif data is not None:
        report = render_report_fragment(data, mode="static")
    else:
        raise ValueError("static mode requires case data")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
  <style>{APP_CSS}</style>
</head>
<body class="{body_class}">
  <header class="hero">
    <div>
      <p class="eyebrow">DrawAI Output Explainer</p>
      <h1>{_esc(title)}</h1>
      <p class="hero-copy">直接从输出目录还原整条处理链：每个阶段读了什么、写了什么、哪些图是模型结果、哪些是确定性逻辑结果。</p>
    </div>
  </header>
  <main>
    {controls}
    {report}
  </main>
  <script>{APP_JS}</script>
</body>
</html>
"""


def render_report_fragment(data: Mapping[str, Any], *, mode: str) -> str:
    resolver = _asset_resolver(data, mode=mode)
    artifacts = data["artifacts"]
    sections = [
        _render_overview(data, artifacts, resolver),
        _render_stage_prepare(artifacts, resolver),
        _render_stage_sam3(data, artifacts, resolver),
        _render_stage_ocr(data, artifacts, resolver),
        _render_stage_boxir(data, artifacts, resolver),
        _render_stage_assets(data, artifacts, resolver),
        _render_stage_svg(data, artifacts, resolver),
        _render_stage_validation(data, artifacts, resolver),
        _render_stage_pptx(data, artifacts, resolver),
        _render_stage_ppt_optimization(data, artifacts, resolver),
        _render_stage_io(data),
        _render_artifact_index(data, artifacts, resolver),
    ]
    nav = """
    <nav class="toc">
      <a href="#overview">总览</a>
      <a href="#prepare">1 输入</a>
      <a href="#sam3">2A SAM3</a>
      <a href="#ocr">2B OCR</a>
      <a href="#boxir">3 layout IR</a>
      <a href="#assets">4 资产</a>
      <a href="#svg">5 SVG/Codex</a>
      <a href="#validate">6 校验</a>
      <a href="#pptx">7 PPTX</a>
      <a href="#ppt-opt">8 PPT 优化</a>
      <a href="#stage-io">I/O</a>
      <a href="#artifact-index">文件</a>
    </nav>
    """
    return nav + "\n".join(sections)


def find_latest_case_dir(runs_root: str | Path = "runs") -> Path | None:
    root = Path(runs_root).expanduser().resolve(strict=False)
    if not root.exists():
        return None
    candidates = [path for path in root.glob("**/outputs/case_*") if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve(strict=False)


class ExplainerServer(ThreadingHTTPServer):
    allow_reuse_address = True


def _handler_factory(default_case_dir: str | None) -> type[BaseHTTPRequestHandler]:
    class ExplainerRequestHandler(BaseHTTPRequestHandler):
        server_version = "DrawAIExplainer/0.1"

        def do_GET(self) -> None:  # noqa: N802 - http.server API.
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path == "/":
                path = query.get("path", [default_case_dir or ""])[0]
                self._send_html(render_full_page(mode="server", default_case_dir=path))
                return
            if parsed.path == "/api/render":
                case_dir = _required_query(query, "path")
                data = load_case_data(case_dir)
                self._send_json({"html": render_report_fragment(data, mode="server"), "case": data})
                return
            if parsed.path == "/api/case":
                self._send_json(load_case_data(_required_query(query, "path")))
                return
            if parsed.path == "/api/latest":
                latest = find_latest_case_dir()
                self._send_json({"case_dir": str(latest) if latest is not None else None})
                return
            if parsed.path == "/file":
                self._send_case_file(query)
                return
            self.send_error(404, "Not found")

        def do_POST(self) -> None:  # noqa: N802 - http.server API.
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/api/write-report":
                self.send_error(404, "Not found")
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            target = write_static_report(payload["path"])
            self._send_json({"path": str(target)})

        def log_message(self, format: str, *args: object) -> None:
            print(format % args, file=sys.stderr)

        def _send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload: Mapping[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_case_file(self, query: Mapping[str, list[str]]) -> None:
            case_dir = Path(_required_query(query, "case")).expanduser().resolve(strict=False)
            rel = _required_query(query, "rel")
            target = (case_dir / rel).resolve(strict=False)
            if not _is_relative_to(target, case_dir):
                self.send_error(403, "File is outside the case directory")
                return
            if not target.exists() or not target.is_file():
                self.send_error(404, "File not found")
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            with target.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    self.wfile.write(chunk)

    return ExplainerRequestHandler


def _render_overview(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    sam3 = data["sam3"]
    boxir = data["boxir"]
    assets = data["assets"]
    svg = data["svg"]
    pptx = data["pptx"]
    ppt_optimization = data["ppt_optimization"]
    stats = [
        ("case", data["case_name"], "输出目录"),
        ("SAM3 prompt", sam3["prompt_count"], f"{sam3['total_regions']} regions"),
        ("OCR", data["ocr"].get("text_box_count", 0), "text boxes"),
        ("layout IR", boxir.get("final_box_count", 0), "semantic boxes"),
        ("Assets", assets.get("asset_count", 0), "raster/hybrid assets"),
        ("Codex", len(data["codex_rounds"]), "model calls"),
        ("SVG", svg.get("semantic_svg_bytes_label", "-"), svg.get("validation_status", "validation")),
        ("PPTX", pptx.get("status", "-"), pptx.get("pptx_bytes_label", "export")),
        ("PPT optimize", ppt_optimization.get("status", "-"), ppt_optimization.get("optimized_pptx_bytes_label", "direct edit")),
    ]
    body = _stat_grid(stats)
    gallery_items = [
        _figure(artifacts["original_image"], "原图", "pipeline 输入拷贝", resolver),
        _figure(artifacts["figure_image"], "工作图", "归一化后的统一坐标系", resolver),
        _figure(artifacts["rendered_png"], "最终 SVG 渲染", "semantic.svg 的 PNG 渲染预览", resolver),
    ]
    if artifacts["ppt_after_preview"].get("exists"):
        gallery_items.append(_figure(artifacts["ppt_after_preview"], "优化后 PPT 预览", "Stage 8 直接 PPT 元素优化后的渲染预览", resolver))
    body += _gallery(gallery_items)
    quick_links = [
        artifacts["semantic_svg"],
        artifacts["rendered_png"],
        artifacts["svg_to_ppt_export_report"],
    ]
    if pptx.get("pptx_artifact"):
        quick_links.append(pptx["pptx_artifact"])
    if artifacts["ppt_optimized"].get("exists"):
        quick_links.append(artifacts["ppt_optimized"])
    if artifacts["ppt_before_after"].get("exists"):
        quick_links.append(artifacts["ppt_before_after"])
    body += _link_strip(quick_links, resolver)
    return _section(
        "overview",
        "0",
        "本轮结果总览",
        "这个页面完全从输出目录读取，不依赖运行时 Python 变量。",
        "directory index",
        body,
    )


def _render_stage_prepare(
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    body = _io_block(
        inputs=[("外部图片", "原始 JPG/PNG")],
        outputs=[artifacts["original_image"], artifacts["figure_image"], artifacts["source_metadata"]],
        resolver=resolver,
    )
    body += _gallery(
        [
            _figure(artifacts["original_image"], "original.png", "原图拷贝", resolver),
            _figure(artifacts["figure_image"], "figure.png", "长边归一化后的工作图，后续 bbox 都在这张图坐标系内", resolver),
        ]
    )
    body += _details_json("source_metadata.json", artifacts["source_metadata"].get("preview", ""))
    return _section("prepare", "1", "输入归一化", "确定性逻辑把输入图落盘成 pipeline 内部统一图像。", "logic", body)


def _render_stage_sam3(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    prompt_runs = data["sam3"]["prompt_runs"]
    rows = []
    figures = []
    for run in prompt_runs:
        rows.append(
            [
                f"<b>{_esc(run['prompt_id'])}</b><small>{_esc(run.get('prompt_text') or '')}</small>",
                _esc(run.get("threshold", "-")),
                str(run.get("region_count", 0)),
                str(run.get("raw_region_count", 0)),
                _format_ms(run.get("elapsed_ms")),
                _file_link(run["json_artifact"], "json", resolver),
            ]
        )
        if run.get("overlay_artifact"):
            figures.append(
                _figure(
                    run["overlay_artifact"],
                    run["prompt_id"],
                    f"{run.get('region_count', 0)} boxes, prompt text: {run.get('prompt_text') or run['prompt_id']}",
                    resolver,
                )
            )
    body = _io_block(
        inputs=[artifacts["figure_image"]],
        outputs=[artifacts["raw_regions"], artifacts["sam_boxes_by_prompt"]],
        resolver=resolver,
        inference=["SAM3 local/http/cli provider"],
    )
    body += _table(["prompt", "阈值", "regions", "raw", "耗时", "记录"], rows)
    body += _gallery(figures, class_name="gallery six")
    body += _details_json("sam_boxes_by_prompt.json", artifacts["sam_boxes_by_prompt"].get("preview", ""))
    return _section(
        "sam3",
        "2A",
        "SAM3 语义 prompt 分割",
        "同一张 figure.png 按固定 prompt 集合分别预测结构候选；每个 prompt 都有自己的 JSON 和 overlay。",
        "model + logic",
        body,
    )


def _render_stage_ocr(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    ocr = data["ocr"]
    body = _io_block(
        inputs=[artifacts["figure_image"]],
        outputs=[artifacts["ocr_boxes"]],
        resolver=resolver,
        inference=[ocr.get("provider") or "OCR provider"],
    )
    body += _stat_grid(
        [
            ("provider", ocr.get("provider", "-"), "OCR runtime"),
            ("text boxes", ocr.get("text_box_count", 0), "recognized boxes"),
            ("elapsed", _format_ms(ocr.get("elapsed_ms")), "provider timing"),
        ]
    )
    body += _details_json("ocr_boxes.json", artifacts["ocr_boxes"].get("preview", ""))
    return _section(
        "ocr",
        "2B",
        "OCR 文本检测",
        "OCR 可以和 SAM3 一样从 prepare 的 figure.png 出发；最终在 assemble layout IR 时合并。",
        "model",
        body,
    )


def _render_stage_boxir(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    boxir = data["boxir"]
    body = _io_block(
        inputs=[artifacts["raw_regions"], artifacts["ocr_boxes"], artifacts["source_metadata"]],
        outputs=[
            artifacts["box_ir_raw"],
            artifacts["box_ir_merged"],
            artifacts["box_ir"],
            artifacts["merge_trace"],
            artifacts["box_merge_diagnostics"],
        ],
        resolver=resolver,
    )
    body += _stat_grid(
        [
            ("raw boxes", boxir.get("raw_box_count", 0), "from SAM3 regions"),
            ("merged boxes", boxir.get("merged_box_count", 0), "after IoU/container merge"),
            ("final boxes", boxir.get("final_box_count", 0), "layout IR boxes"),
            ("OCR text", boxir.get("ocr_text_box_count", 0), "attached text boxes"),
        ]
    )
    body += _gallery(
        [
            _figure(artifacts["semantic_overlay"], "semantic_overlay.png", "合并后的语义 box，还没有 OCR 文本框", resolver),
            _figure(artifacts["semantic_overlay_legend"], "semantic_overlay_legend.png", "语义 overlay 图例", resolver),
            _figure(artifacts["final_semantic_overlay"], "final_semantic_overlay.png", "语义 box + OCR text boxes", resolver),
            _figure(artifacts["final_semantic_overlay_legend"], "final_semantic_overlay_legend.png", "最终 overlay 图例", resolver),
        ],
        class_name="gallery two",
    )
    body += _details_json("box_ir.json", artifacts["box_ir"].get("preview", ""))
    return _section(
        "boxir",
        "3",
        "raw layout IR 构建、合并和文本注入",
        "确定性逻辑把 SAM3/OCR 产物组装成可供后续资产选择和 SVG 生成使用的结构化 IR。",
        "logic",
        body,
    )


def _render_stage_assets(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    assets = data["assets"]
    policy_rows = [[_esc(key), str(value)] for key, value in assets.get("render_policy_counts", {}).items()]
    body = _io_block(
        inputs=[artifacts["figure_image"], artifacts["element_analysis"]],
        outputs=[artifacts["asset_manifest"]],
        resolver=resolver,
        inference=["RMBG only for confirmed no-background raster assets"],
    )
    body += _stat_grid(
        [
            ("decisions", assets.get("decision_count", 0), "asset_decisions"),
            ("manifest assets", assets.get("asset_count", 0), "insertable assets"),
            ("component assets", assets.get("component_asset_count", 0), "split child assets"),
            ("crops", assets.get("crop_count", 0), "files in crops/"),
            ("RMBG elapsed", _format_ms(assets.get("rmbg_elapsed_ms")), "sum from manifest"),
        ]
    )
    body += _gallery(
        [
            _figure(artifacts["asset_recovery_reference"], "asset_recovery_reference.png", "标出哪些区域作为 crop asset", resolver),
            _figure(artifacts["svg_generation_reference"], "svg_generation_reference.png", "给 Codex 的灰盒目标图", resolver),
            _figure(artifacts["visual_template_reference"], "template_reference.png", "模板阶段布局参考图", resolver),
        ],
        class_name="gallery three",
    )
    if policy_rows:
        body += _table(["render_policy", "count"], policy_rows)
    body += _render_asset_gallery(assets, resolver)
    body += _details_json("asset_manifest.json", artifacts["asset_manifest"].get("preview", ""))
    return _section(
        "assets",
        "4",
        "调整后本地素材化",
        "先完成素材调整和确认，再按 refined element plan 裁剪、去背景或保留背景，并生成 asset_manifest。",
        "logic + RMBG",
        body,
    )


def _render_stage_svg(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    codex_rounds = data["codex_rounds"]
    round_blocks = []
    for item in codex_rounds:
        image_links = [_file_link(image, image["label"], resolver) for image in item.get("images", [])]
        round_blocks.append(
            f"""
            <article class="round-card">
              <div class="round-head">
                <span>{_esc(item['label'])}</span>
                <b>{_esc(item.get('model_name') or '-')}</b>
              </div>
              <p class="muted">{_esc(item['purpose'])}</p>
              <div class="mini-label">输入图片</div>
              <div class="links">{''.join(image_links) or '<span class="muted">none</span>'}</div>
              <div class="mini-label">输出</div>
              <p><b>{_esc(str(item.get('output_chars') or '-'))}</b> chars</p>
              <details><summary>请求摘要</summary><pre>{_esc(item.get('request_preview') or '')}</pre></details>
              <details><summary>输出片段</summary><pre>{_esc(item.get('output_excerpt') or '')}</pre></details>
            </article>
            """
        )
    body = _io_block(
        inputs=[
            artifacts["box_ir"],
            artifacts["asset_manifest"],
            artifacts["svg_template_ir"],
            artifacts["svg_generation_reference"],
            artifacts["visual_template_reference"],
        ],
        outputs=[artifacts["template_svg"], artifacts["template_rendered_png"], artifacts["semantic_svg"], artifacts["rendered_png"]],
        resolver=resolver,
        inference=["Codex/OpenAI-compatible SVG invoker", "local SVG render/validation"],
    )
    body += _gallery(
        [
            _figure(artifacts["template_rendered_png"], "template_rendered.png", "Run 1 后的模板渲染结果", resolver),
            _figure(artifacts["rendered_png"], "rendered.png", "最终 semantic.svg 渲染结果", resolver),
        ],
        class_name="gallery two",
    )
    body += _render_svg_runs(data.get("svg_runs") or [], resolver)
    body += '<div class="round-grid">' + "".join(round_blocks) + "</div>"
    body += _link_strip([artifacts["svg_generation_model_trace"], artifacts["semantic_svg"], artifacts["rendered_png"]], resolver)
    return _section(
        "svg",
        "5",
        "SVG 生成和 Codex 调用",
        "这一段有模型参与：Codex 读取灰盒参考图、layout IR/资产约束和前一轮渲染结果，生成并修正 SVG。",
        "LLM/agent + validation",
        body,
    )


def _render_stage_validation(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    svg = data["svg"]
    body = _io_block(
        inputs=[artifacts["semantic_svg"], artifacts["asset_manifest"]],
        outputs=[artifacts["svg_validation_report"], artifacts["rendered_png"]],
        resolver=resolver,
    )
    body += _stat_grid(
        [
            ("status", svg.get("validation_status", "-"), "svg_validation_report"),
            ("issues", svg.get("issue_count", 0), "validation issues"),
            ("bytes", svg.get("semantic_svg_bytes_label", "-"), "semantic.svg"),
        ]
    )
    body += _details_json("svg_validation_report.json", artifacts["svg_validation_report"].get("preview", ""))
    return _section(
        "validate",
        "6",
        "SVG 校验和渲染",
        "本地逻辑检查 SVG profile、引用资源和渲染结果，确保后续能进入 PPTX 编译。",
        "logic",
        body,
    )


def _render_stage_pptx(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    pptx = data["pptx"]
    outputs: list[Mapping[str, Any]] = [artifacts["svg_to_ppt_export_report"]]
    if pptx.get("pptx_artifact"):
        outputs.insert(0, pptx["pptx_artifact"])
    body = _io_block(
        inputs=[artifacts["semantic_svg"], artifacts["asset_manifest"]],
        outputs=outputs,
        resolver=resolver,
        inference=["svg_to_ppt compiler"],
    )
    body += _stat_grid(
        [
            ("status", pptx.get("status", "-"), "export report"),
            ("pptx", pptx.get("pptx_bytes_label", "-"), "PPTX export file"),
            ("issues", pptx.get("issue_count", 0), "reported issues"),
        ]
    )
    body += _details_json("svg_to_ppt_export_report.json", artifacts["svg_to_ppt_export_report"].get("preview", ""))
    return _section(
        "pptx",
        "7",
        "PPTX 导出和检查",
        "把 semantic.svg 和 asset_manifest 导出成 PPTX，再读取 export report 判断是否可打开、是否符合 profile。",
        "compiler + logic",
        body,
    )


def _render_stage_ppt_optimization(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    pptx = data["pptx"]
    ppt_optimization = data["ppt_optimization"]
    inputs: list[Mapping[str, Any] | tuple[str, str]] = []
    if pptx.get("pptx_artifact"):
        inputs.append(pptx["pptx_artifact"])
    else:
        inputs.append(artifacts["svg_to_ppt_export_report"])
    inputs.append(artifacts["original_image"])
    outputs = [
        artifacts["ppt_optimized"],
        artifacts["ppt_before_after"],
        artifacts["ppt_optimization_manifest"],
    ]
    body = _io_block(
        inputs=inputs,
        outputs=outputs,
        resolver=resolver,
        inference=["subagent read-only review", "artifact-tool PPTX import/export"],
    )
    body += _stat_grid(
        [
            ("status", ppt_optimization.get("status", "-"), "direct PPT edit"),
            ("optimized pptx", ppt_optimization.get("optimized_pptx_bytes_label", "-"), "single-slide output"),
            ("before/after", ppt_optimization.get("before_after_pptx_bytes_label", "-"), "two-slide comparison"),
            ("changes", ppt_optimization.get("change_count", 0), "manifest items"),
        ]
    )
    body += _gallery(
        [
            _figure(artifacts["ppt_before_preview"], "优化前 PPT 预览", "Stage 7 产出的初版 PPTX 渲染", resolver),
            _figure(artifacts["ppt_after_preview"], "优化后 PPT 预览", "Stage 8 直接编辑 PPT 元素后的渲染", resolver),
        ],
        class_name="gallery two",
    )
    change_rows = [[_esc(item)] for item in ppt_optimization.get("changes", [])]
    if change_rows:
        body += _table(["优化项"], change_rows)
    body += _details_json("direct-ppt-optimization-manifest.json", artifacts["ppt_optimization_manifest"].get("preview", ""))
    return _section(
        "ppt-opt",
        "8",
        "PPT 元素优化",
        "不再回到 SVG：直接导入 Stage 7 的 PPTX，按原图和 subagent 检查结果调整可编辑 PPT 元素，并输出优化版与前后对比版。",
        "subagent + PPT logic",
        body,
    )


def _render_stage_io(data: Mapping[str, Any]) -> str:
    stage_io = data.get("stage_io") or {}
    stages = stage_io.get("stages") if isinstance(stage_io, Mapping) else None
    rows = []
    if isinstance(stages, Mapping):
        for name, spec in stages.items():
            inputs = ", ".join(_stage_io_names(spec.get("inputs") if isinstance(spec, Mapping) else None))
            outputs = ", ".join(_stage_io_names(spec.get("outputs") if isinstance(spec, Mapping) else None))
            slots = ", ".join(spec.get("inference_slots") or [])
            rows.append([_esc(name), _esc(inputs), _esc(outputs), _esc(slots)])
    body = _table(["stage", "inputs", "outputs", "inference slots"], rows) if rows else "<p class=\"muted\">没有 stage_io_manifest 或当前 run 未写入阶段 I/O。</p>"
    body += _details_json("stage_io_manifest.json", data["artifacts"]["stage_io_manifest"].get("preview", ""))
    return _section(
        "stage-io",
        "I/O",
        "阶段文件边界",
        "这里展示 runner 已经落盘的阶段输入输出边界；页面其它部分会继续从实际目录扫描补齐早期阶段。",
        "manifest",
        body,
    )


def _render_artifact_index(
    data: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    resolver: Callable[[str], str],
) -> str:
    rows = []
    for artifact in artifacts.values():
        if not artifact.get("exists"):
            continue
        rows.append(
            [
                _file_link(artifact, artifact["label"], resolver),
                _esc(artifact.get("rel", "")),
                _esc(artifact.get("bytes_label", "")),
                _esc(artifact.get("kind", "")),
            ]
        )
    body = _table(["artifact", "relative path", "size", "type"], rows)
    body += f"<p class=\"note\">case_dir: <code>{_esc(data['case_dir'])}</code></p>"
    return _section(
        "artifact-index",
        "F",
        "输出文件索引",
        "页面中的所有图、JSON、SVG 和 PPTX 链接都来自这个 output 目录。",
        "files",
        body,
    )


def _load_sam_prompt_runs(root: Path) -> list[dict[str, Any]]:
    prompt_dir = root / "sam3" / "prompt_runs"
    runs: list[dict[str, Any]] = []
    if not prompt_dir.exists():
        return runs
    for path in sorted(prompt_dir.glob("*.json")):
        payload = _read_json(path)
        prompt_id = str(payload.get("prompt_id") or path.stem)
        request_prompts = ((payload.get("request") or {}).get("prompts") or [{}])
        prompt_meta = request_prompts[0] if request_prompts else {}
        regions = payload.get("regions") or (payload.get("response") or {}).get("regions") or []
        raw_regions = payload.get("raw_regions") or (payload.get("response") or {}).get("raw_regions") or []
        overlay_rel = f"sam3/prompt_overlays/{path.stem}.png"
        runs.append(
            {
                "prompt_id": prompt_id,
                "prompt_text": prompt_meta.get("text") or prompt_id,
                "threshold": prompt_meta.get("confidence_threshold"),
                "region_count": len(regions),
                "raw_region_count": len(raw_regions),
                "elapsed_ms": payload.get("elapsed_ms"),
                "json_artifact": _artifact(root, f"sam3_prompt_{prompt_id}", _rel(root, path), f"{prompt_id}.json"),
                "overlay_artifact": _artifact(root, f"sam3_overlay_{prompt_id}", overlay_rel, f"{prompt_id}.png")
                if (root / overlay_rel).exists()
                else None,
            }
        )
    return runs


def _load_boxir_summary(root: Path) -> dict[str, Any]:
    raw = _read_json_if_exists(root / "box_ir/box_ir.raw.json") or {}
    merged = _read_json_if_exists(root / "box_ir/box_ir.merged.json") or {}
    final = _read_json_if_exists(root / "box_ir/box_ir.json") or {}
    return {
        "raw_box_count": len(raw.get("boxes") or []),
        "merged_box_count": len(merged.get("boxes") or []),
        "final_box_count": len(final.get("boxes") or []),
        "ocr_text_box_count": len(final.get("ocr_text_boxes") or []),
        "canvas": final.get("canvas") or merged.get("canvas") or raw.get("canvas") or {},
    }


def _load_ocr_summary(root: Path) -> dict[str, Any]:
    payload = _read_json_if_exists(root / "ocr/ocr_boxes.json") or {}
    boxes = payload.get("ocr_text_boxes") or payload.get("boxes") or payload.get("text_boxes") or payload.get("results") or []
    return {
        "provider": payload.get("provider"),
        "elapsed_ms": payload.get("elapsed_ms"),
        "text_box_count": len(boxes),
    }


def _load_asset_summary(root: Path) -> dict[str, Any]:
    decisions_payload = _read_json_if_exists(root / "svg_to_ppt/assets/asset_decisions.json") or {}
    manifest = _read_json_if_exists(root / "svg_to_ppt/assets/asset_manifest.json") or {}
    assets = manifest.get("assets") or []
    render_policy_counts = Counter(str(asset.get("render_policy") or "unknown") for asset in assets)
    active_variant_counts = Counter(str(asset.get("active_variant") or "unknown") for asset in assets)
    rmbg_elapsed_ms = sum(float(asset.get("rmbg_elapsed_ms") or 0) for asset in assets)
    crops_dir = root / "svg_to_ppt/assets/crops"
    crop_paths = sorted(crops_dir.glob("*.png")) if crops_dir.exists() else []
    decisions = decisions_payload.get("decisions") or decisions_payload.get("assets") or []
    asset_items = _manifest_asset_items(root, assets)
    return {
        "decision_count": len(decisions),
        "asset_count": len(assets),
        "component_asset_count": len([item for item in asset_items if item.get("item_type") == "component"]),
        "display_asset_count": len(asset_items),
        "crop_count": len(crop_paths),
        "crop_files": [
            _artifact(root, f"asset_crop_{index}", _rel(root, path), path.name)
            for index, path in enumerate(crop_paths, start=1)
        ],
        "asset_items": asset_items,
        "render_policy_counts": dict(render_policy_counts),
        "active_variant_counts": dict(active_variant_counts),
        "rmbg_elapsed_ms": rmbg_elapsed_ms,
    }


def _manifest_asset_items(root: Path, assets: Sequence[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, raw_asset in enumerate(assets, start=1):
        if not isinstance(raw_asset, Mapping):
            continue
        items.append(_manifest_asset_item(root, raw_asset, index=index, item_type="asset"))
        for component_index, raw_component in enumerate(raw_asset.get("insertable_components") or [], start=1):
            if not isinstance(raw_component, Mapping):
                continue
            items.append(
                _manifest_asset_item(
                    root,
                    raw_component,
                    index=component_index,
                    item_type="component",
                    parent_asset_id=str(raw_asset.get("asset_id") or ""),
                )
            )
    return items


def _manifest_asset_item(
    root: Path,
    asset: Mapping[str, Any],
    *,
    index: int,
    item_type: str,
    parent_asset_id: str = "",
) -> dict[str, Any]:
    asset_id = str(asset.get("asset_id") or asset.get("component_id") or f"asset_{index:03d}")
    source_artifact = _artifact_from_manifest_href(root, f"{asset_id}_source", asset.get("source_svg_href"), f"{asset_id}.png")
    active_artifact = _artifact_from_manifest_href(
        root,
        f"{asset_id}_active",
        asset.get("svg_href") or asset.get("nobg_svg_href") or asset.get("source_svg_href"),
        f"{asset_id} active",
    )
    nobg_artifact = _artifact_from_manifest_href(root, f"{asset_id}_nobg", asset.get("nobg_svg_href"), f"{asset_id}_nobg.png")
    components = asset.get("components") if isinstance(asset.get("components"), list) else []
    return {
        "asset_id": asset_id,
        "parent_asset_id": parent_asset_id or str(asset.get("parent_asset_id") or ""),
        "item_type": item_type,
        "box_id": str(asset.get("box_id") or ""),
        "bbox": asset.get("bbox") or asset.get("local_bbox") or [],
        "render_policy": str(asset.get("render_policy") or "-"),
        "active_variant": str(asset.get("active_variant") or "-"),
        "background_policy": str(asset.get("background_policy") or "-"),
        "split_policy": str(asset.get("split_policy") or "-"),
        "confidence": str(asset.get("confidence") or "-"),
        "current_label": str(asset.get("current_label") or "-"),
        "should_run_rmbg": asset.get("should_run_rmbg"),
        "rmbg_elapsed_ms": asset.get("rmbg_elapsed_ms"),
        "width": asset.get("width") or asset.get("source_width"),
        "height": asset.get("height") or asset.get("source_height"),
        "reason_codes": [str(item) for item in (asset.get("policy_reason_codes") or asset.get("reason_codes") or [])],
        "component_count": len(components),
        "component_kinds": dict(Counter(str(component.get("kind") or "unknown") for component in components if isinstance(component, Mapping))),
        "source_artifact": source_artifact,
        "active_artifact": active_artifact,
        "nobg_artifact": nobg_artifact,
        "metadata_preview": _json_preview(asset, limit=3500),
    }


def _artifact_from_manifest_href(root: Path, key: str, href: Any, label: str) -> dict[str, Any] | None:
    rel = _manifest_href_rel(root, href)
    if rel is None:
        return None
    return _artifact(root, key, rel, label)


def _manifest_href_rel(root: Path, href: Any) -> str | None:
    if not href:
        return None
    text = str(href).strip()
    if not text or text.startswith(("data:", "http://", "https://")):
        return None
    parsed = urllib.parse.urlparse(text)
    path_text = urllib.parse.unquote(parsed.path or text)
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return _rel_or_none(root, path.resolve(strict=False))
    parts = [part for part in Path(path_text).parts if part not in ("", ".")]
    while parts and parts[0] == "..":
        parts = parts[1:]
    if not parts:
        return None
    rel = "/".join(parts)
    target = (root / rel).resolve(strict=False)
    if _is_relative_to(target, root):
        return rel
    return None


def _load_svg_summary(root: Path) -> dict[str, Any]:
    semantic_svg = root / "svg/semantic.svg"
    report = _read_json_if_exists(root / "reports/svg_validation_report.json") or _read_json_if_exists(root / "svg/svg_validation_report.json") or {}
    issues = report.get("issues") or []
    return {
        "semantic_svg_bytes": semantic_svg.stat().st_size if semantic_svg.exists() else 0,
        "semantic_svg_bytes_label": _format_bytes(semantic_svg.stat().st_size) if semantic_svg.exists() else "-",
        "validation_status": report.get("status") or report.get("result") or "-",
        "issue_count": len(issues),
    }


def _load_pptx_summary(root: Path) -> dict[str, Any]:
    report = _read_json_if_exists(root / "reports/svg_to_ppt_export_report.json") or {}
    pptx_path = _pptx_path(root, report)
    artifact = _artifact(root, "pptx", _rel(root, pptx_path), "semantic.svg_to_ppt.pptx") if pptx_path else None
    issues = report.get("issues") or []
    return {
        "status": report.get("status") or "-",
        "issue_count": len(issues),
        "pptx_artifact": artifact,
        "pptx_bytes_label": artifact.get("bytes_label") if artifact else "-",
    }


def _load_ppt_optimization_summary(root: Path, artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    manifest = _read_json_if_exists(root / "ppt_optimization/direct-ppt-optimization-manifest.json") or {}
    raw_changes = manifest.get("changes") if isinstance(manifest, Mapping) else []
    changes = [str(item) for item in raw_changes] if isinstance(raw_changes, list) else []
    optimized = artifacts["ppt_optimized"]
    before_after = artifacts["ppt_before_after"]
    status = "ok" if optimized.get("exists") and before_after.get("exists") else "-"
    return {
        "status": status,
        "changes": changes,
        "change_count": len(changes),
        "optimized_pptx_bytes_label": optimized.get("bytes_label", "-"),
        "before_after_pptx_bytes_label": before_after.get("bytes_label", "-"),
    }


def _load_codex_rounds(root: Path) -> list[dict[str, Any]]:
    trace_path = root / "trace/svg_generation_model.jsonl"
    if not trace_path.exists():
        return []
    records = _read_jsonl(trace_path)
    labels = [
        ("Run 1", "模板 SVG 起稿：用灰盒生成参考图和模板参考图生成可编辑 SVG 骨架。"),
        ("Run 2", "视觉复核：用上一轮渲染 PNG 和目标参考图检查文字、字号、布局和样式。"),
        ("Run 3", "最终生成：结合资产 manifest 约束，输出可替换真实 raster asset 的 semantic.svg。"),
    ]
    rounds: list[dict[str, Any]] = []
    pending_request: Mapping[str, Any] | None = None
    for record in records:
        if "images" in record and "output_chars" not in record:
            pending_request = record
            continue
        if "output_chars" in record:
            index = len(rounds)
            label, purpose = labels[index] if index < len(labels) else (f"Run {index + 1}", "模型调用")
            images = []
            for image in (pending_request or {}).get("images", []):
                image_path = Path(str(image.get("image_path") or ""))
                rel = _rel_or_none(root, image_path)
                if rel:
                    images.append(_artifact(root, f"codex_round_{index}_{len(images)}", rel, Path(rel).name))
            rounds.append(
                {
                    "label": label,
                    "purpose": purpose,
                    "model_name": (pending_request or {}).get("model_name"),
                    "connection_id": (pending_request or {}).get("connection_id"),
                    "images": images,
                    "max_output_tokens": (pending_request or {}).get("max_output_tokens"),
                    "request_preview": _json_preview(_strip_large_trace_fields(pending_request or {}), limit=6000),
                    "output_chars": record.get("output_chars"),
                    "output_excerpt": str(record.get("output_excerpt") or "")[:8000],
                    "extraction": record.get("extraction"),
                }
            )
            pending_request = None
    return rounds


def _load_svg_attempts(root: Path) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    manifest = _read_json_if_exists(root / "svg/template_iterations/iteration_manifest.json") or {}
    phases = manifest.get("phases") if isinstance(manifest, Mapping) else None
    if isinstance(phases, list):
        for phase in phases:
            if not isinstance(phase, Mapping):
                continue
            phase_name = str(phase.get("phase") or "")
            reports = phase.get("attempt_reports")
            if not isinstance(reports, list):
                continue
            for report in reports:
                if not isinstance(report, Mapping):
                    continue
                attempt = _svg_attempt_from_report(root, report, fallback_phase=phase_name)
                if attempt is None:
                    continue
                key = str(attempt.get("attempt_dir") or attempt["semantic_svg"].get("rel") or attempt["label"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                attempts.append(attempt)

    attempts_dir = root / "svg/attempts"
    if attempts_dir.exists():
        for attempt_dir in sorted(path for path in attempts_dir.glob("*/*") if path.is_dir()):
            attempt = _svg_attempt_from_dir(root, attempt_dir)
            if attempt is None:
                continue
            key = str(attempt.get("attempt_dir") or attempt["semantic_svg"].get("rel") or attempt["label"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            attempts.append(attempt)
    return attempts


def _group_svg_runs(attempts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    by_phase: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        phase = str(attempt.get("phase") or "svg")
        run = by_phase.get(phase)
        if run is None:
            run = {
                "label": f"Run {len(runs) + 1}: {phase}",
                "phase": phase,
                "attempts": [],
                "attempt_count": 0,
                "failed_attempt_count": 0,
            }
            by_phase[phase] = run
            runs.append(run)
        run["attempts"].append(attempt)

    for run in runs:
        run_attempts = [attempt for attempt in run["attempts"] if isinstance(attempt, Mapping)]
        run["attempt_count"] = len(run_attempts)
        run["failed_attempt_count"] = sum(1 for attempt in run_attempts if str(attempt.get("status") or "").lower() == "failed")
        run["status"] = "failed" if run["failed_attempt_count"] == run["attempt_count"] and run_attempts else "ok"
    return runs


def _svg_attempt_from_report(root: Path, report: Mapping[str, Any], *, fallback_phase: str) -> dict[str, Any] | None:
    phase = str(report.get("phase") or fallback_phase or "svg")
    attempt_number = _attempt_number(report.get("attempt"))
    semantic_svg = _artifact_from_path_value(root, f"svg_attempt_{phase}_{attempt_number}_svg", report.get("semantic_svg"), "semantic.svg")
    rendered_png = _artifact_from_path_value(root, f"svg_attempt_{phase}_{attempt_number}_rendered", report.get("rendered_png"), "rendered.png")
    if semantic_svg is None or rendered_png is None:
        return None
    validation_report = _artifact_from_path_value(
        root,
        f"svg_attempt_{phase}_{attempt_number}_validation",
        report.get("validation_report"),
        "validation_report.json",
    )
    model_response = _artifact_from_path_value(
        root,
        f"svg_attempt_{phase}_{attempt_number}_model_response",
        report.get("model_response"),
        "model_response.txt",
    )
    attempt_dir = _attempt_dir_from_artifact(root, semantic_svg)
    return _svg_attempt_payload(
        root,
        phase=phase,
        attempt_number=attempt_number,
        status=str(report.get("status") or "-"),
        issues=list(report.get("issues") or []),
        attempt_dir=attempt_dir,
        semantic_svg=semantic_svg,
        rendered_png=rendered_png,
        validation_report=validation_report,
        model_response=model_response,
    )


def _svg_attempt_from_dir(root: Path, attempt_dir: Path) -> dict[str, Any] | None:
    context = _read_json_if_exists(attempt_dir / "request_context.json") or {}
    validation = _read_json_if_exists(attempt_dir / "validation_report.json") or {}
    phase = str(context.get("phase") or attempt_dir.parent.name) if isinstance(context, Mapping) else attempt_dir.parent.name
    attempt_number = _attempt_number(context.get("attempt") or attempt_dir.name) if isinstance(context, Mapping) else _attempt_number(attempt_dir.name)
    semantic_svg = _artifact(root, f"svg_attempt_{phase}_{attempt_number}_svg", _rel(root, attempt_dir / "semantic.svg"), "semantic.svg")
    rendered_png = _artifact(root, f"svg_attempt_{phase}_{attempt_number}_rendered", _rel(root, attempt_dir / "rendered.png"), "rendered.png")
    if not semantic_svg.get("exists") or not rendered_png.get("exists"):
        return None
    status = str(validation.get("status") or "-") if isinstance(validation, Mapping) else "-"
    issues = list(validation.get("issues") or []) if isinstance(validation, Mapping) else []
    return _svg_attempt_payload(
        root,
        phase=phase,
        attempt_number=attempt_number,
        status=status,
        issues=issues,
        attempt_dir=_rel(root, attempt_dir),
        semantic_svg=semantic_svg,
        rendered_png=rendered_png,
        validation_report=_artifact(root, f"svg_attempt_{phase}_{attempt_number}_validation", _rel(root, attempt_dir / "validation_report.json"), "validation_report.json"),
        model_response=_artifact(root, f"svg_attempt_{phase}_{attempt_number}_model_response", _rel(root, attempt_dir / "model_response.txt"), "model_response.txt"),
    )


def _svg_attempt_payload(
    root: Path,
    *,
    phase: str,
    attempt_number: int,
    status: str,
    issues: list[Any],
    attempt_dir: str | None,
    semantic_svg: dict[str, Any],
    rendered_png: dict[str, Any],
    validation_report: dict[str, Any] | None,
    model_response: dict[str, Any] | None,
) -> dict[str, Any]:
    context = _svg_attempt_context(root, attempt_dir)
    prompt = _svg_attempt_prompt_artifact(root, phase, attempt_number, attempt_dir, context)
    request_context = _artifact_from_attempt_dir(
        root,
        attempt_dir,
        "request_context.json",
        f"svg_attempt_{phase}_{attempt_number}_request_context",
    )
    session_log_artifact = _artifact_from_attempt_dir(
        root,
        attempt_dir,
        "codex_session_log",
        f"svg_attempt_{phase}_{attempt_number}_session_log",
    )
    session_log_manifest = _artifact_from_attempt_dir(
        root,
        attempt_dir,
        "codex_session_log/manifest.json",
        f"svg_attempt_{phase}_{attempt_number}_session_log_manifest",
    )
    output_artifacts = [
        artifact
        for artifact in (
            semantic_svg,
            rendered_png,
            validation_report,
            model_response,
            session_log_artifact,
            session_log_manifest,
        )
        if isinstance(artifact, Mapping)
    ]
    return {
        "label": f"{phase} #{attempt_number}",
        "phase": phase,
        "attempt": attempt_number,
        "status": status,
        "issues": issues,
        "attempt_dir": attempt_dir,
        "semantic_svg": semantic_svg,
        "rendered_png": rendered_png,
        "validation_report": validation_report,
        "model_response": model_response,
        "session_log_artifact": session_log_artifact,
        "session_log_manifest": session_log_manifest,
        "prompt": prompt,
        "instruction": prompt,
        "instruction_preview": _text_from_artifact(root, prompt),
        "request_context": request_context,
        "input_artifacts": _svg_attempt_input_artifacts(root, phase, attempt_number, context),
        "output_artifacts": output_artifacts,
    }


def _svg_attempt_context(root: Path, attempt_dir: str | None) -> Mapping[str, Any]:
    if not attempt_dir:
        return {}
    payload = _read_json_if_exists(root / attempt_dir / "request_context.json")
    return payload if isinstance(payload, Mapping) else {}


def _svg_attempt_prompt_artifact(
    root: Path,
    phase: str,
    attempt_number: int,
    attempt_dir: str | None,
    context: Mapping[str, Any],
) -> dict[str, Any] | None:
    prompt = _artifact_from_path_value(
        root,
        f"svg_attempt_{phase}_{attempt_number}_prompt",
        context.get("prompt_path"),
        "Instruction prompt.txt",
    )
    if prompt is not None and prompt.get("exists"):
        return prompt
    return _artifact_from_attempt_dir(root, attempt_dir, "prompt.txt", f"svg_attempt_{phase}_{attempt_number}_prompt")


def _svg_attempt_input_artifacts(root: Path, phase: str, attempt_number: int, context: Mapping[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for field, label in SVG_ATTEMPT_INPUT_FIELDS:
        artifact = _artifact_from_path_value(
            root,
            f"svg_attempt_{phase}_{attempt_number}_input_{field}",
            context.get(field),
            label,
        )
        if artifact is not None:
            artifacts.append({"role": field, "artifact": artifact})
    return artifacts


def _text_from_artifact(root: Path, artifact: Mapping[str, Any] | None) -> str:
    if not isinstance(artifact, Mapping) or not artifact.get("exists"):
        return ""
    path = root / str(artifact["rel"])
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _attempt_number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _artifact_from_path_value(root: Path, key: str, value: Any, label: str) -> dict[str, Any] | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    rel = _rel_or_none(root, path.resolve(strict=False)) if path.is_absolute() else str(path)
    if rel is None:
        return None
    return _artifact(root, key, rel, label)


def _attempt_dir_from_artifact(root: Path, artifact: Mapping[str, Any]) -> str | None:
    rel = artifact.get("rel")
    if not rel:
        return None
    return _rel(root, (root / str(rel)).parent)


def _artifact_from_attempt_dir(root: Path, attempt_dir: str | None, filename: str, key: str) -> dict[str, Any] | None:
    if not attempt_dir:
        return None
    path = root / attempt_dir / filename
    if not path.exists():
        return None
    return _artifact(root, key, _rel(root, path), filename)


def _artifact(root: Path, key: str, rel: str, label: str) -> dict[str, Any]:
    target = (root / rel).resolve(strict=False)
    exists = target.exists()
    artifact: dict[str, Any] = {
        "key": key,
        "label": label,
        "rel": rel,
        "exists": exists,
        "kind": _file_kind(target),
    }
    if exists and target.is_file():
        size = target.stat().st_size
        artifact["bytes"] = size
        artifact["bytes_label"] = _format_bytes(size)
        if target.suffix.lower() in IMAGE_EXTENSIONS:
            artifact["image_size"] = _image_size(target)
        if target.suffix.lower() in JSON_EXTENSIONS:
            artifact["preview"] = _json_or_text_preview(target)
    elif exists and target.is_dir():
        artifact["bytes_label"] = "directory"
    else:
        artifact["bytes_label"] = "missing"
    return artifact


def _compact_stage_io(payload: Any) -> Any:
    if not isinstance(payload, Mapping):
        return payload
    stages = payload.get("stages")
    if not isinstance(stages, Mapping):
        return _compact_json(payload)
    compact_stages: dict[str, Any] = {}
    for name, spec in stages.items():
        compact_stages[str(name)] = {
            "inputs": _keys_or_empty(spec.get("inputs") if isinstance(spec, Mapping) else None),
            "outputs": _keys_or_empty(spec.get("outputs") if isinstance(spec, Mapping) else None),
            "inference_slots": list(spec.get("inference_slots") or []) if isinstance(spec, Mapping) else [],
        }
    return {
        "schema": payload.get("schema"),
        "execution_mode": payload.get("execution_mode"),
        "latest_stage": payload.get("latest_stage"),
        "stage_order": payload.get("stage_order"),
        "stages": compact_stages,
    }


def _append_ppt_optimization_stage_io(payload: Any, artifacts: Mapping[str, Mapping[str, Any]]) -> Any:
    if not isinstance(payload, Mapping):
        return payload
    if not artifacts["ppt_optimized"].get("exists") and not artifacts["ppt_before_after"].get("exists"):
        return payload
    enriched = dict(payload)
    stages = dict(enriched.get("stages") or {}) if isinstance(enriched.get("stages"), Mapping) else {}
    stages.setdefault(
        "ppt_optimized",
        {
            "inputs": ["original_image", "svg_to_pptx"],
            "outputs": [
                "ppt_optimized",
                "ppt_before_after",
                "ppt_optimization_manifest",
                "ppt_after_preview",
            ],
            "inference_slots": ["subagent_review", "artifact_tool_pptx_export"],
        },
    )
    enriched["stages"] = stages
    stage_order = enriched.get("stage_order")
    if isinstance(stage_order, list) and "ppt_optimized" not in stage_order:
        enriched["stage_order"] = [*stage_order, "ppt_optimized"]
    return enriched


def _compact_json(payload: Any) -> Any:
    if not isinstance(payload, Mapping):
        return payload
    compact = dict(payload)
    artifacts = compact.get("artifacts")
    if isinstance(artifacts, Mapping):
        compact["artifact_count"] = len(artifacts)
        compact["artifacts"] = sorted(artifacts.keys())
    return compact


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return _read_json(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def _json_or_text_preview(path: Path, limit: int = 5000) -> str:
    if path.suffix.lower() == ".jsonl":
        text = "\n".join(json.dumps(record, ensure_ascii=False) for record in _read_jsonl(path)[:6])
    else:
        payload = _read_json(path)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    return text[:limit] + ("\n..." if len(text) > limit else "")


def _json_preview(payload: Any, limit: int = 5000) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return text[:limit] + ("\n..." if len(text) > limit else "")


def _strip_large_trace_fields(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    stripped = dict(payload)
    messages = stripped.get("messages")
    if isinstance(messages, list):
        stripped["messages"] = _compact_messages(messages)
    return stripped


def _compact_messages(messages: Sequence[Any]) -> list[Any]:
    compact = []
    for message in messages:
        if not isinstance(message, Mapping):
            compact.append(message)
            continue
        item = dict(message)
        content = item.get("content")
        if isinstance(content, str) and len(content) > 3000:
            item["content"] = content[:3000] + "\n..."
        compact.append(item)
    return compact


def _keys_or_empty(value: Any) -> list[str]:
    return sorted(str(key) for key in value.keys()) if isinstance(value, Mapping) else []


def _stage_io_names(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return sorted(str(key) for key in value.keys())
    if isinstance(value, list):
        return sorted(str(item) for item in value)
    return []


def _pptx_path(root: Path, report: Mapping[str, Any]) -> Path | None:
    report_path = report.get("pptx_path")
    if report_path:
        path = Path(str(report_path)).expanduser().resolve(strict=False)
        if path.exists():
            return path
    candidates = sorted((root / "svg_to_ppt").glob("*.svg_to_ppt.pptx"))
    return candidates[0] if candidates else None


def _image_size(path: Path) -> str:
    if path.suffix.lower() == ".svg":
        return ""
    with Image.open(path) as image:
        return f"{image.width} x {image.height}"


def _file_kind(path: Path) -> str:
    if path.is_dir():
        return "directory"
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in JSON_EXTENSIONS:
        return "json"
    if suffix == ".pptx":
        return "pptx"
    if suffix == ".svg":
        return "svg"
    return suffix.lstrip(".") or "file"


def _infer_run_dir(case_dir: Path) -> Path:
    parts = case_dir.parts
    if len(parts) >= 3 and parts[-2] == "outputs":
        return case_dir.parents[1]
    return case_dir


def _rel(root: Path, path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False).relative_to(root))


def _rel_or_none(root: Path, path: str | Path) -> str | None:
    try:
        return _rel(root, path)
    except ValueError:
        return None


def _required_query(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values:
        raise KeyError(f"Missing query parameter: {key}")
    return values[0]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _asset_resolver(data: Mapping[str, Any], *, mode: str) -> Callable[[str], str]:
    case_dir = str(data["case_dir"])
    if mode == "server":
        return lambda rel: "/file?" + urllib.parse.urlencode({"case": case_dir, "rel": rel})
    if mode == "static":
        return lambda rel: "../" + _quote_rel(rel)
    raise ValueError(f"unknown mode: {mode}")


def _quote_rel(rel: str) -> str:
    return "/".join(urllib.parse.quote(part) for part in rel.split("/"))


def _section(anchor: str, num: str, title: str, subtitle: str, badge: str, body: str) -> str:
    return f"""
    <section id="{_esc(anchor)}" class="stage panel">
      <div class="stage-head">
        <div class="stage-title"><span class="stage-num">{_esc(num)}</span><div><h2>{_esc(title)}</h2><p class="muted">{_esc(subtitle)}</p></div></div>
        <span class="badge">{_esc(badge)}</span>
      </div>
      {body}
    </section>
    """


def _stat_grid(items: Sequence[tuple[str, Any, str]]) -> str:
    cells = [
        f"<div class=\"stat\"><span>{_esc(label)}</span><strong>{_esc(value)}</strong><em>{_esc(note)}</em></div>"
        for label, value, note in items
    ]
    return '<div class="stats">' + "".join(cells) + "</div>"


def _io_block(
    *,
    inputs: Sequence[Mapping[str, Any] | tuple[str, str]],
    outputs: Sequence[Mapping[str, Any]],
    resolver: Callable[[str], str],
    inference: Sequence[str] = (),
) -> str:
    def render_item(item: Mapping[str, Any] | tuple[str, str]) -> str:
        if isinstance(item, Mapping):
            return _file_link(item, item.get("label", item.get("rel", "")), resolver)
        return f"<span class=\"chip\"><b>{_esc(item[0])}</b><small>{_esc(item[1])}</small></span>"

    inference_html = "".join(f"<span class=\"chip accent\"><b>{_esc(slot)}</b><small>inference</small></span>" for slot in inference)
    return f"""
    <div class="io-grid">
      <div><h3>输入</h3><div class="chips">{''.join(render_item(item) for item in inputs)}</div></div>
      <div><h3>输出</h3><div class="chips">{''.join(render_item(item) for item in outputs)}</div></div>
      <div><h3>推理槽</h3><div class="chips">{inference_html or '<span class="muted">无</span>'}</div></div>
    </div>
    """


def _gallery(figures: Sequence[str], class_name: str = "gallery") -> str:
    return f'<div class="{_esc(class_name)}">' + "".join(figures) + "</div>"


def _render_svg_runs(runs: Sequence[Any], resolver: Callable[[str], str]) -> str:
    if not runs:
        return """
        <div class="asset-empty">
          <b>SVG/Codex 三个 run</b>
          <span>没有找到 template_iterations 或 svg/attempts 下的 SVG/Codex 生成记录。</span>
        </div>
        """
    run_blocks = []
    for raw_run in runs:
        if not isinstance(raw_run, Mapping):
            continue
        attempts = raw_run.get("attempts") if isinstance(raw_run.get("attempts"), list) else []
        attempt_cards = [_render_svg_attempt_card(attempt, resolver) for attempt in attempts if isinstance(attempt, Mapping)]
        failed_count = int(raw_run.get("failed_attempt_count") or 0)
        attempt_count = int(raw_run.get("attempt_count") or len(attempt_cards))
        retry_text = f"{attempt_count} 次 attempt"
        if failed_count:
            retry_text += f"，其中 {failed_count} 次失败"
        run_blocks.append(
            f"""
            <section class="svg-run-block">
              <div class="svg-run-head">
                <div>
                  <h4>{_esc(raw_run.get('label', 'Run'))}</h4>
                  <p class="muted">phase={_esc(raw_run.get('phase', '-'))} · {retry_text}</p>
                </div>
                <span>{_esc(raw_run.get('status', '-'))}</span>
              </div>
              <div class="svg-run-attempts">{''.join(attempt_cards)}</div>
            </section>
            """
        )
    return f"""
    <div class="asset-section-head">
      <h3>SVG/Codex 三个 run</h3>
      <p class="muted">按真实生成阶段拆开：每个 run 下面列出全部输入、Instruction、输出 SVG 和本地 rendered 结果，失败重试也保留。</p>
    </div>
    <div class="svg-run-stack">{''.join(run_blocks)}</div>
    """


def _render_svg_attempt_card(raw_attempt: Mapping[str, Any], resolver: Callable[[str], str]) -> str:
    semantic_svg = raw_attempt.get("semantic_svg") if isinstance(raw_attempt.get("semantic_svg"), Mapping) else None
    rendered_png = raw_attempt.get("rendered_png") if isinstance(raw_attempt.get("rendered_png"), Mapping) else None
    validation_report = raw_attempt.get("validation_report") if isinstance(raw_attempt.get("validation_report"), Mapping) else None
    model_response = raw_attempt.get("model_response") if isinstance(raw_attempt.get("model_response"), Mapping) else None
    session_log_artifact = (
        raw_attempt.get("session_log_artifact")
        if isinstance(raw_attempt.get("session_log_artifact"), Mapping)
        else None
    )
    session_log_manifest = (
        raw_attempt.get("session_log_manifest")
        if isinstance(raw_attempt.get("session_log_manifest"), Mapping)
        else None
    )
    prompt = raw_attempt.get("prompt") if isinstance(raw_attempt.get("prompt"), Mapping) else None
    request_context = raw_attempt.get("request_context") if isinstance(raw_attempt.get("request_context"), Mapping) else None
    input_items = raw_attempt.get("input_artifacts") if isinstance(raw_attempt.get("input_artifacts"), list) else []

    input_figures = []
    input_links = []
    for item in input_items:
        if not isinstance(item, Mapping) or not isinstance(item.get("artifact"), Mapping):
            continue
        role = str(item.get("role") or item["artifact"].get("label") or "input")
        artifact = item["artifact"]
        input_figures.append(_figure(artifact, role, f"输入：{role}", resolver))
        input_links.append(artifact)
    output_figures = []
    if semantic_svg is not None:
        output_figures.append(_figure(semantic_svg, "semantic.svg", "该 attempt 输出的 SVG", resolver))
    if rendered_png is not None:
        output_figures.append(_figure(rendered_png, "rendered.png", "该 attempt 的本地渲染结果", resolver))

    file_inputs = [artifact for artifact in (prompt, request_context, *input_links) if isinstance(artifact, Mapping)]
    file_outputs = [
        artifact
        for artifact in (
            semantic_svg,
            rendered_png,
            validation_report,
            model_response,
            session_log_artifact,
            session_log_manifest,
        )
        if isinstance(artifact, Mapping)
    ]

    issues = raw_attempt.get("issues")
    issue_codes = [
        str(issue.get("code") or issue.get("message") or issue)
        for issue in issues
        if isinstance(issue, Mapping)
    ] if isinstance(issues, list) else []
    if isinstance(issues, list):
        issue_codes.extend(str(issue) for issue in issues if not isinstance(issue, Mapping))
    issue_text = ", ".join(issue_codes) if issue_codes else "无"

    return f"""
    <article class="round-card svg-attempt-card">
      <div class="round-head">
        <span>{_esc(raw_attempt.get('label', 'attempt'))}</span>
        <b>{_esc(raw_attempt.get('status', '-'))}</b>
      </div>
      <p class="muted">phase={_esc(raw_attempt.get('phase', '-'))} · attempt={_esc(raw_attempt.get('attempt', '-'))} · issues={_esc(issue_text)}</p>
      <div class="mini-label">输入</div>
      {_gallery(input_figures, class_name="gallery two svg-run-large-gallery") if input_figures else '<p class="muted">没有记录图片或模板输入。</p>'}
      <div class="mini-label">输入文件</div>
      {_link_strip(file_inputs, resolver) if file_inputs else '<p class="muted">没有附加输入文件。</p>'}
      {_render_instruction_block(prompt, str(raw_attempt.get('instruction_preview') or ''), resolver)}
      <div class="mini-label">输出</div>
      {_gallery(output_figures, class_name="gallery two svg-run-large-gallery") if output_figures else '<p class="muted">没有记录 SVG/rendered 输出。</p>'}
      <div class="mini-label">输出文件</div>
      {_link_strip(file_outputs, resolver) if file_outputs else '<p class="muted">没有附加输出文件。</p>'}
    </article>
    """


def _render_instruction_block(prompt: Mapping[str, Any] | None, instruction_preview: str, resolver: Callable[[str], str]) -> str:
    if not isinstance(prompt, Mapping):
        return """
        <details class="instruction-box" open>
          <summary>Instruction</summary>
          <p class="muted">没有找到 prompt.txt。</p>
        </details>
        """
    prompt_link = _file_link(prompt, "Instruction prompt.txt", resolver)
    return f"""
    <details class="instruction-box" open>
      <summary>Instruction</summary>
      <div class="instruction-link">{prompt_link}</div>
      <pre>{_esc(instruction_preview)}</pre>
    </details>
    """


def _figure(artifact: Mapping[str, Any], title: str, caption: str, resolver: Callable[[str], str]) -> str:
    if not artifact.get("exists"):
        return f"<figure class=\"shot missing\"><div>missing</div><figcaption><b>{_esc(title)}</b><span>{_esc(caption)}</span></figcaption></figure>"
    href = resolver(str(artifact["rel"]))
    size = artifact.get("image_size") or artifact.get("bytes_label") or ""
    return f"""
    <figure class="shot">
      <a href="{_esc(href)}" target="_blank"><img loading="lazy" src="{_esc(href)}" alt="{_esc(title)}"></a>
      <figcaption><b>{_esc(title)}</b><span>{_esc(caption)}{f' · {size}' if size else ''}</span></figcaption>
    </figure>
    """


def _file_link(artifact: Mapping[str, Any], label: Any, resolver: Callable[[str], str]) -> str:
    if not artifact.get("exists"):
        return f"<span class=\"chip missing\"><b>{_esc(label)}</b><small>missing</small></span>"
    href = resolver(str(artifact["rel"]))
    return f"<a class=\"chip\" href=\"{_esc(href)}\" target=\"_blank\"><b>{_esc(label)}</b><small>{_esc(artifact.get('bytes_label', ''))}</small></a>"


def _link_strip(artifacts: Sequence[Mapping[str, Any]], resolver: Callable[[str], str]) -> str:
    return '<div class="links">' + "".join(_file_link(artifact, artifact.get("label", artifact.get("rel", "")), resolver) for artifact in artifacts) + "</div>"


def _render_asset_gallery(assets: Mapping[str, Any], resolver: Callable[[str], str]) -> str:
    items = assets.get("asset_items") or []
    if not items:
        return """
        <div class="asset-empty">
          <b>全部 assets</b>
          <span>asset_manifest 中没有 raster/hybrid assets；当前图可能主要由 native SVG 元素表达。</span>
        </div>
        """
    cards = [_asset_card(item, resolver) for item in items if isinstance(item, Mapping)]
    crop_files = assets.get("crop_files") or []
    crop_links = _link_strip(crop_files, resolver) if crop_files else "<p class=\"muted\">没有 crops/ PNG 文件。</p>"
    return f"""
    <div class="asset-section-head">
      <h3>全部 assets</h3>
      <p class="muted">来自 asset_manifest.json；卡片展示 active variant，下面同时给出 source crop / no-bg variant 链接。</p>
    </div>
    <div class="asset-grid">{''.join(cards)}</div>
    <details class="asset-crops"><summary>全部 crop 文件（{_esc(len(crop_files))}）</summary>{crop_links}</details>
    """


def _asset_card(item: Mapping[str, Any], resolver: Callable[[str], str]) -> str:
    active = item.get("active_artifact") if isinstance(item.get("active_artifact"), Mapping) else None
    source = item.get("source_artifact") if isinstance(item.get("source_artifact"), Mapping) else None
    nobg = item.get("nobg_artifact") if isinstance(item.get("nobg_artifact"), Mapping) else None
    preview_artifact = active or source or nobg
    if preview_artifact and preview_artifact.get("exists"):
        href = resolver(str(preview_artifact["rel"]))
        preview = f'<a href="{_esc(href)}" target="_blank"><img loading="lazy" src="{_esc(href)}" alt="{_esc(item.get("asset_id", "asset"))}"></a>'
    else:
        preview = '<div class="asset-thumb-missing">missing</div>'
    links = [artifact for artifact in (source, active, nobg) if isinstance(artifact, Mapping)]
    bbox = item.get("bbox") if isinstance(item.get("bbox"), (list, tuple)) else []
    bbox_label = ", ".join(str(value) for value in bbox) if bbox else "-"
    reason_codes = item.get("reason_codes") if isinstance(item.get("reason_codes"), list) else []
    reason_html = "".join(f"<span>{_esc(reason)}</span>" for reason in reason_codes[:5])
    component_kinds = item.get("component_kinds") if isinstance(item.get("component_kinds"), Mapping) else {}
    component_html = ", ".join(f"{key}:{value}" for key, value in component_kinds.items()) or "-"
    size_label = "-"
    if item.get("width") and item.get("height"):
        size_label = f"{item['width']} x {item['height']}"
    parent = f" · parent {item['parent_asset_id']}" if item.get("parent_asset_id") else ""
    rmbg = _format_ms(item.get("rmbg_elapsed_ms")) if item.get("rmbg_elapsed_ms") is not None else "-"
    return f"""
    <article class="asset-card">
      <div class="asset-thumb">{preview}</div>
      <div class="asset-meta">
        <div class="asset-title">
          <b>{_esc(item.get("asset_id", "-"))}</b>
          <span>{_esc(item.get("item_type", "asset"))}{_esc(parent)}</span>
        </div>
        <dl>
          <div><dt>box</dt><dd>{_esc(item.get("box_id") or "-")}</dd></div>
          <div><dt>policy</dt><dd>{_esc(item.get("render_policy", "-"))}</dd></div>
          <div><dt>variant</dt><dd>{_esc(item.get("active_variant", "-"))}</dd></div>
          <div><dt>size</dt><dd>{_esc(size_label)}</dd></div>
          <div><dt>bbox</dt><dd>{_esc(bbox_label)}</dd></div>
          <div><dt>rmbg</dt><dd>{_esc(rmbg)}</dd></div>
          <div><dt>components</dt><dd>{_esc(item.get("component_count", 0))} · {_esc(component_html)}</dd></div>
        </dl>
        <div class="asset-reasons">{reason_html or '<span>no reason code</span>'}</div>
        <div class="links asset-links">{''.join(_file_link(artifact, artifact["label"], resolver) for artifact in links)}</div>
        <details><summary>metadata</summary><pre>{_esc(item.get("metadata_preview", ""))}</pre></details>
      </div>
    </article>
    """


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        return '<p class="muted">没有记录。</p>'
    head = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class=\"table-wrap\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _details_json(title: str, preview: str) -> str:
    if not preview:
        return ""
    return f"<details><summary>{_esc(title)}</summary><pre>{_esc(preview)}</pre></details>"


def _format_ms(value: Any) -> str:
    if value is None:
        return "-"
    seconds = float(value) / 1000
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.2f} s"


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


APP_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #172026;
  --muted: #64707d;
  --line: #d9dee5;
  --blue: #2662a6;
  --green: #22735f;
  --amber: #9b6a18;
  --red: #a33b3b;
  --shadow: 0 12px 34px rgba(24, 35, 49, 0.09);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
a { color: inherit; }
.hero { background: #ffffff; border-bottom: 1px solid var(--line); padding: 28px clamp(18px, 4vw, 56px); }
.hero > div { max-width: 1180px; margin: 0 auto; }
.eyebrow { margin: 0 0 8px; color: var(--blue); font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; font-size: 12px; }
h1 { margin: 0; font-size: clamp(30px, 5vw, 54px); line-height: 1.05; letter-spacing: 0; }
.hero-copy { margin: 14px 0 0; max-width: 820px; color: var(--muted); font-size: 17px; line-height: 1.65; }
main { max-width: 1180px; margin: 0 auto; padding: 22px clamp(14px, 3vw, 28px) 80px; }
.panel { background: var(--panel); border: 1px solid var(--line); box-shadow: var(--shadow); border-radius: 8px; }
.loader { padding: 18px; margin: 0 0 18px; }
.loader h2 { margin: 0; }
.loader-row { display: grid; grid-template-columns: 1fr auto auto auto; gap: 10px; margin-top: 14px; }
input { width: 100%; border: 1px solid var(--line); border-radius: 7px; padding: 11px 12px; font: inherit; color: var(--text); background: #fff; }
button { border: 1px solid #b8c2cf; background: #edf3f8; color: #142638; border-radius: 7px; padding: 10px 14px; font: inherit; font-weight: 750; cursor: pointer; }
button:hover { background: #e1edf7; }
.status-line { min-height: 22px; color: var(--muted); margin: 12px 0 0; }
.toc { position: sticky; top: 0; z-index: 10; display: flex; gap: 8px; overflow-x: auto; padding: 10px 0 14px; background: rgba(246, 247, 249, 0.94); backdrop-filter: blur(10px); }
.toc a { flex: 0 0 auto; text-decoration: none; border: 1px solid var(--line); background: #fff; border-radius: 7px; padding: 8px 10px; color: #243547; font-weight: 700; font-size: 14px; }
.stage { padding: 18px; margin: 18px 0; scroll-margin-top: 76px; }
.stage-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; margin-bottom: 14px; }
.stage-title { display: flex; gap: 12px; align-items: flex-start; }
.stage-num { width: 42px; min-width: 42px; height: 36px; border-radius: 7px; background: #e7f0f8; color: var(--blue); display: inline-flex; align-items: center; justify-content: center; font-weight: 900; }
h2, h3 { margin: 0; letter-spacing: 0; }
h2 { font-size: 22px; line-height: 1.25; }
h3 { font-size: 14px; color: #2b3b4c; margin-bottom: 8px; }
.muted { color: var(--muted); }
.stage-head p, .loader p { margin: 5px 0 0; line-height: 1.55; }
.badge { border: 1px solid #c6d2df; color: #27435b; background: #f4f8fb; border-radius: 999px; padding: 6px 9px; font-weight: 800; font-size: 12px; white-space: nowrap; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }
.stat { border: 1px solid var(--line); background: #fbfcfd; border-radius: 7px; padding: 12px; min-height: 88px; }
.stat span { display: block; color: var(--muted); font-size: 12px; font-weight: 750; text-transform: uppercase; }
.stat strong { display: block; margin-top: 6px; font-size: 24px; line-height: 1.1; overflow-wrap: anywhere; }
.stat em { display: block; margin-top: 7px; color: var(--muted); font-style: normal; font-size: 12px; }
.io-grid { display: grid; grid-template-columns: 1fr 1.4fr 0.9fr; gap: 12px; margin: 12px 0 16px; }
.chips, .links { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.chip { text-decoration: none; display: inline-flex; flex-direction: column; gap: 2px; border: 1px solid #cbd5df; background: #fff; border-radius: 7px; padding: 7px 9px; max-width: 280px; }
.chip b { font-size: 13px; overflow-wrap: anywhere; }
.chip small { color: var(--muted); font-size: 11px; }
.chip.accent { border-color: #b8d4c9; background: #f2faf6; color: var(--green); }
.chip.missing { color: var(--red); background: #fff7f7; border-color: #e4bdbd; }
.gallery { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 14px 0; }
.gallery.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.gallery.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.gallery.six { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.gallery.svg-run-large-gallery { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.svg-run-large-gallery .shot img { aspect-ratio: 16 / 11; min-height: 320px; background: #f4f6f8; }
.shot { margin: 0; border: 1px solid var(--line); border-radius: 8px; background: #fff; overflow: hidden; }
.shot a { display: block; background: #f1f3f5; }
.shot img { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: contain; }
.shot figcaption { border-top: 1px solid var(--line); padding: 9px 10px; display: flex; flex-direction: column; gap: 3px; }
.shot figcaption b { font-size: 13px; overflow-wrap: anywhere; }
.shot figcaption span { color: var(--muted); font-size: 12px; line-height: 1.4; }
.shot.missing > div { min-height: 180px; display: flex; align-items: center; justify-content: center; color: var(--red); }
.asset-section-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin: 18px 0 10px; }
.asset-section-head p { margin: 0; line-height: 1.45; }
.asset-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 12px 0; }
.asset-card { border: 1px solid var(--line); border-radius: 8px; background: #fff; display: grid; grid-template-columns: minmax(140px, 0.75fr) minmax(0, 1.25fr); min-width: 0; overflow: hidden; }
.asset-thumb { background: #f2f4f6; min-height: 176px; display: flex; align-items: center; justify-content: center; border-right: 1px solid var(--line); }
.asset-thumb a { display: flex; width: 100%; height: 100%; align-items: center; justify-content: center; padding: 10px; }
.asset-thumb img { display: block; width: 100%; height: 170px; object-fit: contain; }
.asset-thumb-missing { color: var(--red); font-weight: 800; }
.asset-meta { padding: 12px; min-width: 0; }
.asset-title { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; margin-bottom: 10px; }
.asset-title b { font-size: 16px; overflow-wrap: anywhere; }
.asset-title span { color: var(--muted); font-size: 12px; text-align: right; overflow-wrap: anywhere; }
.asset-meta dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px 10px; margin: 0; }
.asset-meta dl div { min-width: 0; }
.asset-meta dt { color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.asset-meta dd { margin: 2px 0 0; font-size: 12px; overflow-wrap: anywhere; }
.asset-reasons { display: flex; flex-wrap: wrap; gap: 5px; margin: 10px 0; }
.asset-reasons span { border: 1px solid #d4dde6; background: #f7f9fb; color: #3b4c5f; border-radius: 999px; padding: 3px 7px; font-size: 11px; font-weight: 700; }
.asset-links { margin-top: 8px; }
.asset-links .chip { max-width: 220px; padding: 6px 8px; }
.asset-card details { margin: 10px 0 0; }
.asset-card summary { padding: 8px 10px; font-size: 12px; }
.asset-card pre { max-height: 260px; }
.asset-empty { border: 1px dashed #c9d4df; border-radius: 8px; background: #fbfcfd; padding: 14px; display: flex; flex-direction: column; gap: 4px; margin: 14px 0; }
.asset-empty span { color: var(--muted); }
.asset-crops .links { padding: 0 12px 12px; }
.svg-run-stack { display: flex; flex-direction: column; gap: 18px; margin: 14px 0; }
.svg-run-block { border: 1px solid var(--line); border-radius: 8px; background: #fff; padding: 14px; }
.svg-run-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.svg-run-head h4 { margin: 0 0 5px; font-size: 19px; color: var(--blue); }
.svg-run-head p { margin: 0; }
.svg-run-head > span { border: 1px solid #b8d4c9; background: #f2faf6; color: var(--green); border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 850; }
.svg-run-attempts { display: flex; flex-direction: column; gap: 14px; margin-top: 14px; }
.svg-attempt-card { background: #fbfcfd; }
.instruction-link { padding: 0 12px 12px; }
.instruction-box pre { max-height: 560px; }
.table-wrap { overflow-x: auto; margin: 12px 0; border: 1px solid var(--line); border-radius: 8px; }
table { width: 100%; border-collapse: collapse; min-width: 720px; background: #fff; }
th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 9px 10px; vertical-align: top; font-size: 13px; }
th { background: #f1f4f7; color: #344558; font-size: 12px; text-transform: uppercase; }
td small { display: block; color: var(--muted); margin-top: 3px; }
details { border: 1px solid var(--line); border-radius: 8px; background: #fbfcfd; margin: 10px 0; }
summary { cursor: pointer; padding: 10px 12px; font-weight: 800; }
pre { margin: 0; border-top: 1px solid var(--line); padding: 12px; overflow: auto; max-height: 460px; font-size: 12px; line-height: 1.45; white-space: pre-wrap; color: #1a2937; }
.round-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 14px 0; }
.round-card { border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfd; min-width: 0; }
.round-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 6px; }
.round-head span { font-weight: 900; color: var(--blue); }
.round-head b { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; text-align: right; }
.mini-label { margin: 12px 0 6px; color: var(--amber); font-weight: 850; font-size: 12px; text-transform: uppercase; }
.note { border-left: 4px solid var(--blue); background: #f4f8fb; padding: 10px 12px; color: #27435b; line-height: 1.5; }
code { background: #eef1f4; border: 1px solid var(--line); border-radius: 4px; padding: 1px 4px; }
@media (max-width: 900px) {
  .loader-row, .io-grid, .stats, .gallery, .gallery.two, .gallery.three, .gallery.six, .gallery.svg-run-large-gallery, .round-grid, .asset-grid, .asset-card { grid-template-columns: 1fr; }
  .stage-head { flex-direction: column; }
  .asset-section-head { flex-direction: column; align-items: flex-start; }
  .asset-thumb { border-right: 0; border-bottom: 1px solid var(--line); }
  .svg-run-head { flex-direction: column; }
  .svg-run-large-gallery .shot img { min-height: 240px; }
  .stage-num { width: 38px; min-width: 38px; height: 34px; }
}
"""


APP_JS = """
(function () {
  const input = document.getElementById("case-path");
  const loadButton = document.getElementById("load-case");
  const latestButton = document.getElementById("load-latest");
  const writeButton = document.getElementById("write-static");
  const status = document.getElementById("app-status");
  const reportRoot = document.getElementById("report-root");

  function setStatus(message) {
    if (status) status.textContent = message || "";
  }

  async function loadCase(path) {
    if (!path) {
      setStatus("需要一个 outputs/case_* 目录。");
      return;
    }
    try {
      setStatus("正在读取 output 目录...");
      const response = await fetch("/api/render?path=" + encodeURIComponent(path));
      if (!response.ok) {
        setStatus(await response.text());
        return;
      }
      const payload = await response.json();
      reportRoot.innerHTML = payload.html;
      history.replaceState(null, "", "/?path=" + encodeURIComponent(path));
      setStatus("已加载: " + path);
    } catch (error) {
      setStatus(String(error));
    }
  }

  if (loadButton) {
    loadButton.addEventListener("click", () => loadCase(input.value.trim()));
  }
  if (latestButton) {
    latestButton.addEventListener("click", async () => {
      try {
        setStatus("正在查找最新 case...");
        const response = await fetch("/api/latest");
        const payload = await response.json();
        if (!payload.case_dir) {
          setStatus("没有找到 runs/**/outputs/case_*。");
          return;
        }
        input.value = payload.case_dir;
        await loadCase(payload.case_dir);
      } catch (error) {
        setStatus(String(error));
      }
    });
  }
  if (writeButton) {
    writeButton.addEventListener("click", async () => {
      const path = input.value.trim();
      if (!path) {
        setStatus("需要一个 outputs/case_* 目录。");
        return;
      }
      try {
        setStatus("正在写入静态 HTML...");
        const response = await fetch("/api/write-report", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({path})
        });
        if (!response.ok) {
          setStatus(await response.text());
          return;
        }
        const payload = await response.json();
        setStatus("已生成: " + payload.path);
      } catch (error) {
        setStatus(String(error));
      }
    });
  }

  if (input) {
    const params = new URLSearchParams(window.location.search);
    const path = params.get("path") || input.value.trim();
    if (path) {
      input.value = path;
      loadCase(path);
    }
  }
})();
"""


if __name__ == "__main__":
    raise SystemExit(main())
