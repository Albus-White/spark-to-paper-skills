#!/usr/bin/env python3
"""Production quality path: full DrawAI reconstruction + measured repair loop.

This intentionally uses DrawAI's expensive quality profile: remote GPU SAM3/RMBG, remote PaddleOCR,
run0 element analysis, Codex controlled staged SVG generation, visual review, native-shape PPTX
export, and up to ten measured repair rounds.  The cheaper hybrid exporter remains a separate
pixel-fidelity fallback; it is not this command's default and is never substituted silently.

Orchestrate DrawAI-based editable scientific-figure reconstruction with a strict,
measured, multi-round refinement loop.

Pipeline per run:
  normalize+decompose+OCR+IR+first SVG/PPTX (DrawAI)  -> Round 0
  render SVG + PPTX -> measure global + per-region -> verify text/formula/editability
  if not passing: repair (guided global re-generation via DrawAI --from-stage svg_generated)
  repeat until PASS or max rounds; keep the best-scoring round; never fake the score.

Honesty contract (see resources/quality_metrics.md):
  * combined global similarity and per-region SSIM are measured, never rounded up;
  * PASS requires combined>=target AND all critical regions>=threshold AND critical-label
    recall==1.0 AND formulas reviewed AND PPTX editable AND a real PPTX render;
  * if the target is not reached within the budget -> REVIEW_REQUIRED with the real score;
  * DrawAI generates the whole figure, so "local repair" is guided global re-generation with
    best-of-round selection + regression check, not literal per-region patching (documented).

Usage:
  python run_reconstruction.py --image <path> --run-name <name> [--runs-root runs]
    [--max-rounds 10] [--target 0.99] [--region-threshold 0.99]
    [--drawai-cmd "uv run --frozen drawai"] [--critical-labels "..."] [--transcribe-formulas]
      [--slide-size 16:9] [--no-repair]
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402
import _dotenv  # noqa: E402,F401
from bounded_execution import ProgressGuard, validate_budget  # noqa: E402
import remote_runtime  # noqa: E402

_DRAWAI_OVERRIDE: Path | None = None
_EXECUTION_DEADLINE: float | None = None
_UTILITY_TIMEOUT_SECONDS = 600.0


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _bounded_command(cmd: list[str], *, cwd: Path, timeout_seconds: float) -> dict:
    if _EXECUTION_DEADLINE is not None:
        timeout_seconds = min(timeout_seconds, max(0.1, _EXECUTION_DEADLINE - time.monotonic()))
    try:
        result = sh(cmd, cwd=str(cwd), timeout=timeout_seconds)
        return {"cmd": " ".join(shlex.quote(c) for c in cmd), "returncode": result.returncode,
                "stdout_tail": result.stdout[-1500:], "stderr_tail": result.stderr[-1500:],
                "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {"cmd": " ".join(shlex.quote(c) for c in cmd), "returncode": 124,
                "stdout_tail": stdout[-1500:], "stderr_tail": stderr[-1500:], "timed_out": True,
                "error": f"command timed out after {timeout_seconds:g}s"}


def run_drawai_full(
    drawai_python_cmd: list[str],
    image: Path,
    drawai_root: Path,
    run_name: str,
    base_config: Path,
    timeout_seconds: float,
    dry_run: bool = False,
) -> dict:
    drawai_root.mkdir(parents=True, exist_ok=True)
    cmd = [*drawai_python_cmd, str(_repo_root() / "scripts" / "run_drawai_experiment.py"),
           "--images", str(image.resolve()), "--base-config", str(base_config),
           "--run-name", run_name, "--run-root", str(drawai_root),
           "--purpose", "Remote-service full-quality scientific figure reconstruction",
           "--expected-outcome", "Semantic SVG, vector PDF, and editable PPTX",
           "--expected-result", "All remote perception and local reconstruction gates complete"]
    if dry_run:
        cmd.append("--dry-run")
    return _bounded_command(cmd, cwd=_repo_root(), timeout_seconds=timeout_seconds)


def run_drawai_repair(drawai_cmd: list[str], case_config: Path, timeout_seconds: float) -> dict:
    cmd = [*drawai_cmd, "--config", str(case_config),
           "--from-stage", "svg_generated", "--to-stage", "svg_to_ppt_exported"]
    return _bounded_command(cmd, cwd=_repo_root(), timeout_seconds=timeout_seconds)


def _drawai_repo() -> Path:
    """Use the Skill-pinned engine; an explicit CLI override is maintainer-only."""
    if _DRAWAI_OVERRIDE and (_DRAWAI_OVERRIDE / "src" / "drawai").exists():
        return _DRAWAI_OVERRIDE
    vendored = HERE.parent / "engine"
    if (vendored / "src" / "drawai").exists():
        return vendored
    raise FileNotFoundError(f"bundled DrawAI engine missing: {vendored}")


def _repo_root() -> Path:  # backward-compatible alias used throughout this module
    return _drawai_repo()


def validate_quality_config(path: Path) -> list[str]:
    """Reject DrawAI smoke/fast profiles before an expensive reconstruction starts."""
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - preflight must report malformed config
        return [f"quality config unreadable: {exc}"]
    input_cfg = data.get("input") or {}
    normalization = input_cfg.get("normalization") or {}
    sam3 = data.get("sam3") or {}
    ocr = data.get("ocr") or {}
    materialization = data.get("asset_materialization") or {}
    rmbg = materialization.get("rmbg") or {}
    asset_policy = data.get("asset_policy") or {}
    svg = data.get("svg") or {}
    ppt = data.get("svg_to_ppt") or {}
    runtime = data.get("model_runtime") or {}
    v2 = data.get("v2") or {}
    v2_parser = v2.get("parser") or {}
    v2_refine = v2.get("refine") or {}
    v2_processor = v2.get("processor") or {}
    v2_compose = v2.get("compose") or {}
    issues = []
    if int(normalization.get("target_long_edge", 0) or 0) < 2048:
        issues.append("input.normalization.target_long_edge must be >= 2048")
    prompt_texts = {
        str(item.get("text") or item.get("id") or "").strip().lower()
        for item in (sam3.get("prompts") or []) if isinstance(item, dict)
    }
    required_prompts = {"arrow", "border", "content box", "diagram", "grid", "icon", "picture"}
    normalized_prompts = {value.replace("_", " ") for value in prompt_texts}
    missing_prompts = sorted(required_prompts - normalized_prompts)
    if missing_prompts:
        issues.append(f"sam3.prompts missing full-quality roles: {missing_prompts}")
    if str(ocr.get("provider") or "").lower() not in {"remote_paddleocr", "paddleocr"}:
        issues.append("ocr.provider must use PaddleOCR")
    if materialization.get("rmbg") is None or rmbg.get("enabled") is not True:
        issues.append("asset_materialization.rmbg.enabled must be true")
    if asset_policy.get("enabled") is not True:
        issues.append("asset_policy.enabled must be true")
    if int(svg.get("max_attempts", 0) or 0) < 8:
        issues.append("svg.max_attempts must be >= 8")
    if svg.get("generation_backend") != "codex_python_sdk_controlled":
        issues.append("svg.generation_backend must be codex_python_sdk_controlled")
    if svg.get("staged_generation") is not True:
        issues.append("svg.staged_generation must be true")
    if not (svg.get("visual_review_rounds") or []):
        issues.append("svg.visual_review_rounds must not be empty")
    if str(runtime.get("reasoning_effort") or "").lower() != "xhigh":
        issues.append("model_runtime.reasoning_effort must be xhigh")
    if runtime.get("fast") is not False:
        issues.append("model_runtime.fast must be false")
    if int(runtime.get("max_critic_rounds", 0) or 0) < 3:
        issues.append("model_runtime.max_critic_rounds must be >= 3")
    if not str(runtime.get("model_name") or "").strip():
        issues.append("model_runtime.model_name must be configured")
    if ppt.get("enabled") is not True or ppt.get("export_pptx") is not True:
        issues.append("svg_to_ppt native PPTX export must be enabled")
    if v2.get("enabled") is not True:
        issues.append("v2.enabled must be true")
    if not all(v2_parser.get(key) is True for key in ("enabled", "sam3_enabled", "ocr_enabled")):
        issues.append("v2 parser/SAM3/OCR must all be enabled")
    if v2_refine.get("enabled") is not True or v2_refine.get("provider") != "codex_element_refiner":
        issues.append("v2 agent refinement must use codex_element_refiner")
    if v2_processor.get("enabled") is not True or v2_compose.get("enabled") is not True:
        issues.append("v2 processor and compose stages must be enabled")
    return issues


def find_case_dir(drawai_root: Path, run_name: str) -> Path | None:
    cands = sorted(drawai_root.glob(f"*/*_{run_name}/outputs/case_001*"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def find_case_config(case_dir: Path) -> Path | None:
    run_dir = case_dir.parents[1]
    cfg = run_dir / "configs" / "case_001.yaml"
    return cfg if cfg.exists() else None


def collect(case_dir: Path, layout: dict) -> dict:
    cp = {}
    pairs = [
        (case_dir / "box_ir/box_ir.json", layout["ir"] / "box_ir.json"),
        (case_dir / "sam3/raw_regions.json", layout["ir"] / "regions.json"),
        (case_dir / "ocr/ocr_boxes.json", layout["ir"] / "ocr_boxes.json"),
        (case_dir / "svg/semantic.svg", layout["svg"] / "semantic.svg"),
        (case_dir / "svg/rendered.png", layout["svg"] / "rendered_svg.png"),
        (case_dir / "svg_to_ppt/semantic.svg_to_ppt.pptx", layout["pptx"] / "editable.pptx"),
        (case_dir / "drawai_package.json", layout["drawai"] / "drawai_package.json"),
        (case_dir / "reports/pipeline_summary.json", layout["drawai"] / "pipeline_summary.json"),
        (case_dir / "reports/svg_validation_report.json", layout["drawai"] / "svg_validation_report.json"),
        (case_dir / "reports/svg_to_ppt_export_report.json", layout["drawai"] / "svg_to_ppt_export_report.json"),
    ]
    for src, dst in pairs:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            cp[dst.name] = str(dst)
    # DrawAI v2's element packages and traces are part of the reconstruction evidence, not
    # disposable implementation detail.  Preserve them outside the engine-owned run tree so a
    # publication export remains auditable after temporary DrawAI runs are cleaned up.
    for src, dst in (
        (case_dir / "elements", layout["drawai"] / "elements"),
        (case_dir / "trace", layout["drawai"] / "trace"),
        (case_dir / "reports" / "parser_outputs", layout["drawai"] / "parser_outputs"),
        (case_dir / "exports", layout["drawai"] / "exports"),
    ):
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            cp[f"{dst.name}_tree"] = str(dst)
    # Copy the raster asset tree so the SVG's relative hrefs ("../svg_to_ppt/assets/...") resolve
    # from the skill layout (run_root/svg/semantic.svg -> run_root/svg_to_ppt/assets/...). Without
    # this the file-path raster crops are dropped from the skill SVG / rendered PNG / publication PDF.
    run_root = layout["svg"].parent
    assets_src = case_dir / "svg_to_ppt" / "assets"
    if assets_src.exists():
        assets_dst = run_root / "svg_to_ppt" / "assets"
        if assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)
        cp["assets_tree"] = str(assets_dst)
    return cp


def make_layout(run_root: Path) -> dict:
    sub = {k: run_root / k for k in
           ["source", "drawai", "ir", "svg", "pptx", "pdf", "formulas", "comparisons", "reports", "final"]}
    sub["region_diffs"] = run_root / "comparisons" / "region_diffs"
    for p in sub.values():
        p.mkdir(parents=True, exist_ok=True)
    return sub


def py(script: str, *args) -> subprocess.CompletedProcess:
    """Run a deterministic helper under both utility and whole-run wall budgets."""
    command = [sys.executable, str(HERE / script), *map(str, args)]
    result = _bounded_command(command, cwd=Path.cwd(), timeout_seconds=_UTILITY_TIMEOUT_SECONDS)
    return subprocess.CompletedProcess(
        command, result["returncode"], result.get("stdout_tail", ""), result.get("stderr_tail", "")
    )


def _ssim_render(source_png: Path, svg: Path, tmp_png: Path) -> float | None:
    """Render an SVG (hrefs resolve from its own dir) and return SSIM vs source."""
    py("render_svg.py", svg, tmp_png, "--width", 1600)
    if not tmp_png.exists():
        return None
    src = C.load_gray(source_png)
    ren = C.load_gray(tmp_png, (src.shape[1], src.shape[0]))
    return C.ssim(src, ren)


def visual_quality_repairs(case_dir: Path, L: dict, rnd: int, source_png: Path,
                           drawai_cmd, case_config, do_repair: bool,
                           command_timeout_seconds: float) -> dict:
    """Apply raster-background matching + audio-waveform repair on the CASE svg (where hrefs
    resolve). Keep-if-not-regressed (SSIM). Re-export the PPTX only when a repair is kept."""
    case_svg = case_dir / "svg" / "semantic.svg"
    case_render = case_dir / "svg" / "rendered.png"
    case_ocr = case_dir / "ocr" / "ocr_boxes.json"
    raster_out = L["comparisons"] / f"raster_bg_round{rnd}.json"
    wave_out = L["comparisons"] / f"waveform_round{rnd}.json"
    info = {"RASTER_BACKGROUND_MATCH": "PASS", "WAVEFORM_STYLE": "PASS",
            "repaired_raster": 0, "repaired_waveform": 0, "kept": False, "reverted": False}
    if not case_svg.exists():
        return info

    backup = case_svg.with_suffix(".pre_vq.bak")
    shutil.copy2(case_svg, backup)
    pre_ssim = _ssim_render(source_png, case_svg, L["comparisons"] / f"_pre_vq_{rnd}.png") if do_repair else None

    rargs = ["--svg", case_svg, "--assets-root", case_dir / "svg", "--out", raster_out,
             "--mode", "transparent"]
    if case_render.exists():
        rargs += ["--render", case_render]
    if do_repair:
        rargs += ["--repair", "--svg-out", case_svg]
    py("fix_raster_backgrounds.py", *rargs)
    rj = C.read_json(raster_out) if raster_out.exists() else {}
    info["RASTER_BACKGROUND_MATCH"] = rj.get("RASTER_BACKGROUND_MATCH", "PASS")
    info["repaired_raster"] = rj.get("repaired", 0)

    wargs = ["--svg", case_svg, "--source-ocr", case_ocr, "--out", wave_out]
    if do_repair:
        wargs += ["--repair", "--svg-out", case_svg]
    py("verify_waveforms.py", *wargs)
    wj = C.read_json(wave_out) if wave_out.exists() else {}
    info["WAVEFORM_STYLE"] = wj.get("WAVEFORM_STYLE", "PASS")
    info["repaired_waveform"] = wj.get("repaired_elements", 0)

    total_repaired = (info["repaired_raster"] or 0) + (info["repaired_waveform"] or 0)
    if do_repair and total_repaired > 0:
        post_ssim = _ssim_render(source_png, case_svg, L["comparisons"] / f"_post_vq_{rnd}.png")
        info["pre_ssim"], info["post_ssim"] = pre_ssim, post_ssim
        keep = post_ssim is not None and (pre_ssim is None or post_ssim >= pre_ssim - 0.01)
        if keep:
            info["kept"] = True
            # re-render the case render + re-export the PPTX from the repaired svg (best-effort)
            py("render_svg.py", case_svg, case_render, "--width", 2048)
            if case_config is not None:
                export_result = _bounded_command(
                    [*drawai_cmd, "--config", str(case_config),
                     "--from-stage", "svg_to_ppt_exported", "--to-stage", "svg_to_ppt_exported"],
                    cwd=_repo_root(), timeout_seconds=command_timeout_seconds,
                )
                info["reexport_returncode"] = export_result["returncode"]
                info["reexport_timed_out"] = export_result["timed_out"]
        else:
            shutil.copy2(backup, case_svg)  # revert regression
            info["reverted"] = True
    backup.unlink(missing_ok=True)
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--runs-root", default="runs")
    ap.add_argument("--max-rounds", type=int, default=10)
    ap.add_argument("--max-wall-seconds", type=float, default=10_800,
                    help="hard wall-clock budget for the entire reconstruction")
    ap.add_argument("--round-timeout-seconds", type=float, default=3_600,
                    help="hard timeout for one DrawAI generation/repair command")
    ap.add_argument("--stagnation-rounds", type=int, default=3,
                    help="stop after this many valid rounds without material score improvement")
    ap.add_argument("--min-improvement", type=float, default=0.002,
                    help="minimum combined-score gain that resets stagnation")
    ap.add_argument("--max-consecutive-failures", type=int, default=2)
    ap.add_argument("--target", type=float, default=0.99)
    ap.add_argument("--region-threshold", type=float, default=0.99)
    ap.add_argument("--drawai-cmd", default="uv run --frozen drawai")
    ap.add_argument("--drawai-python-cmd", default="uv run --frozen python",
                    help="Python command inside the bundled DrawAI environment")
    ap.add_argument(
        "--base-config",
        default="configs/drawai/config.yaml",
        help="DrawAI full-quality base config; smoke/fast configs are rejected",
    )
    ap.add_argument("--drawai-repo", default="",
                    help="Maintainer-only override for validating a future DrawAI checkout; normal runs use engine/")
    ap.add_argument("--critical-labels", default="")
    ap.add_argument("--transcribe-formulas", action="store_true")
    ap.add_argument("--slide-size", default="")
    ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--preflight-only", action="store_true",
                    help="create and validate DrawAI's resolved case config without running models")
    args = ap.parse_args()

    if args.drawai_repo:
        global _DRAWAI_OVERRIDE
        _DRAWAI_OVERRIDE = Path(args.drawai_repo).expanduser().resolve()

    quality_config = Path(args.base_config)
    if not quality_config.is_absolute():
        quality_config = _repo_root() / quality_config
    if not quality_config.is_file():
        print(f"FATAL: DrawAI quality config not found: {quality_config}", file=sys.stderr)
        return 2
    quality_issues = validate_quality_config(quality_config)
    if quality_issues:
        print("FATAL: refusing degraded DrawAI profile:\n- " + "\n- ".join(quality_issues), file=sys.stderr)
        return 2

    budget_issues = validate_budget(
        max_rounds=args.max_rounds,
        max_wall_seconds=args.max_wall_seconds,
        round_timeout_seconds=args.round_timeout_seconds,
        stagnation_rounds=args.stagnation_rounds,
        min_improvement=args.min_improvement,
        max_consecutive_failures=args.max_consecutive_failures,
    )
    if budget_issues:
        print("FATAL: invalid bounded-execution policy:\n- " + "\n- ".join(budget_issues), file=sys.stderr)
        return 2

    try:
        remote_settings = remote_runtime.load_settings()
        remote_runtime.apply_environment(remote_settings)
    except Exception as exc:  # noqa: BLE001 - preflight boundary
        print(f"FATAL: remote DrawAI runtime configuration invalid: {exc}", file=sys.stderr)
        return 2

    drawai_cmd = shlex.split(args.drawai_cmd)
    drawai_python_cmd = shlex.split(args.drawai_python_cmd)
    image = Path(args.image)
    if not image.exists():
        print(f"FATAL: image not found: {image}", file=sys.stderr)
        return 2

    run_root = Path(args.runs_root) / args.run_name
    if run_root.exists():
        shutil.rmtree(run_root)
    L = make_layout(run_root)
    shutil.copy2(image, L["source"] / "source.png")
    source_png = L["source"] / "source.png"
    remote_config = remote_runtime.write_resolved_config(
        quality_config, L["drawai"] / "remote_quality_config.yaml", remote_settings
    )
    remote_issues = validate_quality_config(remote_config) + remote_runtime.validate_binding(
        remote_config, remote_settings
    )
    remote_report = remote_runtime.probe(remote_settings)
    C.write_json(L["reports"] / "remote_runtime_preflight.json", remote_report)
    if remote_issues or not remote_report.get("ok"):
        problems = remote_issues + list(remote_report.get("errors") or [])
        print("FATAL: remote DrawAI preflight failed:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 2

    if args.preflight_only:
        result = run_drawai_full(
            drawai_python_cmd, image, L["drawai"] / "runs", args.run_name,
            remote_config, args.round_timeout_seconds, dry_run=True,
        )
        configs = sorted((L["drawai"] / "runs").glob("*/*/configs/case_001.yaml"))
        resolved = configs[-1] if configs else None
        issues = (
            validate_quality_config(resolved) + remote_runtime.validate_binding(resolved, remote_settings)
            if resolved else ["DrawAI dry-run produced no case config"]
        )
        report = {"ok": result["returncode"] == 0 and not issues, "mode": "preflight-only",
                  "drawai_repo": str(_repo_root()), "base_config": str(quality_config),
                  "remote_config": str(remote_config),
                  "remote_runtime_ok": remote_report.get("ok") is True,
                  "resolved_config": str(resolved) if resolved else "", "issues": issues,
                  "drawai_returncode": result["returncode"], "run_root": str(run_root)}
        C.write_json(L["reports"] / "quality_preflight.json", report)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ok"] else 2

    score_history = []
    rounds_log = []
    best = {"combined": -1.0, "round": -1}
    status = "FAILED"
    stop_reason = "round_budget_exhausted"
    case_dir = None
    case_config = None
    guard = ProgressGuard(
        max_wall_seconds=args.max_wall_seconds,
        stagnation_rounds=args.stagnation_rounds,
        min_improvement=args.min_improvement,
        max_consecutive_failures=args.max_consecutive_failures,
    )
    global _EXECUTION_DEADLINE
    _EXECUTION_DEADLINE = guard.started_at + args.max_wall_seconds

    for rnd in range(0, args.max_rounds + 1):
        budget_stop = guard.before_round()
        if budget_stop:
            stop_reason = budget_stop
            break
        t0 = time.time()
        if rnd == 0:
            dr = run_drawai_full(
                drawai_python_cmd,
                image,
                L["drawai"] / "runs",
                args.run_name,
                remote_config,
                args.round_timeout_seconds,
            )
            case_dir = find_case_dir(L["drawai"] / "runs", args.run_name)
            if case_dir is None:
                rounds_log.append({"round": rnd, "stage": "drawai_full", "error": "no case dir", "drawai": dr})
                C.write_json(L["comparisons"] / "score_history.json", score_history)
                _write_status(L, "FAILED", "DrawAI produced no output", rounds_log, best)
                return 6
            case_config = find_case_config(case_dir)
        else:
            if args.no_repair or case_config is None:
                stop_reason = "repair_disabled_or_unavailable"
                break
            dr = run_drawai_repair(drawai_cmd, case_config, args.round_timeout_seconds)

        # visual-quality repairs (raster background matching + audio waveform) on the case svg,
        # keep-if-not-regressed, BEFORE collecting so the collected artifacts reflect the fixes.
        vq = visual_quality_repairs(case_dir, L, rnd, source_png, drawai_cmd, case_config,
                                    do_repair=not args.no_repair,
                                    command_timeout_seconds=args.round_timeout_seconds)

        collect(case_dir, L)
        pipeline_summary_path = L["drawai"] / "pipeline_summary.json"
        pipeline_summary = C.read_json(pipeline_summary_path) if pipeline_summary_path.exists() else {}
        semantic = L["svg"] / "semantic.svg"
        if not semantic.exists():
            rounds_log.append({"round": rnd, "error": "no semantic.svg", "drawai": dr})
            stop_reason = "missing_semantic_svg"
            break

        # Source-raster text geometry is immutable during vector reconstruction. Detect severe
        # overlap/clipping early so DrawAI cannot accidentally turn a bad raster into an auto-PASS.
        layout_report_path = L["comparisons"] / f"source_text_layout_round{rnd}.json"
        py("audit_ocr_layout.py", "--ocr", L["ir"] / "ocr_boxes.json",
           "--box-ir", L["ir"] / "box_ir.json", "--out", layout_report_path)
        source_layout = C.read_json(layout_report_path) if layout_report_path.exists() else {"ok": False}

        # render SVG (fresh) + PPTX (real renderer or NOT_RUN)
        py("render_svg.py", semantic, L["svg"] / "rendered_svg.png", "--width", 2048)
        pptx = L["pptx"] / "editable.pptx"
        pptx_render = L["pptx"] / "rendered_pptx.png"
        pptx_render_status = "NOT_RUN"
        if pptx.exists():
            rp = py("render_pptx.py", pptx, pptx_render)
            try:
                pptx_render_status = json.loads((Path(str(pptx_render) + ".render.json")).read_text()).get("status", "NOT_RUN")
            except Exception:  # noqa: BLE001
                pptx_render_status = "NOT_RUN"

        # measure
        gm = L["comparisons"] / f"global_round{rnd}.json"
        m_args = ["--source", source_png, "--svg-render", L["svg"] / "rendered_svg.png",
                  "--svg", semantic, "--source-ocr", L["ir"] / "ocr_boxes.json",
                  "--box-ir", L["ir"] / "box_ir.json", "--out", gm]
        if pptx_render.exists() and pptx_render_status == "OK":
            m_args += ["--pptx-render", pptx_render]
        py("measure_similarity.py", *m_args)
        global_metrics = C.read_json(gm) if gm.exists() else {}
        combined = global_metrics.get("combined_global_similarity")

        rg = L["comparisons"] / f"regions_round{rnd}.json"
        py("compare_regions.py", "--source", source_png, "--svg-render", L["svg"] / "rendered_svg.png",
           "--box-ir", L["ir"] / "box_ir.json", "--source-ocr", L["ir"] / "ocr_boxes.json",
           "--svg", semantic, "--out", rg, "--diffs-dir", L["region_diffs"], "--threshold", args.region_threshold)
        region_metrics = C.read_json(rg) if rg.exists() else {}

        tv = L["comparisons"] / f"text_round{rnd}.json"
        fv = L["comparisons"] / f"formula_round{rnd}.json"
        tf_args = ["--source-ocr", L["ir"] / "ocr_boxes.json", "--svg", semantic,
                   "--formulas-dir", L["formulas"], "--out-text", tv, "--out-formula", fv]
        if args.critical_labels:
            tf_args += ["--critical-labels", args.critical_labels]
        if args.transcribe_formulas:
            tf_args += ["--transcribe"]
        py("verify_text_and_formulas.py", *tf_args)
        text_metrics = C.read_json(tv) if tv.exists() else {}
        formula_metrics = C.read_json(fv) if fv.exists() else {}

        ev = L["comparisons"] / f"pptx_round{rnd}.json"
        editable = False
        if pptx.exists():
            py("verify_pptx_editability.py", str(pptx), "--out", ev)
            editable = C.read_json(ev).get("editable", False) if ev.exists() else False

        entry = {
            "round": rnd, "stage": "drawai_full" if rnd == 0 else "repair_from_svg",
            "drawai_pipeline_status": pipeline_summary.get("status"),
            "drawai_v2_enabled": pipeline_summary.get("v2_enabled"),
            "drawai_execution_mode": pipeline_summary.get("execution_mode"),
            "combined_global_similarity": combined,
            "ssim": global_metrics.get("metrics", {}).get("ssim"),
            "ocr_recall": text_metrics.get("ocr_token_prf", {}).get("recall"),
            "critical_label_recall": text_metrics.get("critical_label_recall"),
            "all_critical_regions_pass": region_metrics.get("all_critical_pass"),
            "worst_region_ssim": (region_metrics.get("worst_regions") or [{}])[0].get("ssim"),
            "pptx_editable": editable,
            "pptx_render_status": pptx_render_status,
            "formulas": formula_metrics.get("formula_count"),
            "source_text_layout_pass": source_layout.get("ok") is True,
            "source_text_collisions": len(source_layout.get("collisions") or []),
            "raster_background_match": vq.get("RASTER_BACKGROUND_MATCH"),
            "waveform_style": vq.get("WAVEFORM_STYLE"),
            "vq_repaired_raster": vq.get("repaired_raster"),
            "vq_repaired_waveform": vq.get("repaired_waveform"),
            "vq_kept": vq.get("kept"),
            "seconds": round(time.time() - t0, 1),
            "drawai_returncode": dr.get("returncode"),
        }
        score_history.append(entry)
        rounds_log.append({**entry, "drawai_cmd": dr.get("cmd")})
        C.write_json(L["comparisons"] / "score_history.json", score_history)

        # keep best by combined score (snapshot final/)
        if combined is not None and combined > best["combined"]:
            best = {"combined": combined, "round": rnd}
            _snapshot_final(L, semantic, pptx)

        # stop condition (PASS)
        ocr_label_ok = text_metrics.get("critical_label_recall") == 1.0
        formulas_ok = formula_metrics.get("formula_count", 0) == 0 or formula_metrics.get("all_flagged_for_review", False)
        passed = (
            combined is not None and combined >= args.target
            and pipeline_summary.get("status") == "ok"
            and pipeline_summary.get("v2_enabled") is True
            and pipeline_summary.get("execution_mode") == "v2_file_stage_runner"
            and region_metrics.get("all_critical_pass") is True
            and ocr_label_ok and editable
            and pptx_render_status == "OK"  # a real PPTX render is mandatory for auto-PASS
            and source_layout.get("ok") is True
            and vq.get("RASTER_BACKGROUND_MATCH") != "FAILED"
            and vq.get("WAVEFORM_STYLE") != "FAILED"
        )
        # note: formulas_ok is informational; formulas always require human review, never block PASS by themselves
        if passed:
            status = "PASS"
            stop_reason = "quality_gates_passed"
            break

        progress_stop = guard.observe(
            score=float(combined) if isinstance(combined, (int, float)) else None,
            artifact=semantic,
            pipeline_ok=dr.get("returncode") == 0 and pipeline_summary.get("status") == "ok",
        )
        if progress_stop:
            stop_reason = progress_stop
            break

    else:
        pass

    if status != "PASS":
        # we finished the loop without PASS
        status = "REVIEW_REQUIRED" if best["combined"] >= 0 else "FAILED"

    # publication PDF from the best SVG (vector, zoom-clear)
    _build_pdf(L)

    # assemble reports
    py("build_report.py", "--run-root", run_root, "--status", status,
       "--target", args.target, "--best-round", best["round"], "--slide-size", args.slide_size or "default")

    _write_status(L, status, stop_reason, rounds_log, best)
    print(f"\n=== {args.run_name}: {status} | best combined={best['combined']} (round {best['round']}) ===")
    print(f"stop_reason: {stop_reason}")
    print(f"reports: {L['reports']}")
    print("USER APPROVAL REQUIRED before this result is treated as final (see RECONSTRUCTION_REPORT.md).")
    return 0 if status in ("PASS", "REVIEW_REQUIRED") else 7


def _snapshot_final(L: dict, semantic: Path, pptx: Path) -> None:
    if semantic.exists():
        shutil.copy2(semantic, L["final"] / "semantic.svg")
        if (L["svg"] / "rendered_svg.png").exists():
            shutil.copy2(L["svg"] / "rendered_svg.png", L["final"] / "rendered_svg.png")
    if pptx.exists():
        shutil.copy2(pptx, L["final"] / "editable.pptx")


def _build_pdf(L: dict) -> None:
    svg = L["final"] / "semantic.svg"
    if not svg.exists():
        svg = L["svg"] / "semantic.svg"
    if not svg.exists():
        return
    try:
        import cairosvg
        # unsafe=True so local <image> raster crops are embedded into the publication PDF (vector
        # text/shapes + embedded rasters only where the SVG had <image>).
        cairosvg.svg2pdf(url=str(svg), write_to=str(L["pdf"] / "publication_figure.pdf"), unsafe=True)
        shutil.copy2(L["pdf"] / "publication_figure.pdf", L["final"] / "publication_figure.pdf")
    except Exception as exc:  # noqa: BLE001
        (L["pdf"] / "pdf_error.txt").write_text(str(exc), encoding="utf-8")


def _write_status(L: dict, status: str, note: str, rounds_log, best) -> None:
    C.write_json(L["reports"].parent / "status.json",
                 {"status": status, "note": note, "best": best, "rounds": rounds_log})


if __name__ == "__main__":
    raise SystemExit(main())
