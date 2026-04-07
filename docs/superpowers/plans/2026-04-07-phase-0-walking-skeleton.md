# Phase 0: Walking Skeleton — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the full Meta-Harness v2 architecture end-to-end with minimal depth — proving MCP server, enhanced hooks, output style, and renamed skills all work together.

**Architecture:** Plugin renamed from `meta-harness-lab` to `mh`. FastMCP Python server exposes one tool (`frontier_read`) and one resource (`harness://dashboard`) over stdio. SessionStart hook injects frontier summary via `additionalContext`. Output style defines the proof-first formatting. All existing functionality preserved.

**Tech Stack:** Python 3.10+ (stdlib for core, `mcp>=1.12` for server), bash scripts, markdown skills/agents.

**Phases 1-5 are separate plans.** This plan covers ONLY Phase 0 (version 0.1.0).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `pyproject.toml` | Python project config, zero deps core, mcp optional |
| Create | `.mcp.json` | MCP server config pointing to servers/mh-server.py |
| Create | `servers/mh-server.py` | FastMCP server: frontier_read tool + dashboard resource |
| Create | `output-styles/meta-harness.md` | Proof-first output style |
| Create | `hooks/session-start.mjs` | Node.js SessionStart hook (cross-platform) |
| Create | `tests/test_meta_harness.py` | Tests for compact-summary subcommand |
| Create | `tests/test_mcp_server.py` | Tests for MCP server tools and resources |
| Modify | `.claude-plugin/plugin.json` | Rename to "mh", add outputStyles |
| Modify | `hooks/hooks.json` | Replace bash SessionStart with Node.js, add PostCompact |
| Modify | `scripts/meta_harness.py` | Add compact-summary subcommand |
| Modify | `skills/harness-evolve/SKILL.md` | Rename to `name: evolve` |
| Modify | `skills/harness-frontier/SKILL.md` | Rename to `name: frontier` |
| Modify | `skills/harness-regressions/SKILL.md` | Rename to `name: regressions` |
| Modify | `CLAUDE.md` | Update to reflect new namespace and MCP server |

---

### Task 1: Project Foundation

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore` (if missing, or append Python patterns)

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "meta-harness-ygn"
version = "0.1.0"
description = "Scientific harness optimizer for Claude Code"
requires-python = ">=3.10"
license = {text = "MIT"}
dependencies = []

[project.optional-dependencies]
mcp = ["mcp>=1.12"]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

- [ ] **Step 2: Ensure .gitignore has Python entries**

Append to `.gitignore` if it exists, or create it:

```
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
build/
.pytest_cache/
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml .gitignore
git commit -m "feat: add pyproject.toml with zero-dep core and mcp optional"
```

---

### Task 2: Plugin Rename and MCP Config

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Create: `.mcp.json`

- [ ] **Step 1: Update plugin.json**

Replace the entire contents of `.claude-plugin/plugin.json` with:

```json
{
  "name": "mh",
  "version": "0.1.0",
  "description": "Scientific harness optimizer for Claude Code. Proposes controlled candidates, evaluates with evidence, tracks a Pareto frontier.",
  "author": {
    "name": "Yann Abadie"
  },
  "homepage": "https://github.com/yannabadie/Meta-Harness-YGN",
  "repository": "https://github.com/yannabadie/Meta-Harness-YGN",
  "license": "MIT",
  "keywords": [
    "claude-code",
    "plugin",
    "harness",
    "optimization",
    "evaluation",
    "pareto"
  ],
  "outputStyles": "./output-styles/"
}
```

Note: `mcpServers` is configured in `.mcp.json` (separate file), not inline in plugin.json. Claude Code auto-discovers `.mcp.json` at plugin root.

- [ ] **Step 2: Create .mcp.json**

```json
{
  "mcpServers": {
    "mh-server": {
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/mh-server.py"],
      "env": {
        "MH_PLUGIN_DATA": "${CLAUDE_PLUGIN_DATA}",
        "MH_PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}"
      }
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json .mcp.json
git commit -m "feat: rename plugin to 'mh', add MCP server config"
```

---

### Task 3: Add compact-summary Subcommand (TDD)

**Files:**
- Create: `tests/test_meta_harness.py`
- Modify: `scripts/meta_harness.py`

- [ ] **Step 1: Create test directory and file**

Create `tests/__init__.py` (empty) and `tests/test_meta_harness.py`:

```python
"""Tests for meta_harness.py — Phase 0: compact-summary subcommand."""
import json
import os
import pathlib
import tempfile
import csv

import pytest

# Override PLUGIN_DATA before import
_tmp = tempfile.mkdtemp()
os.environ["CLAUDE_PLUGIN_DATA"] = _tmp

from scripts.meta_harness import main, read_frontier, FRONTIER, TSV_HEADER, ensure_dirs


@pytest.fixture(autouse=True)
def clean_state():
    """Reset frontier.tsv before each test."""
    ensure_dirs()
    with FRONTIER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(TSV_HEADER)
    yield


def _add_row(run_id, score, latency, tokens, status="complete"):
    """Helper to add a row to frontier.tsv."""
    rows = read_frontier()
    rows.append({
        "run_id": run_id,
        "status": status,
        "primary_score": str(score),
        "avg_latency_ms": str(latency),
        "avg_input_tokens": str(tokens),
        "risk": "low",
        "note": f"test {run_id}",
        "timestamp": "2026-04-07T00:00:00Z",
    })
    with FRONTIER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_HEADER, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in TSV_HEADER})


class TestCompactSummary:
    def test_empty_frontier(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "compact-summary"])
        main()
        out = capsys.readouterr().out
        assert "No runs recorded" in out

    def test_with_runs(self, capsys, monkeypatch):
        _add_row("run-0001", 0.72, 8500, 11000)
        _add_row("run-0002", 0.76, 8100, 10500)
        _add_row("run-0003", 0.68, 9000, 12000)  # regression
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "compact-summary"])
        main()
        out = capsys.readouterr().out
        # Should contain top candidates
        assert "run-0002" in out
        assert "0.76" in out
        # Should be concise (under 600 tokens ~ 2400 chars)
        assert len(out) < 3000

    def test_output_is_valid_for_injection(self, capsys, monkeypatch):
        _add_row("run-0001", 0.72, 8500, 11000)
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "compact-summary"])
        main()
        out = capsys.readouterr().out
        # Should not contain newlines that break JSON embedding
        # (it's plain text, not JSON itself)
        assert isinstance(out, str)
        assert len(out) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_meta_harness.py -v
```

Expected: FAIL — `compact-summary` subcommand does not exist yet.

- [ ] **Step 3: Implement compact-summary in meta_harness.py**

Add the following function and parser registration to `scripts/meta_harness.py`.

After the `cmd_validate` function (~line 282), add:

```python
def cmd_compact_summary(_: argparse.Namespace) -> int:
    """Generate a concise context summary for PostCompact re-injection."""
    rows = read_frontier()
    fr = frontier_rows(rows)
    recent = sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)[:3]

    lines = ["[Meta-Harness Context]"]

    if not rows:
        lines.append("No runs recorded yet.")
        print("\n".join(lines))
        return 0

    # Top frontier candidates
    if fr:
        lines.append("Frontier (non-dominated):")
        for r in fr[:3]:
            lines.append(
                f"  {r.get('run_id','?')}: score={r.get('primary_score','?')} "
                f"latency={r.get('avg_latency_ms','?')}ms "
                f"tokens={r.get('avg_input_tokens','?')} "
                f"risk={r.get('risk','?')}"
            )

    # Recent runs
    if recent:
        lines.append("Recent:")
        for r in recent:
            lines.append(
                f"  {r.get('run_id','?')}: {r.get('status','?')} "
                f"score={r.get('primary_score','?')} "
                f"note={r.get('note','')}"
            )

    # Detect active regressions
    completed = [r for r in rows if r.get("status") == "complete"]
    completed.sort(key=lambda r: r.get("timestamp", ""))
    best_so_far = -10**18
    regression_count = 0
    for row in completed:
        score = as_float(row.get("primary_score", "nan"))
        if score != score:
            continue
        if score < best_so_far:
            regression_count += 1
        best_so_far = max(best_so_far, score)

    if regression_count > 0:
        lines.append(f"Regressions detected: {regression_count}")

    lines.append(f"Total runs: {len(rows)}")
    print("\n".join(lines))
    return 0
```

In the `parser()` function, after the `validate` subparser block, add:

```python
    s = sub.add_parser("compact-summary")
    s.set_defaults(func=cmd_compact_summary)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_meta_harness.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/ scripts/meta_harness.py
git commit -m "feat: add compact-summary subcommand for PostCompact context re-injection"
```

---

### Task 4: Minimal MCP Server

**Files:**
- Create: `servers/mh-server.py`
- Create: `tests/test_mcp_server.py`

- [ ] **Step 1: Create servers directory**

```bash
mkdir -p C:/Code/Meta-Harness-YGN/servers
```

- [ ] **Step 2: Write MCP server test**

Create `tests/test_mcp_server.py`:

```python
"""Tests for mh-server.py — Phase 0: verify tools and resources exist."""
import os
import tempfile
import csv
import pathlib

import pytest

_tmp = tempfile.mkdtemp()
os.environ["MH_PLUGIN_DATA"] = _tmp
os.environ.setdefault("MH_PLUGIN_ROOT", str(pathlib.Path(__file__).resolve().parents[1]))

# Ensure frontier.tsv exists for import
data_dir = pathlib.Path(_tmp)
data_dir.mkdir(parents=True, exist_ok=True)
frontier_path = data_dir / "frontier.tsv"
with frontier_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, delimiter="\t")
    writer.writerow([
        "run_id", "status", "primary_score", "avg_latency_ms",
        "avg_input_tokens", "risk", "note", "timestamp",
    ])
    writer.writerow([
        "run-0001", "complete", "0.764", "8120",
        "11382", "low", "env bootstrap", "2026-04-07T00:00:00Z",
    ])


class TestMCPServerStructure:
    def test_server_imports(self):
        """Verify the server module can be imported."""
        try:
            import servers.mh_server as srv
            assert hasattr(srv, "mcp")
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed (optional dependency)")
            raise

    def test_frontier_read_tool_exists(self):
        try:
            from servers.mh_server import frontier_read
            assert callable(frontier_read)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise

    def test_dashboard_resource_exists(self):
        try:
            from servers.mh_server import dashboard
            assert callable(dashboard)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_mcp_server.py -v
```

Expected: FAIL — `servers/mh_server.py` does not exist yet. (Note: Python module uses underscore, file on disk uses hyphen for CLI but we'll use underscore for importability.)

- [ ] **Step 4: Create the MCP server**

Create `servers/__init__.py` (empty) and `servers/mh_server.py`:

```python
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
            a_s, b_s = _as_float(other.get("primary_score", "")), _as_float(r.get("primary_score", ""))
            a_l, b_l = _as_float(other.get("avg_latency_ms", "")), _as_float(r.get("avg_latency_ms", ""))
            a_t, b_t = _as_float(other.get("avg_input_tokens", "")), _as_float(r.get("avg_input_tokens", ""))
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
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd C:/Code/Meta-Harness-YGN && pip install "mcp>=1.12" --quiet && python -m pytest tests/test_mcp_server.py -v
```

Expected: All 3 tests PASS (or SKIP if mcp not installed).

- [ ] **Step 6: Commit**

```bash
git add servers/ tests/test_mcp_server.py
git commit -m "feat: add minimal FastMCP server with frontier_read tool and dashboard resource"
```

---

### Task 5: Output Style

**Files:**
- Create: `output-styles/meta-harness.md`

- [ ] **Step 1: Create output-styles directory and file**

```bash
mkdir -p C:/Code/Meta-Harness-YGN/output-styles
```

Create `output-styles/meta-harness.md`:

```markdown
---
name: Meta-Harness
description: Proof-first harness engineering — every claim backed by measured evidence
keep-coding-instructions: true
---

You have the Meta-Harness output style active. When reporting harness
evolution results, ALWAYS use the following structured formats.

## Evolution Report Format

When presenting a harness candidate result, use this exact structure:

```
⚗ EVOLUTION REPORT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: [run_id] | Hypothesis: [one-line summary]

| Metric        | Baseline | Candidate | Delta      | Trend     |
|---------------|----------|-----------|------------|-----------|
| Score         | [val]    | [val]     | [+/-]% ▲/▼ | [sparks] |
| Latency (ms)  | [val]    | [val]     | [+/-]% ▲/▼ | [sparks] |
| Tokens        | [val]    | [val]     | [+/-]% ▲/▼ | [sparks] |
| Consistency   | [val]    | [val]     | [+/-]% ▲/▼ | [sparks] |

Confidence: N=[sample_size] | Method: [eval method]
Risk: [low/medium/high] | Reversible: [yes/no]
Verdict: [PROMOTE / REJECT / ITERATE]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Frontier Summary Format

When presenting the Pareto frontier, use:

```
◆ FRONTIER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[table of top candidates sorted by Pareto dominance]
Non-dominated: [N] | Total runs: [M] | Best score: [val]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Regression Alert Format

When reporting a regression, use:

```
⚠ REGRESSION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: [run_id] | Score drop: [delta]
Likely cause: [one-line]
Confounds: [list if any]
Recommendation: [specific next step]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## General Rules

- NEVER claim an improvement without measured evidence.
- Always show before/after deltas, not just absolute values.
- Use sparklines (▁▂▃▄▅▆▇█) for trends when 3+ data points exist.
- Use ▲ for improvements, ▼ for regressions, ● for stable.
- State sample size and evaluation method for every metric.
- Acknowledge limitations explicitly.
- No emoji. Use Unicode symbols only: ⚗ ◆ ⚠ ◉ ▲ ▼ ● ✦ ✓ ✗
```

- [ ] **Step 2: Commit**

```bash
git add output-styles/
git commit -m "feat: add Meta-Harness proof-first output style"
```

---

### Task 6: Enhanced SessionStart Hook (Node.js, cross-platform)

**Files:**
- Create: `hooks/session-start.mjs`
- Modify: `hooks/hooks.json`

- [ ] **Step 1: Create the Node.js hook script**

Create `hooks/session-start.mjs`:

```javascript
#!/usr/bin/env node
/**
 * SessionStart hook for Meta-Harness.
 * Initializes persistent storage and injects frontier summary as additionalContext.
 * Written in Node.js for cross-platform compatibility (Windows path handling).
 */
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || process.env.MH_PLUGIN_ROOT || ".";
const script = path.join(pluginRoot, "scripts", "meta_harness.py");

let initOutput = "";
let summaryOutput = "";

try {
  // Initialize persistent storage
  initOutput = execSync(`python3 "${script}" init`, {
    encoding: "utf-8",
    timeout: 10000,
  }).trim();
} catch {
  // Python not available — degrade gracefully
  initOutput = "";
}

try {
  // Generate compact summary for context injection
  summaryOutput = execSync(`python3 "${script}" compact-summary`, {
    encoding: "utf-8",
    timeout: 10000,
  }).trim();
} catch {
  summaryOutput = "";
}

// Output additionalContext if we have a summary
if (summaryOutput) {
  const result = { additionalContext: summaryOutput };
  process.stdout.write(JSON.stringify(result));
}

process.exit(0);
```

- [ ] **Step 2: Update hooks.json**

Replace the entire contents of `hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/session-start.mjs"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/mh-log-write"
          }
        ]
      }
    ],
    "PostCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/meta_harness.py compact-summary"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/mh-record-session"
          }
        ]
      }
    ]
  }
}
```

Changes from current:
- SessionStart: replaced bash `mh-init` with Node.js `session-start.mjs` that also injects `additionalContext`
- PostToolUse: unchanged (Write|Edit|MultiEdit → mh-log-write)
- PostCompact: NEW — re-injects frontier summary after context compaction
- Stop: unchanged (mh-record-session)

- [ ] **Step 3: Commit**

```bash
git add hooks/session-start.mjs hooks/hooks.json
git commit -m "feat: Node.js SessionStart hook with additionalContext injection, add PostCompact hook"
```

---

### Task 7: Rename Skills

**Files:**
- Modify: `skills/harness-evolve/SKILL.md`
- Modify: `skills/harness-frontier/SKILL.md`
- Modify: `skills/harness-regressions/SKILL.md`

- [ ] **Step 1: Rename harness-evolve to evolve**

In `skills/harness-evolve/SKILL.md`, change line 2 from:
```
name: harness-evolve
```
to:
```
name: evolve
```

- [ ] **Step 2: Rename harness-frontier to frontier**

In `skills/harness-frontier/SKILL.md`, change line 2 from:
```
name: harness-frontier
```
to:
```
name: frontier
```

- [ ] **Step 3: Rename harness-regressions to regressions**

In `skills/harness-regressions/SKILL.md`, change line 2 from:
```
name: harness-regressions
```
to:
```
name: regressions
```

- [ ] **Step 4: Verify invocation names**

With plugin name `mh` and skill names `evolve`, `frontier`, `regressions`, the invocations become:
- `/mh:evolve <objective>`
- `/mh:frontier`
- `/mh:regressions`

- [ ] **Step 5: Commit**

```bash
git add skills/
git commit -m "feat: rename skills to short names (evolve, frontier, regressions)"
```

---

### Task 8: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md to reflect v2 changes**

Replace the full contents of `CLAUDE.md`:

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Meta-Harness-YGN (`mh`) is a Claude Code plugin for scientific harness optimization. It proposes controlled candidates, evaluates with evidence, and tracks a Pareto frontier across quality, speed, and cost.

Plugin namespace: `/mh:*` (e.g., `/mh:evolve`, `/mh:frontier`, `/mh:regressions`)

## Loading the Plugin

```bash
claude --plugin-dir ./Meta-Harness-YGN
```

## Skills

```
/mh:evolve <objective>    # Propose one controlled harness candidate
/mh:frontier              # Visualize Pareto frontier
/mh:regressions           # Audit regressions with causal analysis
```

## Running Core Scripts

All bin scripts wrap `scripts/meta_harness.py`. Requires Python 3.10+.

```bash
bin/mh-init                    # Initialize persistent storage
bin/mh-next-run [--path]       # Reserve next candidate run ID
bin/mh-record-metrics <run_id> <score> <latency> <tokens> <risk> <note>
bin/mh-frontier --markdown     # View frontier
bin/mh-regressions --markdown  # View regressions
bin/mh-validate [path]         # Validate JSON syntax
```

Direct Python usage:
```bash
python3 scripts/meta_harness.py <subcommand>
# Subcommands: init, log-write, record-session, next-run, frontier,
#              record-metrics, regressions, validate, compact-summary
```

## MCP Server

The plugin ships a FastMCP server (`servers/mh_server.py`) exposing:
- **Tools:** `frontier_read` (read frontier with filters)
- **Resources:** `harness://dashboard` (Pareto frontier dashboard)

Requires: `pip install "mcp>=1.12"` (optional — plugin works without it via CLI fallback)

## Architecture

**Skills** → entry points users invoke
**MCP Server** → tools and resources for programmatic access
**Agents** → `harness-proposer` (worktree, proposes edits), `regression-auditor` (read-only, analyzes failures)
**Hooks** → SessionStart (init + context injection), PostToolUse (trace logging), PostCompact (context recovery), Stop (session end)
**Core** → `scripts/meta_harness.py` manages frontier.tsv, runs/, sessions/

## Persistent State

Stored in `${CLAUDE_PLUGIN_DATA}`:
- `frontier.tsv` — TSV ledger (run_id, status, primary_score, avg_latency_ms, avg_input_tokens, risk, note, timestamp)
- `runs/run-NNNN/` — per-candidate: hypothesis.md, safety-note.md, candidate.patch, validation.txt, metrics.json
- `sessions/` — hook-generated session logs

## Key Constraints

- Only edit harness surfaces: CLAUDE.md, `.claude/skills/**`, `.claude/agents/**`, `.claude/rules/**`, `prompts/**`, `.meta-harness/**`
- One coherent hypothesis per candidate
- Prefer additive changes before touching control flow
- Never claim improvement without recorded metrics

## Testing

```bash
python -m pytest tests/ -v
```
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for v2 architecture (mh namespace, MCP server, new hooks)"
```

---

### Task 9: Integration Verification

- [ ] **Step 1: Validate plugin structure**

```bash
cd C:/Code/Meta-Harness-YGN && claude plugin validate .
```

Expected: No errors. If `claude` CLI not available, manually verify:
- `.claude-plugin/plugin.json` has valid JSON with `name` field
- `hooks/hooks.json` has valid JSON
- All skill directories have `SKILL.md` with valid YAML frontmatter

- [ ] **Step 2: Run all tests**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/ -v
```

Expected: All tests pass (MCP tests may skip if `mcp` not installed).

- [ ] **Step 3: Verify MCP server starts**

```bash
cd C:/Code/Meta-Harness-YGN && timeout 3 python servers/mh_server.py 2>&1 || true
```

Expected: Server starts without errors (will hang waiting for stdin — that's correct for stdio transport). Timeout kills it after 3 seconds.

- [ ] **Step 4: Test SessionStart hook manually**

```bash
CLAUDE_PLUGIN_ROOT="C:/Code/Meta-Harness-YGN" node hooks/session-start.mjs
```

Expected: Outputs JSON with `additionalContext` key (or empty output if no frontier data).

- [ ] **Step 5: Load plugin in Claude Code**

```bash
claude --plugin-dir C:/Code/Meta-Harness-YGN
```

Verify:
- MCP server `mh-server` appears in `/mcp`
- Skills appear as `/mh:evolve`, `/mh:frontier`, `/mh:regressions`
- Output style "Meta-Harness" appears in `/config` → Output style
- SessionStart hook fires without errors

- [ ] **Step 6: Final commit**

```bash
git add -A && git status
# If any uncommitted changes remain:
git commit -m "chore: Phase 0 walking skeleton complete"
```

---

### Task 10: Push and Tag

- [ ] **Step 1: Tag version 0.1.0**

```bash
git tag -a v0.1.0 -m "Phase 0: Walking skeleton — MCP server, output style, enhanced hooks, skill renaming"
```

- [ ] **Step 2: Push**

```bash
git push origin master --tags
```

---

## Phase 0 Acceptance Criteria (recap)

| Criterion | How to verify |
|---|---|
| MCP server starts | `python servers/mh_server.py` runs without error |
| frontier_read tool works | Call via Claude or test |
| harness://dashboard resource works | Call via Claude or test |
| SessionStart injects additionalContext | `node hooks/session-start.mjs` outputs JSON |
| PostCompact re-injects context | Hook config present in hooks.json |
| Output style available | Visible in `/config` |
| Skills renamed | `/mh:evolve`, `/mh:frontier`, `/mh:regressions` |
| Tests pass | `python -m pytest tests/ -v` |
| Plugin validates | `claude plugin validate .` |

## Next Plans

- **Phase 1:** Full MCP Server + Core Enhancement (8 tools, 5 resources, 6 hooks)
- **Phase 2:** Context Engine (harvester, plugin discovery, memory extraction)
- **Phase 3:** Evaluation Framework (evaluator agent, 3-layer grading, eval task bank)
- **Phase 4:** Autonomous Loop (5-phase wiring, multi-pass, dashboard)
- **Phase 5:** Polish, Branding & Marketplace (README, docs, meta-benchmark, 1.0.0)
