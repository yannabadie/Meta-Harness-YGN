---
name: frontier
description: Summarize the current Meta-Harness-style frontier of harness candidates, including quality, cost, latency, and safety notes.
context: fork
agent: regression-auditor
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(mh-frontier *) Bash(find *) Bash(ls *) Bash(cat *)
---
Provide a concise frontier review using the current run ledger.

## Current frontier
```!
mh-frontier --markdown
```

## Instructions
- Highlight dominant and non-dominated candidates.
- Explain the trade-offs in plain language.
- Call out candidates that are strong but risky.
- Suggest the most informative next experiment.
