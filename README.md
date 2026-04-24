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
- [uv](https://docs.astral.sh/uv/) to run the script via its PEP 723 header
- Python 3.11+ (the script uses only the standard library)

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
Window: 2026-04-17 to 2026-04-24
Parsed 14,423 assistant turns across 60 sessions in 12 repos.

Top 5 most expensive sessions
#  Date         Repo         Model   Turns  Input  Output  Cache   $ Cost  Session
-  -----------  -----------  ------  -----  -----  ------  -----  -------  --------
1  04-22 17:41  stitch-mono  opus-4  1,835   3.3K    1.5M    98%  $824.90  794f6f7a
2  04-20 08:10  stitch-mono  opus-4  1,855  11.4K    1.0M    98%  $729.40  a3e67dda
...

Cost by repo
Repo                 Sessions   Turns    $ Total  $ / session
-------------------  --------  ------  ---------  -----------
meta                       32   5,307  $2,111.88       $66.00
stitch-mono                 5   4,351  $1,782.80      $356.56
...
TOTAL                      60  14,423  $5,505.22       $91.75
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
