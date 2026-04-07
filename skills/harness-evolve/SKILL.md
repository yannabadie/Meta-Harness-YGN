---
name: harness-evolve
description: Evolve repo-local Claude Code harness assets using full history, traces, and Pareto metrics. Use for context engineering, retrieval, validation, or control-flow improvements.
context: fork
agent: harness-proposer
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(git status *) Bash(git diff *) Bash(find *) Bash(ls *) Bash(cat *) Bash(head *) Bash(tail *) Bash(sed *) Bash(python3 *) Bash(node --version) Bash(npm --version) Bash(pytest *) Bash(make *) Bash(just *) Bash(uv *) Bash(ruff *) Bash(mypy *) Write Edit MultiEdit
---
ultrathink.

# Harness evolution task

Goal: improve the repository-local Claude Code harness for the following objective:

$ARGUMENTS

Operate on the harness layer, not arbitrary application code.

## Dynamic context: environment snapshot
```!
mh-bootstrap
```

## Dynamic context: current frontier
```!
mh-frontier --markdown
```

## Dynamic context: regressions and confounds
```!
mh-regressions --markdown
```

## Required workflow
1. Create or reserve a candidate id using `mh-next-run`.
2. Inspect prior candidate files, frontier notes, and regression summaries before editing.
3. Prefer additive changes before touching fragile prompt or control-flow machinery.
4. Keep the change set coherent around one hypothesis.
5. Run `mh-validate` before concluding.
6. Update the candidate directory with:
   - `hypothesis.md`
   - `safety-note.md`
   - `validation.txt`
   - `candidate.patch`
7. Report exactly:
   - what changed
   - why it should help
   - what risk remains
   - what should be measured next

## Default editable surfaces
- `CLAUDE.md`
- `.claude/skills/**`
- `.claude/agents/**`
- `.claude/rules/**`
- `prompts/**`
- `.meta-harness/**`
- helper scripts used by the harness

## Guardrails
- Do not claim benchmark gains without recorded metrics.
- Do not expand scope to product code unless the user explicitly asks.
- Avoid combined prompt + control-flow rewrites unless the evidence strongly justifies it.
- Favor reversible edits and explicit rationale.
