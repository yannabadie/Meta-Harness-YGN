# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

meta-harness-lab is a Claude Code plugin blueprint for **harness engineering** — optimizing Claude Code harness surfaces (CLAUDE.md, skills, agents, rules, prompt templates) through controlled evolution with full history tracking and Pareto frontier analysis. Inspired by the Meta-Harness paper.

This is a **blueprint/template**, not a production plugin. Users adapt the evaluation command, allowed edit surface, risk policy, metrics, and validation.

## Loading and Using the Plugin

```bash
# Load the plugin from disk
claude --plugin-dir ./meta-harness-lab-plugin

# Inside Claude Code:
/meta-harness-lab:harness-evolve <objective>   # propose one controlled candidate
/meta-harness-lab:harness-frontier              # summarize Pareto frontier
/meta-harness-lab:harness-regressions           # audit regressions
```

## Running Core Scripts

All bin scripts are bash wrappers around `scripts/meta_harness.py`. They require Python 3 and use `CLAUDE_PLUGIN_DATA` (defaults to `/tmp/meta-harness-lab`) for persistent state.

```bash
# Initialize plugin data directory
bin/mh-init

# Reserve next candidate run ID
bin/mh-next-run              # prints run ID (e.g., run-0005)
bin/mh-next-run --path       # prints full path to run directory

# Record metrics for a run
bin/mh-record-metrics <run_id> <primary_score> <avg_latency_ms> <avg_input_tokens> <risk> <note>

# View frontier and regressions
bin/mh-frontier --markdown
bin/mh-regressions --markdown

# Validate JSON syntax in harness files
bin/mh-validate [path]

# Environment snapshot
bin/mh-bootstrap
```

To run `meta_harness.py` directly:
```bash
python3 scripts/meta_harness.py <subcommand> [args]
# Subcommands: init, log-write, record-session, next-run, frontier, record-metrics, regressions, validate
```

## Architecture

**Three-tier workflow: Skills → Agents → Scripts**

1. **Skills** (`skills/*/SKILL.md`) — Claude Code slash commands that orchestrate the workflow. `harness-evolve` is the main entry point; it injects dynamic context (environment snapshot, frontier, regressions) and dispatches to the harness-proposer agent.

2. **Agents** (`agents/*.md`) — Two specialized agents:
   - `harness-proposer` — worktree-isolated, proposes controlled edits to harness surfaces. Produces hypothesis, modified files, risk note, validation summary, and candidate patch.
   - `regression-auditor` — read-only (no Write/Edit/MultiEdit), analyzes why candidates regressed by comparing diffs, metrics, and traces.

3. **Core Python module** (`scripts/meta_harness.py`) — Manages all persistent state:
   - `frontier.tsv` — TSV ledger tracking runs with columns: run_id, status, primary_score, avg_latency_ms, avg_input_tokens, risk, note, timestamp
   - `runs/run-NNNN/` — per-candidate directories with hypothesis.md, safety-note.md, validation.txt, candidate.patch, metrics.json, notes.md
   - `sessions/` — hook-generated session logs
   - Pareto dominance: maximizes primary_score, minimizes avg_latency_ms and avg_input_tokens

4. **Lifecycle hooks** (`hooks/hooks.json`) — SessionStart runs `mh-init`, PostToolUse (Write/Edit/MultiEdit) runs `mh-log-write`, Stop runs `mh-record-session`.

5. **Chat modes** (`.github/*.chatmode.md`) — architect, code, ask, debug modes for different interaction styles.

## Key Constraints

- The plugin edits only **harness surfaces**: CLAUDE.md, `.claude/skills/**`, `.claude/agents/**`, `.claude/rules/**`, `prompts/**`, `.meta-harness/**`, and helper scripts. It does not touch arbitrary application code unless the user explicitly widens scope.
- Proposal and evaluation are **separated** — the plugin proposes candidates; evaluation happens externally.
- The harness-proposer runs in a **git worktree** for isolation.
- The regression-auditor is **read-only** (no write tools allowed).
- Each candidate should be one **coherent hypothesis** with reversible, legible changes.
- Prefer **additive changes** (better context, routing, validation) before touching control flow or prompt scaffolding.

## Environment Variables

- `CLAUDE_PLUGIN_DATA` — persistent storage directory (default: `/tmp/meta-harness-lab`)
- `CLAUDE_PLUGIN_ROOT` — plugin root (auto-detected from script location)
- `CLAUDE_SESSION_ID` — current session identifier for hook logs
