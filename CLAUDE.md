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

**Skills** -> entry points users invoke
**MCP Server** -> tools and resources for programmatic access
**Agents** -> `harness-proposer` (worktree, proposes edits), `regression-auditor` (read-only, analyzes failures)
**Hooks** -> SessionStart (init + context injection), PostToolUse (trace logging), PostCompact (context recovery), Stop (session end)
**Core** -> `scripts/meta_harness.py` manages frontier.tsv, runs/, sessions/

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
