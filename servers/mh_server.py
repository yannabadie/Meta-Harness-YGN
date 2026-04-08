#!/usr/bin/env python3
"""Meta-Harness MCP Server — exposes harness tools and resources over stdio."""
from __future__ import annotations

import pathlib
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.config import (
    PLUGIN_DATA,
    PLUGIN_ROOT,
    RUNS_DIR,
    as_float,
    read_frontier,
    upsert_frontier_row,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None  # mcp is optional; error raised only when server is started

def _noop_decorator(*args, **kwargs):
    """No-op decorator used when mcp package is not installed."""
    def wrapper(fn):
        return fn
    if args and callable(args[0]):
        return args[0]
    return wrapper


class _StubMCP:
    """Stub that provides .tool() and .resource() as no-op decorators."""
    tool = staticmethod(_noop_decorator)
    resource = staticmethod(_noop_decorator)


if FastMCP is not None:
    mcp = FastMCP(
        "mh-server",
        instructions="Meta-Harness harness optimization server. Use tools to read frontier and resources for dashboards.",
    )
else:
    mcp = _StubMCP()


def _read_frontier() -> list[dict[str, str]]:
    """Read frontier.tsv and return rows as dicts."""
    return read_frontier()


def _frontier_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return Pareto non-dominated rows."""
    completed = [r for r in rows if r.get("status") == "complete"]
    frontier: list[dict[str, str]] = []
    for r in completed:
        dominated = False
        for other in completed:
            if other is r:
                continue
            a_s = as_float(other.get("primary_score", ""))
            b_s = as_float(r.get("primary_score", ""))
            a_l = as_float(other.get("avg_latency_ms", ""))
            b_l = as_float(r.get("avg_latency_ms", ""))
            a_t = as_float(other.get("avg_input_tokens", ""))
            b_t = as_float(r.get("avg_input_tokens", ""))
            vals = [a_s, b_s, a_l, b_l, a_t, b_t]
            if any(v != v for v in vals):
                continue
            if a_s >= b_s and a_l <= b_l and a_t <= b_t and (a_s > b_s or a_l < b_l or a_t < b_t):
                dominated = True
                break
        if not dominated:
            frontier.append(r)
    return sorted(frontier, key=lambda r: -as_float(r.get("primary_score", "0")))


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
    from scripts.config import iso_timestamp

    upsert_frontier_row({
        "run_id": run_id, "status": status,
        "primary_score": primary_score, "avg_latency_ms": avg_latency_ms,
        "avg_input_tokens": avg_input_tokens, "risk": risk,
        "consistency": consistency, "instruction_adherence": instruction_adherence,
        "tool_efficiency": tool_efficiency, "error_count": error_count,
        "note": note, "timestamp": iso_timestamp(),
    })
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
async def plugin_scan(include_capabilities: bool = True) -> str:
    """Scan installed Claude Code plugins and report their harness surfaces and usable capabilities.

    Args:
        include_capabilities: If True, list each plugin's skills and MCP tools that Meta-Harness agents can call.
    """
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
    capabilities = []
    for key, installs in registry.get("plugins", {}).items():
        plugin_name = key.split("@")[0]
        if plugin_name == "mh":
            continue  # skip self
        if not installs:
            continue
        install = installs[0]
        root = pathlib.Path(install.get("installPath", ""))
        if not root.exists():
            continue
        manifest_path = root / ".claude-plugin" / "plugin.json"
        desc = ""
        manifest = {}
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

        if include_capabilities:
            # List callable skills
            for skill_file in skills:
                try:
                    content = skill_file.read_text(encoding="utf-8", errors="replace")
                    # Extract skill name from frontmatter
                    for line in content.split("\n"):
                        if line.startswith("name:"):
                            sname = line.split(":", 1)[1].strip()
                            capabilities.append(f"- Skill `/{plugin_name}:{sname}` — invoke for {plugin_name} functionality")
                            break
                except Exception:
                    pass
            # List MCP tools (from .mcp.json)
            if has_mcp:
                try:
                    mcp_conf = _json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
                    for server_name in mcp_conf.get("mcpServers", {}):
                        capabilities.append(f"- MCP server `{server_name}` from {plugin_name} — tools available as `mcp__plugin_{plugin_name}_{server_name}__*`")
                except Exception:
                    pass

    output = "# Installed Plugins\n\n" + "\n".join(results) if results else "No plugins found."

    if include_capabilities and capabilities:
        output += "\n\n## Callable Capabilities\n\n"
        output += "These skills and MCP tools from other plugins are available in this session.\n"
        output += "Meta-Harness agents can use them during evolution phases.\n\n"
        output += "\n".join(capabilities)

    return output


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


@mcp.resource("harness://traces/{run_id}")
async def traces_for_run(run_id: str) -> str:
    """Execution traces for a specific run."""
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return f"Run {run_id} not found."
    parts = [f"# Traces: {run_id}"]
    for name in ["hypothesis.md", "safety-note.md", "candidate.patch",
                  "validation.txt", "metrics.json", "notes.md", "analysis.md",
                  "checkpoint.json"]:
        fpath = run_dir / name
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"\n## {name}\n```\n{content}\n```")
    return "\n".join(parts) if len(parts) > 1 else f"No artifacts for {run_id}."


@mcp.resource("harness://regressions")
async def regressions_resource() -> str:
    """Regression analysis — runs where score dropped below previous best."""
    rows = _read_frontier()
    completed = [r for r in rows if r.get("status") == "complete"]
    completed.sort(key=lambda r: r.get("timestamp", ""))
    regression_runs = []
    best_so_far = -1e18
    for row in completed:
        score = as_float(row.get("primary_score", "nan"))
        if score != score:
            continue
        if score < best_so_far:
            regression_runs.append(row)
        best_so_far = max(best_so_far, score)
    regression_runs = list(reversed(regression_runs))[:10]
    cols = ["run_id", "primary_score", "avg_latency_ms", "avg_input_tokens", "risk", "note"]
    lines = ["# Regression Analysis", ""]
    if not regression_runs:
        lines.append("No regressions detected.")
    else:
        lines.append(f"**{len(regression_runs)} regressions found**")
        lines += ["", _md_table(regression_runs, cols)]
    return "\n".join(lines)


@mcp.tool()
async def context_harvest(objective: str = "general harness optimization", budget: int = 2000) -> str:
    """Harvest project context — extracts from CLAUDE.md, memory, git, docs.

    Returns structured markdown scored by relevance to the objective, within token budget.

    Args:
        objective: What you're trying to optimize (used for BM25 relevance scoring).
        budget: Maximum estimated tokens for the output.
    """
    import sys as _sys
    _sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from context_harvester import harvest
    return harvest(str(PLUGIN_ROOT), objective, budget)


@mcp.resource("harness://context")
async def context_resource() -> str:
    """Aggregated project context — CLAUDE.md, memory, git patterns, docs."""
    import sys as _sys
    _sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from context_harvester import harvest
    return harvest(str(PLUGIN_ROOT), "general harness optimization", 2000)


@mcp.tool()
async def eval_run(eval_dir: str = "", cwd: str = "") -> str:
    """Run all eval tasks and return results with scores.

    Args:
        eval_dir: Path to eval-tasks directory. Defaults to plugin's eval-tasks/.
        cwd: Working directory for running checks. Defaults to plugin root.
    """
    import sys as _sys
    _sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from eval_runner import run_all_evals
    _eval_dir = eval_dir or str(PLUGIN_ROOT / "eval-tasks")
    _cwd = cwd or str(PLUGIN_ROOT)
    result = run_all_evals(_eval_dir, _cwd)

    lines = ["## Eval Results", ""]
    lines.append(f"**Tasks:** {result['total_tasks']} | **Passed:** {result['passed_tasks']}/{result['total_tasks']} | **Score:** {result['aggregate_score']:.1%}")
    lines.append("")
    for r in result["tasks"]:
        status = "PASS" if r["deterministic_score"] == 1.0 else "FAIL"
        lines.append(f"### [{status}] {r['name']} ({r['deterministic_score']:.0%})")
        for check in r["check_results"]:
            mark = "✓" if check["passed"] else "✗"
            lines.append(f"- {mark} {check['type']}: {check['evidence']}")
    return "\n".join(lines)


if __name__ == "__main__":
    if FastMCP is None:
        raise SystemExit("mcp package required. Install with: pip install 'mcp>=1.12'")
    mcp.run(transport="stdio")
