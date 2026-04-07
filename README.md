# ⚗ Meta-Harness-YGN

**Don't guess. Evolve. Prove.**

[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin%20%2F%2Fmh-5A67D8?logo=anthropic&logoColor=white)](https://claude.ai/code)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/yannabadie/Meta-Harness-YGN?style=flat)](https://github.com/yannabadie/Meta-Harness-YGN/stargazers)
[![Version](https://img.shields.io/badge/version-v1.0.0-blue)](https://github.com/yannabadie/Meta-Harness-YGN/releases)

Meta-Harness-YGN is a Claude Code plugin (namespace `/mh`) that brings scientific rigor to harness engineering: every proposed change produces a falsifiable hypothesis, a reproducible evaluation against a 9-check suite, and a recorded entry on a multi-objective Pareto frontier — so you always know whether your harness actually improved, regressed, or just changed.

---

## Why Not the Alternatives?

| Capability | ⚗ Meta-Harness-YGN | ECC (144K ★) | Superpowers (139K ★) | Skill-creator (official) |
|---|:---:|:---:|:---:|:---:|
| Harness-level optimization | Yes | No | No | No |
| Falsifiable hypotheses per candidate | Yes | No | No | No |
| Deterministic eval suite (55 checks) | Yes | No | No | Partial |
| Pareto frontier across score / latency / cost | Yes | No | No | No |
| Regression detection + causal audit | Yes | No | No | No |
| Proposer / evaluator context break | Yes | No | No | No |
| MCP server (7 tools, 4 resources) | Yes | No | No | No |
| Safe additive-change policy | Yes | No | No | No |

ECC is an enormous prompt library — useful, but entirely ad hoc.  
Superpowers provides methodology but nothing to measure outcomes against.  
Skill-creator evaluates individual skills in isolation, not the harness as a whole.

---

## Quick Start

**1. Install**

```bash
git clone https://github.com/yannabadie/Meta-Harness-YGN.git
pip install "mcp>=1.12"   # optional — required for MCP server only
```

**2. Load**

```bash
claude --plugin-dir ./Meta-Harness-YGN
```

**3. Use**

```
/mh:bootstrap             # analyse project and generate initial eval tasks
/mh:evolve improve retrieval + validation harness for flaky coding tasks
/mh:frontier              # inspect the Pareto frontier
```

---

## Components

| Command | Symbol | Purpose |
|---|:---:|---|
| `/mh:evolve` | ⚗ | Full 5-phase evolution pipeline — harvest, propose, evaluate, audit, report |
| `/mh:frontier` | ◆ | Visualize the Pareto frontier across score, latency, and token cost |
| `/mh:regressions` | ⚠ | Regression audit with causal analysis and safer next-step recommendations |
| `/mh:dashboard` | ◉ | Live status view — frontier health, eval pass rate, incomplete runs |
| `/mh:eval` | 🔬 | Run the evaluation suite against the current harness or a specific candidate |
| `/mh:bootstrap` | 🏗 | Onboard a new project — generates regression and capability eval tasks |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Skills  /mh:evolve  /mh:frontier  /mh:regressions │
│          /mh:dashboard  /mh:eval  /mh:bootstrap  │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │   MCP Server            │
        │   7 tools · 4 resources │
        └────────────┬────────────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
  Agents           Hooks           Core scripts
  harness-proposer SessionStart    meta_harness.py
  harness-evaluator PostToolUse    eval_runner.py
  regression-auditor PostCompact   context_harvester.py
  context-harvester  Stop / SubagentStop
                     InstructionsLoaded
                     │
                     ▼
            Persistent state (${CLAUDE_PLUGIN_DATA})
            frontier.tsv · runs/ · sessions/
```

Four agents, six skills, and seven hooks wire together a reproducible pipeline where the proposer never sees the evaluator's context — preventing self-congratulatory scoring.

---

## Example Output

```
⚗ EVOLUTION REPORT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: run-0012 | Hypothesis: tighter tool-call validation
reduces eval-task false negatives

| Metric        | Baseline | Candidate | Delta    |
|---------------|----------|-----------|----------|
| Score         | 0.764    | 0.821     | +7.5%  ▲ |
| Latency (ms)  | 8120     | 7340      | -9.6%  ▲ |
| Tokens        | 11382    | 10890     | -4.3%  ▲ |

Confidence: N=12 | Method: deterministic + LLM-judge
Risk: low — additive validation layer, fully reversible
Verdict: PROMOTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## MCP Server

`servers/mh_server.py` is a FastMCP server over stdio. Start it with:

```bash
python3 servers/mh_server.py
```

### Tools

| Tool | Description |
|---|---|
| `frontier_read` | Read the Pareto frontier; returns markdown table or JSON |
| `frontier_record` | Write candidate metrics to `frontier.tsv` |
| `trace_search` | Search session logs and run artifacts by keyword or run ID |
| `candidate_diff` | Retrieve patch, hypothesis, safety note, and validation for a run |
| `plugin_scan` | Scan installed Claude Code plugins and report their harness surfaces |
| `context_harvest` | BM25-scored project context extraction within a token budget |
| `eval_run` | Execute the full 9-check evaluation suite and return scored results |

### Resources

| URI | Description |
|---|---|
| `harness://dashboard` | Pareto frontier + recent runs + regression count |
| `harness://traces/{run_id}` | All artifacts for a specific candidate run |
| `harness://regressions` | Runs where score dropped below the previous best |
| `harness://context` | Aggregated project context for the current working directory |

---

## Evaluation Framework

The eval suite (`eval-tasks/`) combines deterministic checks (60% weight) and LLM-judge criteria (40% weight) into a single `0–1` score recorded per run.

### Check Types

| Type | What it verifies |
|---|---|
| `exit_code` | Command exits with expected code |
| `file_exists` | Required artifact is present on disk |
| `file_contains` | File includes a mandatory string or pattern |
| `file_not_contains` | File is free of forbidden content |
| `json_valid` | File parses as well-formed JSON |
| `command_output` | Command stdout matches expected value |
| `llm_judge` | LLM assesses a plain-English criterion with evidence |
| Regression guard | Score did not drop below previous frontier leader |
| Scope guard | Patch touches only declared harness surfaces |

Run the suite at any time:

```bash
python3 scripts/eval_runner.py --eval-dir eval-tasks --cwd . --json
```

---

## Hooks

Seven lifecycle hooks enforce discipline without requiring manual steps:

| Event | Hook | Effect |
|---|---|---|
| `SessionStart` | `session-start.mjs` | Initialize persistent storage; inject frontier context |
| `PostToolUse` | `mh-log-write` | Trace every file write to the session log |
| `Stop` | `mh-record-session` | Persist the session journal to `sessions/` |
| `Stop` | Haiku quality gate | Block stop if `/mh:evolve` ran without recording metrics |
| `PostCompact` | `meta_harness.py compact-summary` | Recover context after conversation compaction |
| `InstructionsLoaded` | `log-instructions.mjs` | Record loaded instruction set for reproducibility |
| `SubagentStop` | `capture-subagent.mjs` | Capture subagent output to the run directory |

---

## Roadmap

### Done (v1.0.0)
- 5-phase evolution pipeline with proposer / evaluator context break
- Multi-objective Pareto frontier (score, latency, token cost, risk)
- 9-check deterministic + LLM-judge eval suite (55 tests)
- FastMCP server with 7 tools and 4 resources
- 4 specialized agents (proposer, evaluator, auditor, context harvester)
- 7 lifecycle hooks including quality gate at Stop
- `context_harvest` with BM25 relevance scoring
- `/mh:bootstrap` for zero-config project onboarding
- Rollback support via `mh-rollback`

### Next
- Parallel candidate evaluation (multi-worktree runs)
- Automated promotion to `.claude/` on PROMOTE verdict
- Time-series frontier visualization
- Cross-project frontier comparison
- GitHub Actions integration for CI-gated harness evolution

---

## License

MIT — see [LICENSE](LICENSE).
