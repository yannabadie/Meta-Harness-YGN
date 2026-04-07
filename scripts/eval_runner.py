"""eval_runner.py — deterministic grading engine for Claude Code plugin evals.

Public API
----------
run_check(check, cwd)        Execute one deterministic check; return result dict.
compute_score(results)       Weighted score from a list of check result dicts.
run_eval_task(task, cwd)     Run all deterministic checks for one task.
load_eval_tasks(eval_dir)    Load all JSON eval-task files from a directory.
run_all_evals(eval_dir, cwd) Run every task and return aggregate results.
main()                       CLI entry point (argparse).

Supported check types
---------------------
json_valid         File at `path` must parse as valid JSON.
file_exists        File at `path` must exist on disk.
file_contains      File at `path` must match `pattern` (regex).
file_not_contains  File at `path` must NOT match `pattern` (regex).
exit_code          Shell `command` must exit with `expected` code.
command_output     Shell `command` stdout must match `pattern` (regex).

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_path(raw_path: str, cwd: str) -> pathlib.Path:
    """Return an absolute Path; if raw_path is relative, resolve against cwd."""
    p = pathlib.Path(raw_path)
    if not p.is_absolute():
        p = pathlib.Path(cwd) / p
    return p


def _run_subprocess(command: str, cwd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run *command* in a shell and return the CompletedProcess (stdout/stderr captured)."""
    return subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------

def _check_json_valid(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    path = _resolve_path(check["path"], cwd)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            json.load(fh)
        passed = True
        evidence = f"Valid JSON at {path}"
    except (json.JSONDecodeError, OSError) as exc:
        passed = False
        evidence = str(exc)
    return {"type": "json_valid", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


def _check_file_exists(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    path = _resolve_path(check["path"], cwd)
    passed = path.exists()
    evidence = f"{'Found' if passed else 'Missing'}: {path}"
    return {"type": "file_exists", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


def _check_file_contains(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    path = _resolve_path(check["path"], cwd)
    pattern = check.get("pattern", "")
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(pattern, content)
        passed = match is not None
        evidence = f"Pattern {'found' if passed else 'not found'}: {pattern!r} in {path}"
    except OSError as exc:
        passed = False
        evidence = str(exc)
    return {"type": "file_contains", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


def _check_file_not_contains(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    path = _resolve_path(check["path"], cwd)
    pattern = check.get("pattern", "")
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(pattern, content)
        passed = match is None
        evidence = f"Pattern {'absent (good)' if passed else 'found (bad)'}: {pattern!r} in {path}"
    except OSError as exc:
        passed = False
        evidence = str(exc)
    return {"type": "file_not_contains", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


def _check_exit_code(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    command = check.get("command", "")
    expected = check.get("expected", 0)
    try:
        proc = _run_subprocess(command, cwd)
        passed = proc.returncode == expected
        evidence = f"Exit code {proc.returncode} (expected {expected}) for: {command}"
    except Exception as exc:  # noqa: BLE001
        passed = False
        evidence = str(exc)
    return {"type": "exit_code", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


def _check_command_output(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    command = check.get("command", "")
    pattern = check.get("pattern", "")
    try:
        proc = _run_subprocess(command, cwd)
        output = proc.stdout
        match = re.search(pattern, output)
        passed = match is not None
        evidence = (
            f"Pattern {'found' if passed else 'not found'}: {pattern!r} in stdout of: {command}"
        )
    except Exception as exc:  # noqa: BLE001
        passed = False
        evidence = str(exc)
    return {"type": "command_output", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_CHECK_HANDLERS: dict[str, Any] = {
    "json_valid": _check_json_valid,
    "file_exists": _check_file_exists,
    "file_contains": _check_file_contains,
    "file_not_contains": _check_file_not_contains,
    "exit_code": _check_exit_code,
    "command_output": _check_command_output,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_check(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    """Execute one deterministic check and return a result dict.

    Returns a dict with at minimum:
        passed   bool
        weight   float
        type     str
        evidence str
    """
    check_type = check.get("type", "")
    handler = _CHECK_HANDLERS.get(check_type)
    if handler is None:
        return {
            "type": check_type,
            "passed": False,
            "weight": check.get("weight", 1.0),
            "evidence": f"Unknown check type: {check_type!r}",
        }
    try:
        return handler(check, cwd)
    except Exception as exc:  # noqa: BLE001
        return {
            "type": check_type,
            "passed": False,
            "weight": check.get("weight", 1.0),
            "evidence": f"Unexpected error: {exc}",
        }


def compute_score(results: list[dict[str, Any]]) -> float:
    """Return the weighted fraction of passed checks.

    Score = sum(weight for passed checks) / sum(all weights).
    Returns 0.0 for an empty list.
    """
    if not results:
        return 0.0
    total_weight = sum(r.get("weight", 1.0) for r in results)
    if total_weight == 0.0:
        return 0.0
    passed_weight = sum(r.get("weight", 1.0) for r in results if r.get("passed"))
    return passed_weight / total_weight


def run_eval_task(task: dict[str, Any], cwd: str) -> dict[str, Any]:
    """Run all deterministic checks for one eval task.

    Returns a dict with:
        name                 str
        deterministic_score  float   (0.0–1.0)
        total_checks         int
        passed_checks        int
        check_results        list[dict]
    """
    name = task.get("name", "<unnamed>")
    checks_section = task.get("checks", {})
    deterministic_checks = checks_section.get("deterministic", [])

    check_results: list[dict[str, Any]] = []
    for check in deterministic_checks:
        check_results.append(run_check(check, cwd))

    total = len(check_results)
    passed = sum(1 for r in check_results if r.get("passed"))
    score = compute_score(check_results)

    return {
        "name": name,
        "deterministic_score": score,
        "total_checks": total,
        "passed_checks": passed,
        "check_results": check_results,
    }


def load_eval_tasks(eval_dir: str) -> list[dict[str, Any]]:
    """Load all JSON eval-task files from *eval_dir*.

    Each JSON file must be a dict (single task) or a list of dicts (multiple
    tasks).  Files that fail to parse are skipped with a warning on stderr.
    """
    tasks: list[dict[str, Any]] = []
    dir_path = pathlib.Path(eval_dir)
    if not dir_path.is_dir():
        print(f"[eval_runner] eval_dir not found: {eval_dir}", file=sys.stderr)
        return tasks

    for json_file in sorted(dir_path.rglob("*.json")):
        try:
            with open(json_file, encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                tasks.append(data)
            elif isinstance(data, list):
                tasks.extend(item for item in data if isinstance(item, dict))
            else:
                print(f"[eval_runner] Skipping {json_file}: unexpected JSON structure", file=sys.stderr)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[eval_runner] Skipping {json_file}: {exc}", file=sys.stderr)

    return tasks


def run_all_evals(eval_dir: str, cwd: str) -> dict[str, Any]:
    """Run every task in *eval_dir* and return an aggregate report.

    Returns:
        tasks           list of per-task result dicts from run_eval_task()
        aggregate_score float   weighted mean of deterministic_score across tasks
        total_tasks     int
        passed_tasks    int     tasks where deterministic_score == 1.0
    """
    tasks = load_eval_tasks(eval_dir)
    task_results: list[dict[str, Any]] = []
    for task in tasks:
        task_results.append(run_eval_task(task, cwd))

    total_tasks = len(task_results)
    passed_tasks = sum(1 for r in task_results if r.get("deterministic_score", 0.0) == 1.0)
    aggregate_score = (
        sum(r.get("deterministic_score", 0.0) for r in task_results) / total_tasks
        if total_tasks > 0
        else 0.0
    )

    return {
        "tasks": task_results,
        "aggregate_score": aggregate_score,
        "total_tasks": total_tasks,
        "passed_tasks": passed_tasks,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    # Windows-safe UTF-8 stdout
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="eval_runner",
        description="Run deterministic eval checks for the Claude Code plugin harness.",
    )
    parser.add_argument(
        "--eval-dir",
        default="eval-tasks",
        help="Directory containing JSON eval-task files (default: eval-tasks).",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Working directory used when resolving relative paths in checks (default: .).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable text.",
    )

    args = parser.parse_args()
    eval_dir = str(pathlib.Path(args.eval_dir).resolve())
    cwd = str(pathlib.Path(args.cwd).resolve())

    report = run_all_evals(eval_dir, cwd)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Eval report — {report['total_tasks']} task(s) loaded from: {eval_dir}")
        print(f"Passed tasks : {report['passed_tasks']} / {report['total_tasks']}")
        print(f"Aggregate score: {report['aggregate_score']:.2%}\n")
        for task_result in report["tasks"]:
            status = "PASS" if task_result["deterministic_score"] == 1.0 else "FAIL"
            print(
                f"  [{status}] {task_result['name']} "
                f"({task_result['passed_checks']}/{task_result['total_checks']} checks, "
                f"score={task_result['deterministic_score']:.2%})"
            )
            for cr in task_result["check_results"]:
                mark = "+" if cr["passed"] else "-"
                print(f"         [{mark}] {cr['type']}: {cr['evidence']}")

    return 0 if report["aggregate_score"] == 1.0 or report["total_tasks"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
