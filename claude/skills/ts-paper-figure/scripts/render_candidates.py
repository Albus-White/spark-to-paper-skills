#!/usr/bin/env python3
"""Render a PaperBanana-style batch of independent figure candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen_image  # noqa: E402


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _prompt(base: Path, item: dict) -> str:
    if str(item.get("prompt") or "").strip():
        return str(item["prompt"]).strip()
    prompt_file = str(item.get("prompt_file") or "").strip()
    if not prompt_file:
        raise ValueError("candidate needs prompt or prompt_file")
    return _resolve(base, prompt_file).read_text(encoding="utf-8").strip()


def _candidate_spec_hash(base: Path, item: dict) -> str:
    refs = []
    for value in item.get("render_references") or []:
        path = _resolve(base, str(value))
        refs.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                     if path.is_file() else "MISSING"})
    payload = {
        "id": item.get("id"), "composition_strategy": item.get("composition_strategy"),
        "prompt": _prompt(base, item), "references": refs,
        "require_reference": bool(item.get("require_reference", False)),
        "model": os.environ.get("TS_FIG_MODEL", "gpt-image-2"),
        "api_style": os.environ.get("TS_FIG_API_STYLE", "images"),
        "size": os.environ.get("TS_FIG_SIZE", "1536x1024"),
        "quality": os.environ.get("TS_FIG_QUALITY", "high"),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _render_one(base: Path, out_dir: Path, item: dict, retries: int) -> dict:
    candidate_id = str(item.get("id") or "").strip()
    if not candidate_id or "/" in candidate_id or "\\" in candidate_id:
        raise ValueError(f"unsafe candidate id: {candidate_id!r}")
    refs = [_resolve(base, str(path)) for path in (item.get("render_references") or [])]
    output = out_dir / f"{candidate_id}.png"
    result = gen_image.render(
        _prompt(base, item),
        output,
        retries=retries,
        references=[str(path) for path in refs],
        require_reference=bool(item.get("require_reference", False)),
    )
    record = {
        "id": candidate_id,
        "ok": bool(result.get("ok")),
        "output": str(output),
        "render_path": result.get("path", ""),
        "size": result.get("size"),
        "references": [str(path) for path in refs],
        "error": result.get("error", ""),
    }
    if output.is_file():
        record["bytes"] = output.stat().st_size
        record["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True, help="candidate_prompts.json")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-workers", type=int, required=True,
                        help="explicit concurrency allocation from the user resource envelope")
    parser.add_argument("--safety-cap", type=int, required=True,
                        help="run-specific candidate ceiling derived from the user resource envelope")
    parser.add_argument("--retries", type=int, required=True,
                        help="per-candidate retry allocation from the user resource envelope")
    parser.add_argument("--batch-retry-rounds", type=int, required=True,
                        help="model-selected failed-batch retry allocation")
    parser.add_argument("--batch-backoff", type=float, required=True,
                        help="model-selected seconds between retry waves")
    args = parser.parse_args()

    budget_errors = []
    if not 1 <= args.max_workers <= 32:
        budget_errors.append("max-workers must be between 1 and 32")
    if not 1 <= args.safety_cap <= 10_000:
        budget_errors.append("safety-cap exceeds the executor runaway-protection ceiling")
    if not 1 <= args.retries <= 5:
        budget_errors.append("retries must be between 1 and 5")
    if not 0 <= args.batch_retry_rounds <= 3:
        budget_errors.append("batch-retry-rounds must be between 0 and 3")
    if not 0 <= args.batch_backoff <= 60:
        budget_errors.append("batch-backoff must be between 0 and 60 seconds")
    if budget_errors:
        print(json.dumps({"ok": False, "error": "; ".join(budget_errors)}))
        return 2

    source = Path(args.candidates).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list) or not candidates:
        print(json.dumps({"ok": False, "error": "candidates JSON has no candidates list"}))
        return 2
    if len(candidates) > args.safety_cap:
        print(json.dumps({"ok": False, "error": "candidate list exceeds the run-specific safety-cap"}))
        return 2
    ids = [str(item.get("id") or "") for item in candidates if isinstance(item, dict)]
    if len(ids) != len(candidates) or any(not value for value in ids) or len(ids) != len(set(ids)):
        print(json.dumps({"ok": False, "error": "candidate ids must be non-empty and unique"}))
        return 2

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate_by_id = {str(item["id"]): item for item in candidates if isinstance(item, dict)}
    candidate_specs = {candidate_id: _candidate_spec_hash(source.parent, item)
                       for candidate_id, item in candidate_by_id.items()}
    latest: dict[str, dict] = {}
    histories: dict[str, list[dict]] = {candidate_id: [] for candidate_id in candidate_by_id}
    manifest_path = out_dir / "render_manifest.json"
    if manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        previous_specs = (previous.get("candidate_specs") or {}) if isinstance(previous, dict) else {}
        for record in previous.get("results", []) if isinstance(previous, dict) else []:
            if not isinstance(record, dict) or not record.get("ok"):
                continue
            candidate_id = str(record.get("id") or "")
            output = Path(str(record.get("output") or ""))
            expected_hash = str(record.get("sha256") or "")
            if (candidate_id in candidate_by_id and previous_specs.get(candidate_id) == candidate_specs[candidate_id]
                    and output.is_file() and expected_hash
                    and hashlib.sha256(output.read_bytes()).hexdigest() == expected_hash):
                carried = dict(record)
                carried["resumed"] = True
                latest[candidate_id] = carried
                histories[candidate_id] = list(record.get("attempt_history") or [])
    pending = sorted(set(candidate_by_id) - set(latest))
    for batch_round in range(args.batch_retry_rounds + 1):
        if not pending:
            break
        workers = max(1, min(len(pending), args.max_workers // (2 ** batch_round) or 1))
        if batch_round and args.batch_backoff > 0:
            time.sleep(min(args.batch_backoff * batch_round, 30.0))
        wave = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_render_one, source.parent, out_dir, candidate_by_id[candidate_id],
                                args.retries): candidate_id
                for candidate_id in pending
            }
            for future in as_completed(futures):
                candidate_id = futures[future]
                try:
                    record = future.result()
                except Exception as exc:  # noqa: BLE001 - batch boundary records every failure
                    record = {"id": candidate_id, "ok": False,
                              "error": f"{type(exc).__name__}: {exc}"}
                record["batch_round"] = batch_round
                record["batch_workers"] = workers
                histories[candidate_id].append(dict(record))
                latest[candidate_id] = record
                wave.append(record)
        pending = sorted(record["id"] for record in wave if not record.get("ok"))

    records = []
    for candidate_id in sorted(candidate_by_id):
        record = dict(latest.get(candidate_id) or {"id": candidate_id, "ok": False,
                                                   "error": "candidate was not attempted"})
        record["attempt_history"] = histories[candidate_id]
        records.append(record)
    manifest = {
        "schema": "ts.figure.render_manifest.v1",
        "label": payload.get("label", ""),
        "requested": len(candidates),
        "succeeded": sum(bool(item.get("ok")) for item in records),
        "model": os.environ.get("TS_FIG_MODEL", "gpt-image-2"),
        "api_style": os.environ.get("TS_FIG_API_STYLE", "images"),
        "adaptive_retry_rounds": args.batch_retry_rounds,
        "candidate_specs": candidate_specs,
        "results": records,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = manifest["succeeded"] == manifest["requested"]
    print(json.dumps({"ok": ok, "manifest": str(manifest_path), "succeeded": manifest["succeeded"]}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
