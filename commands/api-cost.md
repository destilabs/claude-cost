---
description: Price local Claude Code sessions at the Anthropic API rate card
argument-hint: "[--days N] [--since YYYY-MM-DD] [--top N]"
allowed-tools: Bash
---

!`uv run "${CLAUDE_PLUGIN_ROOT}/scripts/claude_cost.py" $ARGUMENTS`

The block above is the full report. Print it back to the user verbatim inside a single fenced code block and then stop. Do not summarize, truncate, or add commentary.
