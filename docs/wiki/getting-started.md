# Getting Started with Meta-Harness

Meta-Harness turns Claude Code harness engineering into a scientific process: propose one controlled change, measure it with 9 deterministic checks, track it on a Pareto frontier, and roll back safely if anything regresses.

This guide takes you from zero to your first measured improvement in under 10 minutes.

---

## Prerequisites

### Required

| Requirement | Version | Why |
|---|---|---|
| Python | 3.10 or later | All core scripts are Python; `mh-python` resolves the interpreter |
| Claude Code | Latest | Plugin host; provides skills, hooks, agents, MCP runtime |
| Git | Any modern version | Rollback uses `git apply -R`; promotion creates git tags |
| Node.js | 18 or later | Three hook scripts (`session-start.mjs`, `log-instructions.mjs`, `capture-subagent.mjs`) run as Node |

Check what you have:

```bash
python3 --version   # Python 3.10.x or later
node --version      # v18 or later
git --version       # any
claude --version    # Claude Code CLI
```

### Optional

```bash
pip install "mcp>=1.12"
```

The `mcp` package enables the FastMCP server (`servers/mh_server.py`), which exposes 7 tools and 4 resources over the MCP stdio transport. The plugin works without it — all MCP functionality degrades gracefully to CLI fallbacks — but having it unlocks direct tool calls from agents and the MCP client in Claude Code.

---

## Installation

### Step 1: Clone the repository

```bash
git clone https://github.com/yannabadie/Meta-Harness-YGN.git
cd Meta-Harness-YGN
```

No `pip install` is required for core functionality. The plugin is self-contained.

### Step 2: Install optional MCP dependency (recommended)

```bash
pip install "mcp>=1.12"
```

To confirm the server starts correctly:

```bash
python servers/mh_server.py
# Expected: no output (server waits on stdin for MCP messages)
# Press Ctrl+C to exit
```

### Step 3: Verify the test suite

```bash
python -m pytest tests/ -q
```

Expected output:

```
55 passed in Xs
```

If any tests fail, check that Python 3.10+ is active. All tests use stdlib only — no additional packages needed.

---

## Loading the Plugin

Meta-Harness is a Claude Code plugin. Load it with the `--plugin-dir` flag:

```bash
claude --plugin-dir ./Meta-Harness-YGN
```

To make it persistent across sessions, add it to your Claude Code settings (`.claude/settings.json`):

```json
{
  "pluginDirs": ["/absolute/path/to/Meta-Harness-YGN"]
}
```

### What happens at load time

When the plugin loads:

1. The `SessionStart` hook runs `session-start.mjs`, which calls `meta_harness.py init` to create persistent storage directories and appends a `session_start` entry to the session log.
2. The same hook runs `meta_harness.py compact-summary` and injects the output as `additionalContext` — so Claude Code immediately knows about your current frontier and any regressions.
3. The `InstructionsLoaded` hook runs `log-instructions.mjs` to record that the harness was loaded.
4. The MCP server starts (if `mcp` is installed) and registers 7 tools and 4 resources.
5. All 6 `/mh:*` skills become available in the command palette.

Verify the plugin is active:

```
/mh:dashboard
```

Expected first-run output (no runs recorded yet):

```
◉ DASHBOARD ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total runs: 0 | Non-dominated: 0
Best score: —

Frontier: No runs recorded yet.
Regressions: None.
Eval suite: checking...
Incomplete runs: None.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## First Commands

Run these three commands in order on any project to understand the full loop.

### 1. Bootstrap: generate eval tasks

```
/mh:bootstrap
```

This scans your project — `CLAUDE.md`, `.claude/rules/`, skills, agents, git history, tooling — and generates eval task JSON files. It creates two categories:

- `eval-tasks/regression/` — sanity checks that must always pass (e.g., "CLAUDE.md exists", "JSON files are valid", "tests pass")
- `eval-tasks/capability/` — improvement targets specific to your project

Expected output (excerpt):

```
# Environment snapshot
- cwd: /your/project
- git branch: main
- git status: M  src/main.py

## Claude surfaces
- found: CLAUDE.md
- found: .claude

## Tooling
- python3: Python 3.11.4
- node: v20.10.0
```

After bootstrapping, you will have at least 5 eval task files. The exact files depend on your project structure.

### 2. Eval: measure the current harness

```
/mh:eval
```

Runs the deterministic check suite against your current harness state. No run ID required — this evaluates the current working tree.

Expected output:

```
Eval report — 6 task(s) loaded from: /path/to/eval-tasks
Passed tasks : 5 / 6
Aggregate score: 83.33%

  [PASS] harness-valid (4/4 checks, score=100%)
         [+] json_valid: Valid JSON at .claude-plugin/plugin.json
         [+] json_valid: Valid JSON at hooks/hooks.json
         [+] file_contains: Pattern found: '^---' in skills/harness-evolve/SKILL.md
         [+] exit_code: Exit code 0 (expected 0) for: python3 scripts/meta_harness.py validate
  [FAIL] tests-pass (0/1 checks, score=0%)
         [-] exit_code: Exit code 1 (expected 0) for: python -m pytest tests/
```

The deterministic score (60% weight) combines with LLM-judge criteria (40% weight) for the final score. See [Eval Tasks Guide](eval-tasks-guide.md) for the scoring formula.

### 3. Evolve: run the full optimization pipeline

```
/mh:evolve "improve validation coverage"
```

This runs the 5-phase pipeline:

| Phase | Duration | What you see |
|---|---|---|
| Setup | < 1s | `Run: run-0001 at /tmp/meta-harness-lab/runs/run-0001` |
| Harvest | ~5s | BM25-scored context extraction from CLAUDE.md, git, memory |
| Propose | 1–3 min | Proposer agent writes `hypothesis.md`, `candidate.patch`, `safety-note.md` |
| Evaluate | 30–60s | Deterministic checks + LLM-judge criteria scored against the patch |
| Audit | 30–60s | Regression auditor compares against frontier leaders |
| Report | < 1s | Evolution report with PROMOTE/REJECT/ITERATE verdict |

Expected final output:

```
⚗ EVOLUTION REPORT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: run-0001 | Hypothesis: add scope guard to prevent out-of-scope edits

| Metric        | Baseline | Candidate | Delta      |
|---------------|----------|-----------|------------|
| Score         | 0.764    | 0.821     | +7.5%  ▲   |
| Latency (ms)  | 8120     | 7340      | -9.6%  ▲   |
| Tokens        | 11382    | 10890     | -4.3%  ▲   |

Confidence: N=1 | Method: deterministic + LLM-judge
Risk: low — additive validation layer, fully reversible
Verdict: PROMOTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If the verdict is PROMOTE, apply the patch:

```
/mh:rollback run-0001   # undo if needed
```

Or from the CLI:

```bash
bin/mh-promote run-0001
```

---

## Troubleshooting

### "Python not found" or `mh-python: command not found`

**Symptom:** Session hooks fail silently; `/mh:evolve` errors with Python not found.

**Cause:** On Windows, `python3` may not exist — only `python` is in PATH. The `mh-python` resolver handles this, but it must be executable.

**Fix:**

```bash
# On Windows (Git Bash or WSL):
which python   # should return a path
python --version  # must be 3.10+

# Make bin scripts executable if needed:
chmod +x bin/mh-*
```

If Python is installed but not in PATH, add it:

```
# Windows: Settings > Apps > Advanced app execution aliases
# Disable the Python App Installer alias, or add Python's directory to PATH
```

### "MCP server not starting"

**Symptom:** MCP tools like `frontier_read` are unavailable; `/mh:evolve` falls back to CLI only.

**Cause 1:** `mcp` package not installed.

```bash
pip install "mcp>=1.12"
python -c "from mcp.server.fastmcp import FastMCP; print('OK')"
```

**Cause 2:** The server script raises on import.

```bash
python servers/mh_server.py
# Read the traceback — usually a missing dependency or wrong Python version
```

**Cause 3:** `CLAUDE_PLUGIN_ROOT` is not set correctly. The `.mcp.json` uses `${CLAUDE_PLUGIN_ROOT}` which Claude Code expands. If launching manually, set it explicitly:

```bash
MH_PLUGIN_ROOT=/path/to/Meta-Harness-YGN python servers/mh_server.py
```

### "No eval tasks found"

**Symptom:** `/mh:eval` reports "0 task(s) loaded".

**Cause:** You have not run `/mh:bootstrap` yet, or the `eval-tasks/` directory is empty.

**Fix:**

```
/mh:bootstrap
```

Then re-run `/mh:eval`. If the directory exists but is empty, verify the bootstrap skill has write permission to `eval-tasks/`.

### Windows path issues

**Symptom:** Hooks fail with `cannot find path`, or session logs are not created.

**Cause:** Windows uses `\` as a path separator; the plugin uses `CLAUDE_PLUGIN_DATA` which defaults to `/tmp/meta-harness-lab` (a Unix path).

**Fix:** Set the environment variable before launching:

```bash
# In PowerShell:
$env:CLAUDE_PLUGIN_DATA = "C:\Users\YourName\.meta-harness"
claude --plugin-dir .\Meta-Harness-YGN

# In .env or your shell profile:
CLAUDE_PLUGIN_DATA=C:/Users/YourName/.meta-harness
```

The Python scripts (`meta_harness.py`, `eval_runner.py`) are Windows-compatible and handle both `python3` and `python` via `mh-python`. The hook scripts use Node.js for cross-platform path handling.

### "Hooks not running"

**Symptom:** No session log created; stop quality gate not enforcing.

**Cause:** Plugin was loaded without the `--plugin-dir` flag (hooks only activate for plugins loaded via `--plugin-dir` or `pluginDirs` in settings).

**Fix:** Confirm the plugin is loaded:

```
/mh:dashboard
```

If `/mh:dashboard` works but hooks are silent, check Claude Code's hook log output. The hooks degrade gracefully — they use `process.exit(0)` on failure rather than crashing the session.

---

## Next Steps

- Understand what "harness" and "Pareto frontier" mean: [Concepts](concepts.md)
- Full reference for every skill and CLI command: [Commands Reference](commands-reference.md)
- Write your own eval tasks: [Eval Tasks Guide](eval-tasks-guide.md)
- Understand the internals: [Architecture](architecture.md)
- Common questions answered: [FAQ](faq.md)
