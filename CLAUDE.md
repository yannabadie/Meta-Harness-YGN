# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Meta-Harness-YGN (`mh`) is a Claude Code plugin for scientific harness optimization. It proposes controlled candidates, evaluates with evidence, and tracks a Pareto frontier across quality, speed, and cost.

Plugin namespace: `/mh:*`

## Loading the Plugin

```bash
claude --plugin-dir ./Meta-Harness-YGN
```

## Skills

```
/mh:evolve <objective>    # 5-phase evolution pipeline (harvest → propose → evaluate → audit → report)
/mh:frontier              # Pareto frontier visualization
/mh:regressions           # Regression audit with causal analysis
/mh:dashboard             # Full status view (frontier + evals + health)
/mh:eval [run_id]         # Run evaluation suite
/mh:bootstrap             # Auto-generate eval tasks from project analysis
```

## Core Scripts

```bash
bin/mh-init                    # Initialize persistent storage
bin/mh-next-run [--path]       # Reserve next candidate run ID
bin/mh-record-metrics <run_id> <score> <latency> <tokens> <risk> <note> [--consistency X] [--instruction-adherence X] [--tool-efficiency X] [--error-count X]
bin/mh-frontier --markdown     # View frontier
bin/mh-regressions --markdown  # View regressions
bin/mh-validate [path]         # Validate JSON syntax
bin/mh-rollback <run_id>       # Reverse-apply candidate patch
bin/mh-context --project . --objective "..." --budget 1500  # Harvest project context
```

## MCP Server

FastMCP server (`servers/mh_server.py`) with 7 tools and 4 resources:
- **Tools:** frontier_read, frontier_record, trace_search, candidate_diff, plugin_scan, context_harvest, eval_run
- **Resources:** harness://dashboard, harness://traces/{run_id}, harness://regressions, harness://context

Optional: `pip install "mcp>=1.12"` (plugin works without it via CLI fallback)

## Architecture

`/mh:evolve` is an inline orchestrator that dispatches 4 agents sequentially:
1. **context-harvester** (Haiku) — extracts project context via BM25 scoring
2. **harness-proposer** (worktree) — proposes one coherent candidate
3. **harness-evaluator** (worktree, read-only) — measures with deterministic + LLM-judge grading
4. **regression-auditor** (worktree, read-only) — analyzes regressions causally

7 hooks: SessionStart (init + additionalContext), PostToolUse (trace logging), Stop (quality gate Haiku + session end), PostCompact (context recovery), InstructionsLoaded (audit), SubagentStop (capture)

## Eval Framework

9 deterministic check types: json_valid, file_exists, file_contains, file_not_contains, exit_code, command_output, patch_not_empty, max_files_changed, files_in_scope

Eval tasks in `eval-tasks/` (JSON format). Run: `python scripts/eval_runner.py --eval-dir eval-tasks --cwd .`

## Key Constraints

- Only edit harness surfaces: CLAUDE.md, `.claude/{skills,agents,rules}/**`, `prompts/**`, `.meta-harness/**`
- One coherent hypothesis per candidate, max 3 files changed
- Evaluator has context-break: reads only disk artifacts, never proposer reasoning
- Never claim improvement without recorded metrics
- Prefer additive changes before touching control flow

## Testing

```bash
python -m pytest tests/ -v  # 70 tests
```
