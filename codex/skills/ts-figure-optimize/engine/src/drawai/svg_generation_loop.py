from __future__ import annotations

import json
import re
import shlex
import shutil
from pathlib import Path
from typing import Any, Callable, Mapping

from lxml import etree
from PIL import Image, ImageDraw

from .asset_manifest_utils import iter_manifest_image_items
from .svg_validation import validate_svg_file


Invoker = Callable[..., Any]

_SVG_FENCE_RE = re.compile(r"```\s*svg\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_INLINE_SVG_RE = re.compile(r"(<svg\b[\s\S]*?</svg>)", re.IGNORECASE)
_MODIFICATION_NOTES_FENCE_RE = re.compile(
    r"```\s*(?:modification_notes|modification-notes|notes|markdown|md)\s*(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
_CODEX_MERGED_STAGES_PHASE = "codex_merged_stages"
_ATTEMPT_VALIDATOR_SCRIPT = "validate_svg_attempt.py"
_ATTEMPT_VALIDATOR_CONTEXT = "validator_context.json"
_NATIVE_BACKFILL_REQUEST = "native_backfill_request.json"
_NATIVE_BACKFILL_CANDIDATE_LIMIT = 32


class SvgGenerationError(RuntimeError):
    """Raised when the SVG generation loop cannot produce a valid SVG."""

    def __init__(self, message: str, metadata: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.metadata = dict(metadata or {})
        self.attempt_reports = self.metadata.get("attempt_reports", [])
        self.last_issues = self.metadata.get("last_issues", [])


def run_svg_generation_loop(
    box_ir: Mapping[str, Any],
    figure_path: str | Path,
    reference_image_path: str | Path,
    asset_manifest: Mapping[str, Any] | None,
    output_dir: str | Path,
    max_attempts: int,
    invoker: Invoker | None = None,
    runtime_config: Any | None = None,
    staged_generation: bool = False,
    visual_review_rounds: tuple[str, ...] = ("text_style",),
    template_ir: Mapping[str, Any] | None = None,
    text_rendering: str = "model_text",
) -> dict[str, Any]:
    if str(text_rendering or "model_text").strip().lower() != "model_text":
        raise SvgGenerationError(
            "Only model_text rendering is supported in the DrawAI/SAM3 mainline.",
            {
                "status": "failed",
                "attempt_count": 0,
                "last_issues": [
                    _issue(
                        "unsupported_text_rendering",
                        "Use svg.text_rendering=model_text so the model emits editable text/tspan directly.",
                    )
                ],
            },
        )
    text_rendering = "model_text"
    if invoker is None:
        raise SvgGenerationError(
            "No SVG generation invoker was provided, and DrawAI SVG runtime wiring is not available yet.",
            {"status": "failed", "attempt_count": 0, "last_issues": [_issue("invoker_missing", "SVG generation requires an injected invoker.")]},
        )
    if max_attempts < 1:
        raise SvgGenerationError(
            "max_attempts must be at least 1 for SVG generation.",
            {"status": "failed", "attempt_count": 0, "last_issues": [_issue("max_attempts_invalid", "max_attempts must be at least 1.")]},
        )
    normalized_visual_review_rounds = tuple(str(round_name).strip().lower() for round_name in visual_review_rounds)
    for round_name in normalized_visual_review_rounds:
        if round_name not in {"text_style", "layout"}:
            raise SvgGenerationError(
                "Unsupported visual review round.",
                {
                    "status": "failed",
                    "attempt_count": 0,
                    "last_issues": [
                        _issue(
                            "unsupported_visual_review_round",
                            "Use only text_style and layout visual review rounds.",
                            {"round": round_name},
                        )
                    ],
                },
            )

    output_path = Path(output_dir)
    attempts_dir = output_path / "attempts"
    template_iterations_dir = output_path / "template_iterations"
    template_svg = output_path / "template.svg"
    template_render = output_path / "template_rendered.png"
    final_svg = output_path / "semantic.svg"
    final_render = output_path / "rendered.png"
    top_level_report = output_path / "svg_validation_report.json"
    output_path.mkdir(parents=True, exist_ok=True)
    _reset_loop_owned_outputs(
        attempts_dir=attempts_dir,
        template_iterations_dir=template_iterations_dir,
        native_backfill_assets_dir=output_path / "native_backfill_assets",
        template_svg=template_svg,
        template_render=template_render,
        final_svg=final_svg,
        final_render=final_render,
        top_level_report=top_level_report,
    )

    figure = Path(figure_path)
    reference_image = Path(reference_image_path)
    canvas = box_ir.get("canvas") if isinstance(box_ir, Mapping) else None

    if staged_generation:
        return _run_staged_generation_loop(
            box_ir=box_ir,
            figure_path=figure,
            reference_image_path=reference_image,
            asset_manifest=asset_manifest,
            output_path=output_path,
            attempts_dir=attempts_dir,
            template_iterations_dir=template_iterations_dir,
            template_svg=template_svg,
            template_render=template_render,
            final_svg=final_svg,
            final_render=final_render,
            top_level_report=top_level_report,
            max_attempts=max_attempts,
            visual_review_rounds=normalized_visual_review_rounds,
            invoker=invoker,
            runtime_config=runtime_config,
            canvas=canvas,
            template_ir=template_ir,
            text_rendering=text_rendering,
        )

    feedback: dict[str, Any] | None = None
    attempt_reports: list[dict[str, Any]] = []

    for attempt in range(1, max_attempts + 1):
        attempt_dir = attempts_dir / f"{attempt:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        response_path = attempt_dir / "model_response.txt"
        attempt_svg = attempt_dir / "semantic.svg"
        attempt_render = attempt_dir / "rendered.png"
        attempt_report_path = attempt_dir / "validation_report.json"

        report = _run_attempt(
            attempt=attempt,
            feedback=feedback,
            box_ir=box_ir,
            figure_path=figure,
            reference_image_path=reference_image,
            asset_manifest=asset_manifest,
            runtime_config=runtime_config,
            invoker=invoker,
            response_path=response_path,
            svg_path=attempt_svg,
            rendered_path=attempt_render,
            report_path=attempt_report_path,
            canvas=canvas,
            reference_dir=output_path,
            text_rendering=text_rendering,
        )
        attempt_reports.append(
            {
                "attempt": attempt,
                "status": report["status"],
                "issues": report.get("issues", []),
                "validation_report": str(attempt_report_path),
                "semantic_svg": str(attempt_svg),
                "rendered_png": str(attempt_render),
                "model_response": str(response_path),
            }
        )
        _write_json(top_level_report, _top_level_report(report, attempt, final_render if report["status"] == "ok" else None))

        if report["status"] == "ok":
            shutil.copy2(attempt_svg, final_svg)
            shutil.copy2(attempt_render, final_render)
            final_report = _top_level_report(report, attempt, final_render)
            final_report["semantic_svg"] = str(final_svg)
            _write_json(top_level_report, final_report)
            return {
                "status": "ok",
                "attempt_count": attempt,
                "artifacts": {
                    "semantic_svg": str(final_svg),
                    "rendered_png": str(final_render),
                    "validation_report": str(top_level_report),
                    "attempt_dir": str(attempt_dir),
                },
                "attempt_reports": attempt_reports,
                "last_issues": [],
            }

        feedback = {
            "attempt": attempt,
            "status": report["status"],
            "issues": report.get("issues", []),
            "validation_report": str(attempt_report_path),
        }

    metadata = {
        "status": "failed",
        "attempt_count": max_attempts,
        "attempt_reports": attempt_reports,
        "last_issues": feedback.get("issues", []) if feedback else [],
        "validation_report": str(top_level_report),
    }
    raise SvgGenerationError("SVG generation exhausted all attempts without a valid SVG.", metadata)


def _run_staged_generation_loop(
    *,
    box_ir: Mapping[str, Any],
    figure_path: Path,
    reference_image_path: Path,
    asset_manifest: Mapping[str, Any] | None,
    output_path: Path,
    attempts_dir: Path,
    template_iterations_dir: Path,
    template_svg: Path,
    template_render: Path,
    final_svg: Path,
    final_render: Path,
    top_level_report: Path,
    max_attempts: int,
    visual_review_rounds: tuple[str, ...],
    invoker: Invoker,
    runtime_config: Any | None,
    canvas: Any,
    template_ir: Mapping[str, Any] | None,
    text_rendering: str,
) -> dict[str, Any]:
    if _uses_codex_python_sdk_runtime(runtime_config):
        return _run_codex_merged_staged_generation_loop(
            box_ir=box_ir,
            figure_path=figure_path,
            reference_image_path=reference_image_path,
            asset_manifest=asset_manifest,
            output_path=output_path,
            attempts_dir=attempts_dir / "codex_merged",
            template_iterations_dir=template_iterations_dir,
            template_svg=template_svg,
            template_render=template_render,
            final_svg=final_svg,
            final_render=final_render,
            top_level_report=top_level_report,
            max_attempts=max_attempts,
            visual_review_rounds=visual_review_rounds,
            invoker=invoker,
            runtime_config=runtime_config,
            canvas=canvas,
            template_ir=template_ir,
            text_rendering=text_rendering,
        )
    template_result = _run_visual_template_phase(
        box_ir=box_ir,
        figure_path=figure_path,
        reference_image_path=reference_image_path,
        asset_manifest=asset_manifest,
        output_path=output_path,
        attempts_dir=template_iterations_dir / "01_template",
        template_svg=template_svg,
        template_render=template_render,
        top_level_report=top_level_report,
        max_attempts=max_attempts,
        invoker=invoker,
        runtime_config=runtime_config,
        canvas=canvas,
        template_ir=template_ir,
        text_rendering=text_rendering,
    )
    visual_review_result = _run_visual_review_loop(
        box_ir=box_ir,
        figure_path=figure_path,
        asset_manifest=asset_manifest,
        output_path=output_path,
        loop_dir=template_iterations_dir / "02_visual_review_loop",
        template_svg=template_svg,
        template_render=template_render,
        top_level_report=top_level_report,
        max_attempts=max_attempts,
        rounds=visual_review_rounds,
        invoker=invoker,
        runtime_config=runtime_config,
        canvas=canvas,
        base_svg=template_result["svg_text"],
        template_ir=template_ir,
        text_rendering=text_rendering,
    )
    _write_template_iteration_manifest(
        template_iterations_dir=template_iterations_dir,
        template_phase_dir=template_iterations_dir / "01_template",
        template_result=template_result,
        visual_review_result=visual_review_result,
        template_svg=template_svg,
        template_render=template_render,
    )
    refine_result = _run_ir_refine_phase(
        box_ir=box_ir,
        figure_path=figure_path,
        reference_image_path=template_render,
        asset_manifest=asset_manifest,
        output_path=output_path,
        attempts_dir=attempts_dir / "ir_refine",
        final_svg=final_svg,
        final_render=final_render,
        top_level_report=top_level_report,
        max_attempts=max_attempts,
        invoker=invoker,
        runtime_config=runtime_config,
        canvas=canvas,
        base_svg=visual_review_result["svg_text"],
        template_ir=template_ir,
        text_rendering=text_rendering,
    )
    attempt_count = (
        int(template_result["attempt_count"])
        + int(visual_review_result["attempt_count"])
        + int(refine_result["attempt_count"])
    )
    return {
        "status": "ok",
        "attempt_count": attempt_count,
        "artifacts": {
            "template_svg": str(template_svg),
            "template_rendered_png": str(template_render),
            "template_iterations_dir": str(template_iterations_dir),
            "semantic_svg": str(final_svg),
            "rendered_png": str(final_render),
            "validation_report": str(top_level_report),
            "attempt_dir": str(refine_result["attempt_dir"]),
        },
        "phase_reports": {
            "template": template_result["attempt_reports"],
            "visual_review": visual_review_result["attempt_reports"],
            "ir_refine": refine_result["attempt_reports"],
        },
        "attempt_reports": [
            *template_result["attempt_reports"],
            *visual_review_result["attempt_reports"],
            *refine_result["attempt_reports"],
        ],
        "last_issues": [],
    }


def _uses_codex_python_sdk_runtime(runtime_config: Any | None) -> bool:
    if not isinstance(runtime_config, Mapping):
        return False
    provider = str(runtime_config.get("provider") or "").strip().lower()
    connection_id = str(runtime_config.get("connection_id") or "").strip().lower()
    return provider in {"codex-python-sdk"} or connection_id in {
        "codex-python-sdk-controlled",
    }


def _run_codex_merged_staged_generation_loop(
    *,
    box_ir: Mapping[str, Any],
    figure_path: Path,
    reference_image_path: Path,
    asset_manifest: Mapping[str, Any] | None,
    output_path: Path,
    attempts_dir: Path,
    template_iterations_dir: Path,
    template_svg: Path,
    template_render: Path,
    final_svg: Path,
    final_render: Path,
    top_level_report: Path,
    max_attempts: int,
    visual_review_rounds: tuple[str, ...],
    invoker: Invoker,
    runtime_config: Any | None,
    canvas: Any,
    template_ir: Mapping[str, Any] | None,
    text_rendering: str,
) -> dict[str, Any]:
    feedback: dict[str, Any] | None = None
    attempt_reports: list[dict[str, Any]] = []
    phase = _CODEX_MERGED_STAGES_PHASE

    for attempt in range(1, max_attempts + 1):
        attempt_dir = attempts_dir / f"{attempt:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        response_path = attempt_dir / "model_response.txt"
        attempt_svg = attempt_dir / "semantic.svg"
        attempt_render = attempt_dir / "rendered.png"
        attempt_report_path = attempt_dir / "validation_report.json"
        iteration_log = attempt_dir / "iteration_log.md"
        iteration_log_jsonl = attempt_dir / "iteration_log.jsonl"
        report = _run_attempt(
            attempt=attempt,
            feedback=feedback,
            box_ir=box_ir,
            figure_path=figure_path,
            reference_image_path=reference_image_path,
            asset_manifest=asset_manifest,
            runtime_config=runtime_config,
            invoker=invoker,
            response_path=response_path,
            svg_path=attempt_svg,
            rendered_path=attempt_render,
            report_path=attempt_report_path,
            canvas=canvas,
            reference_dir=output_path,
            phase=phase,
            template_ir=template_ir,
            visual_review_rounds=visual_review_rounds,
            text_rendering=text_rendering,
            iteration_log_path=iteration_log,
            iteration_log_jsonl_path=iteration_log_jsonl,
            template_svg_path=template_svg,
            template_rendered_path=template_render,
        )
        attempt_report = _attempt_report(
            phase,
            attempt,
            report,
            attempt_report_path,
            attempt_svg,
            attempt_render,
            response_path,
        )
        if iteration_log.exists():
            attempt_report["iteration_log"] = str(iteration_log)
        if iteration_log_jsonl.exists():
            attempt_report["iteration_log_jsonl"] = str(iteration_log_jsonl)
        attempt_reports.append(attempt_report)

        if report["status"] == "ok":
            shutil.copy2(attempt_svg, final_svg)
            shutil.copy2(attempt_render, final_render)
            shutil.copy2(attempt_svg, template_svg)
            shutil.copy2(attempt_render, template_render)
            _write_template_iteration_manifest(
                template_iterations_dir=template_iterations_dir,
                template_phase_dir=attempts_dir,
                template_result={
                    "status": "ok",
                    "attempt_count": attempt,
                    "attempt_reports": attempt_reports,
                    "attempt_dir": str(attempt_dir),
                },
                visual_review_result={
                    "status": "ok",
                    "attempt_count": 0,
                    "attempt_reports": [],
                    "round_results": [],
                },
                template_svg=template_svg,
                template_render=template_render,
            )
            final_report = _top_level_report(report, attempt, final_render, phase=phase)
            final_report["semantic_svg"] = str(final_svg)
            if iteration_log.exists():
                final_report["iteration_log"] = str(iteration_log)
            if iteration_log_jsonl.exists():
                final_report["iteration_log_jsonl"] = str(iteration_log_jsonl)
            _write_json(top_level_report, final_report)
            artifacts = {
                "template_svg": str(template_svg),
                "template_rendered_png": str(template_render),
                "template_iterations_dir": str(template_iterations_dir),
                "semantic_svg": str(final_svg),
                "rendered_png": str(final_render),
                "validation_report": str(top_level_report),
                "attempt_dir": str(attempt_dir),
            }
            if iteration_log.exists():
                artifacts["iteration_log"] = str(iteration_log)
            if iteration_log_jsonl.exists():
                artifacts["iteration_log_jsonl"] = str(iteration_log_jsonl)
            return {
                "status": "ok",
                "attempt_count": attempt,
                "artifacts": artifacts,
                "phase_reports": {"codex_merged": attempt_reports},
                "attempt_reports": attempt_reports,
                "last_issues": [],
            }

        _write_json(top_level_report, _top_level_report(report, attempt, None, phase=phase))
        feedback = {
            "phase": phase,
            "attempt": attempt,
            "status": report["status"],
            "issues": report.get("issues", []),
            "validation_report": str(attempt_report_path),
        }

    metadata = {
        "status": "failed",
        "phase": phase,
        "attempt_count": max_attempts,
        "attempt_reports": attempt_reports,
        "last_issues": feedback.get("issues", []) if feedback else [],
        "validation_report": str(top_level_report),
    }
    raise SvgGenerationError("Merged Codex SVG generation exhausted all attempts.", metadata)


def _run_visual_template_phase(
    *,
    box_ir: Mapping[str, Any],
    figure_path: Path,
    reference_image_path: Path,
    asset_manifest: Mapping[str, Any] | None,
    output_path: Path,
    attempts_dir: Path,
    template_svg: Path,
    template_render: Path,
    top_level_report: Path,
    max_attempts: int,
    invoker: Invoker,
    runtime_config: Any | None,
    canvas: Any,
    template_ir: Mapping[str, Any] | None,
    text_rendering: str,
) -> dict[str, Any]:
    feedback: dict[str, Any] | None = None
    attempt_reports: list[dict[str, Any]] = []
    phase = "template"
    for attempt in range(1, max_attempts + 1):
        attempt_dir = attempts_dir / f"{attempt:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        response_path = attempt_dir / "model_response.txt"
        attempt_svg = attempt_dir / "semantic.svg"
        attempt_render = attempt_dir / "rendered.png"
        attempt_report_path = attempt_dir / "validation_report.json"
        report = _run_attempt(
            attempt=attempt,
            feedback=feedback,
            box_ir=box_ir,
            figure_path=figure_path,
            reference_image_path=reference_image_path,
            asset_manifest=asset_manifest,
            runtime_config=runtime_config,
            invoker=invoker,
            response_path=response_path,
            svg_path=attempt_svg,
            rendered_path=attempt_render,
            report_path=attempt_report_path,
            canvas=canvas,
            reference_dir=output_path,
            phase=phase,
            template_ir=template_ir,
            text_rendering=text_rendering,
        )
        attempt_reports.append(_attempt_report(phase, attempt, report, attempt_report_path, attempt_svg, attempt_render, response_path))
        _write_json(top_level_report, _top_level_report(report, attempt, None, phase=phase))
        if report["status"] == "ok":
            shutil.copy2(attempt_svg, template_svg)
            shutil.copy2(attempt_render, template_render)
            return {
                "status": "ok",
                "attempt_count": attempt,
                "attempt_reports": attempt_reports,
                "attempt_dir": str(attempt_dir),
                "svg_text": attempt_svg.read_text(encoding="utf-8"),
            }
        feedback = {
            "phase": phase,
            "attempt": attempt,
            "status": report["status"],
            "issues": report.get("issues", []),
            "validation_report": str(attempt_report_path),
        }

    metadata = {
        "status": "failed",
        "phase": phase,
        "attempt_count": max_attempts,
        "attempt_reports": attempt_reports,
        "last_issues": feedback.get("issues", []) if feedback else [],
        "validation_report": str(top_level_report),
    }
    raise SvgGenerationError("Visual template SVG generation exhausted all attempts.", metadata)


def _run_visual_review_loop(
    *,
    box_ir: Mapping[str, Any],
    figure_path: Path,
    asset_manifest: Mapping[str, Any] | None,
    output_path: Path,
    loop_dir: Path,
    template_svg: Path,
    template_render: Path,
    top_level_report: Path,
    max_attempts: int,
    rounds: tuple[str, ...],
    invoker: Invoker,
    runtime_config: Any | None,
    canvas: Any,
    base_svg: str,
    template_ir: Mapping[str, Any] | None,
    text_rendering: str,
) -> dict[str, Any]:
    if not rounds:
        return {
            "status": "ok",
            "attempt_count": 0,
            "attempt_reports": [],
            "round_results": [],
            "attempt_dir": None,
            "svg_text": base_svg,
        }

    current_svg = base_svg
    round_results: list[dict[str, Any]] = []
    attempt_reports: list[dict[str, Any]] = []
    total_rounds = len(rounds)

    for round_index, focus in enumerate(rounds, start=1):
        phase = f"visual_review_{focus}"
        round_result = _run_visual_review_round(
            box_ir=box_ir,
            figure_path=figure_path,
            asset_manifest=asset_manifest,
            current_template_render=template_render,
            output_path=output_path,
            attempts_dir=loop_dir / f"round_{round_index:02d}_{focus}",
            template_svg=template_svg,
            template_render=template_render,
            top_level_report=top_level_report,
            max_attempts=max_attempts,
            invoker=invoker,
            runtime_config=runtime_config,
            canvas=canvas,
            base_svg=current_svg,
            template_ir=template_ir,
            visual_review_round=round_index,
            visual_review_total_rounds=total_rounds,
            text_rendering=text_rendering,
            phase=phase,
            visual_review_focus=focus,
        )
        round_results.append(round_result)
        attempt_reports.extend(round_result["attempt_reports"])
        current_svg = str(round_result["svg_text"])

    return {
        "status": "ok",
        "attempt_count": sum(int(result["attempt_count"]) for result in round_results),
        "attempt_reports": attempt_reports,
        "round_results": round_results,
        "attempt_dir": round_results[-1]["attempt_dir"],
        "svg_text": current_svg,
    }


def _run_visual_review_round(
    *,
    box_ir: Mapping[str, Any],
    figure_path: Path,
    asset_manifest: Mapping[str, Any] | None,
    current_template_render: Path,
    output_path: Path,
    attempts_dir: Path,
    template_svg: Path,
    template_render: Path,
    top_level_report: Path,
    max_attempts: int,
    invoker: Invoker,
    runtime_config: Any | None,
    canvas: Any,
    base_svg: str,
    template_ir: Mapping[str, Any] | None,
    visual_review_round: int,
    visual_review_total_rounds: int,
    text_rendering: str,
    phase: str,
    visual_review_focus: str | None = None,
) -> dict[str, Any]:
    feedback: dict[str, Any] | None = None
    attempt_reports: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        attempt_dir = attempts_dir / f"{attempt:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        response_path = attempt_dir / "model_response.txt"
        attempt_svg = attempt_dir / "semantic.svg"
        attempt_render = attempt_dir / "rendered.png"
        attempt_report_path = attempt_dir / "validation_report.json"
        report = _run_attempt(
            attempt=attempt,
            feedback=feedback,
            box_ir=box_ir,
            figure_path=figure_path,
            reference_image_path=current_template_render,
            asset_manifest=asset_manifest,
            runtime_config=runtime_config,
            invoker=invoker,
            response_path=response_path,
            svg_path=attempt_svg,
            rendered_path=attempt_render,
            report_path=attempt_report_path,
            canvas=canvas,
            reference_dir=output_path,
            phase=phase,
            base_svg=base_svg,
            template_ir=template_ir,
            visual_review_round=visual_review_round,
            visual_review_total_rounds=visual_review_total_rounds,
            visual_review_focus=visual_review_focus,
            text_rendering=text_rendering,
        )
        _write_json(top_level_report, _top_level_report(report, attempt, None, phase=phase))
        if report["status"] == "ok":
            refined_report = validate_svg_file(
                attempt_svg,
                canvas=canvas,
                asset_manifest=asset_manifest,
                rendered_path=attempt_render,
                reference_dir=output_path,
            )
            refined_report = _merge_validation_issues(
                refined_report,
                _model_stage_contract_issues(
                    attempt_svg,
                    phase,
                    text_rendering=text_rendering,
                    allow_manifest_images=_phase_allows_manifest_asset_images(phase),
                ),
            )
            if report.get("modification_notes"):
                refined_report["modification_notes"] = report["modification_notes"]
            _write_json(attempt_report_path, refined_report)
            _write_json(top_level_report, _top_level_report(refined_report, attempt, attempt_render, phase=phase))
            attempt_reports.append(
                _attempt_report(
                    phase,
                    attempt,
                    refined_report,
                    attempt_report_path,
                    attempt_svg,
                    attempt_render,
                    response_path,
                )
            )
            if refined_report["status"] != "ok":
                feedback = {
                    "phase": phase,
                    "attempt": attempt,
                    "status": refined_report["status"],
                    "issues": refined_report.get("issues", []),
                    "validation_report": str(attempt_report_path),
                    "base_svg": base_svg,
                    "visual_review_round": visual_review_round,
                    "visual_review_total_rounds": visual_review_total_rounds,
                    "visual_review_focus": visual_review_focus,
                }
                continue
            shutil.copy2(attempt_svg, template_svg)
            shutil.copy2(attempt_render, template_render)
            return {
                "status": "ok",
                "phase": phase,
                "attempt_count": attempt,
                "attempt_reports": attempt_reports,
                "attempt_dir": str(attempt_dir),
                "round": visual_review_round,
                "focus": visual_review_focus,
                "svg_text": attempt_svg.read_text(encoding="utf-8"),
            }
        attempt_reports.append(_attempt_report(phase, attempt, report, attempt_report_path, attempt_svg, attempt_render, response_path))
        feedback = {
            "phase": phase,
            "attempt": attempt,
            "status": report["status"],
            "issues": report.get("issues", []),
            "validation_report": str(attempt_report_path),
            "base_svg": base_svg,
            "visual_review_round": visual_review_round,
            "visual_review_total_rounds": visual_review_total_rounds,
            "visual_review_focus": visual_review_focus,
        }

    metadata = {
        "status": "failed",
        "phase": phase,
        "attempt_count": max_attempts,
        "round": visual_review_round,
        "focus": visual_review_focus,
        "attempt_reports": attempt_reports,
        "last_issues": feedback.get("issues", []) if feedback else [],
        "validation_report": str(top_level_report),
    }
    raise SvgGenerationError("Visual template review exhausted all attempts.", metadata)


def _run_ir_refine_phase(
    *,
    box_ir: Mapping[str, Any],
    figure_path: Path,
    reference_image_path: Path,
    asset_manifest: Mapping[str, Any] | None,
    output_path: Path,
    attempts_dir: Path,
    final_svg: Path,
    final_render: Path,
    top_level_report: Path,
    max_attempts: int,
    invoker: Invoker,
    runtime_config: Any | None,
    canvas: Any,
    base_svg: str,
    template_ir: Mapping[str, Any] | None,
    text_rendering: str,
) -> dict[str, Any]:
    feedback: dict[str, Any] | None = None
    attempt_reports: list[dict[str, Any]] = []
    phase = "ir_refine"

    for attempt in range(1, max_attempts + 1):
        attempt_dir = attempts_dir / f"{attempt:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        response_path = attempt_dir / "model_response.txt"
        attempt_svg = attempt_dir / "semantic.svg"
        attempt_render = attempt_dir / "rendered.png"
        attempt_report_path = attempt_dir / "validation_report.json"
        report = _run_attempt(
            attempt=attempt,
            feedback=feedback,
            box_ir=box_ir,
            figure_path=figure_path,
            reference_image_path=reference_image_path,
            asset_manifest=asset_manifest,
            runtime_config=runtime_config,
            invoker=invoker,
            response_path=response_path,
            svg_path=attempt_svg,
            rendered_path=attempt_render,
            report_path=attempt_report_path,
            canvas=canvas,
            reference_dir=output_path,
            phase=phase,
            base_svg=base_svg,
            template_ir=template_ir,
            text_rendering=text_rendering,
        )
        if report["status"] == "ok":
            shutil.copy2(attempt_svg, final_svg)
            shutil.copy2(attempt_render, final_render)
            final_report = _top_level_report(report, attempt, final_render, phase=phase)
            final_report["semantic_svg"] = str(final_svg)
            _write_json(top_level_report, final_report)
            attempt_reports.append(
                _attempt_report(
                    phase,
                    attempt,
                    report,
                    attempt_report_path,
                    attempt_svg,
                    attempt_render,
                    response_path,
                )
            )
            return {
                "status": "ok",
                "attempt_count": attempt,
                "attempt_reports": attempt_reports,
                "attempt_dir": str(attempt_dir),
            }
        else:
            _write_json(top_level_report, _top_level_report(report, attempt, None, phase=phase))

        attempt_reports.append(_attempt_report(phase, attempt, report, attempt_report_path, attempt_svg, attempt_render, response_path))
        feedback = {
            "phase": phase,
            "attempt": attempt,
            "status": report["status"],
            "issues": report.get("issues", []),
            "validation_report": str(attempt_report_path),
            "base_svg": base_svg,
        }

    metadata = {
        "status": "failed",
        "phase": phase,
        "attempt_count": max_attempts,
        "attempt_reports": attempt_reports,
        "last_issues": feedback.get("issues", []) if feedback else [],
        "validation_report": str(top_level_report),
    }
    raise SvgGenerationError("IR-refined SVG generation exhausted all attempts.", metadata)


def _write_template_iteration_manifest(
    *,
    template_iterations_dir: Path,
    template_phase_dir: Path,
    template_result: Mapping[str, Any],
    visual_review_result: Mapping[str, Any],
    template_svg: Path,
    template_render: Path,
) -> None:
    review_phases = [
        _template_iteration_phase_manifest(
            str(result.get("phase") or f"visual_review_{result.get('focus') or 'unknown'}"),
            Path(str(result.get("attempt_dir", ""))).parent,
            result,
            round_index=_safe_round_index(result),
            focus=str(result.get("focus")) if result.get("focus") else None,
        )
        for result in visual_review_result.get("round_results", [])
        if isinstance(result, Mapping)
    ]
    payload = {
        "schema": "drawai.svg_template_iterations.v1",
        "status": "ok",
        "phases": [
            _template_iteration_phase_manifest("template", template_phase_dir, template_result),
            *review_phases,
        ],
        "stable_outputs": {
            "template_svg": str(template_svg),
            "template_rendered_png": str(template_render),
        },
    }
    _write_json(template_iterations_dir / "iteration_manifest.json", payload)


def _template_iteration_phase_manifest(
    phase: str,
    phase_dir: Path,
    result: Mapping[str, Any],
    *,
    round_index: int | None = None,
    focus: str | None = None,
) -> dict[str, Any]:
    attempt_reports = list(result.get("attempt_reports") or [])
    selected_report = attempt_reports[-1] if attempt_reports else {}
    if not isinstance(selected_report, Mapping):
        selected_report = {}
    payload = {
        "phase": phase,
        "status": result.get("status", "unknown"),
        "attempt_count": result.get("attempt_count", len(attempt_reports)),
        "attempts_dir": str(phase_dir),
        "selected_attempt_dir": result.get("attempt_dir"),
        "selected_svg": selected_report.get("semantic_svg"),
        "selected_rendered_png": selected_report.get("rendered_png"),
        "selected_validation_report": selected_report.get("validation_report"),
        "attempt_reports": attempt_reports,
    }
    if round_index is not None:
        payload["round"] = round_index
    if focus is not None:
        payload["focus"] = focus
    return payload


def _safe_round_index(result: Mapping[str, Any]) -> int | None:
    try:
        round_index = int(result.get("round"))
    except (TypeError, ValueError):
        return None
    return round_index if round_index > 0 else None


def _write_attempt_request_context(
    path: Path,
    *,
    phase: str,
    attempt: int,
    figure_path: Path,
    reference_image_path: Path,
    response_path: Path,
    svg_path: Path,
    rendered_path: Path,
    report_path: Path,
    prompt_path: Path,
    feedback: Mapping[str, Any] | None,
    runtime_config: Any,
    has_base_svg: bool,
    input_template_path: Path | None,
    has_template_ir: bool,
    has_asset_manifest: bool,
    visual_review_round: int | None,
    visual_review_total_rounds: int | None,
    visual_review_focus: str | None,
    visual_review_rounds: tuple[str, ...] | None,
    iteration_log_path: Path | None,
    iteration_log_jsonl_path: Path | None,
    template_svg_path: Path | None,
    template_rendered_path: Path | None,
    native_backfill_context: Mapping[str, Any],
    validator_script_path: Path,
    validator_context_path: Path,
    validator_command: str,
    text_rendering: str,
) -> None:
    payload = {
        "schema": "drawai.svg_generation_attempt_context.v1",
        "phase": phase,
        "attempt": attempt,
        "figure_path": str(figure_path),
        "reference_image_path": str(reference_image_path),
        "response_path": str(response_path),
        "semantic_svg": str(svg_path),
        "rendered_png": str(rendered_path),
        "validation_report": str(report_path),
        "prompt_path": str(prompt_path),
        "has_base_svg": has_base_svg,
        "input_template_svg": str(input_template_path) if input_template_path is not None else None,
        "has_template_ir": has_template_ir,
        "has_asset_manifest": has_asset_manifest,
        "visual_review_round": visual_review_round,
        "visual_review_total_rounds": visual_review_total_rounds,
        "visual_review_focus": visual_review_focus,
        "visual_review_rounds": list(visual_review_rounds or ()),
        "iteration_log": str(iteration_log_path) if iteration_log_path is not None else None,
        "iteration_log_jsonl": str(iteration_log_jsonl_path) if iteration_log_jsonl_path is not None else None,
        "template_svg": str(template_svg_path) if template_svg_path is not None else None,
        "template_rendered_png": str(template_rendered_path) if template_rendered_path is not None else None,
        "native_backfill_request": str(native_backfill_context.get("request_path") or ""),
        "native_backfill_tools_dir": str(native_backfill_context.get("tools_dir") or ""),
        "native_backfill_assets_dir": str(native_backfill_context.get("assets_dir") or ""),
        "native_backfill_asset_href_prefix": str(native_backfill_context.get("asset_href_prefix") or ""),
        "native_backfill_candidate_count": int(native_backfill_context.get("candidate_count") or 0),
        "native_backfill_allowed_image_hrefs": list(native_backfill_context.get("allowed_image_hrefs") or []),
        "validator_script": str(validator_script_path),
        "validator_context": str(validator_context_path),
        "validator_command": validator_command,
        "text_rendering": text_rendering,
        "feedback": _json_safe(feedback or {}),
        "runtime_config": _redact_sensitive_context(_json_safe(runtime_config or {})),
    }
    _write_json(path, payload)


def _prepare_native_backfill_context(
    *,
    attempt_dir: Path,
    reference_dir: Path,
    figure_path: Path,
    box_ir: Mapping[str, Any],
    base_asset_manifest: Mapping[str, Any] | None,
    phase: str | None,
    attempt: int,
) -> dict[str, Any]:
    tools_dir = attempt_dir / "native_backfill_tools"
    previews_dir = attempt_dir / "native_backfill_previews"
    run_root = reference_dir.parent
    original_figure = run_root / "inputs" / "figure.png"
    source_image = original_figure if original_figure.is_file() else figure_path
    asset_dir_name = f"{_safe_path_token(phase or 'single')}_{attempt:03d}"
    assets_dir = reference_dir / "native_backfill_assets" / asset_dir_name
    href_prefix = f"native_backfill_assets/{asset_dir_name}"
    for directory in (tools_dir, previews_dir, assets_dir):
        directory.mkdir(parents=True, exist_ok=True)

    candidates = _native_backfill_candidates(
        run_root=run_root,
        box_ir=box_ir,
        source_image=source_image,
        previews_dir=previews_dir,
        href_prefix=href_prefix,
    )
    native_validation_manifest = _native_backfill_validation_manifest(candidates)
    base_allowed_hrefs = _manifest_allowed_hrefs(base_asset_manifest)
    native_allowed_hrefs = _manifest_allowed_hrefs(native_validation_manifest)
    request_path = attempt_dir / _NATIVE_BACKFILL_REQUEST
    request = {
        "schema": "drawai.native_backfill_request.v1",
        "phase": phase or "single",
        "attempt": attempt,
        "source_image": str(source_image),
        "assets_dir": str(assets_dir),
        "asset_href_prefix": href_prefix,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "allowed_href_policy": {
            "base_manifest_hrefs": base_allowed_hrefs,
            "native_backfill_hrefs": native_allowed_hrefs,
            "svg_image_href_rule": (
                "SVG <image> href values must be copied exactly from base_manifest_hrefs "
                "or native_backfill_hrefs. Do not use source images, previews, guessed crop paths, "
                "absolute paths, file:// URLs, external URLs, or base64 images as SVG href values."
            ),
            "native_backfill_source_fields_are_read_only": [
                "source_image",
                "source_region_preview",
            ],
        },
        "rules": {
            "keep_native_svg": "Use native SVG when the rendered region is structurally close enough and remains editable.",
            "backfill_crop_preserve": "Use an exact crop when native SVG loses detailed visual content that should remain raster.",
            "backfill_crop_nobg": "Use background removal only for isolated foreground subjects on a removable plain/light/neutral background.",
        },
    }
    _write_json(request_path, request)
    _write_native_backfill_tools(tools_dir)
    return {
        "request_path": request_path,
        "tools_dir": tools_dir,
        "assets_dir": assets_dir,
        "asset_href_prefix": href_prefix,
        "candidate_count": len(candidates),
        "allowed_image_hrefs": [*base_allowed_hrefs, *native_allowed_hrefs],
        "validation_asset_manifest": native_validation_manifest,
    }


def _native_backfill_candidates(
    *,
    run_root: Path,
    box_ir: Mapping[str, Any],
    source_image: Path,
    previews_dir: Path,
    href_prefix: str,
) -> list[dict[str, Any]]:
    boxes = box_ir.get("boxes") if isinstance(box_ir, Mapping) else []
    boxes_by_id = {
        str(box.get("id")): box
        for box in boxes
        if isinstance(box, Mapping) and str(box.get("id") or "").strip()
    }
    asset_root = run_root / "svg_to_ppt" / "assets"
    decisions_payload = _read_json_if_file(asset_root / "asset_decisions.json")
    policy_payload = _read_json_if_file(asset_root / "asset_policy_report.json")
    policy_by_asset_id = _policy_by_asset_id(policy_payload)

    selected: list[Mapping[str, Any]] = []
    decisions = decisions_payload.get("decisions") if isinstance(decisions_payload, Mapping) else None
    if isinstance(decisions, list):
        recovered = []
        native_icon_picture = []
        for decision in decisions:
            if not isinstance(decision, Mapping):
                continue
            box = boxes_by_id.get(str(decision.get("box_id") or ""))
            if decision.get("recovered_asset_id"):
                recovered.append(decision)
            elif (
                decision.get("decision") == "native_svg"
                and isinstance(box, Mapping)
                and str(box.get("type") or "") in {"icon", "picture"}
            ):
                native_icon_picture.append(decision)
        selected = [*recovered, *native_icon_picture]
    else:
        selected = [
            {"box_id": box_id, "decision": "native_svg", "asset_id": f"NB_{box_id}"}
            for box_id, box in boxes_by_id.items()
            if str(box.get("type") or "") in {"icon", "picture"}
        ]

    candidates: list[dict[str, Any]] = []
    seen_asset_ids: set[str] = set()
    for selected_item in selected:
        if len(candidates) >= _NATIVE_BACKFILL_CANDIDATE_LIMIT:
            break
        box_id = str(selected_item.get("box_id") or "").strip()
        if not box_id:
            continue
        box = boxes_by_id.get(box_id)
        if not isinstance(box, Mapping):
            continue
        recovered_asset_id = str(selected_item.get("recovered_asset_id") or "").strip()
        raw_asset_id = str(selected_item.get("asset_id") or recovered_asset_id or f"NB_{box_id}").strip()
        asset_id = _safe_path_token(raw_asset_id or f"NB_{box_id}")
        if asset_id in seen_asset_ids:
            continue
        policy = policy_by_asset_id.get(raw_asset_id) or policy_by_asset_id.get(recovered_asset_id) or {}
        bbox = _first_prompt_bbox(policy.get("bbox"), box.get("bbox"))
        if bbox is None:
            continue
        preserve_href = f"{href_prefix}/{asset_id}.png"
        nobg_href = f"{href_prefix}/{asset_id}_nobg.png"
        source_preview = previews_dir / f"{asset_id}_source.png"
        if source_image.is_file():
            _crop_exact_for_backfill(source_image, bbox, source_preview)
        candidates.append(
            {
                "asset_id": asset_id,
                "box_id": box_id,
                "box_type": box.get("type"),
                "decision": selected_item.get("decision"),
                "recovered_asset_id": recovered_asset_id or None,
                "recovery_reason": selected_item.get("recovery_reason"),
                "bbox": bbox,
                "source_region_preview": str(source_preview) if source_preview.is_file() else None,
                "preserve_href": preserve_href,
                "nobg_href": nobg_href,
                "policy": {
                    "role": policy.get("role"),
                    "render_policy": policy.get("render_policy"),
                    "background_policy": policy.get("background_policy"),
                    "current_label": policy.get("current_label"),
                    "reason_codes": policy.get("reason_codes", []),
                },
            }
        )
        seen_asset_ids.add(asset_id)
    return candidates


def _native_backfill_validation_manifest(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    for candidate in candidates:
        bbox = candidate.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        asset_id = str(candidate.get("asset_id") or "").strip()
        for suffix, href_key, background_policy in (
            ("", "preserve_href", "preserve_crop"),
            ("_nobg", "nobg_href", "transparent_subject"),
        ):
            href = str(candidate.get(href_key) or "").strip()
            if not href:
                continue
            assets.append(
                {
                    "asset_id": f"{asset_id}{suffix}",
                    "box_id": candidate.get("box_id"),
                    "bbox": bbox,
                    "svg_href": href,
                    "render_policy": "raster_png",
                    "background_policy": background_policy,
                    "native_backfill_candidate": True,
                    "insertable": True,
                }
            )
    return {"schema": "drawai.native_backfill_validation_assets.v1", "assets": assets}


def _validation_asset_manifest(
    base_asset_manifest: Mapping[str, Any] | None,
    native_backfill_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    base_assets = []
    if isinstance(base_asset_manifest, Mapping) and isinstance(base_asset_manifest.get("assets"), list):
        base_assets = list(base_asset_manifest.get("assets") or [])
    native_assets = []
    if isinstance(native_backfill_manifest, Mapping) and isinstance(native_backfill_manifest.get("assets"), list):
        native_assets = list(native_backfill_manifest.get("assets") or [])
    schema = (
        base_asset_manifest.get("schema")
        if isinstance(base_asset_manifest, Mapping) and base_asset_manifest.get("schema")
        else "drawai.validation_asset_manifest.v1"
    )
    return {"schema": schema, "assets": [*base_assets, *native_assets]}


def _manifest_allowed_hrefs(asset_manifest: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(asset_manifest, Mapping):
        return []
    hrefs: list[str] = []
    seen: set[str] = set()
    for asset in iter_manifest_image_items(asset_manifest):
        href = str(asset.get("svg_href") or "").strip()
        if href and href not in seen:
            hrefs.append(href)
            seen.add(href)
    return hrefs


def _write_native_backfill_tools(tools_dir: Path) -> None:
    crop_tool = tools_dir / "crop_region.py"
    crop_tool.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description="Crop an exact native-backfill region.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--source", choices=("original", "rendered"), default="original")
    parser.add_argument("--rendered-image", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    candidate = next(item for item in request["candidates"] if item["asset_id"] == args.asset_id)
    bbox = [int(round(float(value))) for value in candidate["bbox"]]
    if args.source == "rendered":
        if not args.rendered_image:
            raise ValueError("--rendered-image is required when --source=rendered")
        image_path = Path(args.rendered_image)
        default_name = f"{args.asset_id}_rendered_region.png"
    else:
        image_path = Path(request["source_image"])
        default_name = f"{args.asset_id}.png"
    image = Image.open(image_path).convert("RGBA")
    crop = image.crop(tuple(bbox))
    output = Path(args.out) if args.out else Path(request["assets_dir"]) / default_name
    output.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output)
    href = f"{request['asset_href_prefix']}/{output.name}" if output.parent == Path(request["assets_dir"]) else None
    print(json.dumps({"asset_id": args.asset_id, "bbox": bbox, "output": str(output), "href": href, "size": list(crop.size)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )
    crop_tool.chmod(0o755)

    remove_bg_tool = tools_dir / "remove_background.py"
    remove_bg_tool.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
from statistics import median
from PIL import Image


def _distance(a, b):
    return sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)) ** 0.5


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove a connected edge background from a crop.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--input", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--threshold", type=float, default=34.0)
    args = parser.parse_args()

    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    candidate = next(item for item in request["candidates"] if item["asset_id"] == args.asset_id)
    input_path = Path(args.input) if args.input else Path(request["assets_dir"]) / f"{args.asset_id}.png"
    output_path = Path(args.output) if args.output else Path(request["assets_dir"]) / f"{args.asset_id}_nobg.png"
    image = Image.open(input_path).convert("RGBA")
    width, height = image.size
    pixels = image.load()
    border = []
    for x in range(width):
        border.append(pixels[x, 0][:3])
        border.append(pixels[x, height - 1][:3])
    for y in range(height):
        border.append(pixels[0, y][:3])
        border.append(pixels[width - 1, y][:3])
    bg = tuple(int(median([rgb[channel] for rgb in border])) for channel in range(3))
    visited = [[False for _x in range(width)] for _y in range(height)]
    queue = deque()

    def enqueue_if_bg(x, y):
        if visited[y][x]:
            return
        if _distance(pixels[x, y][:3], bg) <= args.threshold:
            visited[y][x] = True
            queue.append((x, y))

    for x in range(width):
        enqueue_if_bg(x, 0)
        enqueue_if_bg(x, height - 1)
    for y in range(height):
        enqueue_if_bg(0, y)
        enqueue_if_bg(width - 1, y)

    removed = 0
    while queue:
        x, y = queue.popleft()
        r, g, b, _a = pixels[x, y]
        pixels[x, y] = (r, g, b, 0)
        removed += 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                enqueue_if_bg(nx, ny)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    href = f"{request['asset_href_prefix']}/{output_path.name}" if output_path.parent == Path(request["assets_dir"]) else None
    print(json.dumps({"asset_id": args.asset_id, "input": str(input_path), "output": str(output_path), "href": href, "removed_pixels": removed, "total_pixels": width * height, "bg_rgb": bg}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )
    remove_bg_tool.chmod(0o755)


def _read_json_if_file(path: Path) -> Any:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_by_asset_id(policy_payload: Any) -> dict[str, Mapping[str, Any]]:
    assets = policy_payload.get("assets") if isinstance(policy_payload, Mapping) else None
    if not isinstance(assets, list):
        return {}
    return {
        str(asset.get("asset_id")): asset
        for asset in assets
        if isinstance(asset, Mapping) and str(asset.get("asset_id") or "").strip()
    }


def _first_prompt_bbox(*raw_bboxes: Any) -> list[int] | None:
    for raw_bbox in raw_bboxes:
        bbox = _prompt_bbox(raw_bbox)
        if bbox is not None:
            return bbox
    return None


def _prompt_bbox(raw_bbox: Any) -> list[int] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        values = [max(0, int(round(float(value)))) for value in raw_bbox]
    except (TypeError, ValueError):
        return None
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        return None
    return values


def _crop_exact_for_backfill(image_path: Path, bbox: list[int], output_path: Path) -> None:
    image = Image.open(image_path).convert("RGBA")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.crop(tuple(bbox)).save(output_path)


def _safe_path_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    token = token.strip("._-")
    return token or "asset"


def _write_attempt_validator(
    *,
    attempt_dir: Path,
    canvas: Any,
    asset_manifest: Mapping[str, Any] | None,
    reference_dir: Path,
) -> tuple[Path, Path, str]:
    script_path = attempt_dir / _ATTEMPT_VALIDATOR_SCRIPT
    context_path = attempt_dir / _ATTEMPT_VALIDATOR_CONTEXT
    src_root = Path(__file__).resolve().parents[1]
    _write_json(
        context_path,
        {
            "schema": "drawai.svg_attempt_validator_context.v1",
            "canvas": _json_safe(canvas),
            "asset_manifest": _json_safe(asset_manifest),
            "reference_dir": str(reference_dir),
            "python_path": str(src_root),
        },
    )
    script_path.write_text(
        f"""#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, {str(src_root)!r})

from drawai.svg_validation import validate_svg_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one DrawAI SVG attempt and render it to PNG.")
    parser.add_argument("--svg", required=True)
    parser.add_argument("--rendered", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--context", default=str(Path(__file__).with_name({_ATTEMPT_VALIDATOR_CONTEXT!r})))
    args = parser.parse_args()

    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    report = validate_svg_file(
        args.svg,
        canvas=context["canvas"],
        asset_manifest=context.get("asset_manifest"),
        rendered_path=args.rendered,
        reference_dir=context["reference_dir"],
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    command = (
        f"python {shlex.quote(str(script_path))} "
        "--svg '<SVG_PATH>' --rendered '<PNG_PATH>' --report '<REPORT_PATH>'"
    )
    return script_path, context_path, command


def _run_attempt(
    *,
    attempt: int,
    feedback: dict[str, Any] | None,
    box_ir: Mapping[str, Any],
    figure_path: Path,
    reference_image_path: Path,
    asset_manifest: Mapping[str, Any] | None,
    runtime_config: Any | None,
    invoker: Invoker,
    response_path: Path,
    svg_path: Path,
    rendered_path: Path,
    report_path: Path,
    canvas: Any,
    reference_dir: Path,
    phase: str | None = None,
    base_svg: str | None = None,
    template_ir: Mapping[str, Any] | None = None,
    visual_review_round: int | None = None,
    visual_review_total_rounds: int | None = None,
    visual_review_focus: str | None = None,
    visual_review_rounds: tuple[str, ...] | None = None,
    iteration_log_path: Path | None = None,
    iteration_log_jsonl_path: Path | None = None,
    template_svg_path: Path | None = None,
    template_rendered_path: Path | None = None,
    text_rendering: str = "model_text",
) -> dict[str, Any]:
    pre_validation_issues: list[dict[str, Any]] = []
    attempt_dir = response_path.parent
    prompt_path = attempt_dir / "prompt.txt"
    request_context_path = attempt_dir / "request_context.json"
    input_template_path = attempt_dir / "input_template.svg"
    native_backfill_context = _prepare_native_backfill_context(
        attempt_dir=attempt_dir,
        reference_dir=reference_dir,
        figure_path=figure_path,
        box_ir=box_ir,
        base_asset_manifest=asset_manifest,
        phase=phase,
        attempt=attempt,
    )
    validation_asset_manifest = _validation_asset_manifest(
        asset_manifest,
        native_backfill_context.get("validation_asset_manifest"),
    )
    validator_script_path, validator_context_path, validator_command = _write_attempt_validator(
        attempt_dir=attempt_dir,
        canvas=canvas,
        asset_manifest=validation_asset_manifest,
        reference_dir=reference_dir,
    )
    if base_svg is not None:
        input_template_path.write_text(base_svg, encoding="utf-8")
    try:
        request: dict[str, Any] = {
            "attempt": attempt,
            "feedback": feedback,
            "box_ir": box_ir,
            "figure_path": figure_path,
            "reference_image_path": reference_image_path,
            "asset_manifest": asset_manifest,
            "runtime_config": runtime_config,
            "prompt_path": prompt_path,
            "request_context_path": request_context_path,
            "output_svg_path": svg_path,
            "output_response_path": response_path,
            "output_rendered_path": rendered_path,
            "validator_script_path": validator_script_path,
            "validator_context_path": validator_context_path,
            "validator_command": validator_command,
            "text_rendering": text_rendering,
        }
        if phase is not None:
            request["phase"] = phase
        if base_svg is not None:
            request["base_svg"] = base_svg
            request["base_svg_path"] = input_template_path
        if template_ir is not None:
            request["template_ir"] = template_ir
        if visual_review_round is not None:
            request["visual_review_round"] = visual_review_round
        if visual_review_total_rounds is not None:
            request["visual_review_total_rounds"] = visual_review_total_rounds
        if visual_review_focus is not None:
            request["visual_review_focus"] = visual_review_focus
        if visual_review_rounds is not None:
            request["visual_review_rounds"] = visual_review_rounds
        if iteration_log_path is not None:
            request["iteration_log_path"] = iteration_log_path
        if iteration_log_jsonl_path is not None:
            request["iteration_log_jsonl_path"] = iteration_log_jsonl_path
        if template_svg_path is not None:
            request["template_svg_path"] = template_svg_path
        if template_rendered_path is not None:
            request["template_rendered_path"] = template_rendered_path
        request["native_backfill_request_path"] = native_backfill_context["request_path"]
        request["native_backfill_tools_dir"] = native_backfill_context["tools_dir"]
        request["native_backfill_assets_dir"] = native_backfill_context["assets_dir"]
        request["native_backfill_asset_href_prefix"] = native_backfill_context["asset_href_prefix"]
        request["native_backfill_candidate_count"] = native_backfill_context["candidate_count"]
        _write_attempt_request_context(
            request_context_path,
            phase=phase or "single",
            attempt=attempt,
            figure_path=figure_path,
            reference_image_path=reference_image_path,
            response_path=response_path,
            svg_path=svg_path,
            rendered_path=rendered_path,
            report_path=report_path,
            prompt_path=prompt_path,
            feedback=feedback,
            runtime_config=runtime_config,
            has_base_svg=base_svg is not None,
            input_template_path=input_template_path if base_svg is not None else None,
            has_template_ir=template_ir is not None,
            has_asset_manifest=asset_manifest is not None,
            visual_review_round=visual_review_round,
            visual_review_total_rounds=visual_review_total_rounds,
            visual_review_focus=visual_review_focus,
            visual_review_rounds=visual_review_rounds,
            iteration_log_path=iteration_log_path,
            iteration_log_jsonl_path=iteration_log_jsonl_path,
            template_svg_path=template_svg_path,
            template_rendered_path=template_rendered_path,
            native_backfill_context=native_backfill_context,
            validator_script_path=validator_script_path,
            validator_context_path=validator_context_path,
            validator_command=validator_command,
            text_rendering=text_rendering,
        )
        raw_response = invoker(**request)
    except Exception as exc:  # pragma: no cover - defensive path for real runtime failures.
        raw_response = ""
        pre_validation_issues.append(
            _issue("invoker_error", "SVG generation invoker raised an exception.", repr(exc))
        )

    raw_text = _coerce_response_text(raw_response)
    if not response_path.exists():
        response_path.write_text(raw_text, encoding="utf-8")
    modification_notes = _extract_modification_notes(raw_text)
    modification_notes_path = response_path.parent / "modification_notes.md"
    if modification_notes is not None:
        modification_notes_path.write_text(modification_notes + "\n", encoding="utf-8")
    svg_text = _extract_svg_text(raw_text)
    if svg_text is None:
        svg_text = ""
        pre_validation_issues.append(
            _issue(
                "missing_svg_output",
                "Model response did not contain pure SVG or a fenced ```svg block.",
            )
        )

    svg_path.write_text(svg_text, encoding="utf-8")
    native_backfill_href_repair = _repair_native_backfill_image_hrefs(
        svg_path,
        native_backfill_context,
        reference_dir=reference_dir,
    )
    if native_backfill_href_repair and native_backfill_href_repair.get("unresolved_count"):
        pre_validation_issues.append(
            _issue(
                "native_backfill_asset_missing",
                "A native backfill image href was selected but the raster asset could not be materialized.",
                native_backfill_href_repair.get("unresolved", []),
            )
        )
    manifest_asset_injection = _inject_manifest_asset_images(svg_path, asset_manifest, phase=phase)
    intermediate_manifest_asset_injections = _inject_manifest_asset_images_for_stage_intermediates(
        attempt_dir,
        asset_manifest,
        phase=phase,
    )
    text_format_normalization = _normalize_text_format(svg_path)
    badge_normalization = _normalize_badge_groups(svg_path)
    report = validate_svg_file(
        svg_path,
        canvas=canvas,
        asset_manifest=validation_asset_manifest,
        rendered_path=rendered_path,
        reference_dir=reference_dir,
    )
    report = _merge_validation_issues(
        report,
        _model_stage_contract_issues(
            svg_path,
            phase,
            text_rendering=text_rendering,
            allow_manifest_images=_phase_allows_manifest_asset_images(phase),
        ),
    )
    report = _merge_validation_issues(
        report,
        _iteration_log_contract_issues(
            phase,
            iteration_log_path=iteration_log_path,
            iteration_log_jsonl_path=iteration_log_jsonl_path,
        ),
    )
    report = _merge_validation_issues(report, pre_validation_issues)
    if manifest_asset_injection is not None:
        report["manifest_asset_injection"] = manifest_asset_injection
    if native_backfill_href_repair is not None:
        report["native_backfill_href_repair"] = native_backfill_href_repair
    if intermediate_manifest_asset_injections:
        report["intermediate_manifest_asset_injections"] = intermediate_manifest_asset_injections
    if text_format_normalization is not None:
        report["text_format_normalization"] = text_format_normalization
    if badge_normalization is not None:
        report["badge_normalization"] = badge_normalization
    if modification_notes is not None:
        report["modification_notes"] = str(modification_notes_path)
    if iteration_log_path is not None and iteration_log_path.exists():
        report["iteration_log"] = str(iteration_log_path)
    if iteration_log_jsonl_path is not None and iteration_log_jsonl_path.exists():
        report["iteration_log_jsonl"] = str(iteration_log_jsonl_path)
    if report["status"] != "ok":
        _ensure_diagnostic_render(rendered_path, canvas)
    _write_json(report_path, report)
    return report


def _reset_loop_owned_outputs(
    *,
    attempts_dir: Path,
    template_iterations_dir: Path,
    native_backfill_assets_dir: Path,
    template_svg: Path,
    template_render: Path,
    final_svg: Path,
    final_render: Path,
    top_level_report: Path,
) -> None:
    for path in (template_svg, template_render, final_svg, final_render, top_level_report):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    if attempts_dir.exists():
        if attempts_dir.is_dir():
            shutil.rmtree(attempts_dir)
        else:
            attempts_dir.unlink()
    if template_iterations_dir.exists():
        if template_iterations_dir.is_dir():
            shutil.rmtree(template_iterations_dir)
        else:
            template_iterations_dir.unlink()
    if native_backfill_assets_dir.exists():
        if native_backfill_assets_dir.is_dir():
            shutil.rmtree(native_backfill_assets_dir)
        else:
            native_backfill_assets_dir.unlink()
    attempts_dir.mkdir(parents=True, exist_ok=True)
    template_iterations_dir.mkdir(parents=True, exist_ok=True)


def _extract_svg_text(raw_response: str) -> str | None:
    fenced = _SVG_FENCE_RE.search(raw_response)
    if fenced:
        candidate = fenced.group(1).strip()
        return candidate or None

    stripped = raw_response.strip()
    if stripped.startswith("<svg") or (stripped.startswith("<?xml") and "<svg" in stripped):
        return stripped
    inline = _INLINE_SVG_RE.search(raw_response)
    if inline:
        return inline.group(1).strip()
    return None


def _extract_modification_notes(raw_response: str) -> str | None:
    fenced = _MODIFICATION_NOTES_FENCE_RE.search(raw_response)
    if not fenced:
        return None
    candidate = fenced.group(1).strip()
    return candidate or None


def _coerce_response_text(raw_response: Any) -> str:
    if isinstance(raw_response, bytes):
        return raw_response.decode("utf-8", errors="replace")
    if raw_response is None:
        return ""
    return str(raw_response)


def _repair_native_backfill_image_hrefs(
    svg_path: Path,
    native_backfill_context: Mapping[str, Any],
    *,
    reference_dir: Path,
) -> dict[str, Any] | None:
    request_path = native_backfill_context.get("request_path")
    if request_path is None:
        return None
    request = _read_json_if_file(Path(request_path))
    candidates = request.get("candidates") if isinstance(request, Mapping) else None
    if not isinstance(candidates, list) or not candidates:
        return None

    try:
        root = etree.fromstring(
            svg_path.read_bytes(),
            parser=etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True),
        )
    except Exception as exc:
        return {"status": "skipped", "reason": f"xml_parse_failed: {type(exc).__name__}: {exc}"}

    allowed_hrefs = set(str(href) for href in native_backfill_context.get("allowed_image_hrefs") or [] if str(href).strip())
    native_hrefs = {
        str(asset.get("svg_href") or "").strip()
        for asset in (native_backfill_context.get("validation_asset_manifest") or {}).get("assets", [])
        if str(asset.get("svg_href") or "").strip()
    }
    candidates_by_key: dict[str, Mapping[str, Any]] = {}
    native_target_by_href: dict[str, tuple[Mapping[str, Any], str]] = {}
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        asset_id = str(candidate.get("asset_id") or "").strip()
        recovered_asset_id = str(candidate.get("recovered_asset_id") or "").strip()
        preserve_href = str(candidate.get("preserve_href") or "").strip()
        nobg_href = str(candidate.get("nobg_href") or "").strip()
        for key in (asset_id, recovered_asset_id, _href_asset_key(preserve_href), _href_asset_key(nobg_href)):
            if key:
                candidates_by_key.setdefault(key, candidate)
        if preserve_href:
            native_target_by_href[preserve_href] = (candidate, "preserve_href")
        if nobg_href:
            native_target_by_href[nobg_href] = (candidate, "nobg_href")

    rewritten: list[dict[str, Any]] = []
    materialized: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    changed = False
    for element in root.iter():
        if _local_name(element.tag) != "image":
            continue
        original_href = _image_element_href(element)
        if not original_href:
            continue
        target: tuple[Mapping[str, Any], str, str] | None = None
        if original_href in native_target_by_href:
            candidate, href_key = native_target_by_href[original_href]
            target = (candidate, href_key, original_href)
        elif original_href in allowed_hrefs:
            continue
        else:
            candidate = candidates_by_key.get(_href_asset_key(original_href))
            if candidate is None:
                continue
            href_key = "nobg_href" if _href_requests_nobg(original_href) else "preserve_href"
            target_href = str(candidate.get(href_key) or "").strip()
            if not target_href and href_key == "nobg_href":
                href_key = "preserve_href"
                target_href = str(candidate.get(href_key) or "").strip()
            if not target_href:
                continue
            target = (candidate, href_key, target_href)
            _set_image_element_href(element, target_href)
            rewritten.append(
                {
                    "from": original_href,
                    "to": target_href,
                    "asset_id": str(candidate.get("asset_id") or ""),
                }
            )
            changed = True

        if target is None:
            continue
        candidate, href_key, target_href = target
        materialization = _materialize_native_backfill_href(
            candidate,
            request=request,
            original_href=original_href,
            target_href=target_href,
            href_key=href_key,
            svg_path=svg_path,
            reference_dir=reference_dir,
        )
        if materialization["status"] == "ok":
            if materialization.get("created"):
                materialized.append(materialization)
        else:
            unresolved.append(materialization)

    if changed:
        svg_path.write_bytes(etree.tostring(root, encoding="utf-8", xml_declaration=False))
    if not rewritten and not materialized and not unresolved:
        return None
    return {
        "status": "failed" if unresolved else "ok",
        "rewritten_count": len(rewritten),
        "materialized_count": len(materialized),
        "unresolved_count": len(unresolved),
        "native_allowed_href_count": len(native_hrefs),
        "rewritten": rewritten[:20],
        "materialized": materialized[:20],
        "unresolved": unresolved[:20],
    }


def _image_element_href(element: etree._Element) -> str:
    return str(element.get("href") or element.get("{http://www.w3.org/1999/xlink}href") or "").strip()


def _set_image_element_href(element: etree._Element, href: str) -> None:
    element.set("href", href)
    if element.get("{http://www.w3.org/1999/xlink}href") is not None:
        element.set("{http://www.w3.org/1999/xlink}href", href)


def _href_asset_key(href: str) -> str:
    filename = Path(str(href).split("?", 1)[0].split("#", 1)[0]).name
    if not filename:
        return ""
    stem = filename.rsplit(".", 1)[0]
    if stem.endswith("_nobg"):
        stem = stem[:-5]
    return stem.strip().lower()


def _href_requests_nobg(href: str) -> bool:
    return Path(str(href).split("?", 1)[0].split("#", 1)[0]).stem.endswith("_nobg")


def _materialize_native_backfill_href(
    candidate: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    original_href: str,
    target_href: str,
    href_key: str,
    svg_path: Path,
    reference_dir: Path,
) -> dict[str, Any]:
    target_path = reference_dir / target_href
    if target_path.is_file():
        return {
            "status": "ok",
            "created": False,
            "href": target_href,
            "asset_id": str(candidate.get("asset_id") or ""),
        }

    source_path = _resolve_existing_svg_href(original_href, svg_path=svg_path, reference_dir=reference_dir)
    if source_path is not None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        return {
            "status": "ok",
            "created": True,
            "method": "copy_existing_href_source",
            "source": str(source_path),
            "output": str(target_path),
            "href": target_href,
            "href_key": href_key,
            "asset_id": str(candidate.get("asset_id") or ""),
        }

    bbox = _prompt_bbox(candidate.get("bbox"))
    source_image = Path(str(request.get("source_image") or ""))
    if bbox is not None and source_image.is_file():
        _crop_exact_for_backfill(source_image, bbox, target_path)
        return {
            "status": "ok",
            "created": True,
            "method": "crop_request_source_image",
            "source": str(source_image),
            "output": str(target_path),
            "href": target_href,
            "href_key": href_key,
            "asset_id": str(candidate.get("asset_id") or ""),
        }

    return {
        "status": "failed",
        "reason": "source_image_missing_or_invalid_bbox",
        "from": original_href,
        "href": target_href,
        "href_key": href_key,
        "asset_id": str(candidate.get("asset_id") or ""),
        "source_image": str(source_image),
        "bbox": candidate.get("bbox"),
    }


def _resolve_existing_svg_href(href: str, *, svg_path: Path, reference_dir: Path) -> Path | None:
    raw = str(href).strip()
    lowered = raw.lower()
    if not raw or lowered.startswith(("data:", "http://", "https://", "file:")):
        return None
    candidate_path = Path(raw)
    if candidate_path.is_absolute():
        return candidate_path if candidate_path.is_file() else None
    for base in (svg_path.parent, reference_dir):
        resolved = (base / raw).resolve()
        if resolved.is_file():
            return resolved
    return None


def _merge_validation_issues(
    report: Mapping[str, Any],
    pre_validation_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = dict(report)
    if pre_validation_issues:
        payload["issues"] = [*pre_validation_issues, *list(payload.get("issues", []))]
        payload["status"] = "failed"
    return payload


def _inject_manifest_asset_images(
    svg_path: Path,
    asset_manifest: Mapping[str, Any] | None,
    *,
    phase: str | None,
) -> dict[str, Any] | None:
    if not _phase_allows_manifest_asset_images(phase) or not isinstance(asset_manifest, Mapping):
        return None
    assets = asset_manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        return None
    try:
        root = etree.fromstring(svg_path.read_bytes(), parser=etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))
    except Exception as exc:
        return {"status": "skipped", "reason": f"xml_parse_failed: {type(exc).__name__}: {exc}"}

    existing_hrefs = _existing_image_hrefs(root)
    image_tag = _svg_tag(root, "image")
    group = etree.Element(_svg_tag(root, "g"))
    group.set("id", "pb-manifest-raster-assets")
    group.set("data-pb-role", "image")
    group.set("data-pb-editable", "false")
    group.set("data-pb-source", "asset_manifest")

    removed_placeholders = _remove_manifest_placeholder_rects(root, asset_manifest)
    removed_underlays = _remove_manifest_image_underlay_rects(root, asset_manifest)
    inserted = 0
    skipped: list[dict[str, Any]] = []
    for index, asset in enumerate(iter_manifest_image_items(asset_manifest), start=1):
        href = str(asset.get("svg_href") or "").strip()
        bbox = _manifest_asset_bbox(asset.get("bbox"))
        if not href:
            skipped.append({"index": index, "reason": "missing_svg_href"})
            continue
        if href in existing_hrefs:
            skipped.append({"index": index, "href": href, "reason": "already_present"})
            continue
        if bbox is None:
            skipped.append({"index": index, "href": href, "reason": "invalid_bbox"})
            continue
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0:
            skipped.append({"index": index, "href": href, "reason": "empty_bbox"})
            continue

        image = etree.SubElement(group, image_tag)
        image.set("id", f"pb-raster-asset-{index:03d}")
        image.set("href", href)
        image.set("x", _format_svg_number(x1))
        image.set("y", _format_svg_number(y1))
        image.set("width", _format_svg_number(width))
        image.set("height", _format_svg_number(height))
        image.set("preserveAspectRatio", "none")
        image.set("data-pb-role", "image")
        image.set("data-pb-editable", "false")
        image.set("data-pb-source", "asset_manifest")
        image.set("data-pb-render-policy", str(asset.get("render_policy") or "raster_png"))
        image.set("data-pb-background-policy", str(asset.get("background_policy") or ""))
        parent_asset_id = asset.get("parent_asset_id")
        component_id = asset.get("component_id")
        if isinstance(parent_asset_id, str) and parent_asset_id:
            image.set("data-pb-parent-asset-id", parent_asset_id)
        if isinstance(component_id, str) and component_id:
            image.set("data-pb-component-id", component_id)
        inserted += 1

    if inserted <= 0:
        if removed_placeholders > 0 or removed_underlays > 0:
            svg_path.write_bytes(etree.tostring(root, encoding="utf-8", xml_declaration=False))
            return {
                "status": "ok",
                "inserted_count": inserted,
                "removed_placeholder_count": removed_placeholders,
                "removed_underlay_count": removed_underlays,
                "skipped_count": len(skipped),
                "skipped": skipped[:20],
            }
        return {"status": "skipped", "reason": "no_insertable_assets", "skipped": skipped}

    root.append(group)
    svg_path.write_bytes(etree.tostring(root, encoding="utf-8", xml_declaration=False))
    return {
        "status": "ok",
        "inserted_count": inserted,
        "removed_placeholder_count": removed_placeholders,
        "removed_underlay_count": removed_underlays,
        "skipped_count": len(skipped),
        "skipped": skipped[:20],
    }


def _inject_manifest_asset_images_for_stage_intermediates(
    attempt_dir: Path,
    asset_manifest: Mapping[str, Any] | None,
    *,
    phase: str | None,
) -> dict[str, Any]:
    if str(phase or "") != _CODEX_MERGED_STAGES_PHASE:
        return {}
    results: dict[str, Any] = {}
    for index in range(4):
        candidate = attempt_dir / f"semantic_{index}.svg"
        if not candidate.exists():
            continue
        injection = _inject_manifest_asset_images(candidate, asset_manifest, phase=phase)
        if injection is not None:
            results[candidate.name] = injection
    return results


_BADGE_TEXT_RE = re.compile(r"^[A-Za-z0-9]{1,2}$")
_TEXT_FORMAT_NORMALIZATION_BASE_WIDTH = 3840.0
_TEXT_FORMAT_NORMALIZATION_MIN_WIDTH = 3000.0


def _normalize_text_format(svg_path: Path) -> dict[str, Any] | None:
    try:
        root = etree.fromstring(svg_path.read_bytes(), parser=etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))
    except Exception as exc:
        return {"status": "skipped", "reason": f"xml_parse_failed: {type(exc).__name__}: {exc}"}

    canvas = _svg_canvas_size(root)
    if canvas is None:
        return None
    canvas_width, canvas_height = canvas
    if canvas_width < 1000 or canvas_height < 700:
        return None
    if canvas_width < _TEXT_FORMAT_NORMALIZATION_MIN_WIDTH:
        return None

    text_elements = [
        element
        for element in root.iter()
        if _local_name(element.tag) == "text" and "".join(element.itertext()).strip()
    ]
    if len(text_elements) < 40:
        return None

    scale = canvas_width / _TEXT_FORMAT_NORMALIZATION_BASE_WIDTH
    changes: list[dict[str, Any]] = []
    for text in text_elements:
        label = "".join(text.itertext()).strip()
        if _BADGE_TEXT_RE.fullmatch(label):
            continue
        x = _float_attr(text, "x")
        y = _float_attr(text, "y")
        old_size = _float_attr(text, "font-size")
        if x is None or y is None or old_size is None:
            continue
        bold = str(text.get("font-weight") or "").strip().lower() in {"700", "bold"}
        target = _target_text_font_size(
            x=x,
            y=y,
            old_size=old_size,
            bold=bold,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            scale=scale,
        )
        if target is None:
            continue
        _set_font_size(text, target, changes, reason="uniform_text_format")

    if not changes:
        return None
    svg_path.write_bytes(etree.tostring(root, encoding="utf-8", xml_declaration=False))
    return {
        "status": "ok",
        "normalized_count": len(changes),
        "rule": "uniform_font_sizes_by_visual_region",
        "changes": changes[:80],
        "truncated": len(changes) > 80,
    }


def _svg_canvas_size(root: etree._Element) -> tuple[float, float] | None:
    view_box = str(root.get("viewBox") or root.get("viewbox") or "").strip()
    if view_box:
        values = [item for item in re.split(r"[\s,]+", view_box) if item]
        if len(values) == 4:
            try:
                return (float(values[2]), float(values[3]))
            except ValueError:
                pass
    width = _float_attr(root, "width")
    height = _float_attr(root, "height")
    if width is None or height is None:
        return None
    return (width, height)


def _target_text_font_size(
    *,
    x: float,
    y: float,
    old_size: float,
    bold: bool,
    canvas_width: float,
    canvas_height: float,
    scale: float,
) -> float | None:
    normalized_x = x / canvas_width
    normalized_y = y / canvas_height
    if normalized_y < 0.08 and old_size >= 40 * scale:
        return min(old_size, 44 * scale)
    if 0.08 <= normalized_y <= 0.58 and (
        0.31 <= normalized_x <= 0.38 or 0.63 <= normalized_x <= 0.71
    ):
        return min(old_size, (28 if bold else 27) * scale)
    if 0.44 <= normalized_y <= 0.60 and normalized_x <= 0.24 and old_size >= 25 * scale:
        return min(old_size, 25 * scale)
    if 0.64 <= normalized_y <= 0.95 and 0.22 <= normalized_x <= 0.76:
        if bold and old_size >= 34 * scale:
            return min(old_size, 33 * scale)
        if not bold and old_size >= 28 * scale:
            return min(old_size, 28 * scale)
    if 0.58 <= normalized_y <= 0.95 and normalized_x >= 0.80:
        return min(old_size, (32 if bold else 27) * scale)
    return None


def _set_font_size(element: etree._Element, size: float, changes: list[dict[str, Any]], *, reason: str) -> None:
    old = element.get("font-size")
    new = _format_svg_number(size)
    if old == new:
        return
    element.set("font-size", new)
    changes.append(
        {
            "text": "".join(element.itertext()).strip()[:100],
            "old_font_size": old,
            "new_font_size": new,
            "reason": reason,
        }
    )


def _normalize_badge_groups(svg_path: Path) -> dict[str, Any] | None:
    try:
        root = etree.fromstring(svg_path.read_bytes(), parser=etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))
    except Exception as exc:
        return {"status": "skipped", "reason": f"xml_parse_failed: {type(exc).__name__}: {exc}"}

    candidates: list[tuple[float, etree._Element, etree._Element, dict[str, float]]] = []
    for text in root.iter():
        if _local_name(text.tag) != "text" or _is_inside_badge_group(text):
            continue
        label = "".join(text.itertext()).strip()
        if not _BADGE_TEXT_RE.fullmatch(label):
            continue
        text_x = _float_attr(text, "x")
        text_y = _float_attr(text, "y")
        font_size = _float_attr(text, "font-size")
        if text_x is None or text_y is None or font_size is None:
            continue
        text_parent = text.getparent()
        if text_parent is None:
            continue
        for shape in text_parent:
            shape_name = _local_name(shape.tag)
            if shape_name not in {"circle", "ellipse"} or _is_inside_badge_group(shape):
                continue
            geometry = _badge_shape_geometry(shape)
            if geometry is None:
                continue
            estimated_center = _estimated_short_text_center(label, text_x, text_y, font_size)
            distance = ((estimated_center[0] - geometry["cx"]) ** 2 + (estimated_center[1] - geometry["cy"]) ** 2) ** 0.5
            if distance > max(geometry["radius"] * 0.65, 18.0):
                continue
            candidates.append((distance, shape, text, geometry))

    used_shapes: set[int] = set()
    used_texts: set[int] = set()
    normalized = 0
    skipped = 0
    for _distance, shape, text, geometry in sorted(candidates, key=lambda item: item[0]):
        if id(shape) in used_shapes or id(text) in used_texts:
            skipped += 1
            continue
        if shape.getparent() is None or text.getparent() is None or shape.getparent() is not text.getparent():
            skipped += 1
            continue
        _wrap_badge_pair(shape, text, geometry, normalized + 1)
        used_shapes.add(id(shape))
        used_texts.add(id(text))
        normalized += 1

    if normalized <= 0 and skipped <= 0:
        return None
    if normalized > 0:
        svg_path.write_bytes(etree.tostring(root, encoding="utf-8", xml_declaration=False))
    return {
        "status": "ok",
        "normalized_count": normalized,
        "skipped_count": skipped,
        "rule": "circle_or_ellipse_plus_1_2_char_text",
    }


def _is_inside_badge_group(element: etree._Element) -> bool:
    parent = element.getparent()
    while parent is not None:
        if _local_name(parent.tag) == "g" and str(parent.get("data-pb-role") or "") == "badge":
            return True
        parent = parent.getparent()
    return False


def _badge_shape_geometry(shape: etree._Element) -> dict[str, float] | None:
    if _local_name(shape.tag) == "circle":
        cx = _float_attr(shape, "cx")
        cy = _float_attr(shape, "cy")
        radius = _float_attr(shape, "r")
    else:
        cx = _float_attr(shape, "cx")
        cy = _float_attr(shape, "cy")
        rx = _float_attr(shape, "rx")
        ry = _float_attr(shape, "ry")
        radius = min(rx, ry) if rx is not None and ry is not None else None
    if cx is None or cy is None or radius is None or radius <= 0:
        return None
    return {"cx": cx, "cy": cy, "radius": radius}


def _estimated_short_text_center(label: str, x: float, y: float, font_size: float) -> tuple[float, float]:
    return (x + 0.33 * font_size * len(label), y - 0.35 * font_size)


def _wrap_badge_pair(shape: etree._Element, text: etree._Element, geometry: Mapping[str, float], index: int) -> None:
    parent = shape.getparent()
    if parent is None:
        return
    insert_at = min(parent.index(shape), parent.index(text))
    group = etree.Element(_svg_tag(parent, "g"))
    group.set("id", _next_sibling_id(parent, f"pb-badge-{index:03d}"))
    group.set("data-pb-role", "badge")
    group.set("data-pb-editable", "true")
    group.set("data-pb-badge-kind", "number" if "".join(text.itertext()).strip().isdigit() else "letter")

    parent.remove(shape)
    parent.remove(text)
    group.append(shape)
    group.append(text)
    parent.insert(insert_at, group)

    cx = _format_svg_number(float(geometry["cx"]))
    cy = _format_svg_number(_badge_text_baseline_y(text, float(geometry["cy"])))
    text.set("x", cx)
    text.set("y", cy)
    text.set("text-anchor", "middle")
    text.attrib.pop("dominant-baseline", None)
    text.attrib.pop("alignment-baseline", None)
    text.set("data-pb-role", "label")
    text.set("data-pb-editable", "true")


def _badge_text_baseline_y(text: etree._Element, center_y: float) -> float:
    font_size = _float_attr(text, "font-size") or 0.0
    label = "".join(text.itertext()).strip()
    if font_size <= 0:
        return center_y
    offset_ratio = 0.42 if label.isalpha() else 0.44
    return center_y + font_size * offset_ratio


def _next_sibling_id(parent: etree._Element, preferred: str) -> str:
    existing = {str(child.get("id")) for child in parent.iter() if child.get("id")}
    if preferred not in existing:
        return preferred
    suffix = 2
    while f"{preferred}-{suffix}" in existing:
        suffix += 1
    return f"{preferred}-{suffix}"


def _float_attr(element: etree._Element, name: str) -> float | None:
    raw = element.get(name)
    if raw is None:
        return None
    try:
        return float(str(raw).strip().replace("px", ""))
    except ValueError:
        return None


def _phase_allows_manifest_asset_images(phase: str | None) -> bool:
    phase_name = str(phase or "")
    return phase_name in {"template", "ir_refine", _CODEX_MERGED_STAGES_PHASE} or phase_name.startswith("visual_review_")


def _remove_manifest_placeholder_rects(root: etree._Element, asset_manifest: Mapping[str, Any]) -> int:
    placeholder_bboxes = _manifest_placeholder_bboxes(asset_manifest)
    if not placeholder_bboxes:
        return 0

    removed = 0
    for element in list(root.iter()):
        if _local_name(element.tag) != "rect" or not _is_draft_placeholder_fill(element.get("fill")):
            continue
        bbox = _rect_bbox(element)
        if bbox is None:
            continue
        if not any(_bbox_close(bbox, placeholder_bbox, tolerance=2.5) for placeholder_bbox in placeholder_bboxes):
            continue
        parent = element.getparent()
        if parent is None:
            continue
        parent.remove(element)
        removed += 1
    return removed


def _remove_manifest_image_underlay_rects(root: etree._Element, asset_manifest: Mapping[str, Any]) -> int:
    target_bboxes = _manifest_image_underlay_bboxes(root, asset_manifest)
    if not target_bboxes:
        return 0

    removed = 0
    for element in list(root.iter()):
        if _local_name(element.tag) != "rect":
            continue
        if not _is_neutral_image_underlay_fill(_svg_attr_or_style(element, "fill")):
            continue
        if _has_visible_stroke(element):
            continue
        bbox = _rect_bbox(element)
        if bbox is None:
            continue
        if not any(_bbox_close(bbox, target_bbox, tolerance=3.5) for target_bbox in target_bboxes):
            continue
        parent = element.getparent()
        if parent is None:
            continue
        parent.remove(element)
        removed += 1
    return removed


def _manifest_image_underlay_bboxes(
    root: etree._Element,
    asset_manifest: Mapping[str, Any],
) -> list[tuple[float, float, float, float]]:
    manifest_hrefs: set[str] = set()
    bboxes: list[tuple[float, float, float, float]] = []
    for asset in iter_manifest_image_items(asset_manifest):
        href = str(asset.get("svg_href") or "").strip()
        if href:
            manifest_hrefs.add(href)
        bbox = _manifest_asset_bbox(asset.get("bbox"))
        if bbox is not None:
            bboxes.append(bbox)

    for element in root.iter():
        if _local_name(element.tag) != "image":
            continue
        href = (element.get("href") or element.get("{http://www.w3.org/1999/xlink}href") or "").strip()
        if href not in manifest_hrefs:
            continue
        bbox = _image_bbox(element)
        if bbox is not None:
            bboxes.append(bbox)
    return bboxes


def _manifest_placeholder_bboxes(asset_manifest: Mapping[str, Any]) -> list[tuple[float, float, float, float]]:
    assets = asset_manifest.get("assets")
    if not isinstance(assets, list):
        return []

    bboxes: list[tuple[float, float, float, float]] = []
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        bbox = _manifest_asset_bbox(asset.get("bbox"))
        if bbox is not None:
            bboxes.append(bbox)
        components = asset.get("insertable_components")
        if not isinstance(components, list):
            continue
        for component in components:
            if not isinstance(component, Mapping):
                continue
            component_bbox = _manifest_asset_bbox(component.get("bbox"))
            if component_bbox is not None:
                bboxes.append(component_bbox)
    return bboxes


def _rect_bbox(element: etree._Element) -> tuple[float, float, float, float] | None:
    return _element_xywh_bbox(element)


def _image_bbox(element: etree._Element) -> tuple[float, float, float, float] | None:
    return _element_xywh_bbox(element)


def _element_xywh_bbox(element: etree._Element) -> tuple[float, float, float, float] | None:
    try:
        x = float(element.get("x") or 0.0)
        y = float(element.get("y") or 0.0)
        width = float(element.get("width") or 0.0)
        height = float(element.get("height") or 0.0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, x + width, y + height


def _bbox_close(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    *,
    tolerance: float,
) -> bool:
    return all(abs(a[index] - b[index]) <= tolerance for index in range(4))


def _is_draft_placeholder_fill(raw_fill: str | None) -> bool:
    fill = str(raw_fill or "").strip().lower()
    if not fill:
        return False
    if fill in {"gray", "grey", "darkgray", "darkgrey", "lightgray", "lightgrey"}:
        return True
    if not fill.startswith("#"):
        return False
    hex_value = fill[1:]
    if len(hex_value) == 3:
        hex_value = "".join(char * 2 for char in hex_value)
    if len(hex_value) != 6:
        return False
    try:
        red = int(hex_value[0:2], 16)
        green = int(hex_value[2:4], 16)
        blue = int(hex_value[4:6], 16)
    except ValueError:
        return False
    channel_span = max(red, green, blue) - min(red, green, blue)
    luminance = (red + green + blue) / 3.0
    return channel_span <= 8 and 90 <= luminance <= 190


def _is_neutral_image_underlay_fill(raw_fill: str | None) -> bool:
    fill = str(raw_fill or "").strip().lower()
    if not fill or fill == "none":
        return False
    if fill in {"gray", "grey", "darkgray", "darkgrey", "lightgray", "lightgrey"}:
        return True
    if not fill.startswith("#"):
        return False
    hex_value = fill[1:]
    if len(hex_value) == 3:
        hex_value = "".join(char * 2 for char in hex_value)
    if len(hex_value) != 6:
        return False
    try:
        red = int(hex_value[0:2], 16)
        green = int(hex_value[2:4], 16)
        blue = int(hex_value[4:6], 16)
    except ValueError:
        return False
    channel_span = max(red, green, blue) - min(red, green, blue)
    luminance = (red + green + blue) / 3.0
    return channel_span <= 18 and 60 <= luminance <= 248


def _svg_attr_or_style(element: etree._Element, name: str) -> str | None:
    value = element.get(name)
    if value:
        return value
    style = element.get("style")
    if not style:
        return None
    for item in style.split(";"):
        if ":" not in item:
            continue
        key, raw_value = item.split(":", 1)
        if key.strip().lower() == name:
            return raw_value.strip()
    return None


def _has_visible_stroke(element: etree._Element) -> bool:
    stroke = str(_svg_attr_or_style(element, "stroke") or "").strip().lower()
    if not stroke or stroke == "none" or stroke == "transparent":
        return False
    opacity = str(_svg_attr_or_style(element, "stroke-opacity") or "").strip()
    if opacity in {"0", "0.0", ".0"}:
        return False
    return True


def _existing_image_hrefs(root: etree._Element) -> set[str]:
    hrefs: set[str] = set()
    for element in root.iter():
        if _local_name(element.tag) != "image":
            continue
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href") or ""
        href = href.strip()
        if href:
            hrefs.add(href)
    return hrefs


def _svg_tag(root: etree._Element, local_name: str) -> str:
    tag = root.tag
    if isinstance(tag, str) and tag.startswith("{"):
        namespace = tag.split("}", 1)[0][1:]
        return f"{{{namespace}}}{local_name}"
    return local_name


def _manifest_asset_bbox(raw_bbox: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(value) for value in raw_bbox)
    except (TypeError, ValueError):
        return None
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _format_svg_number(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _model_stage_contract_issues(
    svg_path: Path,
    phase: str | None,
    *,
    text_rendering: str,
    allow_manifest_images: bool = False,
) -> list[dict[str, Any]]:
    phase_name = str(phase or "")
    if phase_name not in {"template", "ir_refine", _CODEX_MERGED_STAGES_PHASE} and not phase_name.startswith("visual_review_"):
        return []
    try:
        root = etree.fromstring(svg_path.read_bytes(), parser=etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))
    except Exception:
        return []

    issues: list[dict[str, Any]] = []
    for element in root.iter():
        local_name = _local_name(element.tag)
        if local_name == "image" and not allow_manifest_images:
            issues.append(
                _issue(
                    "model_asset_fill_not_allowed",
                    "Draft-stage SVG model output must use editable SVG primitives instead of direct <image> fills.",
                )
            )
        if element.get("data-placeholder-kind") or element.get("data-asset-id") or element.get("data-asset-placeholder"):
            issues.append(
                _issue(
                    "model_asset_placeholder_not_allowed",
                    "Asset placeholders and AFxx data attributes are retired from the main SVG generation path.",
                )
            )
        if local_name == "text" and "".join(element.itertext()).strip():
            issues.extend(_model_text_attribute_issues(element))
    return issues


def _iteration_log_contract_issues(
    phase: str | None,
    *,
    iteration_log_path: Path | None,
    iteration_log_jsonl_path: Path | None,
) -> list[dict[str, Any]]:
    if str(phase or "") != _CODEX_MERGED_STAGES_PHASE:
        return []
    issues: list[dict[str, Any]] = []
    if iteration_log_path is None or not iteration_log_path.exists() or iteration_log_path.stat().st_size <= 0:
        issues.append(
            _issue(
                "missing_iteration_log",
                "Merged Codex stage must write a non-empty human-readable iteration_log.md in the attempt directory.",
            )
        )
    if iteration_log_jsonl_path is None or not iteration_log_jsonl_path.exists() or iteration_log_jsonl_path.stat().st_size <= 0:
        issues.append(
            _issue(
                "missing_iteration_log_jsonl",
                "Merged Codex stage must write a non-empty machine-readable iteration_log.jsonl in the attempt directory.",
            )
        )
    return issues


def _model_text_attribute_issues(element: etree._Element) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    text_excerpt = "".join(element.itertext()).strip()[:80]
    role = str(element.get("data-pb-role") or "").strip()
    if role not in {"label", "formula", "title", "legend", "axis"}:
        issues.append(
            _issue(
                "model_text_missing_role",
                "Editable text must set data-pb-role to label, formula, title, legend, or axis.",
                {"text_excerpt": text_excerpt},
            )
        )
    if str(element.get("data-pb-editable") or "").strip().lower() != "true":
        issues.append(
            _issue(
                "model_text_not_marked_editable",
                "Visible text must set data-pb-editable=\"true\".",
                {"text_excerpt": text_excerpt},
            )
        )
    source = str(element.get("data-pb-text-source") or "").strip()
    if source not in {"ocr", "visual_inferred", "model_inferred"}:
        issues.append(
            _issue(
                "model_text_missing_source",
                "Visible text must set data-pb-text-source to ocr, visual_inferred, or model_inferred.",
                {"text_excerpt": text_excerpt},
            )
        )
    orientation = str(element.get("data-pb-orientation") or "").strip()
    if orientation not in {"horizontal", "vertical-rl"}:
        issues.append(
            _issue(
                "model_text_missing_orientation",
                "Visible text must set data-pb-orientation to horizontal or vertical-rl.",
                {"text_excerpt": text_excerpt},
            )
        )
    if orientation == "vertical-rl":
        transform = str(element.get("transform") or "")
        writing_mode = str(element.get("writing-mode") or element.get("style") or "")
        if "rotate(" not in transform and "writing-mode" not in writing_mode:
            issues.append(
                _issue(
                    "vertical_text_missing_rotation",
                    "Vertical text should use transform=\"rotate(...)\" or an explicit writing-mode.",
                    {"text_excerpt": text_excerpt},
                )
            )
    if not str(element.get("font-size") or "").strip():
        issues.append(
            _issue(
                "model_text_missing_font_size",
                "Visible text must set font-size explicitly for PPT-stable conversion.",
                {"text_excerpt": text_excerpt},
            )
        )
    return issues


def _ensure_diagnostic_render(rendered_path: Path, canvas: Any) -> None:
    if rendered_path.exists():
        return

    width, height = _diagnostic_canvas_size(canvas)
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (255, 244, 128))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(0, 0, 0), width=max(1, min(width, height) // 40))
    draw.line((0, 0, width - 1, height - 1), fill=(180, 0, 0), width=max(1, min(width, height) // 20))
    draw.line((0, height - 1, width - 1, 0), fill=(180, 0, 0), width=max(1, min(width, height) // 20))
    draw.text((8, 8), "DIAGNOSTIC\nSVG INVALID", fill=(0, 0, 0))
    image.save(rendered_path)


def _diagnostic_canvas_size(canvas: Any) -> tuple[int, int]:
    if isinstance(canvas, Mapping):
        raw_width = canvas.get("width")
        raw_height = canvas.get("height")
    else:
        try:
            raw_width, raw_height = canvas
        except (TypeError, ValueError):
            return 1, 1

    try:
        width = int(round(float(raw_width)))
        height = int(round(float(raw_height)))
    except (TypeError, ValueError):
        return 1, 1
    return max(1, width), max(1, height)


def _local_name(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def _attempt_report(
    phase: str,
    attempt: int,
    report: Mapping[str, Any],
    report_path: Path,
    svg_path: Path,
    rendered_path: Path,
    response_path: Path,
) -> dict[str, Any]:
    payload = {
        "phase": phase,
        "attempt": attempt,
        "status": report["status"],
        "issues": report.get("issues", []),
        "validation_report": str(report_path),
        "semantic_svg": str(svg_path),
        "rendered_png": str(rendered_path),
        "model_response": str(response_path),
    }
    modification_notes = report.get("modification_notes")
    if modification_notes:
        payload["modification_notes"] = str(modification_notes)
    return payload


def _top_level_report(
    report: Mapping[str, Any],
    attempt: int,
    final_render: Path | None,
    *,
    phase: str | None = None,
) -> dict[str, Any]:
    payload = dict(report)
    payload["attempt"] = attempt
    if phase is not None:
        payload["phase"] = phase
    if final_render is not None:
        payload["rendered_path"] = str(final_render)
    return payload


def _issue(code: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    issue: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        issue["detail"] = detail
    return issue


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value


def _redact_sensitive_context(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lower_key = key_text.lower()
            if (
                "api_key" in lower_key
                or "apikey" in lower_key
                or "token" in lower_key
                or "secret" in lower_key
                or lower_key == "authorization"
            ):
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = _redact_sensitive_context(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_context(item) for item in value]
    return value
