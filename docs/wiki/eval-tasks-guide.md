# Eval Tasks Guide

This guide explains how to write, run, and interpret eval tasks in Meta-Harness. Eval tasks are the measurement layer: without them, you cannot distinguish a genuine improvement from a placebo.

---

## The JSON Schema

Every eval task is a JSON file stored in `eval-tasks/`. The canonical schema is in `eval-tasks/_schema.json`.

```json
{
  "$schema": "meta-harness-eval-task-v1",
  "name": "example-task",
  "type": "regression",
  "difficulty": "easy",
  "description": "Human-readable description of what this eval tests.",
  "checks": {
    "deterministic": [
      {
        "type": "exit_code",
        "command": "python -m pytest tests/",
        "expected": 0,
        "weight": 1.0
      }
    ],
    "llm_judge": [
      {
        "criteria": "Plain-English description of what the LLM judge should evaluate.",
        "weight": 1.0
      }
    ]
  }
}
```

### Field-by-field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Unique identifier for the task. Used in reports and logs. Snake-case recommended. |
| `type` | string | Yes | `"regression"` or `"capability"`. Regression tasks are sanity checks; capability tasks measure improvement. |
| `difficulty` | string | Yes | `"easy"`, `"medium"`, or `"hard"`. Informational; used to prioritize what to fix first. |
| `description` | string | Yes | Human-readable explanation of what the task tests. Shown in reports. |
| `requires_run` | boolean | No | If `true`, the task is skipped during cold evals (no prior `/mh:evolve` run). Use for tasks that check run artifacts. Default: `false`. |
| `checks.deterministic` | array | No | List of deterministic check objects. Can be empty. |
| `checks.llm_judge` | array | No | List of LLM-judge criteria objects. Can be empty. |

A task with no checks passes by definition (score = 1.0, weight = 0). In practice, every task should have at least one deterministic check.

---

## All 9 Check Types

Deterministic checks are implemented in `scripts/eval_runner.py`. Each check is a JSON object with a `type` field and type-specific fields. All checks support a `weight` field (float, default 1.0) that scales their contribution to the task score.

---

### `exit_code`

Runs a shell command and checks that it exits with the expected code.

```json
{
  "type": "exit_code",
  "command": "python -m pytest tests/ -q --tb=no",
  "expected": 0,
  "weight": 5.0
}
```

| Field | Required | Description |
|---|---|---|
| `command` | Yes | Shell command to run. Executed with `shell=True`. |
| `expected` | Yes | Expected exit code (integer). |
| `weight` | No | Default 1.0. |

**Evidence on failure:** `Exit code 1 (expected 0) for: python -m pytest tests/ -q --tb=no`

**Use for:** Running test suites, linters, validators, any command that should succeed.

---

### `file_exists`

Checks that a file exists at the given path.

```json
{
  "type": "file_exists",
  "path": ".claude-plugin/plugin.json",
  "weight": 2.0
}
```

| Field | Required | Description |
|---|---|---|
| `path` | Yes | Relative or absolute path. Relative paths resolve against `--cwd`. |
| `weight` | No | Default 1.0. |

**Evidence on failure:** `Missing: /path/to/.claude-plugin/plugin.json`

**Use for:** Confirming required harness files were created by a candidate.

---

### `file_contains`

Checks that a file's content matches a regular expression.

```json
{
  "type": "file_contains",
  "path": "skills/harness-evolve/SKILL.md",
  "pattern": "^---",
  "weight": 1.0
}
```

| Field | Required | Description |
|---|---|---|
| `path` | Yes | Path to the file. |
| `pattern` | Yes | Python `re.search()` regex. Applied to the entire file content. |
| `weight` | No | Default 1.0. |

**Evidence on failure:** `Pattern not found: '^---' in /path/to/SKILL.md`

**Use for:** Verifying that CLAUDE.md contains a required section, a skill file has valid YAML frontmatter, a rule file references the correct paths.

**Example — check that CLAUDE.md has a constraints section:**

```json
{
  "type": "file_contains",
  "path": "CLAUDE.md",
  "pattern": "(?i)## (key constraints|constraints|rules)",
  "weight": 1.5
}
```

---

### `file_not_contains`

The inverse of `file_contains`. Fails if the pattern is found.

```json
{
  "type": "file_not_contains",
  "path": "CLAUDE.md",
  "pattern": "TODO|FIXME|PLACEHOLDER",
  "weight": 1.0
}
```

**Evidence on failure:** `Pattern found (bad): 'TODO|FIXME|PLACEHOLDER' in CLAUDE.md`

**Use for:** Ensuring that stale placeholders, debug instructions, or deprecated patterns were removed.

---

### `json_valid`

Parses the file as JSON and fails if it raises.

```json
{
  "type": "json_valid",
  "path": "hooks/hooks.json",
  "weight": 2.0
}
```

| Field | Required | Description |
|---|---|---|
| `path` | Yes | Path to the JSON file. |
| `weight` | No | Default 1.0. |

**Evidence on failure:** `Expecting ',' delimiter: line 12 column 5 (char 234)`

**Use for:** Validating all JSON harness files after a candidate modifies them. Always include for `hooks/hooks.json`, `.claude-plugin/plugin.json`, `.mcp.json`.

---

### `command_output`

Runs a shell command and checks that its stdout matches a regex.

```json
{
  "type": "command_output",
  "command": "python scripts/meta_harness.py frontier --markdown",
  "pattern": "Non-dominated",
  "weight": 1.0
}
```

| Field | Required | Description |
|---|---|---|
| `command` | Yes | Shell command to run. |
| `pattern` | Yes | Python `re.search()` regex applied to stdout. |
| `weight` | No | Default 1.0. |

**Evidence on failure:** `Pattern not found: 'Non-dominated' in stdout of: python scripts/meta_harness.py frontier --markdown`

**Use for:** Checking that a CLI tool produces expected output — e.g., that the eval runner reports a pass, that a script outputs a specific field.

---

### `patch_not_empty`

Checks that a patch file exists, is non-empty, and contains more than trivial whitespace (> 10 characters of content).

```json
{
  "type": "patch_not_empty",
  "path": "candidate.patch",
  "weight": 2.0
}
```

| Field | Required | Description |
|---|---|---|
| `path` | Yes | Path to the `.patch` file. |
| `weight` | No | Default 1.0. |

**Evidence on failure:** `patch is empty or trivial (0 chars)`

**Use for:** Guarding against empty or no-op candidates. This is a hard gate: an evaluator that receives an empty patch must reject it.

---

### `max_files_changed`

Counts the number of distinct files in a unified diff patch (`+++ b/` lines) and checks that it does not exceed a maximum.

```json
{
  "type": "max_files_changed",
  "path": "candidate.patch",
  "max": 3,
  "weight": 1.5
}
```

| Field | Required | Description |
|---|---|---|
| `path` | Yes | Path to the `.patch` file. |
| `max` | Yes | Maximum number of files allowed. |
| `weight` | No | Default 1.0. |

**Evidence on failure:** `4 files changed (max 3)`

**Use for:** Enforcing the Meta-Harness constraint that each candidate modifies at most 3 files. This keeps changes focused and reversible.

---

### `files_in_scope`

Checks that every file in a unified diff patch is a harness surface. Files are checked against these prefixes:

```
CLAUDE.md, .claude/, prompts/, .meta-harness/, skills/, agents/, rules/
```

```json
{
  "type": "files_in_scope",
  "path": "candidate.patch",
  "weight": 3.0
}
```

| Field | Required | Description |
|---|---|---|
| `path` | Yes | Path to the `.patch` file. |
| `weight` | No | Default 1.0. High weights recommended — out-of-scope edits are a critical failure. |

**Evidence on failure:** `out-of-scope files: src/main.py, tests/test_api.py`

**Evidence on pass:** `all files within harness scope`

**Use for:** The single most important guard against candidates that accidentally edit application code. Use weight 3.0 or higher.

---

## LLM-Judge Criteria

Each `llm_judge` entry is a plain-English criterion evaluated by the harness-evaluator agent.

```json
{
  "criteria": "The hypothesis clearly states what changed and predicts a specific measurable improvement. It is not vague or generic.",
  "weight": 2.0
}
```

| Field | Required | Description |
|---|---|---|
| `criteria` | Yes | Evaluation criterion in plain English. |
| `weight` | No | Default 1.0. |

### How to write good criteria

**Be specific and falsifiable.** The evaluator should be able to make a binary judgment from the artifacts alone.

Good:
```
"The safety note identifies at least one concrete risk and explains why the change is reversible."
```

Bad:
```
"The candidate looks good and the proposer did a nice job."
```

**Reference observable artifacts.** The evaluator only sees `hypothesis.md`, `candidate.patch`, `safety-note.md`, and `validation.txt`. Criteria must be checkable against these files.

Good:
```
"The candidate patch only modifies harness surfaces (CLAUDE.md, .claude/*, prompts/*, skills/*, agents/*). It does not touch application code."
```

Bad:
```
"The candidate would improve Claude's performance on real tasks."
```

**Avoid criteria that require running the candidate.** The evaluator does not apply the patch and test it — it reads the artifacts.

**Target meaningful quality signals:**
- Hypothesis clarity and specificity
- Safety note completeness (risk identified, reversibility explained)
- Scope compliance
- Coherence between the hypothesis and the actual patch content
- Absence of fabricated claims ("this will improve X by Y%" without evidence)

---

## Scoring Formula

The final score for a run combines two components:

```
final_score = 0.6 × deterministic_score + 0.4 × llm_judge_score
```

**Deterministic score** is the weighted fraction of passed deterministic checks:

```
deterministic_score = sum(weight for passed checks) / sum(all weights)
```

For example, if a task has three checks with weights 2.0, 1.0, 1.5 and the first two pass:

```
deterministic_score = (2.0 + 1.0) / (2.0 + 1.0 + 1.5) = 3.0 / 4.5 = 0.667
```

**LLM-judge score** is computed analogously across the `llm_judge` criteria (same weighted fraction formula, evaluated by the `harness-evaluator` agent).

**Aggregate score** across all tasks is the unweighted mean of per-task deterministic scores:

```
aggregate_score = sum(task.deterministic_score for all tasks) / total_tasks
```

**Verdict thresholds** (applied by the harness-evaluator to the `final_score`):

| Verdict | Condition |
|---|---|
| `accepted` | `final_score >= 0.8` AND no critical failures |
| `accepted_with_warnings` | `0.6 <= final_score < 0.8` |
| `rejected` | `final_score < 0.6` OR critical failure |
| `partial` | Some axes improved, others regressed vs frontier |

---

## The `requires_run` Flag

Tasks with `"requires_run": true` are skipped during cold evals (when no `/mh:evolve` run has been completed).

Use this flag for tasks that check run artifacts — files that only exist inside a run directory like `hypothesis.md`, `candidate.patch`, or `metrics.json`.

```json
{
  "name": "propose-improvement",
  "type": "capability",
  "difficulty": "medium",
  "requires_run": true,
  "checks": {
    "deterministic": [
      { "type": "file_exists", "path": "hypothesis.md", "weight": 2.0 },
      { "type": "patch_not_empty", "path": "candidate.patch", "weight": 2.0 },
      { "type": "files_in_scope", "path": "candidate.patch", "weight": 3.0 }
    ]
  }
}
```

When you run `/mh:eval run-0004`, the evaluator reads artifacts from the run directory as `cwd`, so relative paths like `hypothesis.md` resolve correctly.

To include `requires_run` tasks in a standalone eval run, pass `--include-requires-run` (not exposed in the current CLI, but available via the Python API: `run_all_evals(eval_dir, cwd, include_requires_run=True)`).

---

## Creating Regression Tasks

A regression task checks something that should always be true regardless of what the harness contains. If a regression task fails, something fundamental is broken.

**Directory:** `eval-tasks/regression/`

**Characteristics:**
- `"type": "regression"`
- `"difficulty": "easy"`
- No `requires_run`
- Mostly `exit_code`, `file_exists`, `json_valid` checks
- Minimal or no LLM-judge criteria

**Standard regression tasks to include in every project:**

```json
// File: eval-tasks/regression/plugin-structure.json
{
  "name": "plugin-structure",
  "type": "regression",
  "difficulty": "easy",
  "description": "All required plugin files exist and are valid.",
  "checks": {
    "deterministic": [
      { "type": "file_exists", "path": ".claude-plugin/plugin.json", "weight": 2.0 },
      { "type": "json_valid", "path": ".claude-plugin/plugin.json", "weight": 2.0 },
      { "type": "file_exists", "path": "hooks/hooks.json", "weight": 2.0 },
      { "type": "json_valid", "path": "hooks/hooks.json", "weight": 2.0 }
    ],
    "llm_judge": []
  }
}
```

```json
// File: eval-tasks/regression/tests-pass.json
{
  "name": "tests-pass",
  "type": "regression",
  "difficulty": "easy",
  "description": "All tests must pass. This is the baseline regression check.",
  "checks": {
    "deterministic": [
      {
        "type": "exit_code",
        "command": "python -m pytest tests/ -q --tb=no",
        "expected": 0,
        "weight": 5.0
      }
    ],
    "llm_judge": []
  }
}
```

---

## Creating Capability Tasks

A capability task checks something you want to improve. It may fail initially — that is expected.

**Directory:** `eval-tasks/capability/`

**Characteristics:**
- `"type": "capability"`
- `"difficulty": "medium"` or `"hard"`
- Often `requires_run: true` if checking run artifacts
- Mix of deterministic checks and LLM-judge criteria

**Example — enforce that candidates stay in scope:**

```json
{
  "name": "candidate-scope-guard",
  "type": "capability",
  "difficulty": "medium",
  "requires_run": true,
  "description": "Candidate patch modifies only harness surfaces, is non-empty, and stays under 3 files.",
  "checks": {
    "deterministic": [
      { "type": "patch_not_empty", "path": "candidate.patch", "weight": 2.0 },
      { "type": "max_files_changed", "path": "candidate.patch", "max": 3, "weight": 1.5 },
      { "type": "files_in_scope", "path": "candidate.patch", "weight": 3.0 }
    ],
    "llm_judge": [
      {
        "criteria": "The candidate patch only modifies harness surfaces. It does not touch application code, test files, or configuration files outside the harness.",
        "weight": 3.0
      }
    ]
  }
}
```

---

## Running Evals

### From the CLI

Run all eval tasks (skipping `requires_run` tasks):

```bash
python scripts/eval_runner.py --eval-dir eval-tasks --cwd .
```

Output as JSON:

```bash
python scripts/eval_runner.py --eval-dir eval-tasks --cwd . --json
```

Run against a specific run directory (for capability tasks with `requires_run`):

```bash
python scripts/eval_runner.py \
  --eval-dir eval-tasks \
  --cwd /tmp/meta-harness-lab/runs/run-0004
```

### From the MCP Server

If the MCP package is installed, use the `eval_run` tool:

```
Tool: eval_run
Arguments:
  eval_dir: ""           # defaults to plugin's eval-tasks/
  cwd: ""                # defaults to plugin root
```

The MCP tool returns formatted Markdown with PASS/FAIL per task and check evidence.

### From a Skill

Inside `/mh:eval`, the eval runner is invoked inline:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/eval_runner.py \
  --eval-dir ${CLAUDE_PLUGIN_ROOT}/eval-tasks \
  --cwd . 2>&1
```

---

## Interpreting Results

### Human-readable output

```
Eval report — 6 task(s) loaded from: /path/to/eval-tasks
Passed tasks : 5 / 6
Aggregate score: 83.33%

  [PASS] harness-valid (4/4 checks, score=100%)
         [+] json_valid: Valid JSON at .claude-plugin/plugin.json
         [+] json_valid: Valid JSON at hooks/hooks.json
         [+] file_contains: Pattern found: '^---' in skills/harness-evolve/SKILL.md
         [+] exit_code: Exit code 0 (expected 0) for: python3 scripts/meta_harness.py validate
  [FAIL] tests-pass (0/1 checks, score=0%)
         [-] exit_code: Exit code 1 (expected 0) for: python -m pytest tests/ -q --tb=no
```

- **`[PASS]`** — `deterministic_score == 1.0` (all checks passed)
- **`[FAIL]`** — at least one check failed
- **`[+]`** / **`[-]`** — individual check pass/fail with the evidence string

The `evidence` field tells you exactly what the check found: the path, the pattern, the exit code. Use it to diagnose failures without re-running the check manually.

### JSON output

```json
{
  "tasks": [
    {
      "name": "harness-valid",
      "deterministic_score": 1.0,
      "total_checks": 4,
      "passed_checks": 4,
      "check_results": [
        {
          "type": "json_valid",
          "passed": true,
          "weight": 2.0,
          "evidence": "Valid JSON at /path/.claude-plugin/plugin.json"
        }
      ]
    }
  ],
  "aggregate_score": 0.8333,
  "total_tasks": 6,
  "passed_tasks": 5
}
```

### CLI exit code

The eval runner exits `0` if `aggregate_score == 1.0` or no tasks were loaded; exits `1` otherwise. Use this in CI:

```bash
python scripts/eval_runner.py --eval-dir eval-tasks --cwd . || echo "Eval failed"
```

---

## Adding Custom Eval Checks

The 9 built-in check types cover most harness evaluation needs. For project-specific checks:

**Option 1: Use `command_output` with a custom script.**

```json
{
  "type": "command_output",
  "command": "python scripts/my_custom_check.py",
  "pattern": "PASS",
  "weight": 2.0
}
```

Your script can do anything — query a database, call an API, run a linter. It just needs to print something matching `pattern` to stdout on success.

**Option 2: Use `exit_code` with a test suite.**

```json
{
  "type": "exit_code",
  "command": "python -m pytest tests/harness/ -q --tb=short",
  "expected": 0,
  "weight": 3.0
}
```

**Option 3: Extend `eval_runner.py` (for contributors).**

Add a new handler to `_CHECK_HANDLERS` in `scripts/eval_runner.py`:

```python
def _check_my_type(check: dict, cwd: str) -> dict:
    # ... implementation
    return {
        "type": "my_type",
        "passed": True,
        "weight": check.get("weight", 1.0),
        "evidence": "description of what was found",
    }

_CHECK_HANDLERS["my_type"] = _check_my_type
```

See [Architecture](architecture.md) for a full description of the eval engine's structure.

---

See [Commands Reference](commands-reference.md) for CLI syntax, [Concepts](concepts.md) for the scoring formula in context, and [Architecture](architecture.md) for the eval engine implementation.
