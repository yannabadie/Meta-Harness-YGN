# meta-harness-lab

`meta-harness-lab` is a Claude Code plugin blueprint that turns **harness engineering** into a first-class workflow.

It is inspired by the paper **Meta-Harness: End-to-End Optimization of Model Harnesses** and adapts its main ideas to Claude Code plugins:

- optimize the **harness**, not only the prompt
- keep the **full history** of prior candidates, scores, traces, and regressions
- let a coding agent inspect that history and propose new harness variants
- maintain a **Pareto frontier** across quality, latency, token cost, and risk
- prefer **safe additive changes** before fragile control-loop rewrites
- separate **proposal** from **evaluation**

## What this plugin optimizes

By default, the proposer is asked to edit **repo-local Claude Code harness surfaces** only:

- `CLAUDE.md`
- `.claude/skills/**`
- `.claude/agents/**`
- `.claude/rules/**`
- prompt templates under `prompts/**` or `.meta-harness/**`
- helper scripts that support evaluation or retrieval

It should not rewrite arbitrary application code unless you explicitly widen the scope.

## Included components

- **Skill**: `/meta-harness-lab:harness-evolve`
  - launches one harness-evolution pass in an isolated subagent
- **Skill**: `/meta-harness-lab:harness-frontier`
  - summarizes the current Pareto frontier and recent runs
- **Skill**: `/meta-harness-lab:harness-regressions`
  - audits regressions and highlights likely confounds
- **Agent**: `harness-proposer`
  - worktree-isolated proposer for controlled edits
- **Agent**: `regression-auditor`
  - read-only regression analysis specialist
- **Hooks**
  - initialize persistent storage at session start
  - log edited files and keep a lightweight session journal
- **Executables in `bin/`**
  - `mh-bootstrap`
  - `mh-frontier`
  - `mh-regressions`
  - `mh-next-run`
  - `mh-record-metrics`
  - `mh-validate`

## Development usage

Load the plugin directly from disk:

```bash
claude --plugin-dir ./meta-harness-lab-plugin
```

Then inside Claude Code:

```text
/meta-harness-lab:harness-frontier
/meta-harness-lab:harness-regressions
/meta-harness-lab:harness-evolve improve our retrieval + validation harness for flaky coding tasks
```

## Persistent state

The plugin uses `${CLAUDE_PLUGIN_DATA}` for persistent state. It keeps:

- `runs/` — one directory per proposed candidate
- `sessions/` — lightweight hook logs
- `frontier.tsv` — Pareto-friendly run ledger

## Expected workflow

1. Start from a baseline harness.
2. Build a small hard search set.
3. Use `/meta-harness-lab:harness-evolve ...` to propose one controlled candidate.
4. Run your real evaluator outside the proposer.
5. Record metrics with `mh-record-metrics`.
6. Inspect the frontier and regressions.
7. Promote only candidates that are both better and safer.

## Notes

This repository is a **blueprint**, not a finished production plugin. You will likely adapt:

- the evaluation command
- the allowed edit surface
- the risk policy
- the metrics captured in `frontier.tsv`
- the validation command in `mh-validate`

## Example frontier row

```tsv
run_id	status	primary_score	avg_latency_ms	avg_input_tokens	risk	note
run-0007	complete	0.764	8120	11382	low	env bootstrap + safer validation
```

