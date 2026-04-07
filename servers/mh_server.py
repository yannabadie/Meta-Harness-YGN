#!/usr/bin/env python3
"""Meta-Harness MCP Server — exposes harness tools and resources over stdio."""
from __future__ import annotations

import csv
import io
import os
import pathlib

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise SystemExit(
        "mcp package required. Install with: pip install 'mcp>=1.12'"
    )

PLUGIN_DATA = pathlib.Path(
    os.environ.get("MH_PLUGIN_DATA", os.environ.get("CLAUDE_PLUGIN_DATA", "/tmp/meta-harness"))
)
PLUGIN_ROOT = pathlib.Path(
    os.environ.get("MH_PLUGIN_ROOT", os.environ.get("CLAUDE_PLUGIN_ROOT", "."))
)
FRONTIER = PLUGIN_DATA / "frontier.tsv"
RUNS_DIR = PLUGIN_DATA / "runs"

TSV_HEADER = [
    "run_id", "status", "primary_score", "avg_latency_ms",
    "avg_input_tokens", "risk", "note", "timestamp",
]

mcp = FastMCP(
    "mh-server",
    instructions="Meta-Harness harness optimization server. Use tools to read frontier and resources for dashboards.",
)


def _read_frontier() -> list[dict[str, str]]:
    """Read frontier.tsv and return rows as dicts."""
    if not FRONTIER.exists():
        return []
    with FRONTIER.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def _as_float(value: str) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("nan")


def _frontier_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return Pareto non-dominated rows."""
    completed = [r for r in rows if r.get("status") == "complete"]
    frontier: list[dict[str, str]] = []
    for r in completed:
        dominated = False
        for other in completed:
            if other is r:
                continue
            a_s = _as_float(other.get("primary_score", ""))
            b_s = _as_float(r.get("primary_score", ""))
            a_l = _as_float(other.get("avg_latency_ms", ""))
            b_l = _as_float(r.get("avg_latency_ms", ""))
            a_t = _as_float(other.get("avg_input_tokens", ""))
            b_t = _as_float(r.get("avg_input_tokens", ""))
            vals = [a_s, b_s, a_l, b_l, a_t, b_t]
            if any(v != v for v in vals):
                continue
            if a_s >= b_s and a_l <= b_l and a_t <= b_t and (a_s > b_s or a_l < b_l or a_t < b_t):
                dominated = True
                break
        if not dominated:
            frontier.append(r)
    return sorted(frontier, key=lambda r: -_as_float(r.get("primary_score", "0")))


def _md_table(rows: list[dict[str, str]], cols: list[str], limit: int = 10) -> str:
    """Render rows as a markdown table."""
    if not rows:
        return "No data."
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    lines = [header, sep]
    for row in rows[:limit]:
        lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


@mcp.tool()
async def frontier_read(format: str = "markdown", limit: int = 10) -> str:
    """Read the current Pareto frontier of harness candidates.

    Args:
        format: Output format — "markdown" for tables, "json" for raw data.
        limit: Maximum number of rows to return.
    """
    rows = _read_frontier()
    fr = _frontier_rows(rows)
    recent = sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)[:limit]

    if format == "json":
        import json
        return json.dumps({"frontier": fr, "recent": recent}, indent=2)

    cols = ["run_id", "status", "primary_score", "avg_latency_ms", "avg_input_tokens", "risk", "note"]
    out = ["## Pareto Frontier", "", _md_table(fr, cols, limit)]
    out += ["", "## Recent Runs", "", _md_table(recent, cols, limit)]
    out.append(f"\nNon-dominated: {len(fr)} | Total runs: {len(rows)}")
    return "\n".join(out)


@mcp.resource("harness://dashboard")
async def dashboard() -> str:
    """Frontier dashboard — Pareto analysis with recent runs and regression count."""
    rows = _read_frontier()
    fr = _frontier_rows(rows)
    recent = sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)[:5]
    cols = ["run_id", "primary_score", "avg_latency_ms", "avg_input_tokens", "risk", "note"]

    lines = ["# Meta-Harness Dashboard", ""]
    lines.append(f"**Total runs:** {len(rows)} | **Non-dominated:** {len(fr)}")

    if fr:
        best = fr[0]
        lines.append(f"**Best score:** {best.get('primary_score', '?')} ({best.get('run_id', '?')})")
    lines += ["", "## Frontier", "", _md_table(fr, cols)]
    lines += ["", "## Recent", "", _md_table(recent, cols)]

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
