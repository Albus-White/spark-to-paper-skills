# Spark to Paper for Codex

This directory is the Codex-native distribution of the project. The original Claude Code plugin remains
preserved under `claude/` (`claude/.claude-plugin/` and `claude/skills/`). Codex uses the parallel copy in
`codex/skills/`, with its plugin manifest at `codex/.codex-plugin/plugin.json`.

## Install

### Codex plugin

Load the repository as a local Codex plugin. Its manifest is `codex/.codex-plugin/plugin.json`, and all 14
skills are discovered from `codex/skills/`.

### Standalone skills

```bash
for skill in codex/skills/ts-*; do
  rsync -a --delete "$skill/" "${CODEX_HOME:-$HOME/.codex}/skills/$(basename "$skill")/"
done
```

The per-skill `--delete` removes files retired by the new version without touching Codex system skills.
Restart Codex or open a new session after installation so skill metadata is reloaded.

## Invoke

Use natural language or explicitly name a skill, for example:

```text
Use $ts-paper to turn this proposal into a complete compiled paper.
Use $ts-paper-review to harden this manuscript.
Use $ts-paper-experiment to repair this draft with real experiments.
```

The Codex figure path chooses a renderer and candidate budget from the figure's source of truth,
venue study, unresolved uncertainty, and user resource envelope. Deterministic figures can render
directly; generative figures use a justified bounded search and actual-image review. DrawAI
reconstructs approved rasters as semantic SVG/PDF/PPTX when needed, while already-correct born-vector
figures bypass reconstruction.

The skill owns its reference-data cache and contains a pinned DrawAI engine; neither PaperBanana nor
DrawAI source checkouts are runtime dependencies. GPU services/models are provisioned through the
bundled engine. Raster-hybrid fallback is explicit and never silently presented as fully editable.

## Research lifecycle

Use `$ts-research-lifecycle` as the shared state and evidence core for empirical runs. It versions Ideas and contracts, locks repositories/environments, validates G0-G16 gates, preserves failures, and controls Idea evolution and independent revalidation.
