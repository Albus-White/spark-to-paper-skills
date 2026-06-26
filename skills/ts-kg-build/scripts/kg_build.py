#!/usr/bin/env python3
"""kg_build.py — assemble the research-pattern knowledge graph (deterministic, no LLM).

Combines: per-paper extractions (Claude wrote the story-first pattern fields), the cluster
assignments (cluster.py), and the per-cluster names/summaries (Claude wrote these), into the
node/edge JSON shaped EXACTLY like the product's built KGs (kg_ts/), so ts-idea2story's recall
reads it unchanged.

Inputs:
  --papers papers.jsonl    one obj/paper: {paper_id,title,abstract,keywords,authors,year,venue,
                           doi,url,pages,num_references, base_problem,solution_pattern,story,
                           application,idea, domain,sub_domains[], review_score?}
  --clusters clusters.json (cluster.py output; cluster members are paper_ids)
  --cluster-meta meta.json {cluster_id:{name,summary,llm_enhanced_summary,tier}}  (Claude; optional)
  --domain NAME            the KG domain label (e.g. ts)
  --out DIR               writes nodes_*.json, edges.json, knowledge_graph_stats.json, manifest

Edges: uses_pattern(paper->pattern,quality) | in_domain(paper->domain) | belongs_to(pattern->domain)
       | works_well_in(pattern->domain, effectiveness=avg_quality-baseline, confidence=min(freq/20,1))
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path

REL = {"uses_pattern", "in_domain", "belongs_to", "works_well_in"}


def md5(s):
    return hashlib.md5(str(s).strip().lower().encode()).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", required=True)
    ap.add_argument("--clusters", required=True)
    ap.add_argument("--cluster-meta", default="")
    ap.add_argument("--domain", default="general")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    papers = {p["paper_id"]: p for p in (json.loads(l) for l in open(a.papers) if l.strip())}
    clusters = json.load(open(a.clusters))["clusters"]
    meta = json.load(open(a.cluster_meta)) if a.cluster_meta and Path(a.cluster_meta).exists() else {}

    PAPER_PATTERN_QUALITY_DEFAULT = 0.7

    nodes_paper, nodes_idea, nodes_pattern, edges = [], [], [], []
    idea_seen = {}
    domain_quality = defaultdict(list)
    paper_of_pattern = {}

    for p in papers.values():
        nodes_paper.append({k: p.get(k, "") for k in
            ["paper_id", "title", "abstract", "keywords", "authors", "year", "venue",
             "doi", "url", "pages", "num_references"]} | {"domain": p.get("domain", a.domain)})
        edges.append({"source": p["paper_id"], "target": p.get("domain", a.domain), "relation": "in_domain"})
        idea = (p.get("idea") or "").strip()
        if idea:
            iid = "idea_" + md5(idea)
            if iid not in idea_seen:
                idea_seen[iid] = {"idea_id": iid, "text": idea, "paper_id": p["paper_id"],
                                  "domain": p.get("domain", a.domain)}
    nodes_idea = list(idea_seen.values())

    for ci, c in enumerate(clusters):
        members = [m for m in c["members"] if m in papers]
        if not members:
            continue
        pid = f"pattern_{ci}"
        cm = meta.get(c["cluster_id"], {}) or meta.get(pid, {})
        doms = Counter(papers[m].get("domain", a.domain) for m in members)
        subdoms = sorted({s for m in members for s in (papers[m].get("sub_domains") or [])})
        dom = doms.most_common(1)[0][0]
        nodes_pattern.append({
            "pattern_id": pid,
            "name": cm.get("name", f"pattern {ci}"),
            "size": len(members),
            "domain": dom,
            "sub_domains": subdoms,
            "summary": cm.get("summary", ""),
            "llm_enhanced_summary": cm.get("llm_enhanced_summary", cm.get("summary", "")),
            "tier": cm.get("tier", ""),
            "coherence": c.get("coherence"),
            "exemplar_count": len(c.get("exemplars", [])),
            "exemplar_paper_ids": [e for e in c.get("exemplars", []) if e in papers],
        })
        for m in members:
            q = float(papers[m].get("review_score", PAPER_PATTERN_QUALITY_DEFAULT))
            edges.append({"source": m, "target": pid, "relation": "uses_pattern", "quality": round(q, 3)})
            domain_quality[dom].append(q)
        edges.append({"source": pid, "target": dom, "relation": "belongs_to"})

    # works_well_in: pattern effectiveness = its avg quality minus the domain baseline (a lift)
    dom_baseline = {d: (sum(v) / len(v) if v else 0.0) for d, v in domain_quality.items()}
    for pat in nodes_pattern:
        members = [e["source"] for e in edges if e["relation"] == "uses_pattern" and e["target"] == pat["pattern_id"]]
        qs = [float(papers[m].get("review_score", PAPER_PATTERN_QUALITY_DEFAULT)) for m in members]
        if qs:
            eff = round((sum(qs) / len(qs)) - dom_baseline.get(pat["domain"], 0.0), 3)
            edges.append({"source": pat["pattern_id"], "target": pat["domain"], "relation": "works_well_in",
                          "effectiveness": eff, "confidence": round(min(len(qs) / 20.0, 1.0), 3)})

    nodes_domain = [{"domain": d, "paper_count": int(c)} for d, c in
                    Counter(p.get("domain", a.domain) for p in papers.values()).items()]

    stats = {"domain": a.domain,
             "counts": {"papers": len(nodes_paper), "ideas": len(nodes_idea),
                        "patterns": len(nodes_pattern), "domains": len(nodes_domain), "edges": len(edges)},
             "domain_distribution": {d["domain"]: d["paper_count"] for d in nodes_domain}}

    for name, data in [("nodes_paper", nodes_paper), ("nodes_idea", nodes_idea),
                       ("nodes_pattern", nodes_pattern), ("nodes_domain", nodes_domain),
                       ("edges", edges)]:
        json.dump(data, open(out / f"{name}.json", "w"), ensure_ascii=False, indent=1)
    json.dump(stats, open(out / "knowledge_graph_stats.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "out": str(out), **stats["counts"]}))


if __name__ == "__main__":
    main()
