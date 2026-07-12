# Reasoning and Validation Boundary

## Principle

Use the main model whenever correctness depends on meaning, scientific context, code intent, or a
comparison between competing explanations. Use deterministic code whenever the target fact has an
exact, reproducible oracle.

## Main-model judgments

The main model owns literature relevance, benchmark applicability, estimand and protocol validity,
implementation-to-method alignment, confounders, alternative explanations, mechanism diagnosis,
claim strength, prose quality, and visual semantics. It must inspect raw artifacts and produce a
`scientific_judgment` that records:

- the exact question;
- a supported, partial, unsupported, uncertain, or not-applicable finding;
- reasoning tied to artifact paths;
- limitations and residual uncertainty;
- blocking issues;
- reviewer identity, independence, and the minimal context artifacts reviewed.

Cosine similarity, keywords, regexes, model scores, file existence, and fixed item counts may help
retrieve or organize evidence. They cannot decide a semantic gate.

## Deterministic validations

Code owns schemas, required files, hashes, commits, environment identity, budgets, timeouts, process
status, raw output preservation, numerical recomputation, result-to-run provenance, BibTeX structure,
citation keys, LaTeX syntax/compilation, raster/vector identity, and artifact invalidation.

When code has no exact oracle, it must emit an advisory or prepare evidence for the model. It must not
invent a proxy hard gate.

## Review economy

Use the main model as the default scientific reviewer. Add a fresh independent review set sized to the
uncertainty, consequence, and material disagreement. Do not multiply reviewers by every issue or use a
fixed reviewer quota. After a fix, review only the issue, close criterion, relevant diff, and evidence.
Repeat a full review only when the scientific object changed.

Stop when the issue set repeats without new evidence, the declared budget is exhausted, the claim is
falsified, or remaining uncertainty must be disclosed or decided by the author.
