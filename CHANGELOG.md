# Changelog

All notable changes to Meta-Harness-YGN are documented here.

## [1.2.0] - 2026-04-08

### Paper-Aligned (arXiv:2603.28052)
- **Execution traces fed to proposer** — `harvest_sessions()` reads session logs and prior run artifacts (hypothesis, analysis, patches). Paper proved traces improve proposal quality by +43% vs summaries.
- **Context budget 1,500→8,000 tokens** — Proposer now receives 5x more context, including trace excerpts and prior candidate source code.
- **Prior candidates injected** — Evolve pipeline calls `trace_search` and `candidate_diff` for top-3 frontier runs. Proposer sees what was tried, what worked, what failed.
- **Enriched trace logging** — `cmd_log_write` now captures tool_input excerpt (1500 chars) and tool_response (500 chars), not just tool name and path.
- **Behavioral evaluation** — New `before_after_command` check type for functional testing (does the harness change actually help?).
- **Functional eval task category** — `eval-tasks/functional/test-suite-passes.json` verifies project tests still pass after harness changes.
- **Traces source weight** — `SOURCE_WEIGHTS["traces"] = 0.95` (second only to CLAUDE.md).

### AgentSys-Inspired
- Structural phase gates in evolve pipeline — abort on missing artifacts
- Model tier optimization — evaluator/auditor on sonnet, save opus for proposals
- Two-axis eval scoring — confidence (HIGH/MEDIUM/LOW) based on check type determinism
- Deterministic imperative rule extraction before BM25 scoring

## [1.1.0] - 2026-04-08

### New Features
- **Parallel candidate evaluation** — `parallel-run --count N` reserves N run IDs atomically for concurrent evaluation
- **Automated promotion** — `promote <run_id>` applies candidate patches with safety git tags, updates frontier status to "promoted"
- **Time-series visualization** — `timeline` renders sparkline trends (▁▂▃▅▇) for score, latency, and token metrics over time
- **Cross-project frontier comparison** — `compare-projects` scans sibling frontier.tsv files and ranks projects by best score
- **Plugin capability discovery** — `plugin_scan` now lists callable skills and MCP tools from all installed plugins, injected into the proposer's context
- **New bin scripts** — `mh-promote` for CLI promotion

### Fixes
- Fixed UTF-8 encoding for sparklines and Unicode symbols on Windows
- Filtered empty projects from cross-project comparison
- SessionStart hook Python resolution fallback chain (mh-python → python3 → python)

## [1.0.0] - 2026-04-07

### Release
- Competitive README oriented around user problems
- CHANGELOG.md tracking all versions from v0.1.0
- MIT LICENSE file
- GitHub Release with structured notes
- Meta-benchmark: plugin optimized its own eval suite (run-0005)
- All Codex audit bugs fixed (eval_run KeyError, ISO timestamps, badge version)
- 6 eval tasks at 100% cold-run score

## [0.5.0] - 2026-04-07

### Phase 4: Autonomous Loop
- **BREAKING**: Restructured `/mh:evolve` from `context: fork` to inline orchestrator dispatching 4 agents sequentially (harvest, propose, evaluate, audit)
- Enhanced harness-proposer with anti-hallucination constraints, output template, scope lock, mid-run checkpoint
- Enhanced harness-evaluator with context-break (reads only disk artifacts, not proposer reasoning)
- Enhanced regression-auditor with structured output format
- Added `/mh:dashboard` skill — aggregated status view
- Added `bin/mh-rollback` command — reverse-apply candidate patches with safety tags
- Added 3 eval check types: `patch_not_empty`, `max_files_changed`, `files_in_scope`
- 4-verdict system: accepted, accepted_with_warnings, rejected, partial

## [0.4.0] - 2026-04-07

### Phase 3: Evaluation Framework
- Added `scripts/eval_runner.py` — deterministic grading engine with 6 check types
- Added eval task JSON schema and example tasks (regression + capability)
- Added harness-evaluator agent
- Added `/mh:eval` skill — run evaluation suite
- Added `/mh:bootstrap` skill — auto-generate eval tasks from project analysis
- Added `eval_run` MCP tool

## [0.3.0] - 2026-04-07

### Phase 2: Context Engine
- Added `scripts/context_harvester.py` — BM25 scoring, source harvesters, RRF merge
- Tokenizer for markdown+code (camelCase/snake_case splitting)
- 4 sources: CLAUDE.md, project memory, git history, docs
- Added `context_harvest` MCP tool and `harness://context` resource
- Added context-harvester agent (Haiku, read-only)
- Integrated context injection into `/mh:evolve` skill

## [0.2.0] - 2026-04-07

### Phase 1: MCP Server + Core Enhancement
- Extended frontier.tsv with 4 new columns: consistency, instruction_adherence, tool_efficiency, error_count
- Added checkpoint persistence (write_checkpoint, detect_incomplete_runs)
- Added MCP tools: frontier_record, trace_search, candidate_diff, plugin_scan
- Added MCP resources: harness://traces/{run_id}, harness://regressions
- Added hooks: Stop quality gate (Haiku prompt), InstructionsLoaded audit, SubagentStop capture

## [0.1.0] - 2026-04-07

### Phase 0: Walking Skeleton
- Renamed plugin from `meta-harness-lab` to `mh` (skills: `/mh:evolve`, `/mh:frontier`, `/mh:regressions`)
- Added FastMCP server with `frontier_read` tool and `harness://dashboard` resource
- Added Meta-Harness proof-first output style
- Added Node.js SessionStart hook with `additionalContext` injection
- Added PostCompact hook for context recovery
- Added `compact-summary` subcommand to meta_harness.py
- Added `pyproject.toml` with zero-dep core

## [0.0.1] - 2026-04-07

### Initial Blueprint
- Claude Code plugin blueprint with harness-proposer and regression-auditor agents
- Skills: harness-evolve, harness-frontier, harness-regressions
- Core Python module with Pareto frontier management
- Lifecycle hooks: SessionStart, PostToolUse, Stop
