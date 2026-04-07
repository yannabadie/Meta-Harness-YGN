# Phase 1: MCP Server + Core Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the MCP server to 5 tools and 3 resources, extend frontier.tsv with new columns, add checkpoint persistence, and expand hooks to 7 total.

**Architecture:** Build on Phase 0 walking skeleton. MCP server becomes the primary interface. Hooks expanded with Stop quality gate (Haiku prompt), InstructionsLoaded audit, and SubagentStop capture. Core module gains checkpoint and extended metrics support.

**Tech Stack:** Python 3.10+ (stdlib + mcp>=1.12), Node.js (hooks), bash (bin wrappers).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `scripts/meta_harness.py` | Extended TSV columns, checkpoint support |
| Modify | `servers/mh_server.py` | 4 new tools, 2 new resources |
| Modify | `hooks/hooks.json` | Add Stop (prompt), InstructionsLoaded, SubagentStop |
| Create | `hooks/log-instructions.mjs` | InstructionsLoaded audit hook |
| Create | `hooks/capture-subagent.mjs` | SubagentStop capture hook |
| Modify | `tests/test_meta_harness.py` | Tests for extended columns + checkpoints |
| Modify | `tests/test_mcp_server.py` | Tests for new tools + resources |

---

### Task 1: Extend frontier.tsv Columns (TDD)

**Files:**
- Modify: `scripts/meta_harness.py`
- Modify: `tests/test_meta_harness.py`

- [ ] **Step 1: Add tests for extended columns**

Append to `tests/test_meta_harness.py`:

```python
class TestExtendedFrontier:
    def test_new_columns_in_header(self):
        from scripts.meta_harness import TSV_HEADER
        assert "consistency" in TSV_HEADER
        assert "instruction_adherence" in TSV_HEADER
        assert "tool_efficiency" in TSV_HEADER
        assert "error_count" in TSV_HEADER

    def test_backward_compat_old_rows(self, capsys, monkeypatch):
        """Old rows without new columns should still read correctly."""
        # Write a row with only old columns
        _add_row("run-0010", 0.75, 8000, 11000)
        rows = read_frontier()
        row = rows[0]
        # New columns should be empty string (not KeyError)
        assert row.get("consistency", "") == ""
        assert row.get("instruction_adherence", "") == ""

    def test_record_metrics_with_new_columns(self, capsys, monkeypatch):
        """record-metrics should accept new columns."""
        monkeypatch.setattr("sys.argv", [
            "meta_harness.py", "record-metrics",
            "run-0020", "0.81", "7500", "10000", "low", "test note",
            "--consistency", "0.58",
            "--instruction-adherence", "4.2",
            "--tool-efficiency", "12",
            "--error-count", "2",
        ])
        main()
        rows = read_frontier()
        row = [r for r in rows if r["run_id"] == "run-0020"][0]
        assert row["consistency"] == "0.58"
        assert row["instruction_adherence"] == "4.2"
        assert row["tool_efficiency"] == "12"
        assert row["error_count"] == "2"
```

- [ ] **Step 2: Run tests — should FAIL**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_meta_harness.py::TestExtendedFrontier -v
```

- [ ] **Step 3: Implement extended columns**

In `scripts/meta_harness.py`, update `TSV_HEADER`:

```python
TSV_HEADER = [
    "run_id",
    "status",
    "primary_score",
    "avg_latency_ms",
    "avg_input_tokens",
    "risk",
    "consistency",
    "instruction_adherence",
    "tool_efficiency",
    "error_count",
    "note",
    "timestamp",
]
```

In `cmd_record_metrics`, add the new optional args to the parser and update the row construction. In the `parser()` function, for the `record-metrics` subparser, add:

```python
    s.add_argument("--consistency", default="")
    s.add_argument("--instruction-adherence", default="")
    s.add_argument("--tool-efficiency", default="")
    s.add_argument("--error-count", default="")
```

In `cmd_record_metrics`, add the new fields to both the update and append blocks:

```python
    "consistency": args.consistency,
    "instruction_adherence": args.instruction_adherence,
    "tool_efficiency": args.tool_efficiency,
    "error_count": args.error_count,
```

- [ ] **Step 4: Run tests — should PASS**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_meta_harness.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/meta_harness.py tests/test_meta_harness.py
git commit -m "feat: extend frontier.tsv with consistency, instruction_adherence, tool_efficiency, error_count"
```

---

### Task 2: Checkpoint Persistence (TDD)

**Files:**
- Modify: `scripts/meta_harness.py`
- Modify: `tests/test_meta_harness.py`

- [ ] **Step 1: Add tests for checkpoint support**

Append to `tests/test_meta_harness.py`:

```python
class TestCheckpoint:
    def test_write_checkpoint(self):
        from scripts.meta_harness import write_checkpoint, RUNS_DIR
        ensure_dirs()
        run_dir = RUNS_DIR / "run-0050"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_checkpoint(run_dir, "PROPOSE", 5, "test objective")
        cp_file = run_dir / "checkpoint.json"
        assert cp_file.exists()
        data = json.loads(cp_file.read_text(encoding="utf-8"))
        assert data["phase"] == "PROPOSE"
        assert data["turn"] == 5
        assert data["objective"] == "test objective"

    def test_detect_incomplete_run(self):
        from scripts.meta_harness import write_checkpoint, detect_incomplete_runs, RUNS_DIR
        ensure_dirs()
        run_dir = RUNS_DIR / "run-0051"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_checkpoint(run_dir, "EVALUATE", 12, "improve validation")
        result = detect_incomplete_runs()
        assert result is not None
        assert result["run_id"] == "run-0051"
        assert result["phase"] == "EVALUATE"

    def test_completed_run_not_detected(self):
        from scripts.meta_harness import write_checkpoint, detect_incomplete_runs, RUNS_DIR
        ensure_dirs()
        run_dir = RUNS_DIR / "run-0052"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_checkpoint(run_dir, "COMPLETED", 20, "done")
        # Also write metrics.json to signal completion
        (run_dir / "metrics.json").write_text('{"status": "complete"}', encoding="utf-8")
        result = detect_incomplete_runs()
        # Should not return this run (or return a different one)
        if result:
            assert result["run_id"] != "run-0052"
```

- [ ] **Step 2: Run tests — should FAIL**

- [ ] **Step 3: Implement checkpoint functions**

Add to `scripts/meta_harness.py` after `next_run_id()`:

```python
def write_checkpoint(run_dir: pathlib.Path, phase: str, turn: int, objective: str) -> None:
    """Write a checkpoint file for crash recovery."""
    data = {
        "run_id": run_dir.name,
        "phase": phase,
        "turn": turn,
        "objective": objective,
        "last_updated": dt.datetime.now(dt.timezone.utc).isoformat() + "Z",
    }
    (run_dir / "checkpoint.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def detect_incomplete_runs() -> dict | None:
    """Find a run with checkpoint but no metrics (incomplete)."""
    ensure_dirs()
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        checkpoint = run_dir / "checkpoint.json"
        metrics = run_dir / "metrics.json"
        if checkpoint.exists() and not metrics.exists():
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
            if data.get("phase") != "COMPLETED":
                return data
    return None
```

- [ ] **Step 4: Run tests — should PASS**

- [ ] **Step 5: Commit**

```bash
git add scripts/meta_harness.py tests/test_meta_harness.py
git commit -m "feat: add checkpoint persistence for crash recovery"
```

---

### Task 3: MCP Server — New Tools

**Files:**
- Modify: `servers/mh_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add tests for new tools**

Append to `tests/test_mcp_server.py`:

```python
class TestNewTools:
    def test_frontier_record_exists(self):
        try:
            from servers.mh_server import frontier_record
            assert callable(frontier_record)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise

    def test_trace_search_exists(self):
        try:
            from servers.mh_server import trace_search
            assert callable(trace_search)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise

    def test_candidate_diff_exists(self):
        try:
            from servers.mh_server import candidate_diff
            assert callable(candidate_diff)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise

    def test_plugin_scan_exists(self):
        try:
            from servers.mh_server import plugin_scan
            assert callable(plugin_scan)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise
```

- [ ] **Step 2: Run tests — should FAIL**

- [ ] **Step 3: Implement new tools in mh_server.py**

Add after the existing `frontier_read` tool:

```python
@mcp.tool()
async def frontier_record(
    run_id: str,
    primary_score: str,
    avg_latency_ms: str,
    avg_input_tokens: str,
    risk: str = "low",
    note: str = "",
    status: str = "complete",
    consistency: str = "",
    instruction_adherence: str = "",
    tool_efficiency: str = "",
    error_count: str = "",
) -> str:
    """Record metrics for a harness candidate run into frontier.tsv.

    Args:
        run_id: The candidate run identifier (e.g., run-0012).
        primary_score: Primary quality score (0-1).
        avg_latency_ms: Average latency in milliseconds.
        avg_input_tokens: Average input token count.
        risk: Risk level (low/medium/high).
        note: Description of what changed.
        status: Run status (default: complete).
        consistency: pass^k consistency score.
        instruction_adherence: LLM-judge adherence score (1-5).
        tool_efficiency: Tool calls per task.
        error_count: Number of errors/retries.
    """
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
    """Search execution traces from session logs and run directories.

    Args:
        run_id: Filter to a specific run's traces. Leave empty for all.
        query: Text to search for in trace content.
    """
    results = []
    sessions_dir = PLUGIN_DATA / "sessions"

    # Search session logs
    if sessions_dir.exists():
        for log_file in sorted(sessions_dir.glob("*.log"), reverse=True)[:10]:
            content = log_file.read_text(encoding="utf-8")
            if query and query.lower() not in content.lower():
                continue
            results.append(f"### {log_file.name}\n```\n{content[:2000]}\n```")

    # Search run-specific traces
    if run_id:
        run_dir = RUNS_DIR / run_id
        if run_dir.exists():
            for f in run_dir.iterdir():
                if f.suffix in (".md", ".txt", ".json", ".patch"):
                    content = f.read_text(encoding="utf-8")
                    if query and query.lower() not in content.lower():
                        continue
                    results.append(f"### {run_id}/{f.name}\n```\n{content[:2000]}\n```")

    if not results:
        return "No traces found."
    return "\n\n".join(results[:20])


@mcp.tool()
async def candidate_diff(run_id: str) -> str:
    """Get the patch diff for a candidate run.

    Args:
        run_id: The candidate run identifier (e.g., run-0012).
    """
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

    if len(parts) == 1:
        return f"No artifacts found for {run_id}"
    return "\n".join(parts)


@mcp.tool()
async def plugin_scan() -> str:
    """Scan installed Claude Code plugins and report their harness surfaces.

    Reads ~/.claude/plugins/installed_plugins.json and enumerates each plugin's
    skills, agents, hooks, and MCP servers.
    """
    import json as _json

    plugins_dir = pathlib.Path.home() / ".claude" / "plugins"
    registry_path = plugins_dir / "installed_plugins.json"

    if not registry_path.exists():
        return "No installed_plugins.json found. No plugins installed."

    try:
        registry = _json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as e:
        return f"Error reading plugin registry: {e}"

    results = []
    plugins = registry.get("plugins", {})

    for key, installs in plugins.items():
        plugin_name = key.split("@")[0]
        if not installs:
            continue
        install = installs[0]
        root = pathlib.Path(install.get("installPath", ""))

        if not root.exists():
            continue

        # Read plugin.json
        manifest_path = root / ".claude-plugin" / "plugin.json"
        desc = ""
        if manifest_path.exists():
            try:
                manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
                desc = manifest.get("description", "")
            except Exception:
                pass

        # Count surfaces
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

    if not results:
        return "No plugins found."
    return "# Installed Plugins\n\n" + "\n".join(results)
```

- [ ] **Step 4: Run tests — should PASS**

- [ ] **Step 5: Commit**

```bash
git add servers/mh_server.py tests/test_mcp_server.py
git commit -m "feat: add frontier_record, trace_search, candidate_diff, plugin_scan MCP tools"
```

---

### Task 4: MCP Server — New Resources

**Files:**
- Modify: `servers/mh_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add tests for new resources**

Append to `tests/test_mcp_server.py`:

```python
class TestNewResources:
    def test_traces_resource_exists(self):
        try:
            from servers.mh_server import traces_for_run
            assert callable(traces_for_run)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise

    def test_regressions_resource_exists(self):
        try:
            from servers.mh_server import regressions
            assert callable(regressions)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise
```

- [ ] **Step 2: Run tests — should FAIL**

- [ ] **Step 3: Implement new resources in mh_server.py**

Add after the existing `dashboard` resource:

```python
@mcp.resource("harness://traces/{run_id}")
async def traces_for_run(run_id: str) -> str:
    """Execution traces for a specific run — hypothesis, patch, validation, metrics."""
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
async def regressions() -> str:
    """Regression analysis — runs where score dropped below the previous best."""
    rows = _read_frontier()
    completed = [r for r in rows if r.get("status") == "complete"]
    completed.sort(key=lambda r: r.get("timestamp", ""))

    regression_runs = []
    best_so_far = -1e18
    for row in completed:
        score = _as_float(row.get("primary_score", "nan"))
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
        lines += ["", "## Heuristics", ""]
        lines.append("- Prefer additive changes over prompt + control-flow rewrites")
        lines.append("- Check whether multiple mechanisms changed simultaneously")
        lines.append("- Audit validation gaps before concluding the idea was bad")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests — should PASS**

- [ ] **Step 5: Commit**

```bash
git add servers/mh_server.py tests/test_mcp_server.py
git commit -m "feat: add harness://traces/{run_id} and harness://regressions MCP resources"
```

---

### Task 5: Expand Hooks

**Files:**
- Create: `hooks/log-instructions.mjs`
- Create: `hooks/capture-subagent.mjs`
- Modify: `hooks/hooks.json`

- [ ] **Step 1: Create InstructionsLoaded hook**

Create `hooks/log-instructions.mjs`:

```javascript
#!/usr/bin/env node
/**
 * InstructionsLoaded hook — audit which instruction files are loaded.
 * Logs to sessions directory for observability.
 */
import { readFileSync, appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const pluginData = process.env.CLAUDE_PLUGIN_DATA || process.env.MH_PLUGIN_DATA || "/tmp/meta-harness";
const sessionsDir = path.join(pluginData, "sessions");

let input = "";
try {
  input = readFileSync(0, "utf-8").trim();
} catch { /* no stdin */ }

if (input) {
  try {
    mkdirSync(sessionsDir, { recursive: true });
    const payload = JSON.parse(input);
    const filePath = payload.file_path || "unknown";
    const reason = payload.load_reason || "unknown";
    const ts = new Date().toISOString();
    const line = `[${ts}] instructions_loaded path=${filePath} reason=${reason}\n`;
    const logFile = path.join(sessionsDir, "instructions.log");
    appendFileSync(logFile, line, "utf-8");
  } catch { /* graceful degradation */ }
}

process.exit(0);
```

- [ ] **Step 2: Create SubagentStop hook**

Create `hooks/capture-subagent.mjs`:

```javascript
#!/usr/bin/env node
/**
 * SubagentStop hook — capture subagent results for trace analysis.
 * Logs the agent type and last message to sessions directory.
 */
import { readFileSync, appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const pluginData = process.env.CLAUDE_PLUGIN_DATA || process.env.MH_PLUGIN_DATA || "/tmp/meta-harness";
const sessionsDir = path.join(pluginData, "sessions");

let input = "";
try {
  input = readFileSync(0, "utf-8").trim();
} catch { /* no stdin */ }

if (input) {
  try {
    mkdirSync(sessionsDir, { recursive: true });
    const payload = JSON.parse(input);
    const agentType = payload.agent_type || "unknown";
    const agentId = payload.agent_id || "unknown";
    const lastMsg = (payload.last_assistant_message || "").slice(0, 500);
    const ts = new Date().toISOString();
    const line = `[${ts}] subagent_stop type=${agentType} id=${agentId} msg=${lastMsg}\n`;
    const logFile = path.join(sessionsDir, "subagents.log");
    appendFileSync(logFile, line, "utf-8");
  } catch { /* graceful degradation */ }
}

process.exit(0);
```

- [ ] **Step 3: Update hooks.json with all 7 hooks**

Replace `hooks/hooks.json`:

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
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/mh-record-session"
          },
          {
            "type": "prompt",
            "model": "haiku",
            "timeout": 15,
            "prompt": "You are a Meta-Harness quality gate. Check the stop event: $ARGUMENTS\n\nIf stop_hook_active is true, return {\"ok\": true}.\nOtherwise: did the assistant mention recording metrics, running evaluation, or updating frontier.tsv in the last message? If this was a harness evolution task (/mh:evolve) and no metrics were recorded, return {\"ok\": false, \"reason\": \"Harness evolution requires recording metrics before concluding. Run mh-record-metrics or use the frontier_record tool.\"}.\nFor non-evolution tasks, return {\"ok\": true}."
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
    "InstructionsLoaded": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/log-instructions.mjs"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/hooks/capture-subagent.mjs"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add hooks/
git commit -m "feat: expand hooks to 7 — add Stop quality gate, InstructionsLoaded audit, SubagentStop capture"
```

---

### Task 6: Integration Test + Push

- [ ] **Step 1: Run all tests**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/ -v
```

- [ ] **Step 2: Verify MCP server starts**

```bash
cd C:/Code/Meta-Harness-YGN && timeout 2 python servers/mh_server.py 2>&1; echo "Exit: $?"
```

- [ ] **Step 3: Verify hooks parse**

```bash
python -c "import json; json.load(open('C:/Code/Meta-Harness-YGN/hooks/hooks.json')); print('hooks.json: valid')"
```

- [ ] **Step 4: Tag and push**

```bash
cd C:/Code/Meta-Harness-YGN && git tag -a v0.2.0 -m "Phase 1: MCP server (5 tools, 3 resources), extended frontier, checkpoints, 7 hooks" && git push origin master --tags
```
