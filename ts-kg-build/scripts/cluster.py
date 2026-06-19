#!/usr/bin/env python3
"""cluster.py — deterministic clustering over embeddings (irreducible vector math).

The product used UMAP->HDBSCAN; those aren't always installed, so this uses scikit-learn
AgglomerativeClustering with a cosine distance threshold (graceful, dependency-light) and
falls back to KMeans if needed. For each cluster it reports the members, a per-member
membership score (cosine to the cluster centroid), the cluster coherence (mean intra-cluster
centroid cosine), and the exemplars (the highest-membership members) — exactly the signals
Claude needs to NAME and SUMMARIZE each cluster.

Usage:
  python3 cluster.py --emb kg/pattern_emb.npy --meta kg/pattern_meta.jsonl --out kg/clusters.json
                     [--threshold 0.45] [--min-size 2]
Output kg/clusters.json: {"clusters":[{"cluster_id","members":[id...],"exemplars":[id...],
  "membership":{id:score},"coherence":float,"size":int}], "noise":[id...], "params":{...}}
"""
from __future__ import annotations
import argparse, json, sys
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emb", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=0.45, help="cosine distance merge threshold")
    ap.add_argument("--min-size", type=int, default=2)
    a = ap.parse_args()

    X = np.load(a.emb).astype(np.float64)
    ids = [json.loads(l)["id"] for l in open(a.meta) if l.strip()]
    if len(ids) != X.shape[0]:
        print(json.dumps({"ok": False, "error": f"meta/emb mismatch {len(ids)} vs {X.shape[0]}"})); sys.exit(2)
    # L2-normalize so dot == cosine
    Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    n = Xn.shape[0]
    if n < 3:
        labels = np.zeros(n, dtype=int)
    else:
        from sklearn.cluster import AgglomerativeClustering
        try:
            model = AgglomerativeClustering(n_clusters=None, metric="cosine",
                                            linkage="average", distance_threshold=a.threshold)
            labels = model.fit_predict(Xn)
        except Exception:
            from sklearn.cluster import KMeans
            k = max(2, min(int(np.sqrt(n / 2)) + 1, n - 1))
            labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(Xn)

    clusters, noise = [], []
    for lab in sorted(set(labels.tolist())):
        idx = np.where(labels == lab)[0]
        members = [ids[i] for i in idx]
        if len(idx) < a.min_size:
            noise.extend(members); continue
        centroid = Xn[idx].mean(axis=0)
        centroid /= (np.linalg.norm(centroid) + 1e-9)
        sims = Xn[idx] @ centroid
        order = idx[np.argsort(-sims)]
        membership = {ids[i]: round(float(Xn[i] @ centroid), 4) for i in idx}
        clusters.append({
            "cluster_id": f"c{len(clusters)}",
            "size": int(len(idx)),
            "members": members,
            "exemplars": [ids[i] for i in order[:min(5, len(order))]],
            "membership": membership,
            "coherence": round(float(sims.mean()), 4),
        })
    clusters.sort(key=lambda c: (-c["size"], -c["coherence"]))
    out = {"ok": True, "n": n, "n_clusters": len(clusters), "n_noise": len(noise),
           "clusters": clusters, "noise": noise,
           "params": {"threshold": a.threshold, "min_size": a.min_size, "algo": "agglomerative_cosine"}}
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "n": n, "n_clusters": len(clusters), "n_noise": len(noise), "out": a.out}))


if __name__ == "__main__":
    main()
