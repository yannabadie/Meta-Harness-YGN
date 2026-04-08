"""Repository structure and automation metadata tests."""
from __future__ import annotations

import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestCIWorkflow:
    def test_ci_workflow_exists_with_os_matrix(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        assert workflow.exists()
        content = workflow.read_text(encoding="utf-8")
        assert "ubuntu-latest" in content
        assert "windows-latest" in content
        assert "macos-latest" in content

    def test_ci_runs_validation_and_tests(self):
        workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"

        assert workflow.exists()
        content = workflow.read_text(encoding="utf-8")
        assert "python -m pytest tests -q" in content
        assert "python scripts/meta_harness.py validate" in content
