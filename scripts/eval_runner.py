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

Result caching
--------------
File-based checks (json_valid, file_exists, file_contains, file_not_contains,
patch_not_empty, max_files_changed, files_in_scope) are cached via a SHA-256
fingerprint of the task definition + file contents.  The cache is stored at
$CLAUDE_PLUGIN_DATA/eval_cache.json (or $MH_PLUGIN_DATA).  Use --no-cache to
force a fresh run.  Command-based checks are never cached.

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.config import PLUGIN_DATA

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


def _check_patch_not_empty(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    path = _resolve_path(check["path"], cwd)
    if not path.exists():
        return {"type": "patch_not_empty", "passed": False, "weight": check.get("weight", 1.0), "evidence": "patch file missing"}
    content = path.read_text(encoding="utf-8").strip()
    passed = len(content) > 10  # More than just whitespace
    evidence = f"patch {'has content' if passed else 'is empty or trivial'} ({len(content)} chars)"
    return {"type": "patch_not_empty", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


def _check_max_files_changed(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    path = _resolve_path(check["path"], cwd)
    max_files = int(check.get("max", 3))
    if not path.exists():
        return {"type": "max_files_changed", "passed": False, "weight": check.get("weight", 1.0), "evidence": "patch file missing"}
    content = path.read_text(encoding="utf-8")
    # Count files: lines starting with "+++ b/"
    files: set[str] = set()
    for line in content.split("\n"):
        if line.startswith("+++ b/"):
            files.add(line[6:])
    passed = len(files) <= max_files
    evidence = f"{len(files)} files changed (max {max_files})"
    return {"type": "max_files_changed", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


def _check_before_after(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    """Run a command and check output matches an improvement pattern."""
    command = check.get("command", "")
    pattern = check.get("improvement_pattern", "")
    try:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=cwd, timeout=120)
        output = proc.stdout + proc.stderr
        if pattern:
            match = re.search(pattern, output)
            passed = match is not None
            evidence = f"Pattern '{pattern}': {'found' if passed else 'not found'} in output"
        else:
            passed = proc.returncode == 0
            evidence = f"Exit {proc.returncode}, output: {output[:200]}"
    except subprocess.TimeoutExpired:
        passed, evidence = False, "Timed out (120s)"
    except Exception as exc:
        passed, evidence = False, str(exc)
    return {"type": "before_after_command", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


def _check_files_in_scope(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    path = _resolve_path(check["path"], cwd)
    HARNESS_PATTERNS = [
        "CLAUDE.md", ".claude/", "prompts/", ".meta-harness/",
        "skills/", "agents/", "rules/",
    ]
    if not path.exists():
        return {"type": "files_in_scope", "passed": False, "weight": check.get("weight", 1.0), "evidence": "patch file missing"}
    content = path.read_text(encoding="utf-8")
    out_of_scope: list[str] = []
    for line in content.split("\n"):
        if line.startswith("+++ b/"):
            fpath = line[6:]
            in_scope = any(fpath.startswith(p) or fpath == p.rstrip("/") for p in HARNESS_PATTERNS)
            if not in_scope:
                out_of_scope.append(fpath)
    passed = len(out_of_scope) == 0
    if out_of_scope:
        evidence = f"out-of-scope files: {', '.join(out_of_scope)}"
    else:
        evidence = "all files within harness scope"
    return {"type": "files_in_scope", "passed": passed, "weight": check.get("weight", 1.0), "evidence": evidence}


# ---------------------------------------------------------------------------
# Confidence map — deterministic checks = HIGH, command-dependent = MEDIUM,
# unknown / LLM-driven = LOW.
# ---------------------------------------------------------------------------

CONFIDENCE_MAP: dict[str, str] = {
    "json_valid": "high",
    "file_exists": "high",
    "file_contains": "high",
    "file_not_contains": "high",
    "exit_code": "high",
    "command_output": "medium",  # depends on command reliability
    "patch_not_empty": "high",
    "max_files_changed": "high",
    "files_in_scope": "high",
    "before_after_command": "medium",
}


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
    "patch_not_empty": _check_patch_not_empty,
    "max_files_changed": _check_max_files_changed,
    "files_in_scope": _check_files_in_scope,
    "before_after_command": _check_before_after,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_check(check: dict[str, Any], cwd: str) -> dict[str, Any]:
    """Execute one deterministic check and return a result dict.

    Returns a dict with at minimum:
        passed      bool
        weight      float
        type        str
        evidence    str
        confidence  str   ("high", "medium", or "low")
    """
    check_type = check.get("type", "")
    handler = _CHECK_HANDLERS.get(check_type)
    confidence = CONFIDENCE_MAP.get(check_type, "low")
    if handler is None:
        return {
            "type": check_type,
            "passed": False,
            "weight": check.get("weight", 1.0),
            "evidence": f"Unknown check type: {check_type!r}",
            "confidence": confidence,
        }
    try:
        result = handler(check, cwd)
        result["confidence"] = confidence
        return result
    except Exception as exc:  # noqa: BLE001
        return {
            "type": check_type,
            "passed": False,
            "weight": check.get("weight", 1.0),
            "evidence": f"Unexpected error: {exc}",
            "confidence": confidence,
        }


def compute_score(results: list[dict[str, Any]], weight_by_confidence: bool = False) -> float:
    """Return the weighted fraction of passed checks.

    Score = sum(weight for passed checks) / sum(all weights).
    Returns 0.0 for an empty list.

    Args:
        results: List of check result dicts from run_check().
        weight_by_confidence: If True, multiply each check's weight by a
            confidence factor (high=1.0, medium=0.8, low=0.6) so that
            deterministic checks contribute more than LLM-judged ones.
    """
    if not results:
        return 0.0
    CONF_WEIGHT: dict[str, float] = {"high": 1.0, "medium": 0.8, "low": 0.6}
    total = 0.0
    passed = 0.0
    for r in results:
        w = r.get("weight", 1.0)
        if weight_by_confidence:
            w *= CONF_WEIGHT.get(r.get("confidence", "low"), 0.6)
        total += w
        if r.get("passed"):
            passed += w
    return passed / total if total > 0 else 0.0


def _fingerprint_task(task: dict[str, Any], cwd: str) -> str:
    """SHA-256 fingerprint of task definition + referenced file contents."""
    h = hashlib.sha256()
    h.update(json.dumps(task, sort_keys=True, separators=(",", ":")).encode())
    for check in task.get("checks", {}).get("deterministic", []):
        path_val = check.get("path", "")
        if path_val:
            p = _resolve_path(path_val, cwd)
            if p.exists():
                try:
                    h.update(p.read_bytes())
                except Exception:
                    pass
    return h.hexdigest()


def _load_cache() -> dict:
    cache_file = PLUGIN_DATA / "eval_cache.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "entries": {}}


def _save_cache(cache: dict) -> None:
    cache_file = PLUGIN_DATA / "eval_cache.json"
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def _is_cacheable(task: dict) -> bool:
    """Only cache tasks with purely file-based checks (no commands)."""
    for check in task.get("checks", {}).get("deterministic", []):
        if check.get("type") in ("exit_code", "command_output", "before_after_command"):
            return False
    return True


def run_eval_task(task: dict[str, Any], cwd: str, trials: int = 3) -> dict[str, Any]:
    """Run all deterministic checks for one eval task.

    Pass^N: each check is run *trials* times; a check only counts as passed
    if it passes in ALL trials, making flaky checks visible.

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

    if not deterministic_checks:
        return {
            "name": name,
            "deterministic_score": 0.0,
            "total_checks": 0,
            "passed_checks": 0,
            "check_results": [],
        }

    # Run all checks N times (Pass^N: only pass if ALL trials pass)
    trial_results: list[list[dict[str, Any]]] = []
    for _trial in range(max(1, trials)):
        trial_checks = [run_check(check, cwd) for check in deterministic_checks]
        trial_results.append(trial_checks)

    # Merge: a check passes only if it passed in ALL trials
    merged: list[dict[str, Any]] = []
    for i in range(len(deterministic_checks)):
        passes = [trial_results[t][i]["passed"] for t in range(len(trial_results))]
        result = trial_results[0][i].copy()
        result["passed"] = all(passes)
        result["trials_passed"] = sum(passes)
        result["trials_total"] = len(trial_results)
        if not result["passed"] and any(passes):
            result["evidence"] += f" (flaky: {sum(passes)}/{len(trial_results)} trials)"
        merged.append(result)

    total = len(merged)
    passed = sum(1 for r in merged if r["passed"])
    score = compute_score(merged)

    return {
        "name": name,
        "deterministic_score": score,
        "total_checks": total,
        "passed_checks": passed,
        "check_results": merged,
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
        if json_file.name.startswith("_"):
            continue  # skip schema/meta files like _schema.json
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


def run_all_evals(
    eval_dir: str,
    cwd: str,
    include_requires_run: bool = False,
    trials: int = 3,
    no_cache: bool = False,
) -> dict[str, Any]:
    """Run every task in *eval_dir* and return an aggregate report.

    Args:
        eval_dir: Directory containing eval task JSON files.
        cwd: Working directory for running checks.
        include_requires_run: If False (default), skip tasks with "requires_run": true.
        trials: Pass^N — number of times each check is run (default 3).
        no_cache: If True, skip loading from and saving to the SHA-256 result cache.

    Returns:
        tasks           list of per-task result dicts from run_eval_task()
        aggregate_score float   weighted mean of deterministic_score across tasks
        total_tasks     int
        passed_tasks    int     tasks where deterministic_score == 1.0
    """
    tasks = load_eval_tasks(eval_dir)
    cache = _load_cache() if not no_cache else {"version": 1, "entries": {}}
    task_results: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("requires_run") and not include_requires_run:
            continue
        fingerprint = _fingerprint_task(task, cwd)
        cache_key = f"{fingerprint}:trials={trials}"
        if not no_cache and cache_key in cache.get("entries", {}):
            task_results.append(cache["entries"][cache_key])
            continue
        result = run_eval_task(task, cwd, trials=trials)
        task_results.append(result)
        if not no_cache and _is_cacheable(task):
            cache.setdefault("entries", {})[cache_key] = result
            _save_cache(cache)

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
    parser.add_argument(
        "--trials",
        type=int,
        default=3,
        help="Pass^N: trials per check (default 3)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable SHA-256 result cache — always re-run all checks.",
    )

    args = parser.parse_args()
    eval_dir = str(pathlib.Path(args.eval_dir).resolve())
    cwd = str(pathlib.Path(args.cwd).resolve())

    report = run_all_evals(eval_dir, cwd, trials=args.trials, no_cache=args.no_cache)

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
                mark = "PASS" if cr["passed"] else "FAIL"
                conf = cr.get("confidence", "low").upper()
                trials_info = ""
                if args.trials > 1 and "trials_passed" in cr:
                    trials_info = f" [{cr['trials_passed']}/{cr['trials_total']} trials]"
                print(f"         [{mark}] {cr['type']} ({conf}){trials_info}: {cr['evidence']}")

    return 0 if report["aggregate_score"] == 1.0 or report["total_tasks"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
