# Core Concepts

This document explains the mental model behind Meta-Harness. If you are already familiar with Claude Code but new to this plugin, start here.

---

## What Is a "Harness" in Claude Code?

A **harness** is the collection of configuration artifacts that shape how Claude Code behaves in a repository. These artifacts are all text files — no binaries, no compiled code. Changing a harness means editing these files.

The harness surfaces Meta-Harness can propose, evaluate, and track:

| Surface | Location | What it controls |
|---|---|---|
| `CLAUDE.md` | Repository root | Primary instructions loaded into every session; the most influential harness file |
| Skills | `.claude/skills/*/SKILL.md` or `skills/*/SKILL.md` | Slash commands (`/namespace:name`); define what Claude does when invoked |
| Agents | `.claude/agents/*.md` or `agents/*.md` | Subagents with their own model, tool restrictions, isolation, and system prompt |
| Rules | `.claude/rules/*.md` | Always-on instructions loaded alongside `CLAUDE.md` |
| Hooks | `hooks/hooks.json` | Event-driven scripts triggered on `SessionStart`, `PostToolUse`, `Stop`, etc. |
| Prompts | `prompts/**` or `.meta-harness/**` | Template strings and prompt components referenced by skills or agents |

A harness that is too long, contradictory, or full of instructions Claude already follows by default is worse than a short, precise one. The ETH Zurich finding referenced in the README is real: larger context files do not reliably improve performance and often degrade it.

---

## What Is Harness Optimization?

**Ad hoc harness tweaking** looks like: "I'll add a rule about not editing test files." You edit `CLAUDE.md`, try a few tasks, it feels better, you move on. Three months later you don't remember why the rule is there, whether it helped, or whether it conflicts with the new agent you added last week.

**Harness optimization** is the systematic alternative:

1. You state a specific objective: "reduce tool thrashing on refactoring tasks."
2. A proposer agent generates one controlled change: a single hypothesis, one patch, under 3 files.
3. An evaluator measures the change against 9 deterministic checks plus LLM-judge criteria.
4. The result is recorded on a Pareto frontier with full metrics.
5. Every change is reversible: a git patch plus a safety tag.

The key difference is **measurement before claim**. Nothing is "better" until it has a recorded before/after delta.

---

## The Pareto Frontier Concept

A **Pareto frontier** (also called a Pareto front) is the set of candidates where no other candidate is strictly better on every objective simultaneously.

Meta-Harness tracks three objectives for each harness candidate:

| Objective | Direction | What it measures |
|---|---|---|
| `primary_score` | Maximize | Weighted fraction of eval checks passed |
| `avg_latency_ms` | Minimize | Average response latency observed during evaluation |
| `avg_input_tokens` | Minimize | Average input tokens consumed |

A candidate **dominates** another if it is at least as good on all three axes and strictly better on at least one. Dominated candidates are removed from the frontier.

### Example

Suppose you have three candidates:

| Run | Score | Latency | Tokens |
|---|---|---|---|
| run-0006 | 0.95 | 5200ms | 8500 |
| run-0009 | 0.76 | 7800ms | 12100 |
| run-0012 | 0.82 | 7340ms | 10900 |

Is run-0009 dominated? Check against run-0012: run-0012 has higher score (0.82 > 0.76), lower latency (7340 < 7800), and lower tokens (10900 < 12100). Run-0012 dominates run-0009 on all three axes. Run-0009 is removed.

Is run-0012 dominated by run-0006? Run-0006 has higher score (0.95 > 0.82) and lower latency and tokens. Yes — run-0012 is dominated.

Final frontier: only **run-0006** survives. It is the single non-dominated candidate.

But if run-0012 had a lower latency than run-0006 despite a lower score, neither would dominate the other and both would stay on the frontier. That is the trade-off the frontier captures.

The frontier always answers the question: "given these objectives, what is the best set of candidates no single choice improves upon across all dimensions?"

---

## The Evolution Loop

The `/mh:evolve` command runs a 5-phase loop that repeats each time you invoke it:

```
Harvest → Propose → Evaluate → Audit → Report
```

### Phase 1: Harvest

The `context-harvester` agent (Claude Haiku, max 5 turns, write-disabled) extracts project context relevant to your objective. Sources in priority order:

1. `CLAUDE.md` and `.claude/rules/` (weight 1.0)
2. `~/.claude/projects/*/memory/` (weight 0.9 for current project, 0.3 for others)
3. Git log, file hotspots, recent diff stat (weight 0.8)
4. `README.md` and `docs/*.md` (weight 0.7)

Scoring uses BM25 (Okapi BM25, Lucene-variant IDF) against your objective query, merged with recency ranking via Reciprocal Rank Fusion. The output is packed within a token budget (default: 1500 tokens for the evolve pipeline).

### Phase 2: Propose

The `harness-proposer` agent (inherits model, max 30 turns, worktree-isolated) receives the harvested context plus the frontier and regression history. It must:

- Write exactly one coherent hypothesis
- Modify at most 3 files
- Stay within allowed harness surfaces
- Produce `hypothesis.md`, `safety-note.md`, `candidate.patch`, and `validation.txt`

The proposer also receives a `plugin_scan` of all installed Claude Code plugins, so it can propose harness improvements that reference capabilities from other plugins.

### Phase 3: Evaluate

The `harness-evaluator` agent (inherits model, max 20 turns, read-only, worktree-isolated) reads only the disk artifacts from the run directory — never the proposer's conversation or reasoning. This is the **context break**.

The evaluator runs:

```bash
python scripts/eval_runner.py --eval-dir eval-tasks --cwd . --json
```

Then assesses each `llm_judge` criterion manually. The final score is:

```
final_score = 0.6 × deterministic_score + 0.4 × llm_judge_score
```

Verdicts:
- `accepted` — final_score ≥ 0.8 and no critical failures
- `accepted_with_warnings` — 0.6 ≤ final_score < 0.8
- `rejected` — final_score < 0.6 or critical failure
- `partial` — some axes improved, others regressed vs frontier

### Phase 4: Audit

The `regression-auditor` agent (inherits model, max 20 turns, read-only, worktree-isolated) compares the candidate against prior frontier leaders. It writes `analysis.md` with:

- Regression summary and score delta
- Likely causal mechanism (not just "score went down")
- Confidence level with reasoning
- Confounds (e.g., "prompt rewrite and stop condition changed simultaneously")
- Specific, falsifiable recommendation for the next experiment

### Phase 5: Report

The orchestrator (the `/mh:evolve` skill itself) synthesizes all artifacts into the Evolution Report format and presents the verdict: **PROMOTE**, **REJECT**, or **ITERATE**.

---

## Candidates, Hypotheses, and Patches

Each evolution run produces a **candidate** — a proposed harness state stored as a directory of artifacts:

```
$CLAUDE_PLUGIN_DATA/runs/run-0001/
├── hypothesis.md       # Claim, Evidence, Predicted impact, Risk
├── safety-note.md      # What could go wrong; why it is reversible
├── candidate.patch     # Unified diff (git format)
├── validation.txt      # Output of mh-validate
├── metrics.json        # Scores, latency, tokens, risk, timestamp
├── notes.md            # Free-form notes
├── analysis.md         # Regression auditor's analysis (written by auditor)
└── checkpoint.json     # Crash recovery: phase, turn, objective
```

A **hypothesis** is the proposer's structured claim: one sentence about what changed and why it should help, backed by evidence from prior runs or labeled as an untested hypothesis if no prior data exists.

A **patch** is a standard unified diff in git format. It is applied with `git apply` for promotion and reversed with `git apply -R` for rollback. Maximum 3 files. Only harness surfaces allowed.

---

## The Context Break Between Proposer and Evaluator

The most important architectural constraint in Meta-Harness is the **context break** between the proposer and evaluator.

The evaluator is explicitly instructed:

> You must evaluate ONLY the candidate's output artifacts. Do NOT read the proposer's conversation, reasoning, or internal notes. Do NOT ask about the proposer's intent — judge the artifacts alone.

**Why this matters:** If the evaluator could read the proposer's reasoning, it would tend toward agreement — a form of self-congratulatory scoring. By restricting the evaluator to disk artifacts only, the evaluation is objective: either the `hypothesis.md` is clear and specific, or it is not; either the `candidate.patch` is non-empty and in scope, or it is not.

This mirrors the separation between author and reviewer in code review: the reviewer judges the code, not the author's intentions.

---

## Summary

| Concept | One-line definition |
|---|---|
| Harness | CLAUDE.md + skills + agents + rules + hooks + prompts |
| Harness optimization | Systematic, measured improvement with before/after deltas |
| Pareto frontier | The set of non-dominated candidates across score, latency, tokens |
| Evolution loop | Harvest → Propose → Evaluate → Audit → Report |
| Candidate | One run's artifacts: hypothesis, patch, metrics, analysis |
| Context break | Evaluator reads only disk artifacts, never proposer's reasoning |

---

See [Commands Reference](commands-reference.md) for every available command, [Eval Tasks Guide](eval-tasks-guide.md) for how to write evaluation criteria, and [Architecture](architecture.md) for implementation details.
