---
description: Price local Claude Code sessions at the Anthropic API rate card
argument-hint: "[--days N] [--since YYYY-MM-DD] [--top N]"
allowed-tools: Bash
---

Run the claude-cost analysis script and show its output to the user verbatim.

!uv run "${CLAUDE_PLUGIN_ROOT}/scripts/claude_cost.py" $ARGUMENTS

Do not add commentary or interpretation. The tables are the answer.
