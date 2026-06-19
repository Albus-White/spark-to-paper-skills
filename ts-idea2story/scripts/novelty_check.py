#!/usr/bin/env python3
"""novelty_check.py — anti-collision novelty gate for a generated story (step 7, script-assisted).

Embeds the story.json text via the existing TS_EMBED_* endpoint (same embed_one() pattern as
kg_recall.py) and cosine-compares it against an available reference set:
  - PREFERRED: the abstracts in retrieved_papers.json (the actual prior works the story departs
    from) — embedded on the fly, the truest anti-collision signal.
  - ELSE: the prebuilt PATTERN index kg/pattern_emb.npy (collision with reusable skeletons; the
    0.88/0.82 bands were calibrated against a paper corpus, so read a pattern-index hit loosely).

Emits novelty_report.json:
  {max_similarity, risk_level, threshold_high:0.88, threshold_medium:0.82, top_similar, verdict, basis}
Bands carried verbatim from the source: >=0.88 high -> pivot to a reserved differentiating pattern;
>=0.82 medium -> warn; cap pivots at 2.

GRACEFUL DEGRADE: with no TS_EMBED_* endpoint configured (or no reference set), this exits 0 with a
report whose basis="unconfigured" and a clear "lexical/judgment only — not a semantic guarantee"
note. It NEVER hard-fails a no-endpoint run — the semantic check is honestly optional upstream.

    python3 novelty_check.py <workdir> [--kg <kg_dir>]

Reads <workdir>/{story.json, retrieved_papers.json} and optionally <kg_dir>/pattern_emb.npy +
pattern_meta.jsonl + pattern_manifest.json. Writes <workdir>/novelty_report.json. stdlib + numpy.
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.request
from pathlib import Path

THRESHOLD_HIGH = 0.88     # source NOVELTY_HIGH_TH   -> high risk, pivot
THRESHOLD_MEDIUM = 0.82   # source NOVELTY_MEDIUM_TH -> medium risk, warn
MAX_PIVOTS = 2            # source NOVELTY_MAX_PIVOTS


def embed_one(text):
    """Embed a single text via the configured endpoint; (None, None) if unconfigured/failed.

    Mirrors kg_recall.embed_one() so both scripts share one endpoint contract (TS_EMBED_*)."""
    model = os.environ.get("TS_EMBED_MODEL", "").strip()
    key = os.environ.get("TS_EMBED_API_KEY", "").strip()
    base = os.environ.get("TS_EMBED_BASE_URL", "").strip().rstrip("/")
    if not (model and key and base):
        return None, None
    try:
        req = urllib.request.Request(f"{base}/embeddings",
            data=json.dumps({"model": model, "input": [text]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            import numpy as np
            v = np.asarray(json.loads(r.read().decode())["data"][0]["embedding"], dtype=np.float32)
            return v, model
    except Exception:
        return None, None


def story_text(story):
    """Flatten the 8 story fields into one comparable blob."""
    parts = []
    for k in ("title", "abstract", "problem_framing", "gap_pattern", "solution",
              "method_skeleton", "experiments_plan"):
        v = story.get(k)
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        if v:
            parts.append(str(v))
    claims = story.get("innovation_claims", [])
    if isinstance(claims, list):
        parts.extend(str(c) for c in claims if c)
    elif claims:
        parts.append(str(claims))
    return "\n".join(parts).strip()


def degrade(workdir, note, basis="unconfigured"):
    """Write a degraded (no-semantic-guarantee) report and exit 0 — never hard-fail."""
    report = {
        "ok": True, "basis": basis,
        "max_similarity": None, "risk_level": "unknown",
        "threshold_high": THRESHOLD_HIGH, "threshold_medium": THRESHOLD_MEDIUM,
        "top_similar": [], "verdict": "lexical/judgment only — not a semantic guarantee",
        "note": note, "max_pivots": MAX_PIVOTS,
    }
    (workdir / "novelty_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({"ok": True, "basis": basis, "risk_level": "unknown", "note": note}))
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--kg", default=None, help="kg dir holding pattern_emb.npy (reference fallback)")
    a = ap.parse_args()
    workdir = Path(a.workdir)

    story_path = workdir / "story.json"
    if not story_path.exists():
        # No story to check — degrade rather than crash (step 7 may run before emit on some paths).
        degrade(workdir, "story.json not found — nothing to compare; semantic novelty check skipped.")
    story = json.loads(story_path.read_text())
    s_text = story_text(story)
    if not s_text:
        degrade(workdir, "story.json has no comparable text; semantic novelty check skipped.")

    # Embed the story (the single irreducible endpoint call). No endpoint -> graceful degrade.
    sv, model = embed_one(s_text)
    if sv is None:
        degrade(workdir, "no TS_EMBED_* endpoint configured — run the lexical/judgment check against "
                         "the recalled exemplars instead; not a semantic guarantee.")

    import numpy as np

    def normalize(v):
        return v / (float(np.linalg.norm(v)) + 1e-9)

    svn = normalize(sv)

    # Build the reference set: PREFER retrieved_papers.json abstracts (embed on the fly).
    refs = []            # list of (label, vector)
    basis = None
    rp_path = workdir / "retrieved_papers.json"
    if rp_path.exists():
        try:
            rp = json.loads(rp_path.read_text())
            papers = rp.get("papers", []) if isinstance(rp, dict) else (rp if isinstance(rp, list) else [])
        except Exception:
            papers = []
        for p in papers:
            abs = (p.get("abstract") or "").strip()
            # skip fabricated/missing abstracts — they carry no real signal
            if not abs or p.get("abstract_source") == "missing":
                continue
            pv, _ = embed_one(f"{p.get('title','')}\n{abs}")
            if pv is not None:
                label = p.get("title") or p.get("paper_id") or "(untitled)"
                refs.append((label, normalize(pv)))
        if refs:
            basis = "semantic(cosine) vs retrieved_papers abstracts"

    # ELSE fall back to the prebuilt PATTERN index.
    if not refs:
        kg = Path(a.kg) if a.kg else None
        idx_npy = kg / "pattern_emb.npy" if kg else None
        idx_meta = kg / "pattern_meta.jsonl" if kg else None
        idx_man = kg / "pattern_manifest.json" if kg else None
        if idx_npy and idx_npy.exists() and idx_meta and idx_meta.exists():
            man = json.loads(idx_man.read_text()) if (idx_man and idx_man.exists()) else {}
            if man and man.get("model") != model:
                # refuse to mix embedding spaces (same guard as kg_recall)
                degrade(workdir, f"pattern index built with model {man.get('model')!r} != story model "
                                 f"{model!r}; cannot compare semantically — judgment only.")
            M = np.load(idx_npy)
            ids = [json.loads(l)["id"] for l in idx_meta.read_text().splitlines() if l.strip()]
            Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
            sims = Mn @ svn
            refs = [(ids[i] if i < len(ids) else f"pattern[{i}]", None) for i in range(len(sims))]
            # carry sims directly for the pattern-index path
            sim_vals = [float(x) for x in sims]
            basis = "semantic(cosine) vs kg/pattern_emb.npy (pattern-collision; bands read loosely)"
        else:
            degrade(workdir, "no reference set: retrieved_papers.json has no real abstracts and no "
                             "kg/pattern_emb.npy index — semantic novelty check skipped.")

    # Compute similarities.
    if basis and basis.startswith("semantic(cosine) vs kg"):
        scored = list(zip([lbl for lbl, _ in refs], sim_vals))
    else:
        scored = [(lbl, float(np.dot(svn, rv))) for lbl, rv in refs]

    scored.sort(key=lambda kv: -kv[1])
    max_sim = scored[0][1] if scored else 0.0
    if max_sim >= THRESHOLD_HIGH:
        risk = "high"
        verdict = (f"high collision (max_similarity={max_sim:.3f} >= {THRESHOLD_HIGH}) — pivot to a "
                   f"more differentiating reserved pattern and re-tell (cap {MAX_PIVOTS} pivots).")
    elif max_sim >= THRESHOLD_MEDIUM:
        risk = "medium"
        verdict = (f"medium similarity (max_similarity={max_sim:.3f} >= {THRESHOLD_MEDIUM}) — warn; "
                   f"sharpen the differentiating angle.")
    else:
        risk = "low"
        verdict = f"low collision (max_similarity={max_sim:.3f}) — novelty signal acceptable."

    report = {
        "ok": True, "basis": basis,
        "max_similarity": round(max_sim, 5), "risk_level": risk,
        "threshold_high": THRESHOLD_HIGH, "threshold_medium": THRESHOLD_MEDIUM,
        "top_similar": [{"ref": lbl, "similarity": round(s, 5)} for lbl, s in scored[:5]],
        "verdict": verdict, "max_pivots": MAX_PIVOTS,
    }
    (workdir / "novelty_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({"ok": True, "basis": basis, "max_similarity": report["max_similarity"],
                      "risk_level": risk}))


if __name__ == "__main__":
    main()
