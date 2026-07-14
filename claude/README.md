# Spark to Paper for Claude Code

This is the Claude Code v5 distribution. Its plugin manifest is
`claude/.claude-plugin/plugin.json`; the fourteen shared skills live under `claude/skills/`.

## Install

```bash
claude --plugin-dir ./claude
```

For standalone installation:

```bash
for skill in claude/skills/ts-*; do
  rsync -a --delete "$skill/" "$HOME/.claude/skills/$(basename "$skill")/"
done
rm -rf "$HOME/.claude/skills/ts-idea2story" "$HOME/.claude/skills/ts-kg-build"
```

Open a new Claude Code session after installation.

The Claude and Codex distributions share byte-identical Skill instructions, scripts, references,
schemas, examples, and tests. Host-specific plugin and Codex agent metadata remain separate.

Use `ts-research-lifecycle` as the single state core. v5 separates field science calibration from
target-venue accepted-paper calibration, selects one active Idea from grounded candidates, executes
domain-neutral claim-linked research programs, routes figures by source of truth, keeps internal
audit hashes out of the manuscript, and requires an actual-PDF Publication Judgment before release.

Only explanatory-synthesis figures execute a pinned external PaperBanana checkout. DrawAI is
conditional after raster approval. See the root README and PaperBanana notice for runtime and
licensing details.
