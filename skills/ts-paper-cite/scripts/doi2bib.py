#!/usr/bin/env python3
"""Fetch a complete BibTeX entry for a DOI (Crossref) or an arXiv id (arXiv API),
deterministically (no LLM).

    python doi2bib.py 10.1109/CVPR52688.2022.02032 [bibkey]   # DOI -> Crossref
    python doi2bib.py 2106.09685 [bibkey]                      # arXiv id -> arXiv API
    python doi2bib.py arXiv:2106.09685 [bibkey]

Prints a fully-populated @article/@inproceedings entry (author, year, venue,
volume(issue):pages, doi) for a DOI, or an @article preprint entry with
eprint/archivePrefix/journal="arXiv preprint" for an arXiv id. Turns "I found a
paper / have its DOI or arXiv id" into "I have complete, verified metadata"
without hand-transcription. Falls back to printing an error JSON (and exiting
nonzero) if the id does not resolve (so the paper is NOT cited).
"""
from __future__ import annotations
import json, re, sys, unicodedata, urllib.request
from xml.etree import ElementTree as ET

# arXiv ids: new style NNNN.NNNNN(vN) or old style archive[.subclass]/NNNNNNN(vN).
ARXIV_RE = re.compile(
    r"^(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)$",
    re.IGNORECASE)

def ascii_fold(s: str) -> str:
    """NFKD-decompose and drop combining marks so pdflatex never sees raw Unicode
    (e.g. 'Aljoša Ošep' -> 'Aljosa Osep', 'Leal-Taixé' -> 'Leal-Taixe')."""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c)).encode("ascii", "ignore").decode("ascii")

def fetch(doi: str) -> dict:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={"User-Agent": "ts-paper-cite/1.0 (mailto:author@example.org)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["message"]

def make_key(m: dict) -> str:
    auth = (m.get("author") or [{}])[0].get("family", "anon")
    year = str((m.get("issued", {}).get("date-parts") or [[0]])[0][0])
    title = (m.get("title") or ["x"])[0]
    kw = re.sub(r"[^a-z]", "", title.lower().split()[0]) if title else "ref"
    return re.sub(r"[^A-Za-z0-9]", "", auth.lower()) + year + kw

def to_bibtex(m: dict, key: str) -> str:
    authors = " and ".join(
        f"{a.get('given','')} {a.get('family','')}".strip() for a in m.get("author", [])) or "Unknown"
    year = str((m.get("issued", {}).get("date-parts") or [[ "" ]])[0][0])
    title = (m.get("title") or [""])[0]
    venue = (m.get("container-title") or [""])[0]
    etype = "inproceedings" if m.get("type") == "proceedings-article" else "article"
    fields = [("author", authors), ("title", title),
              ("booktitle" if etype == "inproceedings" else "journal", venue),
              ("year", year), ("volume", m.get("volume", "")), ("number", m.get("issue", "")),
              ("pages", (m.get("page", "") or "").replace("-", "--")), ("doi", m.get("DOI", ""))]
    lines = [f"@{etype}{{{key},"]
    for f, v in fields:
        if v:
            lines.append(f"  {f}={{{ascii_fold(str(v))}}},")
    lines.append("}")
    return "\n".join(lines)

_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}

def fetch_arxiv(arxiv_id: str) -> dict:
    """Fetch a single record from the arXiv API (one GET) and normalize it to the
    same dict shape used by the Crossref path (author/title/issued/...)."""
    arxiv_id = re.sub(r"^arxiv:", "", arxiv_id, flags=re.IGNORECASE)
    url = "http://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(arxiv_id)
    req = urllib.request.Request(url, headers={"User-Agent": "ts-paper-cite/1.0 (mailto:author@example.org)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    entry = root.find("a:entry", _ARXIV_NS)
    # arXiv returns a non-error feed with no <entry> for an unknown id.
    if entry is None or entry.find("a:id", _ARXIV_NS) is None:
        raise ValueError("no arxiv record")
    title = (entry.findtext("a:title", default="", namespaces=_ARXIV_NS) or "").strip()
    published = (entry.findtext("a:published", default="", namespaces=_ARXIV_NS) or "")
    year = published[:4]
    authors = []
    for a in entry.findall("a:author", _ARXIV_NS):
        name = (a.findtext("a:name", default="", namespaces=_ARXIV_NS) or "").strip()
        given, _, family = name.rpartition(" ")
        authors.append({"given": given, "family": family or name})
    doi = (entry.findtext("a:doi", default="", namespaces={**_ARXIV_NS, "a": "http://arxiv.org/schemas/atom"}) or "")
    return {
        "author": authors,
        "title": [re.sub(r"\s+", " ", title)],
        "issued": {"date-parts": [[int(year)]]} if year.isdigit() else {},
        "type": "article",
        "eprint": re.sub(r"^arxiv:", "", arxiv_id, flags=re.IGNORECASE),
        "DOI": doi,
    }

def to_bibtex_arxiv(m: dict, key: str) -> str:
    authors = " and ".join(
        f"{a.get('given','')} {a.get('family','')}".strip() for a in m.get("author", [])) or "Unknown"
    year = str((m.get("issued", {}).get("date-parts") or [[ "" ]])[0][0])
    title = (m.get("title") or [""])[0]
    eprint = m.get("eprint", "")
    fields = [("author", authors), ("title", title),
              ("journal", "arXiv preprint"),
              ("year", year), ("eprint", eprint),
              ("archivePrefix", "arXiv"), ("doi", m.get("DOI", ""))]
    lines = [f"@article{{{key},"]
    for f, v in fields:
        if v:
            lines.append(f"  {f}={{{ascii_fold(str(v))}}},")
    lines.append("}")
    return "\n".join(lines)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: doi2bib.py <doi|arxiv_id> [bibkey]"})); sys.exit(2)
    import urllib.parse  # noqa
    ident = sys.argv[1].strip()
    is_arxiv = bool(ARXIV_RE.match(ident))
    try:
        m = fetch_arxiv(ident) if is_arxiv else fetch(ident)
    except Exception as e:
        print(json.dumps({"ok": False, "id": ident, "error": f"unresolved: {e}"})); sys.exit(1)
    key = sys.argv[2] if len(sys.argv) > 2 else make_key(m)
    print(to_bibtex_arxiv(m, key) if is_arxiv else to_bibtex(m, key))

if __name__ == "__main__":
    main()
