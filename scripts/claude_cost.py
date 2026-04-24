# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "rich>=13.0",
# ]
# ///
"""claude-cost: price local Claude Code sessions at the Anthropic API rate card.

Walks ~/.claude/projects/*.jsonl, computes a per-turn cost from the usage
metadata each assistant message records, and prints two tables:

  1. Top-N most expensive sessions with diagnostic columns (turns, cache
     hit %, model) so the user can see why a session was expensive.
  2. Cost by repo / cwd, to tell a one-off spike apart from a whole-repo
     pattern.

Costs are shadow prices computed against the public Anthropic API rate
card. They represent the value a Max subscription extracts, not dollars
actually paid.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Per-million-token USD rates: (input, output, cache_write_5m, cache_read).
# cache_creation_input_tokens is billed at ~1.25x input for 5m TTL and
# ~2x input for 1h TTL; we approximate with the 5m rate, which slightly
# undercounts 1h cache writes.
MODEL_RATES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-4": (15.00, 75.00, 18.75, 1.50),
    "claude-opus-4-5": (15.00, 75.00, 18.75, 1.50),
    "claude-opus-4-6": (15.00, 75.00, 18.75, 1.50),
    "claude-opus-4-7": (15.00, 75.00, 18.75, 1.50),
    "claude-3-opus": (15.00, 75.00, 18.75, 1.50),
    "claude-sonnet-4": (3.00, 15.00, 3.75, 0.30),
    "claude-sonnet-4-5": (3.00, 15.00, 3.75, 0.30),
    "claude-sonnet-4-6": (3.00, 15.00, 3.75, 0.30),
    "claude-3-5-sonnet": (3.00, 15.00, 3.75, 0.30),
    "claude-3-7-sonnet": (3.00, 15.00, 3.75, 0.30),
    "claude-haiku-4": (1.00, 5.00, 1.25, 0.10),
    "claude-haiku-4-5": (1.00, 5.00, 1.25, 0.10),
    "claude-3-5-haiku": (0.80, 4.00, 1.00, 0.08),
}
DEFAULT_RATE = (15.00, 75.00, 18.75, 1.50)  # unknown models fall back to Opus tier


def lookup_rate(model: str) -> tuple[float, float, float, float]:
    if not model:
        return DEFAULT_RATE
    base = model.split("[")[0]
    best: tuple[int, tuple[float, float, float, float]] | None = None
    for key, rate in MODEL_RATES.items():
        if base.startswith(key) and (best is None or len(key) > best[0]):
            best = (len(key), rate)
    return best[1] if best else DEFAULT_RATE


def compute_cost(
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    rate: tuple[float, float, float, float],
) -> float:
    in_r, out_r, write_r, read_r = rate
    return (
        input_tokens * in_r
        + output_tokens * out_r
        + cache_creation_tokens * write_r
        + cache_read_tokens * read_r
    ) / 1_000_000


@dataclass
class Turn:
    timestamp: datetime
    cwd: str
    repo: str
    model: str
    session_id: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    cost_usd: float


@dataclass
class SessionAgg:
    session_id: str
    repo: str
    start: datetime
    model_costs: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def dominant_model(self) -> str:
        if not self.model_costs:
            return "unknown"
        return max(self.model_costs.items(), key=lambda kv: kv[1])[0]

    @property
    def input_side_tokens(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens

    @property
    def cache_hit_rate(self) -> float:
        total = self.input_side_tokens
        return self.cache_read_tokens / total if total else 0.0


@dataclass
class RepoAgg:
    repo: str
    sessions: set[str] = field(default_factory=set)
    turns: int = 0
    cost_usd: float = 0.0

    @property
    def avg_cost_per_session(self) -> float:
        return self.cost_usd / len(self.sessions) if self.sessions else 0.0


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cwd_to_repo(cwd: str) -> str:
    if not cwd:
        return "(unknown)"
    parts = [p for p in cwd.rstrip("/").split("/") if p]
    return parts[-1] if parts else "(unknown)"


def iter_turns(since: datetime | None) -> list[Turn]:
    turns: list[Turn] = []
    if not CLAUDE_PROJECTS_DIR.exists():
        return turns
    for session_file in CLAUDE_PROJECTS_DIR.rglob("*.jsonl"):
        try:
            with session_file.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if record.get("type") != "assistant":
                        continue
                    message = record.get("message") or {}
                    usage = message.get("usage") or {}
                    if not usage:
                        continue

                    ts = _parse_timestamp(record.get("timestamp"))
                    if ts is None:
                        continue
                    if since is not None and ts < since:
                        continue

                    cwd = record.get("cwd") or ""
                    model = message.get("model") or "unknown"
                    rate = lookup_rate(model)

                    input_tokens = int(usage.get("input_tokens", 0) or 0)
                    output_tokens = int(usage.get("output_tokens", 0) or 0)
                    cache_creation = int(usage.get("cache_creation_input_tokens", 0) or 0)
                    cache_read = int(usage.get("cache_read_input_tokens", 0) or 0)

                    cost = compute_cost(
                        input_tokens, output_tokens, cache_creation, cache_read, rate
                    )

                    turns.append(
                        Turn(
                            timestamp=ts,
                            cwd=cwd,
                            repo=_cwd_to_repo(cwd),
                            model=model,
                            session_id=record.get("sessionId", ""),
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cache_creation_tokens=cache_creation,
                            cache_read_tokens=cache_read,
                            cost_usd=cost,
                        )
                    )
        except OSError:
            continue
    return turns


def aggregate_sessions(turns: list[Turn]) -> list[SessionAgg]:
    by_sid: dict[str, SessionAgg] = {}
    for t in turns:
        agg = by_sid.get(t.session_id)
        if agg is None:
            agg = SessionAgg(session_id=t.session_id, repo=t.repo, start=t.timestamp)
            by_sid[t.session_id] = agg
        agg.turns += 1
        agg.input_tokens += t.input_tokens
        agg.output_tokens += t.output_tokens
        agg.cache_creation_tokens += t.cache_creation_tokens
        agg.cache_read_tokens += t.cache_read_tokens
        agg.cost_usd += t.cost_usd
        agg.model_costs[t.model] += t.cost_usd
        if t.timestamp < agg.start:
            agg.start = t.timestamp
        if t.repo and agg.repo != t.repo:
            # A session usually stays in one cwd; if it didn't, keep the
            # repo that accumulated the most turns. Cheap heuristic: last
            # non-empty wins, which is fine for display.
            agg.repo = t.repo
    return sorted(by_sid.values(), key=lambda s: -s.cost_usd)


def aggregate_repos(turns: list[Turn]) -> list[RepoAgg]:
    by_repo: dict[str, RepoAgg] = {}
    for t in turns:
        agg = by_repo.get(t.repo)
        if agg is None:
            agg = RepoAgg(repo=t.repo)
            by_repo[t.repo] = agg
        agg.sessions.add(t.session_id)
        agg.turns += 1
        agg.cost_usd += t.cost_usd
    return sorted(by_repo.values(), key=lambda r: -r.cost_usd)


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _short_model(model: str) -> str:
    base = model.split("[")[0]
    for family in ("opus", "sonnet", "haiku"):
        if family in base:
            parts = base.split("-")
            for i, p in enumerate(parts):
                if p == family and i + 1 < len(parts):
                    return f"{family}-{parts[i + 1]}"
            return family
    return base


def render_session_table(sessions: list[SessionAgg], top: int, console: Console) -> None:
    table = Table(title=f"Top {top} most expensive sessions")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Date", style="dim")
    table.add_column("Repo")
    table.add_column("Model", style="dim")
    table.add_column("Turns", justify="right")
    table.add_column("Input", justify="right", style="dim")
    table.add_column("Output", justify="right", style="dim")
    table.add_column("Cache hit", justify="right")
    table.add_column("$ Cost", justify="right", style="bold")
    table.add_column("Session", style="dim")

    for rank, s in enumerate(sessions[:top], start=1):
        table.add_row(
            str(rank),
            s.start.strftime("%Y-%m-%d %H:%M"),
            s.repo,
            _short_model(s.dominant_model),
            f"{s.turns:,}",
            _fmt_tokens(s.input_tokens),
            _fmt_tokens(s.output_tokens),
            f"{s.cache_hit_rate * 100:.0f}%",
            f"${s.cost_usd:,.2f}",
            s.session_id[:8],
        )
    console.print(table)


def render_repo_table(repos: list[RepoAgg], console: Console) -> None:
    table = Table(title="Cost by repo")
    table.add_column("Repo", style="bold")
    table.add_column("Sessions", justify="right")
    table.add_column("Turns", justify="right")
    table.add_column("$ Total", justify="right", style="bold")
    table.add_column("$ / session", justify="right")

    total_cost = 0.0
    total_turns = 0
    total_sessions: set[str] = set()
    for r in repos:
        table.add_row(
            r.repo,
            str(len(r.sessions)),
            f"{r.turns:,}",
            f"${r.cost_usd:,.2f}",
            f"${r.avg_cost_per_session:,.2f}",
        )
        total_cost += r.cost_usd
        total_turns += r.turns
        total_sessions |= r.sessions

    table.add_section()
    avg = total_cost / len(total_sessions) if total_sessions else 0.0
    table.add_row(
        "TOTAL",
        str(len(total_sessions)),
        f"{total_turns:,}",
        f"${total_cost:,.2f}",
        f"${avg:,.2f}",
        style="bold",
    )
    console.print(table)


def _resolve_since(days: int | None, since: str | None) -> tuple[datetime | None, date]:
    end_d = date.today()
    if since:
        since_d = date.fromisoformat(since)
    elif days is not None:
        since_d = end_d - timedelta(days=days)
    else:
        since_d = end_d - timedelta(days=30)
    since_dt = datetime.combine(since_d, datetime.min.time(), tzinfo=timezone.utc)
    return since_dt, since_d


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-cost",
        description="Price local Claude Code sessions at the Anthropic API rate card.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Look back N days from today (default: 30).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Include sessions on or after this ISO date (YYYY-MM-DD). Overrides --days.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of rows in the top-sessions table (default: 10).",
    )
    args = parser.parse_args(argv)

    console = Console()
    since_dt, start_d = _resolve_since(args.days, args.since)
    console.print(f"[dim]Window: {start_d} to {date.today()}[/dim]")

    turns = iter_turns(since=since_dt)
    if not turns:
        console.print("[yellow]No Claude Code sessions found in this window.[/yellow]")
        return 0

    sessions = aggregate_sessions(turns)
    repos = aggregate_repos(turns)

    console.print(
        f"[dim]Parsed {len(turns):,} assistant turns across "
        f"{len(sessions)} sessions in {len(repos)} repos.[/dim]\n"
    )

    render_session_table(sessions, args.top, console)
    console.print()
    render_repo_table(repos, console)
    return 0


if __name__ == "__main__":
    sys.exit(main())
