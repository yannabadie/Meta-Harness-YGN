# ⚗ Meta-Harness-YGN

**Don't guess. Evolve. Prove.**

[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin%20%2F%2Fmh-5A67D8?logo=anthropic&logoColor=white)](https://claude.ai/code)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/yannabadie/Meta-Harness-YGN?style=flat)](https://github.com/yannabadie/Meta-Harness-YGN/stargazers)
[![Version](https://img.shields.io/badge/version-v1.0.0-blue)](https://github.com/yannabadie/Meta-Harness-YGN/releases)

---

## The Problem

You've spent hours tweaking your CLAUDE.md, writing custom skills, adjusting agent prompts. But you have **no idea if any of it actually helped.** Did that new rule reduce errors? Did that prompt rewrite cost more tokens? Did the last edit break something that used to work?

Every other approach to harness optimization is guesswork:

- **Edit, hope, repeat** — no measurement, no history, no rollback
- **Copy someone else's CLAUDE.md** — their project isn't yours
- **Add more instructions** — research shows this often makes things worse (ETH Zurich: LLM-generated context files degrade performance by 3%)

## The Solution

Meta-Harness turns harness engineering into a **scientific process**:

1. **You describe what to improve** — `/mh:evolve "reduce tool thrashing on refactoring tasks"`
2. **The plugin proposes a controlled change** — one hypothesis, one patch, with predicted impact and risk assessment
3. **It evaluates the change with evidence** — 9 deterministic checks, not vibes
4. **It tracks everything on a Pareto frontier** — score vs. latency vs. token cost, so you see trade-offs
5. **If something regresses, it explains why** — causal analysis, not just "score went down"

Every improvement has a measured before/after delta. Every regression has a diagnosis. Nothing is lost.

---

## What Can You Do With It?

### "My CLAUDE.md is 300 lines and I don't know what's helping"

```
/mh:eval
```

Runs 9 deterministic checks against your current harness. Shows exactly what's valid, what's broken, and what's untested. Then:

```
/mh:evolve "simplify CLAUDE.md — remove instructions Claude follows without being told"
```

The proposer reads your CLAUDE.md, compares against actual Claude behavior, and suggests specific deletions with predicted token savings.

### "Claude keeps editing files it shouldn't touch"

```
/mh:evolve "add scope constraints to prevent application code edits"
```

The proposer creates a `.claude/rules/` file with path-scoped constraints. The evaluator checks that the `files_in_scope` guard passes. If promoted, the change is tracked with a reversible patch.

### "Someone changed the prompts and now everything is worse"

```
/mh:regressions
```

Shows which run caused the score drop, compares the patch diff against the frontier leader, and identifies confounds ("prompt rewrite and stop condition changed simultaneously — test them in isolation").

```
/mh:rollback run-0011
```

Reverse-applies the patch with a safety git tag. One command, no risk.

### "I want to optimize but I don't know where to start"

```
/mh:bootstrap
```

Analyzes your project — CLAUDE.md, rules, skills, agents, git history, installed plugins — and generates initial eval tasks. Creates both regression tests (things that should always work) and capability tests (things you want to improve).

### "I have 8 plugins installed but no idea how they interact"

```
/mh:dashboard
```

Scans all installed Claude Code plugins, maps their skill/agent/hook surfaces, shows your Pareto frontier, eval health, and active regressions in one view.

### "I want to know if my harness is actually getting better over time"

Run `/mh:evolve` repeatedly. Each run is recorded on the Pareto frontier with full metrics:

```
◆ FRONTIER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
| Run       | Score | Latency | Tokens | Risk |
|-----------|-------|---------|--------|------|
| run-0012  | 0.82  | 7340ms  | 10.9K  | low  |
| run-0009  | 0.76  | 7800ms  | 12.1K  | low  |
| run-0006  | 0.95  | 5200ms  | 8.5K   | low  |

Non-dominated: 3 | Total runs: 12
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Only non-dominated candidates stay on the frontier. You always know the best trade-offs.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/yannabadie/Meta-Harness-YGN.git
pip install "mcp>=1.12"   # optional — MCP server only

# 2. Load
claude --plugin-dir ./Meta-Harness-YGN

# 3. Go
/mh:bootstrap                    # generate eval tasks for your project
/mh:evolve "improve validation"  # propose a measured improvement
/mh:dashboard                    # see the full picture
```

---

## How It Works

When you run `/mh:evolve`, five phases execute in sequence:

| Phase | What happens | Agent |
|-------|-------------|-------|
| **Harvest** | BM25-scored extraction of project context (CLAUDE.md, memory, git history, plugins) | context-harvester |
| **Propose** | One controlled change with hypothesis, patch, and risk assessment | harness-proposer (worktree-isolated) |
| **Evaluate** | 9 deterministic checks + LLM-judge criteria. Evaluator never sees proposer's reasoning (context break) | harness-evaluator |
| **Audit** | Causal regression analysis against the Pareto frontier | regression-auditor (read-only) |
| **Report** | Measured before/after deltas with verdict: PROMOTE / REJECT / ITERATE | — |

```
⚗ EVOLUTION REPORT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: run-0012 | Hypothesis: tighter tool-call validation

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

### Key design decisions

- **Evaluator never sees proposer's reasoning** — prevents self-congratulatory scoring
- **Maximum 3 files per patch** — keeps changes focused and reversible
- **Additive changes first** — new rules before prompt rewrites
- **Everything on disk** — crashes and context compaction don't lose progress
- **Zero external dependencies** for core (mcp package optional for MCP server)

---

## What's Under the Hood

| Layer | What | Count |
|-------|------|-------|
| Skills | Entry points (`/mh:evolve`, `frontier`, `regressions`, `dashboard`, `eval`, `bootstrap`) | 6 |
| MCP Server | Tools (frontier, traces, eval, plugins, context) + Resources (dashboard, traces, regressions, context) | 7 + 4 |
| Agents | Proposer, evaluator (context-break), auditor (read-only), harvester (BM25) | 4 |
| Hooks | SessionStart, PostToolUse, Stop (Haiku quality gate), PostCompact, InstructionsLoaded, SubagentStop | 7 |
| Eval checks | json_valid, file_exists, file_contains, file_not_contains, exit_code, command_output, patch_not_empty, max_files_changed, files_in_scope | 9 |
| Tests | Unit + integration | 55 |

---

## Does It Actually Work?

**Yes. The plugin optimized its own harness (run-0005):**

- **Gap found:** 4 eval check types were implemented but never wired into any eval task. A proposer could submit an empty or out-of-scope patch and pass all checks.
- **Fix applied:** Added 4 deterministic guards, promoting scope checking from LLM-judge-only to a hard gate.
- **Result:** 100% eval score maintained. Guardrail coverage increased from 3 to 7 checks.

This is the proof: the plugin found a real blind spot in its own eval suite and fixed it.

---

## License

MIT — see [LICENSE](LICENSE).
