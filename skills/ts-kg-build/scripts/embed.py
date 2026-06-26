#!/usr/bin/env python3
"""embed.py — the irreducible embedding call (Claude cannot produce embedding vectors).

Reads a JSONL of {"id": ..., "text": ...} and writes:
  <out>_emb.npy      float32 [N, D] matrix (row i = embedding of item i)
  <out>_meta.jsonl   one {"id":...} per row, in matrix order
  <out>_manifest.json {model, dim, n, sha256}  — model+hash so recall can refuse to mix spaces

Config (user-supplied embedding endpoint, paperbanana-style — text/reasoning is Claude, only
the vector math needs an external model):
  TS_EMBED_MODEL     embedding model name   (e.g. text-embedding-3-large, bge-m3, ...)
  TS_EMBED_API_KEY   api key
  TS_EMBED_BASE_URL  OpenAI-compatible base  (e.g. https://api.openai.com/v1, https://sogenport.com/v1)
  TS_EMBED_BATCH     batch size (default 64)

Usage:  python3 embed.py --in items.jsonl --out kg/pattern
Exits non-zero (with a clear message) if the endpoint is not configured — callers should then
fall back to lexical (Jaccard) mode rather than pretend they have semantic similarity.
"""
from __future__ import annotations

import _dotenv  # noqa: F401  -- auto-load unified .env for API keys
import argparse, hashlib, json, os, sys, time, urllib.request, urllib.error
import numpy as np


def _post(url, payload, key, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def embed_texts(texts):
    model = os.environ.get("TS_EMBED_MODEL", "").strip()
    key = os.environ.get("TS_EMBED_API_KEY", "").strip()
    base = os.environ.get("TS_EMBED_BASE_URL", "").strip().rstrip("/")
    batch = int(os.environ.get("TS_EMBED_BATCH", "64"))
    miss = [n for n, v in (("TS_EMBED_MODEL", model), ("TS_EMBED_API_KEY", key),
                           ("TS_EMBED_BASE_URL", base)) if not v]
    if miss:
        print(json.dumps({"ok": False, "error": f"embeddings not configured: unset {', '.join(miss)}",
                          "hint": "fall back to lexical/Jaccard mode"}))
        sys.exit(3)
    url = f"{base}/embeddings"
    vecs = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        for attempt in range(1, 4):
            try:
                j = _post(url, {"model": model, "input": chunk}, key)
                rows = sorted(j["data"], key=lambda d: d.get("index", 0))
                vecs.extend(r["embedding"] for r in rows)
                break
            except Exception as e:
                if attempt == 3:
                    print(json.dumps({"ok": False, "error": f"embed batch {i} failed: {e}"})); sys.exit(4)
                time.sleep(3 * attempt)
    return np.asarray(vecs, dtype=np.float32), model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    items = [json.loads(l) for l in open(a.inp) if l.strip()]
    texts = [str(it.get("text", "")) for it in items]
    mat, model = embed_texts(texts)
    np.save(a.out + "_emb.npy", mat)
    with open(a.out + "_meta.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps({"id": it.get("id")}, ensure_ascii=False) + "\n")
    h = hashlib.sha256(mat.tobytes()).hexdigest()[:16]
    json.dump({"model": model, "dim": int(mat.shape[1]), "n": int(mat.shape[0]), "sha256": h},
              open(a.out + "_manifest.json", "w"), indent=1)
    print(json.dumps({"ok": True, "out": a.out, "n": int(mat.shape[0]), "dim": int(mat.shape[1]), "model": model}))


if __name__ == "__main__":
    main()
