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
    "avg_input_tokens", "risk",
    "consistency", "instruction_adherence", "tool_efficiency", "error_count",
    "note", "timestamp",
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


@mcp.tool()
async def frontier_record(
    run_id: str, primary_score: str, avg_latency_ms: str,
    avg_input_tokens: str, risk: str = "low", note: str = "",
    status: str = "complete", consistency: str = "",
    instruction_adherence: str = "", tool_efficiency: str = "",
    error_count: str = "",
) -> str:
    """Record metrics for a harness candidate run into frontier.tsv."""
    import datetime as dt
    rows = _read_frontier()
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
    new_row = {
        "run_id": run_id, "status": status,
        "primary_score": primary_score, "avg_latency_ms": avg_latency_ms,
        "avg_input_tokens": avg_input_tokens, "risk": risk,
        "consistency": consistency, "instruction_adherence": instruction_adherence,
        "tool_efficiency": tool_efficiency, "error_count": error_count,
        "note": note, "timestamp": timestamp,
    }
    updated = False
    for row in rows:
        if row.get("run_id") == run_id:
            row.update(new_row)
            updated = True
            break
    if not updated:
        rows.append(new_row)
    PLUGIN_DATA.mkdir(parents=True, exist_ok=True)
    with FRONTIER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_HEADER, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in TSV_HEADER})
    return f"Recorded metrics for {run_id}"


@mcp.tool()
async def trace_search(run_id: str = "", query: str = "") -> str:
    """Search execution traces from session logs and run directories."""
    results = []
    sessions_dir = PLUGIN_DATA / "sessions"
    if sessions_dir.exists():
        for log_file in sorted(sessions_dir.glob("*.log"), reverse=True)[:10]:
            content = log_file.read_text(encoding="utf-8")
            if query and query.lower() not in content.lower():
                continue
            results.append(f"### {log_file.name}\n```\n{content[:2000]}\n```")
    if run_id:
        run_dir = RUNS_DIR / run_id
        if run_dir.exists():
            for f in run_dir.iterdir():
                if f.suffix in (".md", ".txt", ".json", ".patch"):
                    content = f.read_text(encoding="utf-8")
                    if query and query.lower() not in content.lower():
                        continue
                    results.append(f"### {run_id}/{f.name}\n```\n{content[:2000]}\n```")
    return "\n\n".join(results[:20]) if results else "No traces found."


@mcp.tool()
async def candidate_diff(run_id: str) -> str:
    """Get the patch diff and artifacts for a candidate run."""
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return f"Run directory not found: {run_id}"
    parts = [f"# Candidate {run_id}"]
    for name in ["hypothesis.md", "safety-note.md", "candidate.patch", "validation.txt"]:
        fpath = run_dir / name
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"\n## {name}\n```\n{content}\n```")
    return "\n".join(parts) if len(parts) > 1 else f"No artifacts found for {run_id}"


@mcp.tool()
async def plugin_scan() -> str:
    """Scan installed Claude Code plugins and report their harness surfaces."""
    import json as _json
    plugins_dir = pathlib.Path.home() / ".claude" / "plugins"
    registry_path = plugins_dir / "installed_plugins.json"
    if not registry_path.exists():
        return "No installed_plugins.json found."
    try:
        registry = _json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as e:
        return f"Error reading plugin registry: {e}"
    results = []
    for key, installs in registry.get("plugins", {}).items():
        plugin_name = key.split("@")[0]
        if not installs:
            continue
        install = installs[0]
        root = pathlib.Path(install.get("installPath", ""))
        if not root.exists():
            continue
        manifest_path = root / ".claude-plugin" / "plugin.json"
        desc = ""
        if manifest_path.exists():
            try:
                manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
                desc = manifest.get("description", "")
            except Exception:
                pass
        skills = list((root / "skills").glob("*/SKILL.md")) if (root / "skills").exists() else []
        agents = list((root / "agents").glob("*.md")) if (root / "agents").exists() else []
        has_hooks = (root / "hooks" / "hooks.json").exists()
        has_mcp = (root / ".mcp.json").exists()
        version = install.get("version", "?")
        results.append(
            f"- **{plugin_name}** v{version}: {len(skills)} skills, "
            f"{len(agents)} agents, hooks={'yes' if has_hooks else 'no'}, "
            f"mcp={'yes' if has_mcp else 'no'}"
            + (f"\n  {desc}" if desc else "")
        )
    return "# Installed Plugins\n\n" + "\n".join(results) if results else "No plugins found."


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
