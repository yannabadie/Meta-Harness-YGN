---
name: regressions
description: Audit recent regressions in the harness search and identify likely confounds, brittle edits, and safer next-step ideas.
context: fork
agent: regression-auditor
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(mh-regressions *) Bash(find *) Bash(ls *) Bash(cat *) Bash(git diff *)
---
Analyze recent regressions in the harness search.

## Recent regression summary
```!
mh-regressions --markdown
```

## Instructions
- Identify repeated failure modes.
- Distinguish additive changes from risky structural rewrites.
- Recommend the next lower-risk candidate to test.
