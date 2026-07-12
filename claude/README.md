# Spark to Paper for Claude Code

This directory is the Claude Code distribution of the project. Its plugin manifest is
`claude/.claude-plugin/plugin.json`, and all 14 Claude-native skills live under `claude/skills/`.

## Install

### Local plugin

Load `claude/` as the Claude Code plugin directory:

```bash
claude --plugin-dir ./spark-to-paper-skills/claude
```

### Standalone skills

```bash
for skill in spark-to-paper-skills/claude/skills/ts-*; do
  rsync -a --delete "$skill/" "$HOME/.claude/skills/$(basename "$skill")/"
done
```

Restart Claude Code or open a new session after installation so the skill metadata is reloaded.

## Invoke

Plugin skills remain available through the plugin namespace; standalone copies can be invoked by
skill name. The Claude and Codex distributions share the same model-first lifecycle contracts,
scripts, templates, deterministic gates, and tests. Host-specific plugin metadata remains separate.

## Research lifecycle

Use `$ts-research-lifecycle` as the shared state and evidence core for empirical runs. It versions Ideas and contracts, locks repositories/environments, validates G0-G16 gates, preserves failures, and controls Idea evolution and independent revalidation.
