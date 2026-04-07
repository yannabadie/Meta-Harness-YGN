# Phase 4: Autonomous Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the 5-phase evolution loop (Harvest→Propose→Evaluate→Audit→Report) as an inline orchestrator that dispatches agents sequentially. Add dashboard skill, rollback command, and safety guards.

**Architecture change:** `harness-evolve` becomes an INLINE skill (no `context: fork`) that dispatches 4 agents sequentially via the Agent tool. Multi-pass = user re-invokes the skill (not internal loop). Disk artifacts coordinate between agents.

**Tech Stack:** Markdown skills/agents, Python scripts, Node.js hooks.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Rewrite | `skills/harness-evolve/SKILL.md` | Inline orchestrator dispatching 4 agents |
| Enhance | `agents/harness-proposer.md` | Anti-hallucination, scope lock, output template |
| Enhance | `agents/harness-evaluator.md` | Context-break, reads only disk artifacts |
| Enhance | `agents/regression-auditor.md` | Structured output format |
| Create | `skills/harness-dashboard/SKILL.md` | /mh:dashboard aggregation view |
| Create | `bin/mh-rollback` | Reverse-apply candidate patch |
| Modify | `scripts/eval_runner.py` | Add novelty + scope checks |
| Modify | `tests/test_eval_runner.py` | Tests for new checks |

---

### Task 1: Restructure harness-evolve as Inline Orchestrator

**Files:**
- Rewrite: `skills/harness-evolve/SKILL.md`

The skill removes `context: fork` and `agent: harness-proposer` from frontmatter. It becomes an inline skill that instructs Claude to dispatch agents sequentially.

### Task 2: Enhance Agent Prompts

**Files:**
- Modify: `agents/harness-proposer.md` — add anti-hallucination, output template, scope lock
- Modify: `agents/harness-evaluator.md` — context-break (only read disk artifacts)
- Modify: `agents/regression-auditor.md` — structured output format

### Task 3: Dashboard Skill

**Files:**
- Create: `skills/harness-dashboard/SKILL.md`

### Task 4: Rollback Command + Eval Guards

**Files:**
- Create: `bin/mh-rollback`
- Modify: `scripts/eval_runner.py` — add novelty_check and scope_check
- Modify: `tests/test_eval_runner.py`

### Task 5: Integration Test + Tag v0.5.0
