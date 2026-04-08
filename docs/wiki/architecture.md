# Architecture

Technical reference for contributors and advanced users. Describes the full file structure, the 7-layer stack, MCP server, hooks, agents, persistent state, and the context engine.

---

## File Structure

```
Meta-Harness-YGN/
├── .claude-plugin/
│   └── plugin.json            # Plugin manifest (name, version, description, author)
├── .mcp.json                  # MCP server declaration for Claude Code
├── agents/
│   ├── context-harvester.md   # Haiku agent; extract and score project context
│   ├── harness-proposer.md    # Proposer agent; write hypothesis + patch
│   ├── harness-evaluator.md   # Evaluator agent; deterministic + LLM-judge scoring
│   └── regression-auditor.md # Auditor agent; causal regression analysis
├── bin/
│   ├── mh-bootstrap           # Environment snapshot for bootstrap skill
│   ├── mh-context             # CLI wrapper for context_harvester.py
│   ├── mh-frontier            # CLI wrapper for meta_harness.py frontier
│   ├── mh-init                # CLI wrapper for meta_harness.py init
│   ├── mh-log-write           # CLI wrapper for meta_harness.py log-write
│   ├── mh-next-run            # CLI wrapper for meta_harness.py next-run
│   ├── mh-promote             # CLI wrapper for meta_harness.py promote
│   ├── mh-python              # Python interpreter resolver (python3 → python fallback)
│   ├── mh-record-metrics      # CLI wrapper for meta_harness.py record-metrics
│   ├── mh-record-session      # CLI wrapper for meta_harness.py record-session
│   ├── mh-regressions         # CLI wrapper for meta_harness.py regressions
│   ├── mh-rollback            # Reverse-apply a candidate patch with safety tag
│   └── mh-validate            # CLI wrapper for meta_harness.py validate
├── eval-tasks/
│   ├── _schema.json           # Reference schema for eval task format
│   ├── capability/
│   │   └── propose-improvement.json  # Checks run artifacts (requires_run=true)
│   └── regression/
│       ├── context-harvester-runs.json
│       ├── harness-valid.json
│       ├── mcp-server-starts.json
│       ├── plugin-structure.json
│       └── tests-pass.json
├── hooks/
│   ├── capture-subagent.mjs   # SubagentStop handler
│   ├── hooks.json             # Hook configuration (event → command mappings)
│   ├── log-instructions.mjs   # InstructionsLoaded handler
│   └── session-start.mjs      # SessionStart handler (init + additionalContext)
├── output-styles/
│   └── meta-harness.md        # Output style definition (Evolution Report, Frontier, etc.)
├── scripts/
│   ├── context_harvester.py   # BM25 + RRF context pipeline
│   ├── eval_runner.py         # 9 deterministic check types + scoring
│   └── meta_harness.py        # CLI: init, frontier, regressions, metrics, promote, timeline
├── servers/
│   └── mh_server.py           # FastMCP server (7 tools + 4 resources)
├── skills/
│   ├── harness-bootstrap/SKILL.md
│   ├── harness-dashboard/SKILL.md
│   ├── harness-eval/SKILL.md
│   ├── harness-evolve/SKILL.md
│   ├── harness-frontier/SKILL.md
│   └── harness-regressions/SKILL.md
├── tests/
│   ├── test_context_harvester.py
│   ├── test_eval_runner.py
│   └── test_meta_harness.py
├── CHANGELOG.md
├── CLAUDE.md                  # Primary harness instructions for this repo
├── LICENSE
├── pyproject.toml             # requires-python = ">=3.10"; optional mcp dep
└── README.md
```

---

## The 7-Layer Stack

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Skills                                            │
│  /mh:evolve  /mh:frontier  /mh:regressions                 │
│  /mh:dashboard  /mh:eval  /mh:bootstrap                    │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: MCP Server                                        │
│  7 tools + 4 resources over stdio (FastMCP)                │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Agents                                            │
│  context-harvester  harness-proposer                        │
│  harness-evaluator  regression-auditor                      │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Hooks                                             │
│  SessionStart  PostToolUse  Stop (quality gate)             │
│  PostCompact  InstructionsLoaded  SubagentStop              │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Core Scripts                                      │
│  meta_harness.py  eval_runner.py  context_harvester.py      │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: Eval Engine                                       │
│  9 check types  compute_score  run_all_evals               │
├─────────────────────────────────────────────────────────────┤
│  Layer 7: Persistent State                                  │
│  frontier.tsv  runs/*  sessions/*.log  checkpoint.json      │
└─────────────────────────────────────────────────────────────┘
```

Each layer depends only on layers below it. The skills (layer 1) invoke agents (layer 3) and call CLI tools (layer 5). Hooks (layer 4) are event-driven and write to state (layer 7). The MCP server (layer 2) is a parallel access path to layers 5–7, usable by any agent with MCP tool access.

---

## Data Flow Diagram

```
User invokes /mh:evolve "objective"
           │
           ▼
[Phase 0: Setup]
  mh-next-run → run-NNNN reserved
  run dir created with placeholder files
           │
           ▼
[Phase 1: Harvest]
  context_harvester.py
    ├── harvest_claude_md()    → weight 1.0
    ├── harvest_memory()       → weight 0.9
    ├── harvest_git()          → weight 0.8
    └── harvest_docs()         → weight 0.7
  BM25 scoring against objective
  Reciprocal Rank Fusion (BM25 + recency)
  Greedy pack within token budget
  → context-snapshot.md written to run dir
  frontier_read / mh-frontier --markdown → frontier data
  plugin_scan → installed plugin capabilities
           │
           ▼
[Phase 2: Propose]
  harness-proposer subagent (worktree-isolated, max 30 turns)
    Reads: context-snapshot.md, frontier, regressions, plugin capabilities
    Writes to run dir:
      hypothesis.md     (Claim / Evidence / Predicted impact / Risk)
      safety-note.md    (risks and reversibility)
      candidate.patch   (unified diff, max 3 files, harness surfaces only)
      validation.txt    (output of mh-validate)
    Also writes checkpoint.json for crash recovery
           │
           ▼
[Phase 3: Evaluate]
  eval_runner.py (deterministic checks)
    → 9 check types executed against --cwd
    → JSON result per task
  harness-evaluator subagent (read-only, max 20 turns)
    Reads: hypothesis.md, candidate.patch, safety-note.md, validation.txt
    Does NOT read: proposer conversation (context break)
    Computes: 0.6 × deterministic + 0.4 × llm_judge
    Writes: metrics.json to run dir
    Calls: mh-record-metrics → writes frontier.tsv row
           │
           ▼
[Phase 4: Audit]
  regression-auditor subagent (read-only, max 20 turns)
    Reads: candidate.patch, metrics.json, frontier history, session traces
    Writes: analysis.md to run dir
    (analysis.md: regression summary, likely cause, confidence, confounds, recommendation)
           │
           ▼
[Phase 5: Report]
  Orchestrator reads run dir artifacts
  Renders Evolution Report (output-styles/meta-harness.md format)
  Verdict: PROMOTE / REJECT / ITERATE
```

---

## MCP Server

**File:** `servers/mh_server.py`
**Transport:** stdio
**Framework:** FastMCP (`mcp>=1.12`)
**Config:** `.mcp.json`

```json
{
  "mcpServers": {
    "mh-server": {
      "command": "${CLAUDE_PLUGIN_ROOT}/bin/mh-python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/mh_server.py"],
      "env": {
        "MH_PLUGIN_DATA": "${CLAUDE_PLUGIN_DATA}",
        "MH_PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}"
      }
    }
  }
}
```

### Tools (7)

Tools are callable from agents and the MCP client. All are `async`.

#### `frontier_read`

```python
async def frontier_read(format: str = "markdown", limit: int = 10) -> str
```

Reads `frontier.tsv`, computes Pareto non-dominated candidates, and returns the frontier plus recent runs. `format="json"` returns raw JSON; `format="markdown"` returns tables.

#### `frontier_record`

```python
async def frontier_record(
    run_id: str, primary_score: str, avg_latency_ms: str,
    avg_input_tokens: str, risk: str = "low", note: str = "",
    status: str = "complete", consistency: str = "",
    instruction_adherence: str = "", tool_efficiency: str = "",
    error_count: str = "",
) -> str
```

Writes or updates a row in `frontier.tsv`. Returns `"Recorded metrics for {run_id}"`.

#### `trace_search`

```python
async def trace_search(run_id: str = "", query: str = "") -> str
```

Searches session logs in `sessions/` and run directory files for `query`. If `run_id` is provided, includes that run's artifacts. Returns up to 20 matches, each truncated to 2000 characters.

#### `candidate_diff`

```python
async def candidate_diff(run_id: str) -> str
```

Returns the `hypothesis.md`, `safety-note.md`, `candidate.patch`, and `validation.txt` for a run, formatted as Markdown with fenced code blocks.

#### `plugin_scan`

```python
async def plugin_scan(include_capabilities: bool = True) -> str
```

Reads `~/.claude/plugins/installed_plugins.json` and reports each plugin's skill count, agent count, hooks presence, and MCP server presence. With `include_capabilities=True`, lists each plugin's callable skills and MCP tools — used by the proposer to discover cross-plugin capabilities.

#### `context_harvest`

```python
async def context_harvest(
    objective: str = "general harness optimization",
    budget: int = 2000
) -> str
```

Calls `scripts/context_harvester.harvest()` and returns structured Markdown scored by relevance to `objective`, packed within `budget` estimated tokens.

#### `eval_run`

```python
async def eval_run(eval_dir: str = "", cwd: str = "") -> str
```

Calls `eval_runner.run_all_evals()` and returns formatted Markdown with per-task PASS/FAIL and check evidence. Defaults to the plugin's `eval-tasks/` directory and plugin root as `cwd`.

### Resources (4)

Resources are read-only, URI-addressable via `mcp://`.

#### `harness://dashboard`

Returns the full dashboard: total runs, non-dominated count, best score, frontier table (score/latency/tokens/risk/note), and recent runs table.

#### `harness://traces/{run_id}`

Returns all artifacts for a run: `hypothesis.md`, `safety-note.md`, `candidate.patch`, `validation.txt`, `metrics.json`, `notes.md`, `analysis.md`, `checkpoint.json`. Missing files are silently skipped.

#### `harness://regressions`

Returns the regression analysis: runs where score dropped below the previous chronological best, formatted as a Markdown table.

#### `harness://context`

Returns the aggregated project context harvested with the objective `"general harness optimization"` and a 2000-token budget.

---

## Hooks

All 7 hooks are configured in `hooks/hooks.json`.

### `SessionStart`

**Command:** `node ${CLAUDE_PLUGIN_ROOT}/hooks/session-start.mjs`

**What it does:**

1. Discovers Python interpreter via `mh-python` → `python3` → `python` fallback chain
2. Calls `meta_harness.py init` to create storage dirs and write `session_start` log entry
3. Calls `meta_harness.py compact-summary` to generate a compact state summary
4. Writes `{"additionalContext": "<summary>"}` to stdout — Claude Code injects this into the session context

**Payload:** Standard Claude Code `SessionStart` event.

**Failure mode:** If Python is not found, exits 0 (graceful degradation — session starts normally).

**Why Node.js:** Cross-platform path handling. On Windows, `process.env.CLAUDE_PLUGIN_ROOT` requires no shell translation.

---

### `PostToolUse` (matcher: `Write|Edit|MultiEdit`)

**Command:** `${CLAUDE_PLUGIN_ROOT}/bin/mh-log-write`

**What it does:** Reads the `PostToolUse` event JSON from stdin. Extracts `tool_name` and `file_path` from the payload and appends a `write_event` entry to the session log.

**Payload fields used:**
- `tool_name` / `toolName`
- `tool_input.file_path` / `tool_input.filePath` / `tool_input.path`

**Why only Write|Edit|MultiEdit:** These are the only tool calls that modify files. The trace log captures which files were written during a session for post-session analysis.

---

### `Stop`

**Two hooks fire in sequence:**

**Hook 1 — session recording:**

```
command: ${CLAUDE_PLUGIN_ROOT}/bin/mh-record-session
```

Appends a `session_stop` entry to the session log. Runs on every stop event.

**Hook 2 — quality gate (Haiku):**

```json
{
  "type": "prompt",
  "model": "haiku",
  "timeout": 30,
  "prompt": "You are a Meta-Harness quality gate. Check this stop event: $ARGUMENTS\n\nRules:\n1. If stop_hook_active is true, return {\"ok\": true}.\n2. If the last_assistant_message mentions /mh:evolve and does NOT mention recording metrics or updating frontier, return {\"ok\": false, \"reason\": \"...\"}.\n3. Otherwise return {\"ok\": true}."
}
```

The quality gate uses Claude Haiku (30-second timeout) to check whether a `/mh:evolve` run concluded without recording metrics. If it detects this pattern, it returns `{"ok": false, "reason": "..."}` to block the stop event and prompt the user to complete the metric recording.

**Rule 1 (stop_hook_active guard):** Prevents infinite loops — if the quality gate itself triggers a stop, it passes immediately.

**Cost:** One Haiku call per session stop where `/mh:evolve` was involved. Haiku is the cheapest Claude model. See [FAQ](faq.md) for token cost estimates.

---

### `PostCompact`

**Command:** `${CLAUDE_PLUGIN_ROOT}/bin/mh-python ${CLAUDE_PLUGIN_ROOT}/scripts/meta_harness.py compact-summary`

**What it does:** When Claude Code compacts the conversation context (removes older turns), Meta-Harness re-injects a compact state summary so the next turn knows the current frontier and regression state.

**Output format:**

```
[Meta-Harness Context]
Frontier (non-dominated):
  run-0006: score=0.95 latency=5200ms tokens=8500 risk=low
Recent:
  run-0006: complete score=0.95 note=simplified CLAUDE.md
Regressions detected: 2
Total runs: 12
```

---

### `InstructionsLoaded`

**Command:** `node ${CLAUDE_PLUGIN_ROOT}/hooks/log-instructions.mjs`

**What it does:** Appends an `instructions_loaded` entry to the session log recording that the harness was loaded and which CLAUDE.md file was active. Used for audit trails — if instructions change between sessions, the log shows when.

---

### `SubagentStop`

**Command:** `node ${CLAUDE_PLUGIN_ROOT}/hooks/capture-subagent.mjs`

**What it does:** Captures the stop event from a subagent (proposer, evaluator, auditor) and appends a `subagent_stop` entry to the session log. Used to trace which subagents ran during a session and whether they completed normally.

---

## The 4 Agents

### `context-harvester`

| Property | Value |
|---|---|
| File | `agents/context-harvester.md` |
| Model | Haiku |
| Max turns | 5 |
| Isolation | None (shared context) |
| Write tools | Disabled (`disallowedTools: Write, Edit, MultiEdit`) |
| Primary tool | `context_harvest` MCP tool |

**Role:** Gather and structure project context for the proposer. Summarizes the most relevant findings under 2000 tokens. Fast and cheap — Haiku is intentional.

**Constraint:** Cannot write files. All output is returned in the agent's response, which the orchestrator captures and passes to the proposer.

---

### `harness-proposer`

| Property | Value |
|---|---|
| File | `agents/harness-proposer.md` |
| Model | Inherit (parent model) |
| Max turns | 30 |
| Isolation | Worktree |
| Write tools | Enabled |

**Role:** Read the full context (frontier, regressions, plugin capabilities, harvested context) and propose one coherent harness improvement. Deliverables written to the run directory: `hypothesis.md`, `safety-note.md`, `candidate.patch`, `validation.txt`.

**Key constraints:**
- Only editable surfaces: `CLAUDE.md`, `.claude/skills/**`, `.claude/agents/**`, `.claude/rules/**`, `prompts/**`, `.meta-harness/**`, helper scripts
- Maximum 3 files per candidate
- One hypothesis per candidate
- Anti-hallucination: must label anything without evidence as "UNTESTED HYPOTHESIS"
- Mid-run checkpoint at turn 15 (writes current state, narrows scope if it has grown)

**Anti-pattern detection:** If the proposer finds itself editing application code, it must stop and explain why rather than proceeding.

---

### `harness-evaluator`

| Property | Value |
|---|---|
| File | `agents/harness-evaluator.md` |
| Model | Inherit (parent model) |
| Max turns | 20 |
| Isolation | Worktree |
| Write tools | Disabled (`disallowedTools: Write, Edit, MultiEdit`) |

**Role:** Evaluate the proposer's artifacts objectively. The **context break** is enforced by the system prompt: the evaluator reads only disk artifacts and must not be shown the proposer's reasoning.

**Evaluation workflow:**
1. Read `hypothesis.md`, `candidate.patch`, `safety-note.md`, `validation.txt`
2. Run `eval_runner.py --json` for deterministic checks
3. Assess each `llm_judge` criterion — binary judgment per criterion, evidence required
4. Compute `final = 0.6 × deterministic + 0.4 × llm_judge`
5. Write `metrics.json` to run dir
6. Call `mh-record-metrics` to persist to `frontier.tsv`

---

### `regression-auditor`

| Property | Value |
|---|---|
| File | `agents/regression-auditor.md` |
| Model | Inherit (parent model) |
| Max turns | 20 |
| Isolation | Worktree |
| Write tools | Disabled (`disallowedTools: Write, Edit, MultiEdit`) |

**Role:** Provide causal explanation for regressions. Also used by the `/mh:frontier` and `/mh:regressions` skills (via `context: fork`).

**Output format** (written to `analysis.md`):
- Regression summary (run_id, score delta)
- Likely cause (specific mechanism, not "it didn't work")
- Confidence (low/medium/high with justification)
- Evidence (file:line or metric references)
- Confounds (alternative explanations)
- Recommendation (specific, falsifiable next step)

**Anti-patterns the auditor flags:**
- Multiple mechanisms changed simultaneously
- Patch touches files unrelated to the hypothesis
- Metrics improved on one axis but regressed on others
- Candidate replicates a previously-failed approach

---

## Persistent State

All state is stored in `$CLAUDE_PLUGIN_DATA` (default: `/tmp/meta-harness-lab`).

### `frontier.tsv`

Tab-separated values file. One row per run (created by `mh-record-metrics` or `frontier_record`).

**Schema:**

| Column | Type | Description |
|---|---|---|
| `run_id` | string | `run-NNNN` format |
| `status` | string | `complete` or `promoted` |
| `primary_score` | float | Weighted eval score 0.0–1.0 |
| `avg_latency_ms` | float | Average response latency in ms |
| `avg_input_tokens` | float | Average input tokens |
| `risk` | string | `low`, `medium`, or `high` |
| `consistency` | float | Optional sub-score |
| `instruction_adherence` | float | Optional sub-score |
| `tool_efficiency` | float | Optional sub-score |
| `error_count` | int | Optional error count |
| `note` | string | Short hypothesis description |
| `timestamp` | ISO 8601 | UTC timestamp of recording |

**Pareto domination logic:**
- Maximize: `primary_score`
- Minimize: `avg_latency_ms`, `avg_input_tokens`
- Row A dominates Row B if A is at least as good on all three axes and strictly better on at least one

### `runs/` directory

One subdirectory per run (`run-NNNN/`). Contents:

| File | Written by | Content |
|---|---|---|
| `hypothesis.md` | harness-proposer | Claim, Evidence, Predicted impact, Risk |
| `safety-note.md` | harness-proposer | Risks and reversibility |
| `candidate.patch` | harness-proposer | Unified diff (git format) |
| `validation.txt` | harness-proposer | Output of `mh-validate` |
| `metrics.json` | harness-evaluator | Full metrics dict mirroring frontier.tsv row |
| `notes.md` | Optional | Free-form notes |
| `analysis.md` | regression-auditor | Regression analysis |
| `checkpoint.json` | Orchestrator | Crash recovery: phase, turn, objective, last_updated |
| `context-snapshot.md` | Harvest phase | Harvested context at time of run |

### `sessions/` directory

One log file per session (`{CLAUDE_SESSION_ID}.log`). Each line is a structured entry:

```
[2024-01-15T14:32:01.123456Z] session_start cwd=/projects/myapp
[2024-01-15T14:32:45.654321Z] write_event tool=Write path=CLAUDE.md
[2024-01-15T14:45:12.789012Z] subagent_stop ...
[2024-01-15T14:45:13.000000Z] session_stop cwd=/projects/myapp
```

---

## Context Engine

**File:** `scripts/context_harvester.py`

### Tokenizer

```python
def tokenize(text: str) -> list[str]
```

Handles: camelCase splitting, snake_case → spaces, markdown link unwrapping, fenced code block markers, lowercasing. Filters tokens shorter than 2 characters.

### BM25

Okapi BM25 with Lucene-variant IDF (`k1=1.2`, `b=0.75`):

```
IDF(t) = log(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
score(q, d) = Σ IDF(t) × (tf(t,d) × (k1+1)) / (tf(t,d) + k1 × (1 - b + b × |d|/avgdl))
```

### Token Estimator

Heuristic (no tiktoken dependency):

```python
estimate_tokens(text) = int((len(text)/3.5 + len(text.split())*1.33) / 2)
```

### Reciprocal Rank Fusion

```python
rrf_score(item) = Σ 1/(k + rank_in_list)   # k=60
```

Merges two ranked lists: BM25-by-relevance and recency-by-timestamp. Both produce `(id, score)` pairs; RRF fuses them without requiring score normalization.

### Source Weights

| Source | Weight | Contents |
|---|---|---|
| `claude_md` | 1.0 | `CLAUDE.md`, `.claude/rules/*.md` |
| `memory` | 0.9 (current) / 0.3 (other) | `~/.claude/projects/*/memory/` |
| `git_recent` | 0.8 | Recent commits, file hotspots, diff stat |
| `docs` | 0.7 | `README.md`, `docs/*.md` (top 5) |

BM25 scores are multiplied by source weight before ranking. This ensures `CLAUDE.md` consistently outranks documentation for harness-specific objectives.

### Greedy Budget Packing

After RRF fusion, sections are added in order until the estimated token budget is exhausted. If a section would exceed the budget, a truncated version is included if at least 50 tokens remain.

---

## Dependency Policy

| Layer | Dependencies | Rationale |
|---|---|---|
| Core scripts | stdlib only | Zero install friction; works in any Python 3.10+ environment |
| MCP server | `mcp>=1.12` (optional) | Provides FastMCP; entire plugin works without it via CLI fallback |
| Hooks | Node.js (stdlib only) | Cross-platform; no npm install required |
| Tests | `pytest>=8.0` (dev only) | Listed in `pyproject.toml` `[project.optional-dependencies].dev` |

The core scripts (`meta_harness.py`, `eval_runner.py`, `context_harvester.py`) import only: `argparse`, `collections`, `csv`, `datetime`, `json`, `math`, `os`, `pathlib`, `re`, `subprocess`, `sys`. No third-party packages.

---

## Output Style

The `output-styles/meta-harness.md` file defines the required output formats for all evolution reports, frontier summaries, and regression alerts. Key rules:

- No emoji — Unicode symbols only: `⚗ ◆ ⚠ ◉ ▲ ▼ ● ✦ ✓ ✗`
- Always show before/after deltas, not just absolute values
- Sparklines (▁▂▃▄▅▆▇█) for trends when 3+ data points exist
- State sample size and evaluation method for every metric
- Never claim improvement without measured evidence

---

See [Commands Reference](commands-reference.md) for CLI syntax, [Eval Tasks Guide](eval-tasks-guide.md) for the eval engine's check types, and [FAQ](faq.md) for operational questions.
