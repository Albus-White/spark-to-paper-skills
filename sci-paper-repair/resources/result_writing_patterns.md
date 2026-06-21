# Result Writing Patterns

Safe, cautious phrasings for the results and discussion sections, plus phrases to avoid. Match
the strength of language to the strength of the evidence (GR-004, GR-012).

## Safe patterns (prefer these)

- "The results **indicate** that ..."
- "The proposed method **achieved** an accuracy of X on dataset Y."
- "**Compared with the strongest baseline**, the method improved metric M by Δ."
- "The improvement is **modest but consistent** across the tested settings."
- "**The current evidence supports** ... under the evaluated conditions."
- "**This limitation suggests** that ..."
- "Within the scope of these experiments, ..."
- "We **observe** ... (results); a possible explanation is ... (discussion)."
- "These results are **consistent with** the hypothesis that ..."

## Unsafe phrases (avoid)

- "This **proves** ..." — experiments support, they rarely prove.
- "**universally superior** / **the best** / **state-of-the-art**" without scoped, fair
  comparison.
- "**significantly improves**" without a statistical test or repeated-run evidence (GR-006).
- "**extensive experiments**" when experiments are limited.
- "**robust** / **generalizes**" without robustness / cross-dataset evidence (GR-005).
- "**always / never / guarantees**" — absolutes rarely hold.

## Quick conversions

| Risky | Safer |
|-------|-------|
| "significantly outperforms" | "outperforms ... by Δ (no significance test performed)" or add the test |
| "proves the method works" | "provides evidence that the method works under the tested conditions" |
| "robust to noise" | "stable across the noise levels we evaluated (X–Y)" |
| "generalizes well" | "transfers to dataset Z; broader generalization is untested" |
| "extensive experiments show" | "the experiments reported here show" |
