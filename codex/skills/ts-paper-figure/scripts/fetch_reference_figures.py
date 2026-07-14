#!/usr/bin/env python3
"""Fetch candidate figures from model-selected arXiv papers without judging relevance or quality."""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urljoin


def arxiv_id(url: str) -> str | None:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", url or "")
    return match.group(1) if match else None


def ar5iv_url(identifier: str) -> str:
    return f"https://ar5iv.labs.arxiv.org/html/{identifier}"


def _get(url: str, timeout: int = 40) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "spark-to-paper-figure-fetcher/3"})
    return urllib.request.urlopen(request, timeout=timeout).read()


def ar5iv_figures(identifier: str, max_figures: int = 3) -> list[tuple[str, str]]:
    """Return figures in document order; the main model decides which, if any, is useful."""
    try:
        html = _get(ar5iv_url(identifier)).decode("utf-8", "ignore")
    except Exception:
        return []
    figures: list[tuple[str, str]] = []
    for match in re.finditer(r"<figure[^>]*>(.*?)</figure>", html, re.S | re.I):
        block = match.group(1)
        image = re.search(r'<img[^>]+src="([^"]+\.(?:png|jpg|jpeg|svg))"', block, re.I)
        if not image:
            continue
        caption_match = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", block, re.S | re.I)
        caption = ""
        if caption_match:
            caption = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", caption_match.group(1))).strip()
        figures.append((urljoin(ar5iv_url(identifier), image.group(1)), caption))
        if len(figures) >= max_figures:
            break
    return figures


def load_papers(path: str) -> list[dict]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    papers = value if isinstance(value, list) else value.get("papers") or value.get("retrieved") or value.get("results")
    if not isinstance(papers, list):
        raise ValueError("papers JSON must contain a list")
    return [item for item in papers if isinstance(item, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", default="", help="model-selected papers with title and arXiv URL")
    parser.add_argument("--arxiv", default="", help="one explicit arXiv identifier")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--max-papers", type=int, required=True,
                        help="model-selected fetch budget from the venue profile and task relevance")
    parser.add_argument("--max-figures-per-paper", type=int, required=True,
                        help="model-selected per-paper inspection budget")
    args = parser.parse_args()
    if not 1 <= args.max_papers <= 20 or not 1 <= args.max_figures_per_paper <= 12:
        print(json.dumps({"ok": False, "error": "fetch budgets are outside bounded limits"}))
        return 2
    try:
        papers = ([{"title": f"arXiv:{args.arxiv}", "arxiv_url": f"https://arxiv.org/abs/{args.arxiv}"}]
                  if args.arxiv else load_papers(args.papers) if args.papers else [])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "search_required": True, "selection_optional": True}))
        return 1
    if not papers:
        print(json.dumps({"ok": False, "error": "no papers supplied", "search_required": True, "selection_optional": True}))
        return 1

    out_dir = Path(args.out_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    for paper_index, paper in enumerate(papers[:args.max_papers]):
        identifier = arxiv_id(str(paper.get("url") or paper.get("arxiv_url") or paper.get("pdf_url") or ""))
        if not identifier:
            continue
        for figure_index, (source_url, caption) in enumerate(ar5iv_figures(identifier, args.max_figures_per_paper)):
            try:
                content = _get(source_url)
            except Exception:
                continue
            suffix = Path(source_url.split("?", 1)[0]).suffix.lower()
            suffix = suffix if suffix in {".png", ".jpg", ".jpeg", ".svg"} else ".png"
            target = out_dir / f"{args.label}.ref_{paper_index + 1}_{figure_index + 1}{suffix}"
            target.write_bytes(content)
            candidates.append({
                "reference_id": f"R-{paper_index + 1:02d}-{figure_index + 1:02d}",
                "title": paper.get("title"), "venue": paper.get("venue") or paper.get("journal"),
                "source": {"paper_url": paper.get("url") or paper.get("arxiv_url"), "arxiv": identifier,
                           "image_url": source_url},
                "document_order": figure_index + 1, "caption": caption, "image": str(target),
            })
    output = out_dir / f"{args.label}.candidates.json"
    output.write_text(json.dumps({
        "label": args.label, "candidates": candidates,
        "instruction": "The main model must inspect actual images, add reason_selected/visual_conventions to chosen references, and write retrieval.json. NO_SUITABLE_REFERENCE is valid only with attempted sources and rejection reasons.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "n": len(candidates), "candidates_json": str(output), "search_required": True, "selection_optional": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
