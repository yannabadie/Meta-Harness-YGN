"""Tests for mh_server.py — Phase 0: verify tools and resources exist."""
import asyncio
import builtins
import importlib
import json
import os
import tempfile
import csv
import pathlib
import sys

import pytest

_tmp = tempfile.mkdtemp()
os.environ["MH_PLUGIN_DATA"] = _tmp
os.environ.setdefault("MH_PLUGIN_ROOT", str(pathlib.Path(__file__).resolve().parents[1]))

# Ensure frontier.tsv exists for import
data_dir = pathlib.Path(_tmp)
data_dir.mkdir(parents=True, exist_ok=True)
frontier_path = data_dir / "frontier.tsv"
from scripts.config import TSV_HEADER
with frontier_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, delimiter="\t")
    writer.writerow(TSV_HEADER)
    writer.writerow({
        "run_id": "run-0001",
        "status": "complete",
        "primary_score": "0.764",
        "avg_latency_ms": "8120",
        "avg_input_tokens": "11382",
        "risk": "low",
        "note": "env bootstrap",
        "timestamp": "2026-04-07T00:00:00Z",
    }.get(k, "") for k in TSV_HEADER)


class TestMCPServerStructure:
    @staticmethod
    def _import_server(monkeypatch: pytest.MonkeyPatch, *, missing_mcp: bool = False):
        sys.modules.pop("servers.mh_server", None)
        if missing_mcp:
            real_import = builtins.__import__

            def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == "mcp.server.fastmcp":
                    raise ImportError("mcp not installed")
                return real_import(name, globals, locals, fromlist, level)

            monkeypatch.setattr(builtins, "__import__", fake_import)
        return importlib.import_module("servers.mh_server")

    def test_server_imports(self):
        """Verify the server module can be imported."""
        try:
            import servers.mh_server as srv
            assert hasattr(srv, "mcp")
        except ImportError as e:
            if "mcp" in str(e).lower():
                pytest.skip("mcp package not installed (optional dependency)")
            raise

    def test_import_without_mcp_uses_stub(self, monkeypatch):
        srv = self._import_server(monkeypatch, missing_mcp=True)

        assert srv.FastMCP is None
        assert hasattr(srv.mcp, "tool")
        assert hasattr(srv.mcp, "resource")

    def test_run_server_requires_mcp_only_at_runtime(self, monkeypatch):
        srv = self._import_server(monkeypatch, missing_mcp=True)

        with pytest.raises(RuntimeError, match="mcp package required"):
            srv.run_server()

    def test_frontier_read_tool_exists(self):
        try:
            from servers.mh_server import frontier_read
            assert callable(frontier_read)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise

    def test_dashboard_resource_exists(self):
        try:
            from servers.mh_server import dashboard
            assert callable(dashboard)
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed")
            raise


class TestNewTools:
    def test_frontier_record_exists(self):
        try:
            from servers.mh_server import frontier_record
            assert callable(frontier_record)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise

    def test_trace_search_exists(self):
        try:
            from servers.mh_server import trace_search
            assert callable(trace_search)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise

    def test_candidate_diff_exists(self):
        try:
            from servers.mh_server import candidate_diff
            assert callable(candidate_diff)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise

    def test_plugin_scan_exists(self):
        try:
            from servers.mh_server import plugin_scan
            assert callable(plugin_scan)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise

    def test_frontier_record_persists_extended_metrics(self):
        from servers.mh_server import RUNS_DIR, frontier_record

        asyncio.run(frontier_record(
            run_id="run-0090",
            primary_score="0.88",
            avg_latency_ms="7000",
            avg_input_tokens="9800",
            risk="low",
            note="server metadata",
            status="complete",
            consistency="0.71",
            instruction_adherence="4.1",
            tool_efficiency="11",
            error_count="0",
            sample_size="6",
            eval_method="deterministic+llm",
            deterministic_score="0.91",
            llm_judge_score="0.80",
            evaluation_verdict="accepted",
            report_verdict="PROMOTE",
            benchmark_version="2026-04-09",
            baseline_run_id="run-0001",
            seed="7",
        ))

        metrics_path = RUNS_DIR / "run-0090" / "metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert metrics["metrics_schema_version"] == "2"
        assert metrics["eval_method"] == "deterministic+llm"
        assert metrics["report_verdict"] == "PROMOTE"


class TestNewResources:
    def test_traces_resource_exists(self):
        try:
            from servers.mh_server import traces_for_run
            assert callable(traces_for_run)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise

    def test_regressions_resource_exists(self):
        try:
            from servers.mh_server import regressions_resource
            assert callable(regressions_resource)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise


class TestContextEngine:
    def test_context_harvest_tool_exists(self):
        try:
            from servers.mh_server import context_harvest
            assert callable(context_harvest)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise

    def test_context_resource_exists(self):
        try:
            from servers.mh_server import context_resource
            assert callable(context_resource)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise


class TestEvalIntegration:
    def test_eval_run_tool_exists(self):
        try:
            from servers.mh_server import eval_run
            assert callable(eval_run)
        except ImportError as e:
            if "mcp" in str(e): pytest.skip("mcp not installed")
            raise
