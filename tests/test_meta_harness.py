"""Tests for meta_harness.py — Phase 0: compact-summary subcommand."""
import json
import os
import pathlib
import tempfile
import csv
import subprocess

import pytest

# Override PLUGIN_DATA before import
_tmp = tempfile.mkdtemp()
os.environ["CLAUDE_PLUGIN_DATA"] = _tmp

from scripts.meta_harness import main, read_frontier, FRONTIER, TSV_HEADER, ensure_dirs


@pytest.fixture(autouse=True)
def clean_state():
    """Reset frontier.tsv and RUNS_DIR before each test."""
    import shutil
    from scripts.meta_harness import RUNS_DIR
    ensure_dirs()
    with FRONTIER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(TSV_HEADER)
    if RUNS_DIR.exists():
        shutil.rmtree(RUNS_DIR)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    yield


def _add_row(run_id, score, latency, tokens, status="complete"):
    """Helper to add a row to frontier.tsv."""
    rows = read_frontier()
    rows.append({
        "run_id": run_id,
        "status": status,
        "primary_score": str(score),
        "avg_latency_ms": str(latency),
        "avg_input_tokens": str(tokens),
        "risk": "low",
        "note": f"test {run_id}",
        "timestamp": "2026-04-07T00:00:00Z",
    })
    with FRONTIER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_HEADER, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in TSV_HEADER})


class TestExtendedFrontier:
    def test_new_columns_in_header(self):
        from scripts.config import EVALUATION_VERDICTS, REPORT_VERDICTS, RUN_STATUSES
        from scripts.meta_harness import TSV_HEADER
        assert "consistency" in TSV_HEADER
        assert "instruction_adherence" in TSV_HEADER
        assert "tool_efficiency" in TSV_HEADER
        assert "error_count" in TSV_HEADER
        assert "metrics_schema_version" in TSV_HEADER
        assert "sample_size" in TSV_HEADER
        assert "eval_method" in TSV_HEADER
        assert "deterministic_score" in TSV_HEADER
        assert "llm_judge_score" in TSV_HEADER
        assert "evaluation_verdict" in TSV_HEADER
        assert "report_verdict" in TSV_HEADER
        assert "benchmark_version" in TSV_HEADER
        assert "baseline_run_id" in TSV_HEADER
        assert "seed" in TSV_HEADER
        assert RUN_STATUSES == ("reserved", "complete", "promoted")
        assert EVALUATION_VERDICTS == ("accepted", "accepted_with_warnings", "rejected", "partial")
        assert REPORT_VERDICTS == ("PROMOTE", "REJECT", "ITERATE")

    def test_backward_compat_old_rows(self):
        _add_row("run-0010", 0.75, 8000, 11000)
        rows = read_frontier()
        row = rows[0]
        assert row.get("consistency", "") == ""

    def test_record_metrics_with_new_columns(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", [
            "meta_harness.py", "record-metrics",
            "run-0020", "0.81", "7500", "10000", "low", "test note",
            "--consistency", "0.58",
            "--instruction-adherence", "4.2",
            "--tool-efficiency", "12",
            "--error-count", "2",
        ])
        main()
        rows = read_frontier()
        row = [r for r in rows if r["run_id"] == "run-0020"][0]
        assert row["consistency"] == "0.58"
        assert row["instruction_adherence"] == "4.2"
        assert row["tool_efficiency"] == "12"
        assert row["error_count"] == "2"

    def test_record_metrics_persists_evaluation_metadata(self, capsys, monkeypatch):
        from scripts.meta_harness import RUNS_DIR

        monkeypatch.setattr("sys.argv", [
            "meta_harness.py", "record-metrics",
            "run-0021", "0.83", "7300", "9800", "low", "metadata test",
            "--sample-size", "8",
            "--eval-method", "deterministic+llm",
            "--deterministic-score", "0.92",
            "--llm-judge-score", "0.75",
            "--evaluation-verdict", "accepted_with_warnings",
            "--report-verdict", "ITERATE",
            "--benchmark-version", "2026-04-09",
            "--baseline-run-id", "run-0007",
            "--seed", "42",
        ])
        main()

        rows = read_frontier()
        row = [r for r in rows if r["run_id"] == "run-0021"][0]
        assert row["sample_size"] == "8"
        assert row["eval_method"] == "deterministic+llm"
        assert row["deterministic_score"] == "0.92"
        assert row["llm_judge_score"] == "0.75"
        assert row["evaluation_verdict"] == "accepted_with_warnings"
        assert row["report_verdict"] == "ITERATE"
        assert row["benchmark_version"] == "2026-04-09"
        assert row["baseline_run_id"] == "run-0007"
        assert row["seed"] == "42"
        metrics = json.loads((RUNS_DIR / "run-0021" / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["metrics_schema_version"] == "2"
        assert metrics["evaluation_verdict"] == "accepted_with_warnings"
        assert metrics["report_verdict"] == "ITERATE"


class TestCheckpoint:
    def test_write_checkpoint(self):
        from scripts.meta_harness import write_checkpoint, RUNS_DIR
        ensure_dirs()
        run_dir = RUNS_DIR / "run-0050"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_checkpoint(run_dir, "PROPOSE", 5, "test objective")
        cp_file = run_dir / "checkpoint.json"
        assert cp_file.exists()
        data = json.loads(cp_file.read_text(encoding="utf-8"))
        assert data["phase"] == "PROPOSE"
        assert data["turn"] == 5
        assert data["objective"] == "test objective"

    def test_detect_incomplete_run(self):
        from scripts.meta_harness import write_checkpoint, detect_incomplete_runs, RUNS_DIR
        ensure_dirs()
        run_dir = RUNS_DIR / "run-0051"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_checkpoint(run_dir, "EVALUATE", 12, "improve validation")
        result = detect_incomplete_runs()
        assert result is not None
        assert result["run_id"] == "run-0051"
        assert result["phase"] == "EVALUATE"

    def test_completed_run_not_detected(self):
        from scripts.meta_harness import write_checkpoint, detect_incomplete_runs, RUNS_DIR
        ensure_dirs()
        run_dir = RUNS_DIR / "run-0052"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_checkpoint(run_dir, "COMPLETED", 20, "done")
        (run_dir / "metrics.json").write_text('{"status": "complete"}', encoding="utf-8")
        result = detect_incomplete_runs()
        if result:
            assert result["run_id"] != "run-0052"


class TestCompareProjects:
    def test_compare_shows_current(self, capsys, monkeypatch):
        _add_row("run-0080", 0.85, 7000, 9000)
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "compare-projects"])
        main()
        out = capsys.readouterr().out
        assert "Cross-Project" in out
        assert "current" in out
        assert "0.850" in out


class TestTimeline:
    def test_timeline_with_data(self, capsys, monkeypatch):
        _add_row("run-0070", 0.72, 8500, 11000)
        _add_row("run-0071", 0.76, 8100, 10500)
        _add_row("run-0072", 0.81, 7800, 10000)
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "timeline"])
        main()
        out = capsys.readouterr().out
        assert "Timeline" in out
        assert "Score" in out
        assert "0.81" in out or "0.810" in out

    def test_timeline_empty(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "timeline"])
        main()
        out = capsys.readouterr().out
        assert "No completed runs" in out


class TestPromote:
    @staticmethod
    def _write_candidate(run_id: str, patch_text: str = "--- a/CLAUDE.md\n+++ b/CLAUDE.md\n@@ -1 +1 @@\n-old\n+new\n"):
        from scripts.meta_harness import RUNS_DIR

        ensure_dirs()
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "candidate.patch").write_text(patch_text, encoding="utf-8")
        (run_dir / "metrics.json").write_text(
            json.dumps({"run_id": run_id, "status": "complete"}, indent=2),
            encoding="utf-8",
        )
        return run_dir

    def test_promote_requires_metrics(self, capsys, monkeypatch):
        from scripts.meta_harness import RUNS_DIR
        ensure_dirs()
        run_dir = RUNS_DIR / "run-0060"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "candidate.patch").write_text("some patch", encoding="utf-8")
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "promote", "run-0060"])
        result = main()
        assert result == 1  # no metrics = error
        out = capsys.readouterr().out
        assert "No metrics" in out

    def test_promote_refuses_dirty_worktree(self, capsys, monkeypatch):
        self._write_candidate("run-0061")

        def fake_run(args, capture_output=True, text=True):
            if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
                return subprocess.CompletedProcess(args, 0, stdout="true\n", stderr="")
            if args[:3] == ["git", "status", "--porcelain"]:
                return subprocess.CompletedProcess(args, 0, stdout=" M CLAUDE.md\n", stderr="")
            raise AssertionError(f"Unexpected git call: {args}")

        monkeypatch.setattr("scripts.meta_harness.subprocess.run", fake_run)
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "promote", "run-0061"])
        result = main()

        assert result == 1
        out = capsys.readouterr().out
        assert "dirty git worktree" in out

    def test_promote_updates_metrics_on_success(self, capsys, monkeypatch):
        run_dir = self._write_candidate("run-0062")

        def fake_run(args, capture_output=True, text=True):
            if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
                return subprocess.CompletedProcess(args, 0, stdout="true\n", stderr="")
            if args[:3] == ["git", "status", "--porcelain"]:
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if args[:3] == ["git", "tag", "--list"]:
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if args[:3] == ["git", "apply", "--check"]:
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if args[:2] == ["git", "tag"]:
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if args[:2] == ["git", "apply"]:
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            raise AssertionError(f"Unexpected git call: {args}")

        monkeypatch.setattr("scripts.meta_harness.subprocess.run", fake_run)
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "promote", "run-0062"])
        result = main()

        assert result == 0
        out = capsys.readouterr().out
        assert "Promoted run-0062" in out
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["status"] == "promoted"


class TestNextRun:
    def test_initializes_reserved_metrics_for_new_run(self, capsys, monkeypatch):
        from scripts.meta_harness import RUNS_DIR

        monkeypatch.setattr("sys.argv", ["meta_harness.py", "next-run"])
        result = main()

        assert result == 0
        run_id = capsys.readouterr().out.strip()
        metrics = json.loads((RUNS_DIR / run_id / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["run_id"] == run_id
        assert metrics["status"] == "reserved"
        assert metrics["timestamp"]

    def test_records_reserved_row_in_frontier_for_new_run(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "next-run"])
        result = main()

        assert result == 0
        run_id = capsys.readouterr().out.strip()
        rows = {row["run_id"]: row for row in read_frontier()}
        assert rows[run_id]["status"] == "reserved"
        assert rows[run_id]["timestamp"]

    def test_existing_run_id_preserves_completed_state(self, capsys, monkeypatch):
        from scripts.meta_harness import RUNS_DIR

        run_dir = RUNS_DIR / "run-0099"
        run_dir.mkdir(parents=True, exist_ok=True)
        original_metrics = {
            "run_id": "run-0099",
            "status": "complete",
            "primary_score": "0.91",
            "timestamp": "2026-04-08T10:00:00Z",
        }
        (run_dir / "metrics.json").write_text(
            json.dumps(original_metrics, indent=2) + "\n",
            encoding="utf-8",
        )
        _add_row("run-0099", 0.91, 5100, 8400, status="complete")

        monkeypatch.setattr("sys.argv", ["meta_harness.py", "next-run", "--run-id", "run-0099", "--path"])
        result = main()

        assert result == 0
        assert capsys.readouterr().out.strip() == str(run_dir)
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        assert metrics == original_metrics
        rows = {row["run_id"]: row for row in read_frontier()}
        assert rows["run-0099"]["status"] == "complete"


class TestParallelRun:
    def test_reserves_multiple_ids(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "parallel-run", "--count", "3", "--json"])
        main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["count"] == 3
        assert len(data["run_ids"]) == 3
        assert data["run_ids"][0] != data["run_ids"][1]

    def test_rejects_non_positive_count(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "parallel-run", "--count", "0"])
        result = main()

        assert result == 1
        out = capsys.readouterr().out
        assert "count must be >= 1" in out

    def test_initializes_reserved_metrics(self, capsys, monkeypatch):
        from scripts.meta_harness import RUNS_DIR

        monkeypatch.setattr("sys.argv", ["meta_harness.py", "parallel-run", "--count", "2", "--json"])
        result = main()

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)

        for run_id in data["run_ids"]:
            metrics = json.loads((RUNS_DIR / run_id / "metrics.json").read_text(encoding="utf-8"))
            assert metrics["run_id"] == run_id
            assert metrics["status"] == "reserved"
            assert metrics["timestamp"]

    def test_records_reserved_rows_in_frontier(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "parallel-run", "--count", "2", "--json"])
        result = main()

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        rows = {row["run_id"]: row for row in read_frontier()}

        for run_id in data["run_ids"]:
            assert rows[run_id]["status"] == "reserved"
            assert rows[run_id]["timestamp"]


class TestCompactSummary:
    def test_empty_frontier(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "compact-summary"])
        main()
        out = capsys.readouterr().out
        assert "No runs recorded" in out

    def test_with_runs(self, capsys, monkeypatch):
        _add_row("run-0001", 0.72, 8500, 11000)
        _add_row("run-0002", 0.76, 8100, 10500)
        _add_row("run-0003", 0.68, 9000, 12000)
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "compact-summary"])
        main()
        out = capsys.readouterr().out
        assert "run-0002" in out
        assert "0.76" in out
        assert len(out) < 3000

    def test_output_is_valid_for_injection(self, capsys, monkeypatch):
        _add_row("run-0001", 0.72, 8500, 11000)
        monkeypatch.setattr("sys.argv", ["meta_harness.py", "compact-summary"])
        main()
        out = capsys.readouterr().out
        assert isinstance(out, str)
        assert len(out) > 0
