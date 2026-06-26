# Anti-Patterns in AI-Generated Paper Drafts

Common problems to detect during diagnosis (Step 2). For each, the repair action is to flag it,
trace the underlying evidence, and weaken/remove/fix per `claim_evidence_rules.md`.

| Anti-pattern | What it looks like | Repair |
|--------------|--------------------|--------|
| **Vague contribution** | "We propose a novel framework" with no concrete, testable claim | Force a precise, falsifiable contribution statement |
| **Fake / unsupported novelty** | Claims of novelty without comparison to prior work | Require baseline comparison or soften to "to our knowledge" |
| **Citation dumping** | Long citation lists unrelated to the sentence's claim | Cite only what supports the specific claim; verify each reference exists |
| **Untraceable numbers** | Result values with no log/CSV/experiment behind them | Mark `AUTHOR_TODO` or remove; never keep invented numbers |
| **Overclaiming** | "Our method is the best / universally superior" | Scope to the tested conditions; remove absolutes |
| **"Significantly" without tests** | "Significantly improves" with no statistical test | Remove "significantly" or add proper statistical evidence (GR-006) |
| **Robustness/generalization without evidence** | Claims robustness or generalization with single-setting results | Require robustness/cross-dataset evidence or weaken claim (GR-005) |
| **Abstract/results/conclusion mismatch** | Abstract promises more than results show | Align all sections; abstract rewritten last (GR-003, GR-009) |
| **Methods too vague to reproduce** | Missing hyperparameters, splits, seeds, hardware | Add reproducibility details or mark `AUTHOR_TODO` |
| **Hiding weak/negative results** | Only favorable numbers reported | Report weak/negative results honestly; discuss limitations |

## Detection tips

- Walk the **PAPER_LOGIC_MAP** chain (problem → contribution → method → experiments → results →
  claims) and mark every broken link.
- Cross-check each abstract sentence against the results section.
- For every number in a table, ask: *where is the artifact that produced this?*
