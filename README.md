# claude-cost

Price your local Claude Code sessions at the Anthropic API rate card.

Adds an `/api-cost` slash command that walks `~/.claude/projects/*.jsonl`,
computes a shadow cost for each assistant turn from its `usage` metadata,
and prints two tables:

1. **Top N most expensive sessions** - with turns, input/output tokens,
   cache hit %, and the dominant model, so you can see *why* a session was
   expensive, not just that it was.
2. **Cost by repo** - tells a one-off spike apart from a whole-repo pattern.

Costs are shadow prices against the public Anthropic API rate card. They
represent the dollar value a Max subscription extracts, not dollars actually
paid.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- [uv](https://docs.astral.sh/uv/) (the script uses PEP 723 inline deps;
  `uv run` auto-installs `rich` on first run)
- Python 3.11+

## Install

```bash
claude plugin install destilabs/claude-cost
```

Or clone this repo and point Claude Code at it as a local plugin.

## Usage

```
/api-cost                       # last 30 days, top 10 sessions
/api-cost --days 7              # last 7 days
/api-cost --since 2026-04-01    # since a specific date
/api-cost --top 25              # wider session table
```

The bare `/cost` slash is reserved by Claude Code (aliased to `/usage`
for subscription info), which is why this plugin uses `/api-cost`.

## What you will see

```
Window: 2026-03-25 to 2026-04-24
Parsed 8,421 assistant turns across 127 sessions in 14 repos.

Top 10 most expensive sessions
 #  Date              Repo       Model     Turns   Input  Output  Cache hit   $ Cost  Session
 1  2026-04-18 09:12  meta       opus-4    412     1.2M   89.3K   72%         $48.21  a1b2c3d4
 2  2026-04-20 14:30  stitch     opus-4    287     810K   54.1K   68%         $33.08  e5f6g7h8
 ...

Cost by repo
 Repo       Sessions   Turns   $ Total    $ / session
 meta       42         2,104   $210.44    $5.01
 stitch     18         1,322   $128.70    $7.15
 ...
 TOTAL      127        8,421   $612.33    $4.82
```

## How the pricing works

Each assistant turn in a Claude Code session JSONL carries a `usage` block:

```json
{
  "input_tokens": 42,
  "output_tokens": 1240,
  "cache_creation_input_tokens": 18500,
  "cache_read_input_tokens": 95000
}
```

The script multiplies each token count by the per-model rate in the public
[Anthropic pricing page](https://www.anthropic.com/pricing#api) and sums.
`cache_creation_input_tokens` is billed between 1.25x and 2x the input rate
depending on TTL; the script uses the 5-minute rate, which slightly
undercounts 1-hour cache writes.

Unknown models fall back to the Opus tier (conservative over-count).

## Scope

v1 is deliberately minimal. Not included:

- Model-mix or slash-command breakdowns
- Week-over-week trends or time-series charts
- HTML / JSON export
- Max-subscription ROI framing
- Alerts or budget pacing

These may come later if there is demand. Open an issue.

## License

MIT
