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
        assert abs(score - 0.75) < 0.01

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
