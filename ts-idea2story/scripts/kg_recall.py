#!/usr/bin/env python3
"""kg_recall.py — retrieve the Top-K candidate research PATTERNS for an idea (for Claude to reason over).

Deterministic retrieval only (vector math + graph hops); the RANKING JUDGEMENT is Claude's job —
this just surfaces candidates. Two-stage like the product: Jaccard coarse-filter, then (if an
embedding endpoint + a prebuilt pattern index exist) cosine fine-rank fused by RRF, plus a graph
boost (idea -> lexically-near papers -> the patterns they use). Degrades gracefully: with no
embeddings it runs LEXICAL-ONLY and says so (honest: "not semantic similarity").

    python3 kg_recall.py --idea "<text>" --kg <kg_dir> --out recall.json [--topk 8]

Reads <kg_dir>/{nodes_pattern.json,nodes_paper.json,edges.json} and optionally
<kg_dir>/pattern_{emb.npy,meta.jsonl,manifest.json}. Embedding config = TS_EMBED_* (see embed.py).
"""
from __future__ import annotations

import _dotenv  # noqa: F401  -- auto-load unified .env for API keys
import argparse, json, os, re, sys, urllib.request
from pathlib import Path

STOP = set("the a an of for to in on and or with from by is are be this that we our using based via "
           "approach method model framework toward using novel new paper study via into over under".split())


def toks(s):
    return {w for w in re.split(r"[^a-z0-9]+", str(s).lower()) if len(w) > 2 and w not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 0.0


def embed_one(text):
    """Embed a single text via the configured endpoint.

    Returns (vector, model) on success, else (None, reason): reason is "unconfigured"
    when TS_EMBED_* is unset (intentional lexical run) or "error:<type>" when a
    configured endpoint fails (outage/bad key) — so the caller can tell the two apart.
    """
    model = os.environ.get("TS_EMBED_MODEL", "").strip()
    key = os.environ.get("TS_EMBED_API_KEY", "").strip()
    base = os.environ.get("TS_EMBED_BASE_URL", "").strip().rstrip("/")
    if not (model and key and base):
        return None, "unconfigured"
    try:
        req = urllib.request.Request(f"{base}/embeddings",
            data=json.dumps({"model": model, "input": [text]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            import numpy as np
            v = np.asarray(json.loads(r.read().decode())["data"][0]["embedding"], dtype=np.float32)
            return v, model
    except Exception as e:
        return None, f"error:{type(e).__name__}"


def rrf(rank_lists, k=60):
    score = {}
    for ranks in rank_lists:
        for rank, key in enumerate(ranks):
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank + 1)
    return score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--idea", required=True)
    ap.add_argument("--kg", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--topk", type=int, default=8)
    a = ap.parse_args()
    kg = Path(a.kg)
    patterns = json.loads((kg / "nodes_pattern.json").read_text())
    papers = {p["paper_id"]: p for p in json.loads((kg / "nodes_paper.json").read_text())}
    edges = json.loads((kg / "edges.json").read_text()) if (kg / "edges.json").exists() else []
    idea_t = toks(a.idea)

    # pattern text = name + summary + exemplar titles
    def ptext(p):
        ex = " ".join(papers.get(e, {}).get("title", "") for e in p.get("exemplar_paper_ids", []))
        return f"{p.get('name','')} {p.get('llm_enhanced_summary') or p.get('summary','')} {ex}"

    jac = {p["pattern_id"]: jaccard(idea_t, toks(ptext(p))) for p in patterns}
    jac_rank = [pid for pid, _ in sorted(jac.items(), key=lambda kv: -kv[1])]
    rank_lists = [jac_rank]
    basis = "lexical(jaccard)"

    # optional embedding fine-rank
    embed_fail = None  # set to the reason string when a CONFIGURED endpoint errored
    idx_npy = kg / "pattern_emb.npy"; idx_meta = kg / "pattern_meta.jsonl"; idx_man = kg / "pattern_manifest.json"
    if idx_npy.exists() and idx_meta.exists():
        v, model = embed_one(a.idea)            # on success model=name; on failure model=reason ("unconfigured"/"error:..")
        if v is None and isinstance(model, str) and model.startswith("error:"):
            embed_fail = model
        man = json.loads(idx_man.read_text()) if idx_man.exists() else {}
        if v is not None and (not man or man.get("model") == model):   # refuse to mix embedding spaces (reads v first)
            import numpy as np
            M = np.load(idx_npy)
            order_ids = [json.loads(l)["id"] for l in open(idx_meta) if l.strip()]
            Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
            vn = v / (np.linalg.norm(v) + 1e-9)
            sims = Mn @ vn
            cos_rank = [order_ids[i] for i in np.argsort(-sims)]
            rank_lists.append(cos_rank)
            basis = "semantic(cosine)+lexical(jaccard,RRF)"

    # graph boost: idea -> top lexically-near papers -> the patterns they use
    psim = {pid: jaccard(idea_t, toks(p.get("title", "") + " " + p.get("abstract", ""))) for pid, p in papers.items()}
    near_papers = {pid for pid, _ in sorted(psim.items(), key=lambda kv: -kv[1])[:8]}
    via = {}
    for e in edges:
        if e.get("relation") == "uses_pattern" and e.get("source") in near_papers:
            via[e["target"]] = via.get(e["target"], 0.0) + 0.15

    fused = rrf(rank_lists)
    for pid, b in via.items():
        fused[pid] = fused.get(pid, 0.0) + b

    ranked = sorted(patterns, key=lambda p: -fused.get(p["pattern_id"], 0.0))[:a.topk]
    out = {"ok": True, "idea": a.idea, "score_basis": basis, "n_patterns_total": len(patterns),
           "candidates": [{
               "pattern_id": p["pattern_id"], "name": p.get("name"),
               "summary": p.get("llm_enhanced_summary") or p.get("summary"),
               "domain": p.get("domain"), "sub_domains": p.get("sub_domains", []),
               "size": p.get("size"), "tier": p.get("tier", ""),
               "score": round(fused.get(p["pattern_id"], 0.0), 5),
               "exemplar_paper_ids": p.get("exemplar_paper_ids", []),
               "exemplar_titles": [papers.get(e, {}).get("title", "") for e in p.get("exemplar_paper_ids", [])],
           } for p in ranked]}
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    if embed_fail:
        note = (f"LEXICAL FALLBACK — embedding endpoint configured but FAILED ({embed_fail}); "
                "semantic recall did NOT run")
    elif basis.startswith("lexical"):
        note = "LEXICAL ONLY — not semantic"
    else:
        note = "semantic"
    print(json.dumps({"ok": True, "score_basis": basis, "returned": len(ranked), "note": note}))


if __name__ == "__main__":
    main()
