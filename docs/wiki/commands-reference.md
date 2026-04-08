# Commands Reference

Complete reference for every skill, CLI command, and Python subcommand in Meta-Harness.

---

## Skills (Slash Commands)

Skills are invoked from the Claude Code chat input with `/mh:<name>`. They are defined in `skills/harness-*/SKILL.md`.

---

### `/mh:evolve`

**File:** `skills/harness-evolve/SKILL.md`

**Syntax:**
```
/mh:evolve <objective>
```

**Arguments:**

| Argument | Required | Description |
|---|---|---|
| `<objective>` | Yes | Plain-English description of what you want to improve. Used for BM25 context scoring in the Harvest phase. |

**What it does:**

Runs the complete 5-phase evolution pipeline as an inline orchestrator:

1. Reserves a run ID and creates the run directory with placeholder files
2. Harvests project context (BM25 + RRF from CLAUDE.md, memory, git, docs)
3. Dispatches the `harness-proposer` subagent to propose a controlled change
4. Runs deterministic eval checks, then dispatches `harness-evaluator` for LLM-judge scoring
5. Dispatches `regression-auditor` to compare against the frontier
6. Presents the Evolution Report with verdict: PROMOTE / REJECT / ITERATE

The evaluator operates under a context break — it reads only disk artifacts, never the proposer's reasoning. Maximum 3 files per patch. Only harness surfaces are editable.

**Example:**

```
/mh:evolve "reduce tool thrashing on refactoring tasks"
```

Expected output:

```
⚗ EVOLUTION REPORT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: run-0003 | Hypothesis: tighter scope rules reduce unnecessary file reads

| Metric        | Baseline | Candidate | Delta      |
|---------------|----------|-----------|------------|
| Score         | 0.764    | 0.821     | +7.5%  ▲   |
| Latency (ms)  | 8120     | 7340      | -9.6%  ▲   |
| Tokens        | 11382    | 10890     | -4.3%  ▲   |

Confidence: N=3 | Method: deterministic + LLM-judge
Risk: low — additive rule, fully reversible
Verdict: PROMOTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**When to use it:** Any time you want to measure a proposed harness improvement. Run it repeatedly with different objectives to build up the frontier.

**Allowed tools:** `Read`, `Grep`, `Glob`, `Bash(python3 *)`, `Bash(git *)`, `Bash(mh-*)`, `Bash(node *)`, `Write`, `Edit`

---

### `/mh:frontier`

**File:** `skills/harness-frontier/SKILL.md`

**Syntax:**
```
/mh:frontier
```

**Arguments:** None

**What it does:**

Displays the current Pareto frontier using a fork context (does not consume the main session's context). Dispatches through the `regression-auditor` agent. Shows:

- Non-dominated candidates sorted by score descending
- Trade-off analysis in plain language
- Which candidates are strong but risky
- Suggested next experiment

Reads from `frontier.tsv` via `mh-frontier --markdown`.

**Example:**

```
/mh:frontier
```

Expected output:

```
◆ FRONTIER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
| Run       | Score | Latency | Tokens | Risk |
|-----------|-------|---------|--------|------|
| run-0006  | 0.95  | 5200ms  | 8.5K   | low  |
| run-0012  | 0.82  | 7340ms  | 10.9K  | low  |

Non-dominated: 2 | Total runs: 6
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

run-0006 dominates on all three axes. run-0012 is non-dominated because
it was measured before run-0006 and no candidate with a higher score
at run-0006's latency and token cost has appeared.

Suggested next experiment: test whether the CLAUDE.md simplification in
run-0006 generalizes to multi-file refactoring tasks.
```

**When to use it:** After several evolution runs, to understand which candidates represent genuine trade-offs.

---

### `/mh:regressions`

**File:** `skills/harness-regressions/SKILL.md`

**Syntax:**
```
/mh:regressions
```

**Arguments:** None

**What it does:**

Audits recent regressions (runs where the score dropped below the previous best). Uses a fork context dispatched through `regression-auditor`. Reads from `frontier.tsv` via `mh-regressions --markdown`.

Identifies:
- Repeated failure modes across multiple regressions
- Which changes were additive (lower risk) vs structural rewrites (higher risk)
- The next lower-risk candidate to test

**Example:**

```
/mh:regressions
```

Expected output (one regression found):

```
⚠ REGRESSION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run: run-0008 | Score drop: 0.82 → 0.71 (−0.11)
Likely cause: prompt rewrite changed stop condition simultaneously with
  scope rules — too many variables changed in one patch.
Confounds: run-0007 also changed the PostToolUse hook; interaction unknown.
Recommendation: isolate prompt rewrite from scope rules; test each separately.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**When to use it:** When the frontier shows a score drop, or before starting a new evolution run to understand what failed previously.

---

### `/mh:dashboard`

**File:** `skills/harness-dashboard/SKILL.md`

**Syntax:**
```
/mh:dashboard
```

**Arguments:** None

**What it does:**

Runs five shell commands inline to assemble a full status view:

1. `mh-frontier --markdown` — Pareto frontier table
2. `mh-regressions --markdown` — recent regressions
3. `python3 scripts/eval_runner.py --eval-dir eval-tasks --cwd .` — eval suite health
4. `detect_incomplete_runs()` — any crash-recovered runs waiting for completion
5. A plugin scan from `installed_plugins.json` — what plugins are active

Synthesizes results into the dashboard format using the Meta-Harness output style.

**Example:**

```
/mh:dashboard
```

Expected output:

```
◉ DASHBOARD ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total runs: 12 | Non-dominated: 3 | Best score: 0.95 (run-0006)

Frontier:
  run-0006  score=0.95  latency=5200ms  tokens=8500  risk=low
  run-0012  score=0.82  latency=7340ms  tokens=10900 risk=low
  run-0009  score=0.76  latency=7800ms  tokens=12100 risk=low

Regressions: 2 (run-0004 −0.08, run-0008 −0.11)
Eval suite: 5/6 tasks passing (83%)
Incomplete runs: None
Plugins: superpowers, context7, playwright

Recommendations:
  1. run-0009 is dominated by run-0012. Focus next experiment on
     reproducing run-0006's token efficiency at higher accuracy.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**When to use it:** At the start of a session, to get the full picture before deciding what to optimize next.

---

### `/mh:eval`

**File:** `skills/harness-eval/SKILL.md`

**Syntax:**
```
/mh:eval [run_id]
```

**Arguments:**

| Argument | Required | Description |
|---|---|---|
| `[run_id]` | No | If provided, evaluates the artifacts in `runs/<run_id>/`. If omitted, evaluates the current working tree. |

**What it does:**

1. Runs `python3 scripts/eval_runner.py --eval-dir eval-tasks --cwd . 2>&1` to execute all deterministic checks
2. For each eval task with `llm_judge` criteria, manually reads the relevant files and assesses the criteria
3. Computes `final_score = 0.6 × deterministic_score + 0.4 × llm_judge_score`
4. Presents results in the Meta-Harness output format

**Example (current harness):**

```
/mh:eval
```

**Example (specific run):**

```
/mh:eval run-0006
```

Expected output:

```
Eval report — 6 task(s) loaded from: eval-tasks
Passed tasks : 6 / 6
Aggregate score: 100.00%

  [PASS] harness-valid (4/4 checks, score=100%)
         [+] json_valid: Valid JSON at .claude-plugin/plugin.json
         [+] json_valid: Valid JSON at hooks/hooks.json
         [+] file_contains: Pattern '^---' found in skills/harness-evolve/SKILL.md
         [+] exit_code: Exit code 0 for: python3 scripts/meta_harness.py validate
  [PASS] tests-pass (1/1 checks, score=100%)
         [+] exit_code: Exit code 0 for: python -m pytest tests/ -q --tb=no
```

**When to use it:** Before starting an evolution run (to establish a baseline), and after promoting a candidate (to confirm nothing regressed).

---

### `/mh:bootstrap`

**File:** `skills/harness-bootstrap/SKILL.md`

**Syntax:**
```
/mh:bootstrap
```

**Arguments:** None

**What it does:**

Analyzes the current project and generates initial eval tasks:

1. Takes an environment snapshot: current working directory, git branch and status
2. Scans Claude harness surfaces: `CLAUDE.md`, `.claude/`, `.meta-harness/`, `prompts/`
3. Detects available tooling: Python, Node, npm, pytest, ruff, mypy, Go, Rust, Java
4. Reads the current plugin ledger from `frontier.tsv` (if it exists)
5. Generates JSON eval task files following the `_schema.json` format

Generated task types:
- **Regression tasks** (`eval-tasks/regression/`): Checks that must always pass — harness files valid, CLAUDE.md exists with required sections, skills have frontmatter, `mh-validate` passes.
- **Capability tasks** (`eval-tasks/capability/`): Improvement targets based on the project's domain, git history patterns, and CLAUDE.md constraints.

**Allowed tools:** `Read`, `Grep`, `Glob`, `Bash(python3 *)`, `Bash(git *)`, `Bash(ls *)`, `Write`

**Example:**

```
/mh:bootstrap
```

Expected output (varies by project):

```
# Environment snapshot
- cwd: /projects/myapp
- git branch: main
- git status: (clean)

## Claude surfaces
- found: CLAUDE.md
- found: .claude
  .claude/rules/no-edit-tests.md

## Tooling
- python3: Python 3.11.4
- pytest: pytest 8.1.0
- node: v20.10.0

Generated eval tasks:
  eval-tasks/regression/harness-valid.json
  eval-tasks/regression/tests-pass.json
  eval-tasks/capability/scope-constraints.json
```

**When to use it:** Once, when setting up Meta-Harness on a new project. Re-run if you add new harness surfaces or significant new capabilities to your project.

---

## CLI Commands

CLI commands live in `bin/`. They are thin shell wrappers around `scripts/meta_harness.py` subcommands, invocable directly from the terminal or from skills/hooks.

---

### `mh-init`

**Syntax:**
```bash
bin/mh-init
```

**What it does:** Initializes persistent storage directories and writes a `session_start` entry to the session log. Prints `$CLAUDE_PLUGIN_DATA` on success.

**Example:**

```bash
bin/mh-init
# Output: /tmp/meta-harness-lab
```

---

### `mh-next-run`

**Syntax:**
```bash
bin/mh-next-run [--run-id RUN_ID] [--path]
```

**Arguments:**

| Flag | Description |
|---|---|
| `--run-id` | Override the auto-incremented ID with a specific one |
| `--path` | Print the full path to the run directory instead of just the run ID |

**What it does:** Reserves the next candidate run ID (e.g., `run-0004`) by scanning existing directories under `$CLAUDE_PLUGIN_DATA/runs/`, creates the directory, touches placeholder files, writes a valid `metrics.json` stub with `status=reserved`, and records a matching `reserved` row in `frontier.tsv`. If you pass an existing `--run-id`, it returns that run directory without resetting its recorded state.

**Example:**

```bash
RUN_ID=$(bin/mh-next-run)
echo $RUN_ID         # run-0004

RUN_DIR=$(bin/mh-next-run --run-id run-0004 --path)
echo $RUN_DIR        # /tmp/meta-harness-lab/runs/run-0004
```

---

### `mh-record-metrics`

**Syntax:**
```bash
bin/mh-record-metrics <run_id> <score> <latency_ms> <tokens> <risk> <note> \
  [--status STATUS] \
  [--consistency X] \
  [--instruction-adherence X] \
  [--tool-efficiency X] \
  [--error-count X]
```

**Arguments:**

| Argument | Required | Description |
|---|---|---|
| `run_id` | Yes | Run identifier, e.g., `run-0004` |
| `score` | Yes | Primary score, float 0.0–1.0 |
| `latency_ms` | Yes | Average latency in milliseconds |
| `tokens` | Yes | Average input tokens |
| `risk` | Yes | `low`, `medium`, or `high` |
| `note` | Yes | Short description of the hypothesis |
| `--status` | No | Default `complete`. Also accepts `promoted`. |
| `--consistency` | No | Optional consistency sub-score |
| `--instruction-adherence` | No | Optional instruction adherence sub-score |
| `--tool-efficiency` | No | Optional tool efficiency sub-score |
| `--error-count` | No | Optional error count |

**What it does:** Writes or updates a row in `frontier.tsv` and writes `metrics.json` to the run directory. Prints the run ID on success.

**Example:**

```bash
bin/mh-record-metrics run-0004 0.821 7340 10890 low "scope guard additive rule"
# Output: run-0004
```

---

### `mh-frontier`

**Syntax:**
```bash
bin/mh-frontier [--markdown] [--limit N]
```

**Arguments:**

| Flag | Default | Description |
|---|---|---|
| `--markdown` | off | Render as Markdown tables with headers |
| `--limit N` | 10 | Maximum rows to display |

**What it does:** Reads `frontier.tsv`, computes Pareto non-dominated candidates, and prints the frontier plus recent runs.

**Example:**

```bash
bin/mh-frontier --markdown
```

Output:

```markdown
# Pareto frontier

| run_id   | status   | primary_score | avg_latency_ms | avg_input_tokens | risk | note |
|----------|----------|---------------|----------------|-----------------|------|------|
| run-0006 | complete | 0.95          | 5200           | 8500            | low  | simplified CLAUDE.md |

# Recent runs

| run_id   | status   | primary_score | ...
```

---

### `mh-regressions`

**Syntax:**
```bash
bin/mh-regressions [--markdown] [--limit N]
```

**Arguments:** Same as `mh-frontier`.

**What it does:** Identifies runs where the score dropped below the previous chronological best and prints them with heuristics for diagnosis.

**Example:**

```bash
bin/mh-regressions --markdown
```

---

### `mh-validate`

**Syntax:**
```bash
bin/mh-validate [path]
```

**Arguments:**

| Argument | Default | Description |
|---|---|---|
| `path` | Current directory | Project root to validate |

**What it does:** Lightweight JSON syntax validator. Scans `.claude-plugin/*.json`, `.claude/**/*.json`, `.meta-harness/**/*.json`, `prompts/**/*.json`, and `.mcp.json`. Prints errors and exits 1 if any file fails to parse; exits 0 with a pass message otherwise.

**Example:**

```bash
bin/mh-validate .
# Output: Lightweight validation passed. Add project-specific checks...
```

---

### `mh-rollback`

**Syntax:**
```bash
bin/mh-rollback <run_id>
```

**Arguments:**

| Argument | Required | Description |
|---|---|---|
| `run_id` | Yes | The run whose `candidate.patch` to reverse-apply |

**What it does:**

1. Creates a git safety tag `harness-pre-rollback-<run_id>`
2. Checks `candidate.patch` exists and is non-empty
3. Runs `git apply --check -R` to verify the patch can be reversed cleanly
4. Applies `git apply -R` to reverse the change

Exits 1 if the patch cannot be applied cleanly (working tree diverged). The safety tag is always created before attempting the rollback.

**Example:**

```bash
bin/mh-rollback run-0004
# Output:
# Created safety tag: harness-pre-rollback-run-0004
# Rolled back run-0004 successfully
# To undo this rollback: git apply /tmp/meta-harness-lab/runs/run-0004/candidate.patch
```

---

### `mh-promote`

**Syntax:**
```bash
bin/mh-promote <run_id>
```

**Arguments:**

| Argument | Required | Description |
|---|---|---|
| `run_id` | Yes | The run to promote to the working tree |

**What it does:**

1. Checks that `candidate.patch` exists and is non-empty for the run
2. Checks that `metrics.json` exists (refuses to promote unevaluated candidates)
3. Validates that `metrics.json` contains valid JSON
4. Refuses to continue unless the current directory is inside a git worktree
5. Refuses to continue if tracked files are dirty (`git status --porcelain --untracked-files=no`)
6. Refuses to continue if the safety tag `harness-pre-<run_id>` already exists
7. Runs `git apply --check` to verify the patch applies cleanly
8. Creates a git safety tag `harness-pre-<run_id>`
9. Applies `git apply`
10. Updates `frontier.tsv` and `metrics.json` to `status=promoted`

**Example:**

```bash
bin/mh-promote run-0006
# Output:
# Promoted run-0006
# Safety tag: harness-pre-run-0006
# To rollback: git apply -R /tmp/meta-harness-lab/runs/run-0006/candidate.patch
```

---

### `mh-context`

**Syntax:**
```bash
bin/mh-context --project <path> --objective "<text>" [--budget N]
```

**Arguments:**

| Flag | Default | Description |
|---|---|---|
| `--project` | `.` | Project directory to harvest context from |
| `--objective` | Required | Query string used for BM25 relevance scoring |
| `--budget` | 2000 | Token budget for the output |

**What it does:** Calls `scripts/context_harvester.py` directly. Collects context from all sources, scores against the objective, merges with RRF, and packs within the budget. Outputs structured Markdown.

**Example:**

```bash
bin/mh-context --project . --objective "reduce token usage" --budget 1500
```

---

### `mh-bootstrap`

**Syntax:**
```bash
bin/mh-bootstrap
```

**What it does:** Runs the bootstrap data collection (environment snapshot, Claude surfaces, tooling, plugin ledger) that the `/mh:bootstrap` skill uses as input. Outputs Markdown suitable for feeding to a model to generate eval tasks. This is the shell portion of bootstrap — the model completes the work.

---

## Python Subcommands

All subcommands are run via `python scripts/meta_harness.py <subcommand>` (or via `bin/mh-python scripts/meta_harness.py <subcommand>` on Windows).

---

### `init`

**Syntax:**
```bash
python scripts/meta_harness.py init
```

Creates storage directories (`$CLAUDE_PLUGIN_DATA`, `runs/`, `sessions/`) and initializes `frontier.tsv` with headers if it does not exist. Writes a `session_start` log entry. Prints the data directory path.

---

### `log-write`

**Syntax:**
```bash
echo '<json>' | python scripts/meta_harness.py log-write
```

Reads JSON from stdin (a `PostToolUse` hook payload) and appends a structured `write_event` entry to the session log. Fields extracted: `tool_name`, `file_path`.

---

### `record-session`

**Syntax:**
```bash
python scripts/meta_harness.py record-session
```

Appends a `session_stop` entry to the session log. Called by the `Stop` hook.

---

### `next-run`

**Syntax:**
```bash
python scripts/meta_harness.py next-run [--run-id RUN_ID] [--path]
```

**Arguments:**

| Flag | Description |
|---|---|
| `--run-id` | Override the auto-incremented ID with a specific one |
| `--path` | Print the full directory path instead of just the ID |

Reserves a run directory and initializes new reservations with placeholder files, a valid `metrics.json` stub with `status=reserved`, and a matching `reserved` row in `frontier.tsv`. If `--run-id` points to an existing run, the command returns that directory without resetting its metrics or frontier row. Used by skills and hooks.

---

### `frontier`

**Syntax:**
```bash
python scripts/meta_harness.py frontier [--markdown] [--limit N]
```

Reads `frontier.tsv`, computes Pareto non-dominated set, and prints the result. Raw JSON per line without `--markdown`; Markdown tables with it.

---

### `record-metrics`

**Syntax:**
```bash
python scripts/meta_harness.py record-metrics \
  <run_id> <primary_score> <avg_latency_ms> <avg_input_tokens> <risk> <note> \
  [--status complete|promoted] \
  [--consistency X] \
  [--instruction-adherence X] \
  [--tool-efficiency X] \
  [--error-count X]
```

Writes or updates a row in `frontier.tsv` and creates `metrics.json` in the run directory. Prints the run ID.

**Example:**

```bash
python scripts/meta_harness.py record-metrics \
  run-0004 0.821 7340 10890 low "scope guard additive rule" \
  --consistency 0.9 --instruction-adherence 0.95 --tool-efficiency 0.88 --error-count 0
```

---

### `regressions`

**Syntax:**
```bash
python scripts/meta_harness.py regressions [--markdown] [--limit N]
```

Identifies chronological regressions in the completed run history. Same output as `mh-regressions`.

---

### `validate`

**Syntax:**
```bash
python scripts/meta_harness.py validate [path]
```

Lightweight JSON syntax check for `.claude-plugin/`, `.claude/`, `.meta-harness/`, and `prompts/`. Exits 1 on error.

---

### `compact-summary`

**Syntax:**
```bash
python scripts/meta_harness.py compact-summary
```

Generates a compact context summary for re-injection after context compaction (`PostCompact` hook). Output format:

```
[Meta-Harness Context]
Frontier (non-dominated):
  run-0006: score=0.95 latency=5200ms tokens=8500 risk=low
Recent:
  run-0006: complete score=0.95 note=simplified CLAUDE.md
Total runs: 12
```

---

### `parallel-run`

**Syntax:**
```bash
python scripts/meta_harness.py parallel-run [--count N] [--json]
```

**Arguments:**

| Flag | Default | Description |
|---|---|---|
| `--count` | 3 | Number of run directories to reserve |
| `--json` | off | Output as `{"run_ids": [...], "count": N}` |

Reserves N run IDs simultaneously. Refuses counts below 1. Each reserved run gets placeholder files, a valid `metrics.json` stub with `status=reserved`, and a matching `reserved` row in `frontier.tsv`. Used for parallel candidate evaluation (multiple proposers working concurrently).

**Example:**

```bash
python scripts/meta_harness.py parallel-run --count 3 --json
# Output: {"run_ids": ["run-0005", "run-0006", "run-0007"], "count": 3}
```

---

### `promote`

**Syntax:**
```bash
python scripts/meta_harness.py promote <run_id>
```

Applies the candidate patch to the working tree, creates a safety tag, and updates `frontier.tsv` plus `metrics.json` to `status=promoted`. Refuses if `metrics.json` is missing or invalid, if the directory is not a git worktree, if tracked files are dirty, or if the safety tag already exists. Equivalent to `bin/mh-promote`.

---

### `timeline`

**Syntax:**
```bash
python scripts/meta_harness.py timeline
```

Shows frontier metrics over time with Unicode sparkline visualization (▁▂▃▄▅▆▇█). Displays score, latency, and token trends across all completed runs.

**Example output:**

```
# Frontier Timeline

Runs: 8 | Period: 2024-01-15 to 2024-02-03

Score    0.950  ▲ +0.186  ▁▂▃▄▄▆▇█
Latency  5200ms ▼ -2920ms  █▇▆▅▄▃▂▁
Tokens   8500   ▼ -2882    █▇▆▅▅▄▃▁

Best score: 0.950
```

---

### `compare-projects`

**Syntax:**
```bash
python scripts/meta_harness.py compare-projects
```

Scans `~/.claude/plugins/data/` and sibling directories for other Meta-Harness `frontier.tsv` files. Compares best scores and frontier sizes across projects.

**Example output:**

```
# Cross-Project Frontier Comparison

| Project          | Runs | Frontier | Best Score |
|------------------|------|----------|------------|
| current          |   12 |        3 |      0.950 |
| my-other-project |    4 |        2 |      0.780 |

2 project(s) found.
```

---

## Environment Variables

| Variable | Default | Used by |
|---|---|---|
| `CLAUDE_PLUGIN_DATA` | `/tmp/meta-harness-lab` | All storage (frontier, runs, sessions) |
| `CLAUDE_PLUGIN_ROOT` | Auto-detected | Server and scripts resolve their own location |
| `MH_PLUGIN_DATA` | Falls back to `CLAUDE_PLUGIN_DATA` | MCP server |
| `MH_PLUGIN_ROOT` | Falls back to `CLAUDE_PLUGIN_ROOT` | MCP server |

---

See [Eval Tasks Guide](eval-tasks-guide.md) for the eval runner CLI, [Architecture](architecture.md) for MCP tool and resource signatures, and [Getting Started](getting-started.md) for first-run instructions.
