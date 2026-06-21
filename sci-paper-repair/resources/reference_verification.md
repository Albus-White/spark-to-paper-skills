# Reference Verification

Mandatory module (SKILL Step 12), run **after manuscript repair and before the final submission
checks**. Output: `./outputs/reports/REFERENCE_VERIFICATION_REPORT.md`.

Validated lesson **CAND-007**; enforced by golden rule **GR-014** ("verify every reference; never
invent citation fields"). This is the operational procedure for that rule — there is no separate
"references must be real" golden rule because GR-014 already covers it.

Purpose: prevent fake, incomplete, or duplicated references and keep every citation aligned with
the claim it supports.

## Rules

- **Every bibliography entry must be verified.** The report must **state the verification source**
  for each entry. A search-engine hit alone is **not** sufficient — name the authoritative source.
- **Do not invent** authors, year, venue, pages, DOI, arXiv ID, or URLs.
- If a reference is **real but incomplete**, complete it from a reliable source.
- If a reference **cannot be verified**, **remove it or replace it** with a real, related
  reference (and update the citing sentence so the claim still holds).
- If a reference is **duplicated**, merge/remove the duplicate and fix all `\cite` keys.
- **Preserve claim–reference alignment:** after any citation change, the cited work must still
  support the exact sentence that cites it.

## Reliable verification sources

Official publisher pages, **CVF** (openaccess.thecvf.com), **IEEE Xplore**, **ACM Digital
Library**, **AAAI**, **NeurIPS** proceedings, **ICLR** (OpenReview), **arXiv**, **PubMed**,
**DBLP**. Prefer the version of record; use arXiv when that is the canonical/only version.

## Report format (`outputs/reports/REFERENCE_VERIFICATION_REPORT.md`)

```
# Reference Verification Report

| Cite key | Title | Status | Verification source | Action | Note |
|----------|-------|--------|---------------------|--------|------|
| smith2021 | ... | Verified / Incomplete / Unverifiable / Duplicate | DBLP / arXiv:xxxx.xxxxx / IEEE DOI ... | keep / complete / replace / remove / merge | ... |

Summary: <N verified> / <N total>; <N completed>; <N replaced/removed>; <N duplicates merged>.
Claim–reference alignment preserved: yes/no (explain any change).
```

## Notes

- Edit the `.bib`/citation files **directly inside `./paper/`** (the manuscript source of truth).
- Never fabricate a citation to satisfy a claim. If no real reference supports a claim, weaken or
  `AUTHOR_TODO` the claim instead.
