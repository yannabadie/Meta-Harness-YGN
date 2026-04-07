# Phase 3: Evaluation Framework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the evaluation framework that grades harness candidates with deterministic checks and LLM-judge criteria, enabling the "proof-first" differentiator.

**Architecture:** Eval tasks are JSON files in `eval-tasks/`. A new `scripts/eval_runner.py` module handles deterministic grading (exit codes, file checks, regex matches). The evaluator agent reads eval tasks and judges LLM criteria. Skills `/mh:eval` and `/mh:bootstrap` provide entry points.

**Tech Stack:** Python 3.10+ (stdlib only — json, re, subprocess, pathlib). JSON for eval task format (no PyYAML dependency).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `eval-tasks/_schema.json` | Reference schema for eval tasks |
| Create | `eval-tasks/regression/harness-valid.json` | Example: harness files parse correctly |
| Create | `eval-tasks/capability/propose-improvement.json` | Example: propose a coherent improvement |
| Create | `scripts/eval_runner.py` | Deterministic grading engine |
| Create | `tests/test_eval_runner.py` | Tests for eval runner |
| Create | `agents/harness-evaluator.md` | Evaluator agent definition |
| Create | `skills/harness-eval/SKILL.md` | /mh:eval skill |
| Create | `skills/harness-bootstrap/SKILL.md` | /mh:bootstrap skill |
| Modify | `servers/mh_server.py` | Enhance eval_run tool |
| Modify | `tests/test_mcp_server.py` | Test for enhanced eval_run |

---

### Task 1: Eval Task Schema + Examples

**Files:**
- Create: `eval-tasks/_schema.json`
- Create: `eval-tasks/regression/harness-valid.json`
- Create: `eval-tasks/capability/propose-improvement.json`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p C:/Code/Meta-Harness-YGN/eval-tasks/regression
mkdir -p C:/Code/Meta-Harness-YGN/eval-tasks/capability
```

- [ ] **Step 2: Create _schema.json**

```json
{
  "$schema": "meta-harness-eval-task-v1",
  "_comment": "Reference schema for Meta-Harness eval tasks. All eval tasks follow this format.",
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
        "weight": 1.0,
        "_comment": "Types: exit_code, file_exists, file_contains, file_not_contains, json_valid, command_output"
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

- [ ] **Step 3: Create regression/harness-valid.json**

```json
{
  "name": "harness-valid",
  "type": "regression",
  "difficulty": "easy",
  "description": "Verify all harness files parse correctly — JSON valid, YAML frontmatter present, patch applies.",
  "checks": {
    "deterministic": [
      {
        "type": "json_valid",
        "path": ".claude-plugin/plugin.json",
        "weight": 2.0
      },
      {
        "type": "json_valid",
        "path": "hooks/hooks.json",
        "weight": 2.0
      },
      {
        "type": "file_contains",
        "path": "skills/harness-evolve/SKILL.md",
        "pattern": "^---",
        "weight": 1.0
      },
      {
        "type": "exit_code",
        "command": "python3 scripts/meta_harness.py validate",
        "expected": 0,
        "weight": 2.0
      }
    ],
    "llm_judge": []
  }
}
```

- [ ] **Step 4: Create capability/propose-improvement.json**

```json
{
  "name": "propose-improvement",
  "type": "capability",
  "difficulty": "medium",
  "description": "Evaluate whether a proposed harness candidate includes a coherent hypothesis, safety note, and valid patch.",
  "checks": {
    "deterministic": [
      {
        "type": "file_exists",
        "path": "hypothesis.md",
        "weight": 2.0
      },
      {
        "type": "file_exists",
        "path": "safety-note.md",
        "weight": 1.0
      },
      {
        "type": "file_exists",
        "path": "candidate.patch",
        "weight": 2.0
      }
    ],
    "llm_judge": [
      {
        "criteria": "The hypothesis clearly states what changed and predicts a specific measurable improvement. It is not vague or generic.",
        "weight": 2.0
      },
      {
        "criteria": "The safety note identifies at least one concrete risk and explains why the change is reversible.",
        "weight": 1.5
      },
      {
        "criteria": "The candidate patch only modifies harness surfaces (CLAUDE.md, .claude/*, prompts/*, skills/*, agents/*). It does not touch application code.",
        "weight": 3.0
      }
    ]
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add eval-tasks/
git commit -m "feat: add eval task schema and example tasks (regression + capability)"
```

---

### Task 2: Eval Runner — Deterministic Grading (TDD)

**Files:**
- Create: `scripts/eval_runner.py`
- Create: `tests/test_eval_runner.py`

- [ ] **Step 1: Create tests**

Create `tests/test_eval_runner.py`:

```python
"""Tests for eval_runner.py — deterministic grading engine."""
import json
import os
import tempfile
import pathlib

import pytest


class TestCheckTypes:
    def test_json_valid_pass(self, tmp_path):
        from scripts.eval_runner import run_check
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        result = run_check({"type": "json_valid", "path": str(f), "weight": 1.0}, str(tmp_path))
        assert result["passed"] is True

    def test_json_valid_fail(self, tmp_path):
        from scripts.eval_runner import run_check
        f = tmp_path / "bad.json"
        f.write_text('{bad json', encoding="utf-8")
        result = run_check({"type": "json_valid", "path": str(f), "weight": 1.0}, str(tmp_path))
        assert result["passed"] is False

    def test_file_exists_pass(self, tmp_path):
        from scripts.eval_runner import run_check
        f = tmp_path / "exists.txt"
        f.write_text("hello", encoding="utf-8")
        result = run_check({"type": "file_exists", "path": str(f), "weight": 1.0}, str(tmp_path))
        assert result["passed"] is True

    def test_file_exists_fail(self, tmp_path):
        from scripts.eval_runner import run_check
        result = run_check({"type": "file_exists", "path": str(tmp_path / "nope.txt"), "weight": 1.0}, str(tmp_path))
        assert result["passed"] is False

    def test_file_contains_pass(self, tmp_path):
        from scripts.eval_runner import run_check
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    return 42\n", encoding="utf-8")
        result = run_check({"type": "file_contains", "path": str(f), "pattern": "def hello", "weight": 1.0}, str(tmp_path))
        assert result["passed"] is True

    def test_file_contains_fail(self, tmp_path):
        from scripts.eval_runner import run_check
        f = tmp_path / "code.py"
        f.write_text("x = 1", encoding="utf-8")
        result = run_check({"type": "file_contains", "path": str(f), "pattern": "def hello", "weight": 1.0}, str(tmp_path))
        assert result["passed"] is False

    def test_file_not_contains_pass(self, tmp_path):
        from scripts.eval_runner import run_check
        f = tmp_path / "clean.py"
        f.write_text("x = safe()", encoding="utf-8")
        result = run_check({"type": "file_not_contains", "path": str(f), "pattern": "eval\\(", "weight": 1.0}, str(tmp_path))
        assert result["passed"] is True

    def test_exit_code_pass(self, tmp_path):
        from scripts.eval_runner import run_check
        result = run_check({"type": "exit_code", "command": "python -c \"print('ok')\"", "expected": 0, "weight": 1.0}, str(tmp_path))
        assert result["passed"] is True

    def test_exit_code_fail(self, tmp_path):
        from scripts.eval_runner import run_check
        result = run_check({"type": "exit_code", "command": "python -c \"exit(1)\"", "expected": 0, "weight": 1.0}, str(tmp_path))
        assert result["passed"] is False


class TestScoring:
    def test_weighted_score(self):
        from scripts.eval_runner import compute_score
        results = [
            {"passed": True, "weight": 2.0},
            {"passed": False, "weight": 1.0},
            {"passed": True, "weight": 1.0},
        ]
        score = compute_score(results)
        assert abs(score - 0.75) < 0.01  # 3/4 weighted

    def test_empty_results(self):
        from scripts.eval_runner import compute_score
        assert compute_score([]) == 0.0


class TestRunEvalTask:
    def test_run_eval_task(self, tmp_path):
        from scripts.eval_runner import run_eval_task
        f = tmp_path / "valid.json"
        f.write_text('{"ok": true}', encoding="utf-8")
        task = {
            "name": "test-task",
            "checks": {
                "deterministic": [
                    {"type": "json_valid", "path": str(f), "weight": 1.0},
                    {"type": "file_exists", "path": str(f), "weight": 1.0},
                ],
                "llm_judge": []
            }
        }
        result = run_eval_task(task, str(tmp_path))
        assert result["deterministic_score"] == 1.0
        assert result["total_checks"] == 2
        assert result["passed_checks"] == 2
```

- [ ] **Step 2: Run tests — should FAIL**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_eval_runner.py -v
```

- [ ] **Step 3: Implement eval_runner.py**

Create `scripts/eval_runner.py`:

```python
#!/usr/bin/env python3
"""Eval runner for Meta-Harness — deterministic grading of harness candidates.

Zero external dependencies. Handles: exit_code, file_exists, file_contains,
file_not_contains, json_valid, command_output checks.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
from typing import Any


def run_check(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    """Run a single deterministic check. Returns {passed, weight, type, evidence}."""
    check_type = check.get("type", "")
    weight = float(check.get("weight", 1.0))
    result = {"type": check_type, "weight": weight, "passed": False, "evidence": ""}

    try:
        if check_type == "json_valid":
            path = pathlib.Path(check["path"])
            if not path.is_absolute():
                path = pathlib.Path(cwd) / path
            content = path.read_text(encoding="utf-8")
            json.loads(content)
            result["passed"] = True
            result["evidence"] = f"{path.name}: valid JSON"

        elif check_type == "file_exists":
            path = pathlib.Path(check["path"])
            if not path.is_absolute():
                path = pathlib.Path(cwd) / path
            result["passed"] = path.exists()
            result["evidence"] = f"{'exists' if result['passed'] else 'missing'}: {path.name}"

        elif check_type == "file_contains":
            path = pathlib.Path(check["path"])
            if not path.is_absolute():
                path = pathlib.Path(cwd) / path
            content = path.read_text(encoding="utf-8")
            pattern = check.get("pattern", "")
            match = re.search(pattern, content, re.MULTILINE)
            result["passed"] = match is not None
            result["evidence"] = f"pattern '{pattern}': {'found' if match else 'not found'}"

        elif check_type == "file_not_contains":
            path = pathlib.Path(check["path"])
            if not path.is_absolute():
                path = pathlib.Path(cwd) / path
            content = path.read_text(encoding="utf-8")
            pattern = check.get("pattern", "")
            match = re.search(pattern, content, re.MULTILINE)
            result["passed"] = match is None
            result["evidence"] = f"pattern '{pattern}': {'absent (good)' if match is None else 'found (bad)'}"

        elif check_type == "exit_code":
            command = check.get("command", "")
            expected = int(check.get("expected", 0))
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                cwd=cwd, timeout=60,
            )
            result["passed"] = proc.returncode == expected
            result["evidence"] = f"exit={proc.returncode} (expected {expected})"

        elif check_type == "command_output":
            command = check.get("command", "")
            pattern = check.get("pattern", "")
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                cwd=cwd, timeout=60,
            )
            match = re.search(pattern, proc.stdout, re.MULTILINE)
            result["passed"] = match is not None
            result["evidence"] = f"output match '{pattern}': {'found' if match else 'not found'}"

        else:
            result["evidence"] = f"unknown check type: {check_type}"

    except FileNotFoundError:
        result["evidence"] = "file not found"
    except json.JSONDecodeError as e:
        result["evidence"] = f"invalid JSON: {e}"
    except subprocess.TimeoutExpired:
        result["evidence"] = "command timed out (60s)"
    except Exception as e:
        result["evidence"] = f"error: {e}"

    return result


def compute_score(results: list[dict[str, Any]]) -> float:
    """Compute weighted score from check results."""
    total_weight = sum(r.get("weight", 1.0) for r in results)
    if total_weight == 0:
        return 0.0
    passed_weight = sum(r.get("weight", 1.0) for r in results if r.get("passed"))
    return passed_weight / total_weight


def run_eval_task(task: dict[str, Any], cwd: str) -> dict[str, Any]:
    """Run all deterministic checks for an eval task."""
    checks = task.get("checks", {})
    deterministic = checks.get("deterministic", [])
    llm_judge = checks.get("llm_judge", [])

    results = []
    for check in deterministic:
        results.append(run_check(check, cwd))

    passed = sum(1 for r in results if r["passed"])
    return {
        "task_name": task.get("name", "unknown"),
        "deterministic_score": compute_score(results),
        "total_checks": len(results),
        "passed_checks": passed,
        "failed_checks": len(results) - passed,
        "results": results,
        "llm_judge_criteria": llm_judge,
    }


def load_eval_tasks(eval_dir: str | pathlib.Path) -> list[dict[str, Any]]:
    """Load all eval task JSON files from a directory tree."""
    eval_path = pathlib.Path(eval_dir)
    tasks = []
    for json_file in sorted(eval_path.rglob("*.json")):
        if json_file.name.startswith("_"):
            continue
        try:
            task = json.loads(json_file.read_text(encoding="utf-8"))
            if "name" in task and "checks" in task:
                task["_file"] = str(json_file)
                tasks.append(task)
        except Exception:
            pass
    return tasks


def run_all_evals(eval_dir: str, cwd: str) -> dict[str, Any]:
    """Run all eval tasks and return aggregate results."""
    tasks = load_eval_tasks(eval_dir)
    results = []
    for task in tasks:
        result = run_eval_task(task, cwd)
        results.append(result)

    total = sum(r["total_checks"] for r in results)
    passed = sum(r["passed_checks"] for r in results)
    scores = [r["deterministic_score"] for r in results if r["total_checks"] > 0]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        "tasks_run": len(results),
        "total_checks": total,
        "passed_checks": passed,
        "average_score": round(avg_score, 4),
        "results": results,
    }


def main() -> int:
    import argparse
    import sys
    p = argparse.ArgumentParser(prog="eval_runner")
    p.add_argument("--eval-dir", default="eval-tasks")
    p.add_argument("--cwd", default=".")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    args = p.parse_args()

    result = run_all_evals(args.eval_dir, args.cwd)

    if args.json:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(result, indent=2))
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(f"Tasks: {result['tasks_run']} | Checks: {result['passed_checks']}/{result['total_checks']} | Score: {result['average_score']:.1%}")
        for r in result["results"]:
            status = "PASS" if r["deterministic_score"] == 1.0 else "FAIL"
            print(f"  [{status}] {r['task_name']}: {r['passed_checks']}/{r['total_checks']} ({r['deterministic_score']:.0%})")
            for check in r["results"]:
                mark = "✓" if check["passed"] else "✗"
                print(f"    {mark} {check['type']}: {check['evidence']}")

    return 0 if result["average_score"] >= 0.5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests — should PASS**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_eval_runner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_runner.py tests/test_eval_runner.py
git commit -m "feat: add eval runner with deterministic grading engine (6 check types)"
```

---

### Task 3: Evaluator Agent + Skills

**Files:**
- Create: `agents/harness-evaluator.md`
- Create: `skills/harness-eval/SKILL.md`
- Create: `skills/harness-bootstrap/SKILL.md`

- [ ] **Step 1: Create evaluator agent**

Create `agents/harness-evaluator.md`:

```markdown
---
name: harness-evaluator
description: Evaluate harness candidates using deterministic checks and LLM judgment. Run eval tasks, compare against baseline, record metrics.
model: inherit
effort: high
maxTurns: 20
isolation: worktree
---
You are a harness evaluator for Meta-Harness.

Your job is to objectively evaluate a harness candidate against defined criteria.

## Evaluation workflow

1. Read the eval task definitions from eval-tasks/
2. Run deterministic checks using the eval_runner
3. For each LLM-judge criteria, evaluate the candidate's work against the criteria
4. Compute a weighted score
5. Record results in the candidate's metrics.json

## Deterministic grading

Run: `python3 scripts/eval_runner.py --eval-dir eval-tasks --cwd . --json`

This produces pass/fail for each deterministic check with evidence.

## LLM-judge grading

For each criteria in the eval task's `llm_judge` section:
1. Read the relevant files modified by the candidate
2. Evaluate whether the criteria is met
3. Record: {"text": "criteria", "passed": true/false, "evidence": "specific finding"}

## Scoring

Final score = 0.6 * deterministic_score + 0.4 * llm_judge_score

## Principles

- Be objective. Evidence over opinion.
- If a check is ambiguous, fail it and explain why.
- Never fabricate evidence. If you cannot determine pass/fail, mark as failed with evidence "unable to determine".
- Report the exact score, not a rounded or optimistic version.
```

- [ ] **Step 2: Create /mh:eval skill**

Create `skills/harness-eval/SKILL.md`:

```markdown
---
name: eval
description: Run the evaluation suite on the current harness or a specific candidate run. Reports deterministic check results and LLM-judge assessment.
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(python3 *) Bash(git *)
---

# Harness Evaluation

Run the evaluation suite to measure harness quality.

## Deterministic checks
```!
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/eval_runner.py --eval-dir ${CLAUDE_PLUGIN_ROOT}/eval-tasks --cwd . 2>&1 || echo "Eval runner not available"
```

## Instructions

1. Review the deterministic check results above.
2. For each eval task that has `llm_judge` criteria, evaluate the criteria manually:
   - Read the relevant files
   - Assess whether each criteria is met
   - Record evidence for your judgment
3. Compute the final score: 0.6 * deterministic + 0.4 * llm_judge
4. Present results using the Meta-Harness output format.

If a specific run_id was provided as $ARGUMENTS, evaluate that candidate's artifacts in runs/{run_id}/.
Otherwise, evaluate the current harness state.
```

- [ ] **Step 3: Create /mh:bootstrap skill**

Create `skills/harness-bootstrap/SKILL.md`:

```markdown
---
name: bootstrap
description: Analyze the current project and generate initial eval tasks for harness optimization. Creates regression and capability eval tasks based on project structure.
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(python3 *) Bash(git *) Bash(ls *) Write
---

# Harness Bootstrap

Analyze this project and generate appropriate eval tasks for harness optimization.

## Current project state
```!
ls -la
```

## Current harness surfaces
```!
ls .claude/rules/ 2>/dev/null || echo "No rules"
ls .claude/skills/*/SKILL.md 2>/dev/null || echo "No skills"
ls .claude/agents/*.md 2>/dev/null || echo "No agents"
cat CLAUDE.md 2>/dev/null | head -50 || echo "No CLAUDE.md"
```

## Current eval tasks
```!
find ${CLAUDE_PLUGIN_ROOT}/eval-tasks -name '*.json' ! -name '_*' 2>/dev/null || echo "No eval tasks"
```

## Instructions

Generate eval tasks for this project:

1. **Regression tasks** (eval-tasks/regression/): Easy checks that should ALWAYS pass.
   - Harness files are valid JSON/YAML
   - CLAUDE.md exists and has required sections
   - Skills have valid frontmatter
   - mh-validate passes

2. **Capability tasks** (eval-tasks/capability/): Harder checks measuring improvement.
   - Based on the project's actual domain and coding patterns
   - Based on recent git history (what kind of tasks are common)
   - Based on CLAUDE.md constraints (are they being followed?)

Write each task as a JSON file following the schema in eval-tasks/_schema.json.

Each task must have: name, type, difficulty, description, checks (deterministic + llm_judge).
Use only check types: exit_code, file_exists, file_contains, file_not_contains, json_valid, command_output.
```

- [ ] **Step 4: Commit**

```bash
git add agents/harness-evaluator.md skills/harness-eval/ skills/harness-bootstrap/
git commit -m "feat: add evaluator agent, /mh:eval and /mh:bootstrap skills"
```

---

### Task 4: MCP Integration + Tests + Tag

**Files:**
- Modify: `servers/mh_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add eval_run tool to MCP server**

Add to `servers/mh_server.py` before `if __name__`:

```python
@mcp.tool()
async def eval_run(eval_dir: str = "", cwd: str = "") -> str:
    """Run all eval tasks and return results with scores.

    Args:
        eval_dir: Path to eval-tasks directory. Defaults to plugin's eval-tasks/.
        cwd: Working directory for running checks. Defaults to plugin root.
    """
    import sys as _sys
    _sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from eval_runner import run_all_evals
    _eval_dir = eval_dir or str(PLUGIN_ROOT / "eval-tasks")
    _cwd = cwd or str(PLUGIN_ROOT)
    result = run_all_evals(_eval_dir, _cwd)

    lines = [f"## Eval Results", ""]
    lines.append(f"**Tasks:** {result['tasks_run']} | **Checks:** {result['passed_checks']}/{result['total_checks']} | **Score:** {result['average_score']:.1%}")
    lines.append("")
    for r in result["results"]:
        status = "PASS" if r["deterministic_score"] == 1.0 else "FAIL"
        lines.append(f"### [{status}] {r['task_name']} ({r['deterministic_score']:.0%})")
        for check in r["results"]:
            mark = "✓" if check["passed"] else "✗"
            lines.append(f"- {mark} {check['type']}: {check['evidence']}")
    return "\n".join(lines)
```

- [ ] **Step 2: Add test**

Append to `tests/test_mcp_server.py`:

```python
class TestEvalIntegration:
    def test_eval_run_tool_exists(self):
        try:
            from servers.mh_server import eval_run
            assert callable(eval_run)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise
```

- [ ] **Step 3: Run ALL tests**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/ -v
```

- [ ] **Step 4: Test eval runner on our own project**

```bash
cd C:/Code/Meta-Harness-YGN && python scripts/eval_runner.py --eval-dir eval-tasks --cwd .
```

- [ ] **Step 5: Commit, tag, push**

```bash
git add servers/mh_server.py tests/test_mcp_server.py
git commit -m "feat: add eval_run MCP tool for running eval suite"
git tag -a v0.4.0 -m "Phase 3: Eval framework — deterministic grading, evaluator agent, eval/bootstrap skills"
git push origin master --tags
```
