from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an HTML comparison for two DrawAI runs.")
    parser.add_argument("--old-manifest", required=True, type=Path)
    parser.add_argument("--new-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    old_manifest = args.old_manifest.expanduser().resolve()
    new_root = args.new_root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    old_rows = _load_old_rows(old_manifest)
    new_rows = _load_new_rows(new_root)
    rows = _align_rows(old_rows, new_rows)
    if args.limit > 0:
        rows = rows[: args.limit]
    web_assets = _stage_web_assets(rows, output)

    payload = {
        "schema": "drawai.run_comparison.v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "old_manifest": str(old_manifest),
        "new_root": str(new_root),
        "html": str(output),
        "web_asset_dir": str(web_assets["asset_dir"]),
        "case_count": len(rows),
        "status_counts": dict(Counter(row["new"].get("status") or "missing" for row in rows)),
        "rows": rows,
    }
    output.write_text(_render_html(payload), encoding="utf-8")
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)
    print(manifest_path)


def _load_old_rows(manifest_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(manifest_path)
    rows = [row for row in payload.get("rows", []) if isinstance(row, Mapping)]
    return [dict(row) for row in rows]


def _load_new_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    orchestrator_logs_dir = root.parent.parent / "orchestrator_logs"
    for case_dir in sorted(root.glob("**/outputs/case_*")):
        if not case_dir.is_dir():
            continue
        run_dir = case_dir.parents[1] if len(case_dir.parents) > 1 else case_dir
        metadata = _read_json_optional(case_dir / "inputs" / "source_metadata.json")
        summary = _case_summary(case_dir)
        exitcode = _orchestrator_exitcode(orchestrator_logs_dir, run_dir.name)
        source_path = _metadata_text(metadata, "source_path")
        if not source_path:
            source_path = str(case_dir / "inputs" / "original.png")
        stage_status = _stage_status(case_dir)
        status = summary.get("status") or stage_status.get("latest_status") or "unknown"
        if exitcode not in ("", "0") and status == "running":
            status = "terminated" if exitcode == "143" else "failed"
        failed_stage = summary.get("failed_stage") or ""
        if not failed_stage and status not in {"completed", "ok", "success", "passed"}:
            failed_stage = stage_status.get("latest_stage") or ""
        row = {
            "case_dir": str(case_dir),
            "case_slug": case_dir.name,
            "source_image": source_path,
            "status": status,
            "exitcode": exitcode,
            "failed_stage": failed_stage,
            "duration_seconds": summary.get("duration_seconds"),
            "svg_path": _best_file(summary.get("semantic_svg"), case_dir / "svg" / "semantic.svg"),
            "rendered_path": _best_file(summary.get("semantic_rendered_png"), case_dir / "svg" / "rendered.png"),
            "pptx_path": _best_file(summary.get("pptx"), case_dir / "svg_to_ppt" / "semantic.svg_to_ppt.pptx"),
            "attempts": _attempt_rows(case_dir / "svg" / "attempts" / "codex_merged"),
            "pipeline_summary": str(case_dir / "reports" / "pipeline_summary.json")
            if (case_dir / "reports" / "pipeline_summary.json").is_file()
            else "",
        }
        row["native_backfill_candidate_count"] = sum(
            int(attempt.get("native_backfill_candidate_count") or 0) for attempt in row["attempts"]
        )
        row["zero_byte_attempt_semantic_count"] = sum(
            1 for attempt in row["attempts"] if attempt.get("semantic_svg_bytes") == 0
        )
        row["native_backfill_png_count"] = _count_files(case_dir / "svg" / "native_backfill_assets", "*.png")
        row["references_native_backfill_assets"] = _text_file_contains(
            Path(str(row["svg_path"])), "native_backfill_assets"
        )
        row["zero_byte_semantic_svg"] = bool(row["svg_path"]) and _file_size(Path(str(row["svg_path"]))) == 0
        rows.append(row)
    return rows


def _align_rows(old_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    old_by_source = {_source_key(row.get("source_image")): row for row in old_rows if _source_key(row.get("source_image"))}
    result = []
    for new in sorted(new_rows, key=lambda row: str(row.get("source_image") or row.get("case_slug") or "")):
        key = _source_key(new.get("source_image"))
        old = old_by_source.get(key, {})
        result.append({"key": key, "old": old, "new": new})
    return result


def _stage_web_assets(rows: list[dict[str, Any]], output: Path) -> dict[str, str]:
    asset_dir = output.with_name(output.stem + "_assets")
    if asset_dir.exists():
        shutil.rmtree(asset_dir)
    asset_dir.mkdir(parents=True)
    for index, row in enumerate(rows, start=1):
        old = row.get("old") if isinstance(row.get("old"), dict) else {}
        new = row.get("new") if isinstance(row.get("new"), dict) else {}
        row["web_images"] = {
            "original": _copy_web_asset(
                new.get("source_image") or old.get("source_image"),
                asset_dir,
                output.parent,
                f"case_{index:03d}_original",
            ),
            "old_rendered": _copy_web_asset(
                old.get("rendered_path"),
                asset_dir,
                output.parent,
                f"case_{index:03d}_old_rendered",
            ),
            "new_rendered": _copy_web_asset(
                new.get("rendered_path"),
                asset_dir,
                output.parent,
                f"case_{index:03d}_new_rendered",
            ),
        }
    return {"asset_dir": str(asset_dir)}


def _copy_web_asset(path_value: Any, asset_dir: Path, html_dir: Path, stem: str) -> str:
    source = Path(str(path_value or ""))
    if not source.is_file():
        return ""
    suffix = source.suffix.lower() or ".bin"
    target = asset_dir / f"{stem}{suffix}"
    shutil.copy2(source, target)
    return target.relative_to(html_dir).as_posix()


def _case_summary(case_dir: Path) -> dict[str, Any]:
    run_dir = case_dir.parents[1] if len(case_dir.parents) > 1 else case_dir
    summary = _read_json_optional(run_dir / "reports" / "run_summary.json")
    if isinstance(summary, Mapping):
        for item in summary.get("cases", []):
            if isinstance(item, Mapping) and str(item.get("case_slug") or "") in case_dir.name:
                return dict(item)
        cases = [item for item in summary.get("cases", []) if isinstance(item, Mapping)]
        if len(cases) == 1:
            return dict(cases[0])
    return {}


def _orchestrator_exitcode(logs_dir: Path, run_name: str) -> str:
    match = re.search(r"_case_(\d{2})_", run_name)
    if not match or not logs_dir.is_dir():
        return ""
    prefix = f"case_{match.group(1)}_"
    candidates = sorted(logs_dir.glob(prefix + "*.exitcode"))
    if not candidates:
        return ""
    return candidates[0].read_text(encoding="utf-8").strip()


def _stage_status(case_dir: Path) -> dict[str, Any]:
    payload = _read_json_optional(case_dir / "reports" / "stage_status.json")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _attempt_rows(attempts_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not attempts_dir.is_dir():
        return rows
    for attempt_dir in sorted(path for path in attempts_dir.iterdir() if path.is_dir() and path.name.isdigit()):
        request = _read_json_optional(attempt_dir / "native_backfill_request.json")
        session = _read_json_optional(attempt_dir / "codex_session_log" / "turn_result_summary.json")
        usage = session.get("usage") if isinstance(session, Mapping) else None
        rows.append(
            {
                "attempt": attempt_dir.name,
                "semantic_svg_bytes": _file_size(attempt_dir / "semantic.svg"),
                "model_response_bytes": _file_size(attempt_dir / "model_response.txt"),
                "iteration_log_bytes": _file_size(attempt_dir / "iteration_log.md"),
                "validation_report_bytes": _file_size(attempt_dir / "validation_report.json"),
                "session_log_bytes": _file_size(attempt_dir / "codex_session_log" / "turn_result_summary.json"),
                "native_backfill_candidate_count": len(request.get("candidates", []))
                if isinstance(request, Mapping)
                else 0,
                "internal_iteration_svgs": _count_files(attempt_dir, "semantic_*.svg"),
                "internal_iteration_pngs": _count_files(attempt_dir, "rendered_*.png"),
                "status": session.get("status") if isinstance(session, Mapping) else "",
                "usage": usage if isinstance(usage, Mapping) else {},
            }
        )
    return rows


def _render_html(payload: Mapping[str, Any]) -> str:
    rows_html = "\n".join(_render_case(index, row) for index, row in enumerate(payload["rows"], start=1))
    style = """
body{margin:0;background:#f6f7f9;color:#1e2329;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #d9dee7;padding:16px 24px}
h1{font-size:20px;margin:0 0 8px} .meta{font-size:12px;color:#5d6675;display:flex;gap:16px;flex-wrap:wrap}
main{padding:20px 24px 36px}.case{background:#fff;border:1px solid #d9dee7;border-radius:8px;margin-bottom:22px;overflow:hidden}
.case-head{padding:14px 16px;border-bottom:1px solid #e5e9f0;display:flex;gap:12px;align-items:flex-start;justify-content:space-between}
.title{font-weight:650}.badges{display:flex;gap:8px;flex-wrap:wrap}.badge{font-size:12px;padding:3px 8px;border-radius:999px;background:#edf1f7;color:#303846}.ok{background:#e7f6ee;color:#166339}.failed{background:#fdecec;color:#9d2222}.running{background:#fff6d8;color:#765400}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:16px}.panel{min-width:0}.panel h3{font-size:13px;margin:0 0 8px;color:#3a4352}
img{width:100%;height:auto;display:block;border:1px solid #d5dbe5;background:#fff}.details{padding:0 16px 16px}.kv{display:grid;grid-template-columns:170px minmax(0,1fr);gap:6px 10px;font-size:12px;color:#333}
code{font-family:"SFMono-Regular",Consolas,monospace;font-size:11px;word-break:break-all}.attempts{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}.attempts th,.attempts td{border:1px solid #dfe4ec;padding:6px;text-align:left;vertical-align:top}
details{margin-top:10px}summary{cursor:pointer;font-size:13px;font-weight:600}.svg-box{max-height:360px;overflow:auto;background:#0f1720;color:#dce7f7;padding:12px;border-radius:6px;font-size:11px;white-space:pre-wrap}
a{color:#175cd3;text-decoration:none}@media(max-width:1100px){.grid{grid-template-columns:1fr}.kv{grid-template-columns:1fr}}
"""
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>DrawAI Run Comparison</title>
  <style>{style}</style>
</head>
<body>
<header>
  <h1>DrawAI Run Comparison</h1>
  <div class="meta">
    <span>Generated: {escape(str(payload.get("generated_at") or ""))}</span>
    <span>Cases: {len(payload.get("rows", []))}</span>
    <span>Status: {escape(json.dumps(payload.get("status_counts", {}), ensure_ascii=False))}</span>
  </div>
</header>
<main>
{rows_html}
</main>
</body>
</html>
"""


def _render_case(index: int, row: Mapping[str, Any]) -> str:
    old = row.get("old") if isinstance(row.get("old"), Mapping) else {}
    new = row.get("new") if isinstance(row.get("new"), Mapping) else {}
    web_images = row.get("web_images") if isinstance(row.get("web_images"), Mapping) else {}
    title = Path(str(new.get("source_image") or old.get("source_image") or row.get("key") or "")).name
    status = str(new.get("status") or "missing")
    badge_class = "ok" if status == "completed" else "failed" if status == "failed" else "running"
    attempts_html = _render_attempts(new.get("attempts") if isinstance(new.get("attempts"), list) else [])
    old_svg_text = _read_text_sample(Path(str(old.get("svg_path") or "")))
    new_svg_text = _read_text_sample(Path(str(new.get("svg_path") or "")))
    return f"""
<section class="case">
  <div class="case-head">
    <div>
      <div class="title">{index}. {escape(title)}</div>
      <div class="meta"><span>{escape(str(row.get("key") or ""))}</span></div>
    </div>
    <div class="badges">
      <span class="badge {badge_class}">new: {escape(status)}</span>
      <span class="badge">old: {escape(str(old.get("status") or "missing"))}</span>
      <span class="badge">attempts: {len(new.get("attempts") or [])}</span>
      <span class="badge">exit: {escape(str(new.get("exitcode") or ""))}</span>
    </div>
  </div>
  <div class="grid">
    {_image_panel("Original", new.get("source_image") or old.get("source_image"), web_images.get("original"))}
    {_image_panel("Old rendered", old.get("rendered_path"), web_images.get("old_rendered"))}
    {_image_panel("New rendered", new.get("rendered_path"), web_images.get("new_rendered"))}
  </div>
  <div class="details">
    <div class="kv">
      <div>New duration</div><div>{escape(_format_seconds(new.get("duration_seconds")))}</div>
      <div>Failed stage</div><div>{escape(str(new.get("failed_stage") or ""))}</div>
      <div>Zero-byte semantic.svg</div><div>{escape(str(new.get("zero_byte_semantic_svg") or False))}</div>
      <div>Zero-byte attempt semantic.svg</div><div>{escape(str(new.get("zero_byte_attempt_semantic_count") or 0))}</div>
      <div>Native backfill candidates</div><div>{escape(str(new.get("native_backfill_candidate_count") or 0))}</div>
      <div>Native backfill PNGs</div><div>{escape(str(new.get("native_backfill_png_count") or 0))}</div>
      <div>References native_backfill_assets</div><div>{escape(str(new.get("references_native_backfill_assets") or False))}</div>
      <div>New SVG</div><div>{_link(new.get("svg_path"))}</div>
      <div>Old SVG</div><div>{_link(old.get("svg_path"))}</div>
      <div>New PPTX</div><div>{_link(new.get("pptx_path"))}</div>
      <div>Old PPTX</div><div>{_link(old.get("pptx_path"))}</div>
      <div>Case dir</div><div><code>{escape(str(new.get("case_dir") or ""))}</code></div>
    </div>
    {attempts_html}
    <details><summary>Old SVG text</summary><pre class="svg-box">{escape(old_svg_text)}</pre></details>
    <details><summary>New SVG text</summary><pre class="svg-box">{escape(new_svg_text)}</pre></details>
  </div>
</section>
"""


def _image_panel(label: str, path_value: Any, web_src: Any = "") -> str:
    path = Path(str(path_value or ""))
    src = str(web_src or "")
    if not path.is_file() or not src:
        body = "<div class=\"badge failed\">missing</div>"
    else:
        body = f'<a href="{escape(src)}"><img src="{escape(src)}" loading="lazy"></a>'
    return f'<div class="panel"><h3>{escape(label)}</h3>{body}</div>'


def _render_attempts(attempts: list[Any]) -> str:
    if not attempts:
        return ""
    rows = []
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            continue
        usage = attempt.get("usage") if isinstance(attempt.get("usage"), Mapping) else {}
        rows.append(
            "<tr>"
            f"<td>{escape(str(attempt.get('attempt') or ''))}</td>"
            f"<td>{escape(str(attempt.get('semantic_svg_bytes') or 0))}</td>"
            f"<td>{escape(str(attempt.get('iteration_log_bytes') or 0))}</td>"
            f"<td>{escape(str(attempt.get('internal_iteration_svgs') or 0))} SVG / {escape(str(attempt.get('internal_iteration_pngs') or 0))} PNG</td>"
            f"<td>{escape(str(attempt.get('native_backfill_candidate_count') or 0))}</td>"
            f"<td><code>{escape(json.dumps(usage, ensure_ascii=False))}</code></td>"
            "</tr>"
        )
    return (
        "<table class=\"attempts\"><thead><tr>"
        "<th>Attempt</th><th>semantic.svg bytes</th><th>iteration log bytes</th>"
        "<th>internal iterations</th><th>backfill candidates</th><th>usage</th>"
        "</tr></thead><tbody>"
        + "\n".join(rows)
        + "</tbody></table>"
    )


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_json_optional(path: Path) -> Any:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _metadata_text(payload: Any, key: str) -> str:
    if isinstance(payload, Mapping):
        value = payload.get(key)
        return str(value) if value else ""
    return ""


def _source_key(value: Any) -> str:
    path = Path(str(value or ""))
    parts = path.parts
    if len(parts) >= 3:
        return "/".join(parts[-3:])
    return path.name


def _best_file(value: Any, fallback: Path) -> str:
    path = Path(str(value or ""))
    if path.is_file():
        return str(path)
    if fallback.is_file():
        return str(fallback)
    return ""


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def _count_files(path: Path, pattern: str) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for _ in path.rglob(pattern))


def _text_file_contains(path: Path, needle: str) -> bool:
    if not path.is_file():
        return False
    return needle in path.read_text(encoding="utf-8", errors="ignore")


def _read_text_sample(path: Path, limit: int = 120_000) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n... truncated ..."


def _format_seconds(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return ""
    minutes, sec = divmod(seconds, 60)
    return f"{int(minutes)}m {sec:04.1f}s"


def _link(path_value: Any) -> str:
    path = Path(str(path_value or ""))
    if not path.is_file():
        return ""
    return f'<a href="{escape(_uri(path))}"><code>{escape(str(path))}</code></a>'


def _uri(path: Path) -> str:
    return path.expanduser().resolve().as_uri()


if __name__ == "__main__":
    main()
