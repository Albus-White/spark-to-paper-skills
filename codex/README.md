# Spark to Paper for Codex

This is the Codex-native v5 distribution. Skills live under `codex/skills/`; the plugin manifest is
`codex/.codex-plugin/plugin.json`. The parallel Claude Code distribution remains under `claude/`.

## Install standalone skills

```bash
for skill in codex/skills/ts-*; do
  rsync -a --delete "$skill/" "${CODEX_HOME:-$HOME/.codex}/skills/$(basename "$skill")/"
done
rm -rf "${CODEX_HOME:-$HOME/.codex}/skills/ts-idea2story" \
       "${CODEX_HOME:-$HOME/.codex}/skills/ts-kg-build"
```

Open a new Codex session after installation.

## Invoke

```text
Use $ts-paper to run one evidence-bound lifecycle from this seed.
Use $ts-paper-experiment to execute the frozen research program.
Use $ts-paper-review to review this manuscript against its raw evidence.
```

`$ts-research-lifecycle` is the single state core. It versions policy, seed, science and venue
profiles, candidate selection, Ideas, claims, research programs, code/environment locks, runs,
canonical facts, publication contracts, manuscript artifacts, judgments, and release audit.

Figures route by source of truth. Only explanatory synthesis executes an external pinned PaperBanana
checkout; DrawAI is conditional after raster approval. See the root README and
`ts-paper-figure/references/PAPERBANANA_NOTICE.md` for dependencies and licensing notice.
