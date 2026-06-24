#!/usr/bin/env python3
"""fetch_reference_figures.py — GROUND step FETCHER for ts-paper-figure (step 2b).

This script does NOT search the web itself. Claude (the figure stage) uses `WebSearch` — the SAME
literature-search capability the cite stage uses — to find on-topic TOP-venue papers, then passes
them here (via `--papers <claude_candidates.json>` = [{title,venue,arxiv_url}], or `--arxiv <id>
--venue <v>` for a single clear winner). For each, this fetches the paper's **MAIN / hero /
overall-method-overview** figure from ar5iv (an overview-style caption) and ONLY those — never
scattered minor figures (results/ablation/qualitative/curves/insets/sample grids) — saving them
under figures/refs/ + a <label>.candidates.json for Claude to VIEW and pick the single best,
type-matched reference. It reports each candidate's venue `tier` and a `search_again` flag (true
when the best candidate is NOT a top/mid venue, or none came back). There is **NO 'proceed without a
reference' path**: if nothing usable comes back, Claude must WebSearch again with refined queries —
grounding a free-form schematic is MANDATORY (the `check_figure_critique` gate fails grounding=none).
"""
import json, re, sys, os, argparse, urllib.request

# Venue tiers (regex over the venue/journal string, case-insensitive).
TOP = [r"transactions on geoscience and remote sensing", r"transactions on pattern analysis",
       r"international journal of computer vision", r"\bcvpr\b", r"\biccv\b", r"\beccv\b",
       r"neurips|advances in neural", r"\bicml\b", r"\biclr\b", r"isprs journal",
       r"remote sensing of environment", r"\bnature\b", r"\bscience\b"]
MID = [r"^remote sensing\b", r"geoscience and remote sensing letters", r"\bigarss\b",
       r"computer vision and image understanding", r"pattern recognition", r"\bjstars\b",
       r"\bieee access\b", r"\bicip\b", r"\bmiccai\b"]
# A MAIN figure caption talks about the overall method; a MINOR one is results/ablation/etc.
MAIN_RE = re.compile(r"(overall|framework|architecture|overview|pipeline|proposed|"
                     r"the\s+\w+\s+(?:network|model|framework))", re.I)
MINOR_RE = re.compile(r"(result|ablation|qualitative|accuracy|curve|loss\b|dataset|sample|"
                      r"visualiz|confusion|comparison|t-?sne|grad-?cam|receptive field|\berf\b|"
                      r"attention map|heatmap of|example of)", re.I)


def venue_tier(venue):
    v = (venue or "").lower()
    if any(re.search(p, v) for p in TOP): return 1
    if any(re.search(p, v) for p in MID): return 2
    return 3


def arxiv_id(url):
    m = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", url or "")
    return m.group(1) if m else None


def ar5iv_url(aid):
    return f"https://ar5iv.labs.arxiv.org/html/{aid}"


def rank_candidates(papers):
    idx = {id(p): i for i, p in enumerate(papers)}
    return sorted(papers, key=lambda p: (venue_tier(p.get("venue") or p.get("journal")), idx[id(p)]))


def is_main_figure(caption):
    c = caption or ""
    return bool(MAIN_RE.search(c)) and not MINOR_RE.search(c)


def _get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def ar5iv_main_figures(aid, max_figs=2):
    """Return [(img_url, caption)] for up to `max_figs` MAIN figures on the ar5iv page."""
    try:
        html = _get(ar5iv_url(aid)).decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    for m in re.finditer(r"<figure[^>]*>(.*?)</figure>", html, re.S | re.I):
        block = m.group(1)
        img = re.search(r'<img[^>]+src="([^"]+\.(?:png|jpg|jpeg|svg))"', block, re.I)
        cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", block, re.S | re.I)
        if not img:
            continue
        caption = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cap.group(1))).strip() if cap else ""
        if not is_main_figure(caption):
            continue
        src = img.group(1)
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://ar5iv.labs.arxiv.org" + src
        elif not src.startswith("http"):
            src = ar5iv_url(aid).rsplit("/", 1)[0] + "/" + src
        out.append((src, caption))
        if len(out) >= max_figs:
            break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--papers", default="", help="JSON of candidate papers Claude found via WebSearch "
                    "(or an upstream seed): [{title, venue, arxiv_url}]")
    ap.add_argument("--arxiv", default="", help="a single arXiv id (e.g. 2401.12345) for a clear winner; "
                    "pair with --venue for the tier check")
    ap.add_argument("--venue", default="", help="venue/journal string for --arxiv")
    ap.add_argument("--out-dir", required=True, help="figures/refs")
    ap.add_argument("--label", required=True, help="figure label, e.g. architecture")
    ap.add_argument("--max-papers", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    # This script only FETCHES main figures from papers Claude ALREADY found by searching — it does not
    # search itself (that is the figure stage's WebSearch, ts-paper-figure step 2b). Build the candidate
    # list from EITHER a single --arxiv winner OR a --papers JSON (Claude's WebSearch hits / a seed).
    # There is NO "proceed without a reference" path: nothing usable -> Claude must WebSearch again.
    papers = []
    if a.arxiv:
        papers = [{"title": f"arXiv:{a.arxiv}", "venue": a.venue, "arxiv_url": f"https://arxiv.org/abs/{a.arxiv}"}]
    elif a.papers and os.path.isfile(a.papers):
        try:
            d = json.load(open(a.papers))
            papers = d if isinstance(d, list) else (d.get("papers") or d.get("retrieved") or d.get("results") or [])
        except (ValueError, OSError) as e:
            print(json.dumps({"ok": False, "n": 0, "search_again": True,
                              "reason": f"--papers unreadable ({type(e).__name__})",
                              "next": "WebSearch for an on-topic TOP-venue paper and re-run with --papers / --arxiv"}))
            return 1
    if not papers:
        print(json.dumps({"ok": False, "n": 0, "search_again": True,
                          "reason": "no candidate papers supplied",
                          "next": "WebSearch (like the cite stage) for the MAIN figure of an on-topic TOP-venue "
                                  "paper, write [{title,venue,arxiv_url}] to JSON, re-run with --papers (or --arxiv). "
                                  "Do NOT proceed without a reference — grounding is mandatory."}))
        return 1

    candidates = []
    for p in rank_candidates(papers)[: a.max_papers]:
        aid = arxiv_id(p.get("url") or p.get("arxiv_url") or p.get("pdf_url") or "") or (a.arxiv or None)
        if not aid:
            continue
        tier = venue_tier(p.get("venue") or p.get("journal"))
        for i, (src, cap) in enumerate(ar5iv_main_figures(aid)):
            try:
                data = _get(src)
            except Exception:
                continue
            fn = f"{a.label}.ref_{aid}_{i}.png"
            with open(os.path.join(a.out_dir, fn), "wb") as fh:
                fh.write(data)
            candidates.append({"paper": p.get("title"), "venue": p.get("venue") or p.get("journal"),
                               "tier": tier, "arxiv": aid, "fig_index": i, "caption": cap,
                               "file": os.path.join(a.out_dir, fn)})
    out_json = os.path.join(a.out_dir, f"{a.label}.candidates.json")
    with open(out_json, "w") as fh:
        json.dump({"label": a.label, "candidates": candidates}, fh, ensure_ascii=False, indent=2)
    best_tier = min((c["tier"] for c in candidates), default=9)
    search_again = (not candidates) or best_tier >= 3   # 1=TOP, 2=MID, 3=other/none
    print(json.dumps({"ok": True, "n": len(candidates), "candidates_json": out_json,
                      "best_tier": best_tier, "search_again": search_again,
                      "hint": ("best candidate is NOT a top/mid venue (or none found) — WebSearch AGAIN "
                               "for a better-tier on-topic paper; do not settle"
                               if search_again else
                               "top/mid-venue MAIN figure(s) found — Read them and pick the single best, type-matched one")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
