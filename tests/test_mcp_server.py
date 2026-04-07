"""Tests for mh_server.py — Phase 0: verify tools and resources exist."""
import os
import tempfile
import csv
import pathlib

import pytest

_tmp = tempfile.mkdtemp()
os.environ["MH_PLUGIN_DATA"] = _tmp
os.environ.setdefault("MH_PLUGIN_ROOT", str(pathlib.Path(__file__).resolve().parents[1]))

# Ensure frontier.tsv exists for import
data_dir = pathlib.Path(_tmp)
data_dir.mkdir(parents=True, exist_ok=True)
frontier_path = data_dir / "frontier.tsv"
with frontier_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, delimiter="\t")
    writer.writerow([
        "run_id", "status", "primary_score", "avg_latency_ms",
        "avg_input_tokens", "risk", "note", "timestamp",
    ])
    writer.writerow([
        "run-0001", "complete", "0.764", "8120",
        "11382", "low", "env bootstrap", "2026-04-07T00:00:00Z",
    ])


class TestMCPServerStructure:
    def test_server_imports(self):
        """Verify the server module can be imported."""
        try:
            import servers.mh_server as srv
            assert hasattr(srv, "mcp")
        except ImportError as e:
            if "mcp" in str(e):
                pytest.skip("mcp package not installed (optional dependency)")
            raise

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
