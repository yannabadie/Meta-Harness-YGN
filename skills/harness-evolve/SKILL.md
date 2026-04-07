---
name: evolve
description: Evolve repo-local Claude Code harness assets through a 5-phase pipeline — harvest context, propose candidate, evaluate with evidence, audit regressions, report results.
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(python3 *) Bash(git *) Bash(mh-*) Bash(node *) Write Edit
---
ultrathink.

# Harness Evolution Pipeline

**Objective:** $ARGUMENTS

You are the pipeline orchestrator. Execute these 5 phases IN ORDER, using subagents and MCP tools. Each phase produces disk artifacts consumed by the next.

## Phase 0: Setup

Reserve a candidate run ID and record the objective:

```bash
RUN_ID=$(mh-next-run)
RUN_DIR=$(mh-next-run --run-id $RUN_ID --path)
echo "Run: $RUN_ID at $RUN_DIR"
```

## Phase 1: HARVEST

Gather project context relevant to the objective. Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/context_harvester.py --project . --objective "$ARGUMENTS" --budget 1500
```

Save the output to `$RUN_DIR/context-snapshot.md` for crash recovery.

Also read the current frontier and regressions:
- Call the `frontier_read` MCP tool (or run `mh-frontier --markdown`)
- Call the `harness://regressions` MCP resource (or run `mh-regressions --markdown`)

## Phase 2: PROPOSE

Dispatch the **harness-proposer** subagent with this context:

> You are proposing a harness improvement for: "$ARGUMENTS"
>
> Run ID: $RUN_ID
> [Include the harvested context, frontier, and regressions from Phase 1]
>
> Create these files in $RUN_DIR:
> - hypothesis.md (Claim / Evidence / Predicted impact / Risk)
> - safety-note.md
> - candidate.patch (unified diff of your changes)
>
> Edit ONLY harness surfaces: CLAUDE.md, .claude/skills/**, .claude/agents/**, .claude/rules/**, prompts/**, .meta-harness/**, helper scripts.
> Do NOT edit application code.
> Run `mh-validate` before finishing.

Wait for the proposer to complete. Verify that `$RUN_DIR/hypothesis.md` and `$RUN_DIR/candidate.patch` exist.

## Phase 3: EVALUATE

Run deterministic evaluation:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/eval_runner.py --eval-dir ${CLAUDE_PLUGIN_ROOT}/eval-tasks --cwd . --json
```

Then dispatch the **harness-evaluator** subagent to assess LLM-judge criteria:

> Evaluate candidate $RUN_ID.
> Read ONLY the files in $RUN_DIR (hypothesis.md, candidate.patch, safety-note.md).
> Do NOT read the proposer's reasoning or conversation — only its output artifacts.
>
> Deterministic results: [paste eval_runner output]
>
> For each LLM-judge criteria in eval-tasks/, assess whether the candidate meets it.
> Write metrics.json to $RUN_DIR and record to frontier using `mh-record-metrics`.

Wait for the evaluator. Verify that `$RUN_DIR/metrics.json` exists.

## Phase 4: AUDIT

Dispatch the **regression-auditor** subagent:

> Audit candidate $RUN_ID for regressions.
> Read the frontier (mh-frontier --markdown), the candidate's metrics.json, and the patch.
> Compare against prior frontier leaders.
> Write analysis.md to $RUN_DIR with: likely cause, confidence, evidence, recommendation.

Wait for the auditor. Read `$RUN_DIR/analysis.md`.

## Phase 5: REPORT

Present results using the Meta-Harness output style:

```
⚗ EVOLUTION REPORT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: $RUN_ID | Hypothesis: [from hypothesis.md]

| Metric        | Baseline | Candidate | Delta      |
|---------------|----------|-----------|------------|
| Score         | [val]    | [val]     | [+/-]% ▲/▼ |
| Latency (ms)  | [val]    | [val]     | [+/-]% ▲/▼ |
| Tokens        | [val]    | [val]     | [+/-]% ▲/▼ |

Confidence: N=[sample] | Method: deterministic + LLM-judge
Risk: [from safety-note.md]
Verdict: [PROMOTE / REJECT / ITERATE]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Guardrails

- Do NOT skip any phase. Each phase must produce its artifact before the next begins.
- Do NOT claim benchmark gains without recorded metrics in frontier.tsv.
- The evaluator must NOT see the proposer's reasoning — only disk artifacts (context break).
- If candidate.patch is empty or trivially small, REJECT immediately.
- Maximum 3 files modified per candidate patch.
- If the proposer exceeds scope (edits non-harness files), REJECT.
