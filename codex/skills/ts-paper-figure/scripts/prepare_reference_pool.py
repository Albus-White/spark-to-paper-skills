#!/usr/bin/env python3
"""Prepare a resource-bounded candidate pool from a user-owned reference corpus.

Lexical/type hints are non-authoritative. The main model reranks the emitted pool by domain and visual
intent, inspects actual images where useful, and selects references only when they improve the figure.
This utility does not impose a semantic Top-K decision or a default pool size.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _dotenv  # noqa: E402,F401  -- load PAPERBANANA_CACHE_ROOT from the unified .env

TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)
INTENT_TERMS = {
    "architecture": {"architecture", "framework", "overview", "network", "model"},
    "pipeline": {"pipeline", "workflow", "process", "stage", "procedure"},
    "module": {"module", "block", "component", "layer", "detail"},
    "loop": {"loop", "feedback", "iterative", "cycle", "closed"},
    "concept": {"concept", "illustration", "geometry", "manifold", "mechanism"},
    "plot": {"plot", "chart", "curve", "bar", "heatmap", "scatter", "radar"},
}


def tokens(value: Any) -> list[str]:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return TOKEN_RE.findall(str(value or "").lower())


def intent_classes(value: Any) -> set[str]:
    toks = set(tokens(value))
    return {name for name, terms in INTENT_TERMS.items() if toks & terms}


def _overlap(query: Counter[str], candidate: Counter[str]) -> float:
    if not query or not candidate:
        return 0.0
    shared = sum(min(count, candidate.get(token, 0)) for token, count in query.items())
    return shared / math.sqrt(sum(query.values()) * sum(candidate.values()))


def score_item(item: dict[str, Any], query: dict[str, Any]) -> tuple[float, dict[str, float]]:
    q_intent = Counter(tokens(query.get("visual_intent") or query.get("caption")))
    q_content = Counter(tokens(query.get("content") or query.get("methodology")))
    q_domain = Counter(tokens(query.get("domain")))
    c_intent = Counter(tokens(item.get("visual_intent") or item.get("caption")))
    c_content = Counter(tokens(item.get("content") or item.get("methodology")))
    intent_overlap = _overlap(q_intent, c_intent)
    content_overlap = _overlap(q_content, c_content)
    domain_overlap = _overlap(q_domain, c_content + c_intent)
    target_classes = intent_classes(
        " ".join(str(query.get(key) or "") for key in ("figure_type", "visual_intent", "caption"))
    )
    candidate_classes = intent_classes(item.get("visual_intent") or item.get("caption"))
    class_match = 1.0 if target_classes and target_classes & candidate_classes else 0.0
    class_conflict = 1.0 if target_classes and candidate_classes and not (target_classes & candidate_classes) else 0.0
    parts = {
        "visual_intent": round(intent_overlap, 6),
        "methodology": round(content_overlap, 6),
        "domain": round(domain_overlap, 6),
        "intent_class_match": class_match,
        "intent_class_conflict": class_conflict,
    }
    score = 5.0 * class_match - 2.5 * class_conflict + 4.0 * intent_overlap + 1.5 * content_overlap + domain_overlap
    return score, parts


def locate_ref_json(explicit: str, task: str) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.is_file() else None
    cache_root = Path(os.path.expandvars(os.environ.get(
        "PAPERBANANA_CACHE_ROOT", str(Path.home() / ".cache" / "ts-paper-figure")
    ))).expanduser()
    # The normal runtime is deliberately cache-owned.  A caller may still pass --ref-json for a
    # custom corpus, but no path into a PaperBanana source checkout is discovered implicitly.
    roots = [cache_root / "PaperBananaBench"]
    for root in roots:
        candidate = root / task / "ref.json"
        if candidate.is_file():
            return candidate.resolve()
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="JSON with content, visual_intent, domain, figure_type")
    parser.add_argument("--ref-json", default="", help="PaperBananaBench/<task>/ref.json")
    parser.add_argument("--task", choices=("diagram", "plot"), default="diagram")
    parser.add_argument("--limit", type=int, required=True,
                        help="model-selected inspection cap from the user resource envelope; <=0 keeps all")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    query = json.loads(Path(args.query).read_text(encoding="utf-8"))
    ref_json = locate_ref_json(args.ref_json, args.task)
    if ref_json is None:
        print(json.dumps({
            "ok": False,
            "error": "PaperBananaBench ref.json not found",
            "next": "run setup_reference_corpus.py, or pass --ref-json for an explicit user-owned corpus",
        }))
        return 1
    pool = json.loads(ref_json.read_text(encoding="utf-8"))
    if not isinstance(pool, list):
        print(json.dumps({"ok": False, "error": "ref.json must contain a list"}))
        return 1

    ranked = []
    for index, item in enumerate(pool):
        if not isinstance(item, dict):
            continue
        score, parts = score_item(item, query)
        image = item.get("path_to_gt_image") or item.get("image") or ""
        image_path = (ref_json.parent / image).resolve() if image else None
        ranked.append({
            "id": item.get("id") or f"ref_{index}",
            "score": round(score, 6),
            "score_parts": parts,
            "visual_intent": item.get("visual_intent") or item.get("caption") or "",
            "content": item.get("content") or item.get("methodology") or "",
            "image": str(image_path) if image_path else "",
        })
    ranked.sort(key=lambda item: (-item["score"], str(item["id"])))
    selected_pool = ranked if args.limit <= 0 else ranked[: max(args.limit, 1)]
    result = {
        "schema": "ts.figure.reference_pool.v1",
        "ok": True,
        "retriever": "paperbanana-full-paired-example-pool",
        "ref_json": str(ref_json),
        "query": query,
        "candidate_count": len(pool),
        "candidate_pool": selected_pool,
        "instruction": "The main model must semantically rerank the emitted pool, inspect actual images where useful, and select only references that materially inform this figure.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out), "candidate_pool": len(result["candidate_pool"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
