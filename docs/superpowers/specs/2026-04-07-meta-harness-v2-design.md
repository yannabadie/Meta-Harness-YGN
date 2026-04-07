# Meta-Harness-YGN v2 Design Specification

**Date:** 2026-04-07
**Status:** Approved
**Version:** 0.1.0 → 1.0.0 (6-phase roadmap)

---

## 1. Vision & Positioning

**Tagline:** *"Don't guess. Evolve. Prove."*

Meta-Harness-YGN is the scientific harness optimizer for Claude Code. It proposes controlled candidates, evaluates with evidence, and tracks a Pareto frontier across quality, speed, and cost.

### Differentiators (unique in the ecosystem)

- Pareto frontier analysis across multiple objectives
- Hypothesis-driven experimentation for harness surfaces
- Regression auditing with causal analysis
- Full history/provenance ledger (every candidate tracked)
- Proof-first: no claim without measured evidence

### Competitive positioning

| | ECC (144K stars) | Superpowers (139K) | Skill-creator (official) | **Meta-Harness** |
|---|---|---|---|---|
| Optimizes | Everything, vaguely | Dev workflow | Individual skills | **Harness global** |
| Methodology | Ad hoc | Rigid, unmeasured | Basic eval | **Scientific** |
| Proof | None | None | Pass rate | **Multi-axis Pareto** |
| Autonomy | Manual | Manual | Semi-auto | **Autonomous loop** |
| History | None | None | Per-skill | **Full ledger** |

### Founding principles (research-backed)

1. **Raw traces > LLM summaries** — +15 points in Meta-Harness ablation (arXiv:2603.28052)
2. **Tool improvements > prompt improvements** — Self-Improving Coding Agent (arXiv:2504.15228)
3. **Proof-first** — no assertion without measured data

---

## 2. Architecture

### 7-layer stack

```
┌─────────────────────────────────────────────────────────┐
│                    CLAUDE CODE SESSION                    │
├─────────────────────────────────────────────────────────┤
│  Output Style    │    8 Hooks       │    6 Skills        │
│  (branding)      │    (lifecycle)   │    (entry points)  │
├──────────────────┴─────────────────┴────────────────────┤
│              MCP SERVER (FastMCP / Python)                │
│  8 Tools  │  5 Resources  │  Context Engine              │
├──────────────────────────────────────────────────────────┤
│                      4 AGENTS                            │
│  proposer  ·  evaluator  ·  auditor  ·  harvester        │
├──────────────────────────────────────────────────────────┤
│              PERSISTENT STATE (disk)                      │
│  frontier.tsv · runs/ · traces/ · eval-tasks/            │
└──────────────────────────────────────────────────────────┘
```

### 2.1 MCP Server (`servers/mh-server.py`)

FastMCP Python, stdio transport, launched automatically by Claude Code.

**Tools:**

| Tool | Role |
|---|---|
| `frontier_read` | Read frontier with filters, markdown/JSON output |
| `frontier_record` | Record metrics for a run |
| `eval_run` | Execute an eval task |
| `eval_judge` | LLM-as-judge pairwise comparison |
| `trace_search` | Search raw execution traces |
| `context_harvest` | Extract project memory + docs + git + plugins |
| `candidate_diff` | Generate/apply a candidate patch |
| `plugin_scan` | Scan installed plugins and their configs |

**Resources (on-demand, zero cost when unused):**

| URI | Content |
|---|---|
| `harness://dashboard` | Pareto frontier + recent runs + metrics |
| `harness://traces/{run_id}` | Raw traces for a specific run |
| `harness://regressions` | Structured regression analysis |
| `harness://context` | Aggregated project context |
| `harness://evolution-history` | Complete mutation history with results |

### 2.2 Hooks (8 total)

| Hook | Type | Role | Token cost |
|---|---|---|---|
| `SessionStart` | `command` | Init + inject additionalContext with frontier summary | 0 |
| `PostToolUse` (Write/Edit) | `command` | Log complete traces (tool_input + tool_response) | 0 |
| `PostToolUse` (Bash) | `command` | Capture stdout/stderr for execution traces | 0 |
| `Stop` | `prompt` (Haiku) | Quality gate: "Did agent record eval metrics?" | ~100 |
| `PostCompact` | `command` | Re-inject critical state (frontier top-3, current run, hypothesis) | 0 |
| `TaskCompleted` | `command` | Verify eval recorded before allowing completion | 0 |
| `SubagentStop` | `command` | Capture subagent results for traces | 0 |
| `InstructionsLoaded` | `command` | Audit which instruction files loaded and their size | 0 |

7/8 hooks are `command` type (zero token cost). Only the Stop hook uses Haiku (~100 tokens).

### 2.3 Agents (4 total)

| Agent | Isolation | Role | Write? |
|---|---|---|---|
| `harness-proposer` | worktree | Propose ONE coherent candidate based on history + traces + context | Yes |
| `harness-evaluator` | worktree | Execute eval tasks, LLM-as-judge, record metrics | No (judge) |
| `regression-auditor` | worktree | Causal analysis of regressions, falsifiable recommendations | No |
| `context-harvester` | none | Extract project memory, docs, git, plugins → structured context | No |

### 2.4 Skills (6 total)

| Skill | Role |
|---|---|
| `/mh:evolve <objective>` | Full loop: harvest → propose → evaluate → audit → report |
| `/mh:frontier` | Pareto frontier dashboard with rich visualization |
| `/mh:regressions` | Regression audit + recommendations |
| `/mh:eval [run_id]` | Run eval suite on a candidate or current harness |
| `/mh:dashboard` | Full status: frontier + runs + traces + metrics + health |
| `/mh:bootstrap` | Intelligent project onboarding, auto-generate eval tasks |

### 2.5 Eval Framework

```
eval-tasks/
├── _schema.yaml          # Reference format
├── capability/           # Hard tasks (measure ceiling)
└── regression/           # Easy tasks (must always pass)
```

**3-layer grading:**

1. **Deterministic** (free, instant): patch valid? tests pass? linter OK? tokens < threshold?
2. **LLM-as-judge** (Haiku, ~200 tokens): instruction adherence 1-5, code quality 1-5, pairwise before/after
3. **Consistency** (multi-trial): pass@1 AND pass^3

**Extended frontier.tsv columns:**
```
run_id | status | primary_score | avg_latency_ms | avg_input_tokens | risk |
consistency | instruction_adherence | tool_efficiency | error_count | note | timestamp
```

### 2.6 Output Style (`output-styles/meta-harness.md`)

```yaml
name: Meta-Harness
description: Proof-first harness engineering with rich metrics display
keep-coding-instructions: true
```

Signature visual formats:
- `⚗ EVOLUTION REPORT ━━━` — candidate results with before/after deltas
- `◆ FRONTIER ━━━` — Pareto frontier visualization with sparklines
- `⚠ REGRESSION ━━━` — regression alerts with causal analysis
- Trend sparklines: `▁▂▃▄▅▆▇█`
- Delta indicators: `▲` improvement, `▼` regression, `●` stable

No emoji. Unicode symbols only (⚗◆⚠●▲▼✦✓✗). Technical rigor as brand identity.

### 2.7 File Structure

```
Meta-Harness-YGN/
├── .claude-plugin/plugin.json    # mcpServers, outputStyles
├── .mcp.json                     # MCP server config
├── servers/mh-server.py          # FastMCP brain
├── agents/
│   ├── harness-proposer.md       # Enhanced with anti-hallucination
│   ├── harness-evaluator.md      # NEW
│   ├── regression-auditor.md     # Enhanced
│   └── context-harvester.md      # NEW
├── skills/
│   ├── harness-evolve/SKILL.md   # Enhanced: 5-phase loop
│   ├── harness-frontier/SKILL.md # Enhanced: rich visualization
│   ├── harness-regressions/SKILL.md
│   ├── harness-eval/SKILL.md     # NEW
│   ├── harness-dashboard/SKILL.md # NEW
│   └── harness-bootstrap/SKILL.md # NEW
├── hooks/hooks.json              # 8 hooks
├── output-styles/meta-harness.md # Signature branding
├── eval-tasks/                   # Eval task bank
│   ├── _schema.yaml
│   ├── capability/
│   └── regression/
├── bin/                          # CLI wrappers
├── scripts/
│   ├── meta_harness.py           # Enhanced core
│   └── context_harvester.py      # NEW
├── pyproject.toml                # Zero deps core, mcp optional
├── CLAUDE.md
├── README.md
└── CHANGELOG.md
```

---

## 3. Autonomous Evolution Loop

### 5-phase workflow

```
/mh:evolve <objective>
    │
    ├── PHASE 1: HARVEST — context-harvester extracts project context
    │   Output: harness://context (MCP resource)
    │
    ├── PHASE 2: PROPOSE — harness-proposer (worktree) creates candidate
    │   Output: runs/run-NNNN/ (hypothesis, patch, safety-note)
    │
    ├── PHASE 3: EVALUATE — harness-evaluator (worktree) measures
    │   Output: metrics.json + frontier.tsv updated
    │
    ├── PHASE 4: AUDIT — regression-auditor (read-only) analyzes
    │   Output: analysis.md in runs/run-NNNN/
    │
    └── PHASE 5: REPORT — output style renders results
        Output: ⚗ EVOLUTION REPORT with before/after deltas
```

### 3 execution modes

1. **Single pass** (`/mh:evolve <objective>`) — One iteration, user decides to promote
2. **Multi-pass** (`/mh:evolve <objective> --iterations N`) — N sequential iterations, each informed by prior traces
3. **Scheduled** (via RemoteTrigger) — Recurring optimization in background

### Coordination via disk artifacts

Each phase produces files consumed by the next. No in-memory dependencies between agents. If context compacts or session crashes, the chain resumes from the last checkpoint.

```
HARVEST  → harness://context         (MCP resource)
PROPOSE  → runs/run-NNNN/            (files on disk)
EVALUATE → runs/run-NNNN/metrics.json (+ frontier.tsv)
AUDIT    → runs/run-NNNN/analysis.md  (+ regression update)
REPORT   → stdout via output style    (visible to user)
```

---

## 4. Context Engine

### 3-temperature architecture

| Temperature | Loaded when | Budget | Content |
|---|---|---|---|
| **HOT** | Always (SessionStart additionalContext) | <500 tokens | Critical constraints, build commands, top-3 frontier |
| **WARM** | Per skill invocation (dynamic `!` blocks) | <1500 tokens | Architecture, git patterns, project memory, plugin surfaces |
| **COLD** | On-demand (MCP resources) | Unlimited | Raw traces, full git history, complete docs, plugin configs |

### COLLECT → EXTRACT → SCORE → COMPACT pipeline

**Stage 1: COLLECT** (parallel, ~2s)
- CLAUDE.md + .claude/rules/ → constraints, conventions
- MEMORY.md + topic files → project-specific insights
- git log/diff/blame → hotspots, focus areas, commit patterns
- README + docs/ → architecture decisions
- installed_plugins.json → plugin surfaces

**Stage 2: EXTRACT**
- Split markdown by ## headers into chunks
- Parse conventional commits (type/scope)
- Extract imperative sentences (must/never/always/should)
- File churn analysis for pain points
- Deduplicate with fuzzy matching

**Stage 3: SCORE**
```
score = (w1 * BM25(item, objective) + w2 * recency + w3 * frequency + w4 * specificity) * source_weight
```
Source weights: claude_md=1.0, memory=0.9, git_recent=0.8, docs=0.7, git_old=0.5, plugins=0.6.
Multi-source merge via Reciprocal Rank Fusion (RRF, k=60).

**Stage 4: COMPACT** (budget: 2000 tokens)
- Sort by score descending
- Greedy pack until budget exhausted
- Lower-priority items compressed to one-liners
- Structured markdown output

### Plugin discovery

The MCP server reads `~/.claude/plugins/installed_plugins.json` to enumerate installed plugins, then reads each plugin's `plugin.json`, skills, agents, hooks, and MCP configs. Cross-references with `enabledPlugins` from settings to determine active plugins. Exposes this as optimizable harness surface.

### Memory extraction

Reads `~/.claude/projects/<project-hash>/memory/` directory. Parses MEMORY.md index + topic files. Scores each extracted insight against the current optimization objective via BM25. Only loads topic files whose name/preview exceeds a relevance threshold (0.3).

---

## 5. Output Style & Branding

### Output style specification

```markdown
---
name: Meta-Harness
description: Proof-first harness engineering with rich metrics display
keep-coding-instructions: true
---
```

`keep-coding-instructions: true` preserves Claude Code's software engineering capabilities while adding the proof-first formatting layer.

### Visual vocabulary

| Context | Symbol | Usage |
|---|---|---|
| Evolution report | `⚗` | Report header |
| Frontier Pareto | `◆` | Frontier header |
| Regression | `⚠` | Alert header |
| Dashboard | `◉` | Overview header |
| Heavy separator | `━━━` | Block delimiters |
| Improvement | `▲` | After positive delta |
| Regression | `▼` | After negative delta |
| Stable | `●` | No significant change |
| Trend | `▁▂▃▄▅▆▇█` | Sparkline on 3+ data points |
| Pareto dominant | `✦` | Candidate dominates baseline |
| Rejected | `✗` | Dominated candidate |
| Promoted | `✓` | Validated candidate |

### Report templates

**Evolution report:**
```
⚗ EVOLUTION REPORT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: [run_id] | Hypothesis: [one-line]

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

### README branding

Comparative table vs competitors, badges, 3-step quick start, component table with symbols, architecture diagram, benchmark results. Tagline: "Don't guess. Evolve. Prove."

---

## 6. Robustness & Stability

### Known Claude Code bugs to work around

| Bug | Impact | Workaround |
|---|---|---|
| MCP servers don't auto-reconnect ([#24350](https://github.com/anthropics/claude-code/issues/24350)) | MCP server is vital | Stateless design: all state on disk |
| False "hook error" labels ([#34713](https://github.com/anthropics/claude-code/issues/34713)) | 200+ false errors/session | Minimize frequent hooks, strict matchers |
| Windows paths break bash hooks ([#18527](https://github.com/anthropics/claude-code/issues/18527)) | We're on Windows | Critical hooks in Node.js, `path.join()` everywhere |
| Team agent worktree ignored ([#33045](https://github.com/anthropics/claude-code/issues/33045)) | Agents use worktree | Use subagents, not agent teams |
| FastMCP ClosedResourceError ([#823](https://github.com/jlowin/fastmcp/issues/823)) | Client timeout crashes server | Explicit timeouts + try/except + progress notifications |

### 4-layer resilience

**Layer 1 — Crash Recovery:**
- `checkpoint.json` written after each phase (survives crashes)
- `context-snapshot.md` written early in runs (survives context compaction)
- SessionStart hook detects incomplete runs and offers to resume
- PostCompact hook re-injects critical state (~500 tokens)

**Layer 2 — Validation Gates:**
- Gate 1 (structural, 0 tokens): patch applies, files parse, scope respected
- Gate 2 (semantic, ~500 tokens Haiku): diff matches hypothesis, scope lock verified
- Gate 3 (baseline regression, ~2000 tokens): metrics >= frontier leader on all axes

**Layer 3 — Defensive Prompting:**
- Anti-hallucination clause: no metric claims without evidence from prior runs
- Scope lock reminder at turn 15: force hypothesis serialization + scope narrowing
- Constrained output template for hypothesis.md: Claim / Evidence / Predicted impact / Risk

**Layer 4 — Graceful Degradation:**
- Skills work WITHOUT MCP server via `!` blocks calling bin/ scripts directly
- Non-critical hooks always `exit 0` (never block on failure)
- Python dependency check with clear warning if missing
- Fallback: `uv sync` → `pip install` → stdlib-only mode

### 4-verdict system

| Verdict | Meaning | Action |
|---|---|---|
| `accepted` | Pareto dominant, all gates passed | Ready to promote |
| `accepted_with_warnings` | Improvement but identified risks | Promote with monitoring |
| `rejected` | Regression or failed gates | Archive, do not promote |
| `partial` | Some axes improved, others regressed | Iterate with focus |

### Reliability tax budget

| Mechanism | Token cost | Frequency |
|---|---|---|
| Checkpoints on disk | 0 | Every phase |
| Gate 1 (structural) | 0 | Every candidate |
| Gate 2 (semantic, Haiku) | ~500 | Every candidate |
| Gate 3 (baseline eval) | ~2000 | Only before PROMOTE |
| Stop hook quality gate | ~100 | Every Stop |
| PostCompact re-injection | 0 | Every compact |

**Total: ~600 tokens/candidate** (~3% of a typical run). Gate 3 only fires for promotions.

### Cross-platform rules

- Critical hooks in Node.js (not bash) for Windows compatibility
- Python uses `pathlib.Path` exclusively (no hardcoded separators)
- `os.homedir()` instead of `$HOME` in Node.js hooks
- Core script (`meta_harness.py`) has **zero external dependencies** (stdlib only)
- MCP server requires `mcp` package (optional dependency)

### Dependency management

```toml
# pyproject.toml
[project]
name = "meta-harness-ygn"
version = "0.2.0"
requires-python = ">=3.10"
dependencies = []  # Zero external deps for core

[project.optional-dependencies]
mcp = ["mcp>=1.12"]  # Only for MCP server
```

---

## 7. Implementation Roadmap

### 6 phases

| Phase | Version | Deliverable |
|---|---|---|
| **0: Walking Skeleton** | 0.1.0 | End-to-end wiring: MCP minimal + output style + SessionStart hook |
| **1: MCP Server + Core** | 0.2.0 | Full MCP server (8 tools, 5 resources), 6 hooks, extended frontier |
| **2: Context Engine** | 0.3.0 | Context harvester, plugin discovery, memory extraction |
| **3: Eval Framework** | 0.4.0 | Evaluator agent, 3-layer grading, eval task bank, bootstrap skill |
| **4: Autonomous Loop** | 0.5.0 | 5 phases wired, multi-pass, dashboard skill, rollback |
| **5: Polish & Marketplace** | 1.0.0 | README, docs, CHANGELOG, meta-benchmark, marketplace submission |

### Dependency graph

```
Phase 0 ──┬── Phase 1 ──┬── Phase 2 ──┐
           │             │             ├── Phase 4 ── Phase 5
           │             └── Phase 3 ──┘
           │
           └── (output style usable immediately)
```

Phases 2 and 3 can proceed in parallel (independent agents).

### Phase 0 acceptance criteria

```
claude --plugin-dir ./Meta-Harness-YGN
# → MCP server starts
# → /mh:frontier displays dashboard via MCP resource
# → SessionStart injects frontier summary into additionalContext
# → Output style visible in /config
```

### Phase 5 acceptance criteria (marketplace-ready)

```
claude plugin validate .  → clean
README > 200 words with examples
CHANGELOG.md complete
At least 1 real benchmark documented
Cross-platform verified (Windows + macOS/Linux)
Quality rubric target: Gold (84/100)
```

### Meta-benchmark (Phase 5 final deliverable)

The plugin optimizes its own harness:
1. `/mh:bootstrap` on the Meta-Harness-YGN repo itself
2. `/mh:evolve "improve proposal quality"` for 5 iterations
3. Document measured results in README as proof

---

## Research References

### Papers
- Meta-Harness: End-to-End Optimization of Model Harnesses (arXiv:2603.28052)
- GEPA: Reflective Prompt Evolution (arXiv:2507.19457, ICLR 2026 Oral)
- A Self-Improving Coding Agent (arXiv:2504.15228)
- ADAS: Automated Design of Agentic Systems (arXiv:2408.08435, ICLR 2025)
- TextGrad: Automatic Differentiation via Text (arXiv:2406.07496, Nature 2025)
- Natural-Language Agent Harnesses (arXiv:2603.25723)
- SWE-Bench Pro: Long-Horizon Tasks (arXiv:2509.16941)
- VIGIL: Reflective Runtime for Self-Healing Agents (arXiv:2512.07094)
- PALADIN: Self-Correcting Language Model Agents (arXiv:2509.25238)
- Contextual Memory Virtualisation (arXiv:2602.22402)

### Ecosystem resources
- Claude Code Plugins Reference: code.claude.com/docs/en/plugins-reference
- MCP Python SDK: github.com/modelcontextprotocol/python-sdk
- CLAUDE.md Best Practices: arize.com/blog/claude-md-best-practices
- ETH Zurich AGENTbench: infoq.com/news/2026/03/agents-context-file-value-review
- Anthropic Context Engineering: anthropic.com/engineering/effective-context-engineering
