# Phase 2: Context Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the context harvester that extracts, scores, and compacts project context from CLAUDE.md, memory files, git history, docs, and installed plugins into a <2000-token structured summary.

**Architecture:** New module `scripts/context_harvester.py` (pure stdlib) implements BM25 scoring, source harvesters, and RRF merge. MCP server exposes `context_harvest` tool and `harness://context` resource. New `context-harvester` agent definition. `harness-evolve` skill updated to inject harvested context.

**Tech Stack:** Python 3.10+ (stdlib only — math, re, collections, csv, json, subprocess, pathlib).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scripts/context_harvester.py` | BM25, tokenizer, harvesters, scoring, compaction |
| Create | `tests/test_context_harvester.py` | Tests for all harvester components |
| Create | `agents/context-harvester.md` | Agent definition |
| Create | `bin/mh-context` | CLI wrapper for context harvesting |
| Modify | `servers/mh_server.py` | Add context_harvest tool + harness://context resource |
| Modify | `skills/harness-evolve/SKILL.md` | Inject harvested context in HARVEST phase |
| Modify | `tests/test_mcp_server.py` | Tests for new MCP tool + resource |

---

### Task 1: BM25 Scorer + Tokenizer (TDD)

**Files:**
- Create: `scripts/context_harvester.py`
- Create: `tests/test_context_harvester.py`

- [ ] **Step 1: Create test file**

Create `tests/test_context_harvester.py`:

```python
"""Tests for context_harvester.py — BM25, tokenizer, scoring."""
import os
import tempfile
import pathlib

import pytest

# Set up test environment
_tmp = tempfile.mkdtemp()


class TestTokenizer:
    def test_basic_words(self):
        from scripts.context_harvester import tokenize
        tokens = tokenize("Hello world")
        assert "hello" in tokens
        assert "world" in tokens

    def test_camel_case_split(self):
        from scripts.context_harvester import tokenize
        tokens = tokenize("getDocFreq")
        assert "get" in tokens
        assert "doc" in tokens
        assert "freq" in tokens

    def test_snake_case_split(self):
        from scripts.context_harvester import tokenize
        tokens = tokenize("read_frontier_data")
        assert "read" in tokens
        assert "frontier" in tokens
        assert "data" in tokens

    def test_markdown_stripped(self):
        from scripts.context_harvester import tokenize
        tokens = tokenize("## Heading\n```python\ncode here\n```")
        assert "heading" in tokens
        assert "code" in tokens

    def test_short_tokens_filtered(self):
        from scripts.context_harvester import tokenize
        tokens = tokenize("a b cd ef")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "cd" in tokens


class TestBM25:
    def test_relevant_doc_scores_higher(self):
        from scripts.context_harvester import BM25, tokenize
        corpus = [
            tokenize("validation rules for refactoring"),
            tokenize("git commit history and branches"),
            tokenize("database migration scripts"),
        ]
        bm25 = BM25(corpus)
        query = tokenize("validation refactoring")
        scores = [(i, bm25.score(query, i)) for i in range(3)]
        scores.sort(key=lambda x: x[1], reverse=True)
        assert scores[0][0] == 0  # validation doc ranks first

    def test_empty_query(self):
        from scripts.context_harvester import BM25, tokenize
        corpus = [tokenize("some text")]
        bm25 = BM25(corpus)
        score = bm25.score([], 0)
        assert score == 0.0

    def test_idf_never_negative(self):
        from scripts.context_harvester import BM25, tokenize
        # Term appears in all documents
        corpus = [tokenize("common word"), tokenize("common thing")]
        bm25 = BM25(corpus)
        for v in bm25.idf.values():
            assert v >= 0.0


class TestEstimateTokens:
    def test_empty(self):
        from scripts.context_harvester import estimate_tokens
        assert estimate_tokens("") == 0

    def test_short_text(self):
        from scripts.context_harvester import estimate_tokens
        result = estimate_tokens("Hello world, this is a test.")
        assert 5 <= result <= 15  # reasonable range

    def test_budget_safe(self):
        from scripts.context_harvester import estimate_tokens
        # 2000 tokens ~ 7000 chars; make sure we don't underestimate
        text = "word " * 1500  # ~1500 words
        result = estimate_tokens(text)
        assert result >= 1500  # at least 1 token per word
```

- [ ] **Step 2: Run tests — should FAIL**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_context_harvester.py -v
```

- [ ] **Step 3: Implement BM25, tokenizer, and token estimator**

Create `scripts/context_harvester.py`:

```python
#!/usr/bin/env python3
"""Context harvester for Meta-Harness — extracts, scores, and compacts project context.

Zero external dependencies. Uses BM25 scoring + Reciprocal Rank Fusion.
"""
from __future__ import annotations

import math
import re
import subprocess
import json
import pathlib
from collections import Counter
from typing import Any


# ── Tokenizer ────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """Tokenize code-mixed text (markdown + code) for BM25."""
    text = text.lower()
    text = re.sub(r"```\w*\n?", " ", text)
    text = re.sub(r"`([^`]*)`", r" \1 ", text)
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r" \1 \2 ", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"[_\-./\\]", " ", text)
    tokens = re.findall(r"[a-z][a-z0-9]*|[0-9]+", text)
    return [t for t in tokens if len(t) >= 2]


# ── BM25 ─────────────────────────────────────────────────────────

class BM25:
    """Okapi BM25 scorer. Lucene-variant IDF (always non-negative)."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lens = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_lens) / self.corpus_size if self.corpus_size else 1.0
        self.doc_freqs: list[Counter] = [Counter(doc) for doc in corpus]
        self.df: dict[str, int] = {}
        for tf in self.doc_freqs:
            for term in tf:
                self.df[term] = self.df.get(term, 0) + 1
        self.idf: dict[str, float] = {}
        for term, freq in self.df.items():
            self.idf[term] = math.log(
                1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5)
            )

    def score(self, query: list[str], doc_idx: int) -> float:
        s = 0.0
        dl = self.doc_lens[doc_idx]
        tf_doc = self.doc_freqs[doc_idx]
        for q in query:
            if q not in self.idf:
                continue
            tf = tf_doc.get(q, 0)
            numer = tf * (self.k1 + 1.0)
            denom = tf + self.k1 * (1.0 - self.b + self.b * dl / self.avgdl)
            s += self.idf[q] * numer / denom
        return s


# ── Token estimation ─────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Estimate LLM token count. Mixed markdown+code: ~3.5 chars/token."""
    if not text:
        return 0
    char_est = len(text) / 3.5
    word_est = len(text.split()) * 1.33
    return int((char_est + word_est) / 2.0 + 0.5)


# ── Reciprocal Rank Fusion ───────────────────────────────────────

def reciprocal_rank_fusion(
    *ranked_lists: list[tuple[str, float]], k: int = 60
) -> list[tuple[str, float]]:
    """RRF merge of multiple ranked lists. Returns [(id, score)] descending."""
    scores: dict[str, float] = {}
    for ranked_list in ranked_lists:
        for rank_0, (doc_id, _) in enumerate(ranked_list):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank_0 + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ── Source Harvesters ────────────────────────────────────────────

def _read_file_safe(path: pathlib.Path, max_chars: int = 50000) -> str:
    """Read a file, returning empty string on any error."""
    try:
        return path.read_text(encoding="utf-8")[:max_chars]
    except Exception:
        return ""


def harvest_claude_md(project_path: pathlib.Path) -> list[dict[str, Any]]:
    """Extract context items from CLAUDE.md and .claude/rules/."""
    items = []
    for name in ["CLAUDE.md", ".claude/CLAUDE.md"]:
        p = project_path / name
        if p.exists():
            content = _read_file_safe(p)
            sections = re.split(r"(?m)^##\s+", content)
            for section in sections:
                if not section.strip():
                    continue
                items.append({
                    "id": f"claude_md:{hash(section[:100])}",
                    "source": "claude_md",
                    "text": section.strip()[:1000],
                    "recency": 1.0,
                    "freq": 1,
                })
    # Rules
    rules_dir = project_path / ".claude" / "rules"
    if rules_dir.exists():
        for rule_file in rules_dir.glob("*.md"):
            content = _read_file_safe(rule_file)
            if content.strip():
                items.append({
                    "id": f"rule:{rule_file.name}",
                    "source": "claude_md",
                    "text": content.strip()[:1000],
                    "recency": 1.0,
                    "freq": 1,
                })
    return items


def harvest_memory(project_path: pathlib.Path) -> list[dict[str, Any]]:
    """Extract context from Claude Code auto-memory."""
    items = []
    projects_dir = pathlib.Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return items
    # Scan all project memory directories for MEMORY.md files
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        memory_dir = proj_dir / "memory"
        if not memory_dir.exists():
            continue
        memory_md = memory_dir / "MEMORY.md"
        if memory_md.exists():
            content = _read_file_safe(memory_md)
            if content.strip():
                items.append({
                    "id": f"memory:{proj_dir.name}:index",
                    "source": "memory",
                    "text": content[:2000],
                    "recency": 0.9,
                    "freq": 1,
                })
        # Topic files
        for topic_file in memory_dir.glob("*.md"):
            if topic_file.name == "MEMORY.md":
                continue
            content = _read_file_safe(topic_file)
            if content.strip():
                items.append({
                    "id": f"memory:{proj_dir.name}:{topic_file.stem}",
                    "source": "memory",
                    "text": content[:1000],
                    "recency": 0.7,
                    "freq": 1,
                })
    return items


def harvest_git(project_path: pathlib.Path, n_commits: int = 50) -> list[dict[str, Any]]:
    """Extract patterns from git history."""
    items = []
    try:
        log = subprocess.run(
            ["git", "log", f"--oneline", f"-{n_commits}", "--format=%s"],
            capture_output=True, text=True, cwd=str(project_path), timeout=10,
        )
        if log.returncode != 0:
            return items
        messages = log.stdout.strip().split("\n")
        if messages and messages[0]:
            items.append({
                "id": "git:recent_commits",
                "source": "git_recent",
                "text": "Recent commits: " + "; ".join(messages[:20]),
                "recency": 1.0,
                "freq": len(messages),
            })
    except Exception:
        pass

    # File hotspots
    try:
        hotspot = subprocess.run(
            ["git", "log", "--format=format:", "--name-only", f"-{n_commits}"],
            capture_output=True, text=True, cwd=str(project_path), timeout=10,
        )
        if hotspot.returncode == 0:
            files = [f for f in hotspot.stdout.strip().split("\n") if f.strip()]
            counts = Counter(files)
            top = counts.most_common(10)
            if top:
                hotspot_text = "High-churn files: " + ", ".join(
                    f"{f} ({c}x)" for f, c in top
                )
                items.append({
                    "id": "git:hotspots",
                    "source": "git_recent",
                    "text": hotspot_text,
                    "recency": 0.8,
                    "freq": sum(c for _, c in top),
                })
    except Exception:
        pass

    return items


def harvest_docs(project_path: pathlib.Path) -> list[dict[str, Any]]:
    """Extract context from README and docs/."""
    items = []
    readme = project_path / "README.md"
    if readme.exists():
        content = _read_file_safe(readme)
        # Extract first 2 sections
        sections = re.split(r"(?m)^##\s+", content)[:3]
        for section in sections:
            if section.strip():
                items.append({
                    "id": f"docs:readme:{hash(section[:50])}",
                    "source": "docs",
                    "text": section.strip()[:800],
                    "recency": 0.5,
                    "freq": 1,
                })
    return items


# ── Main Pipeline ────────────────────────────────────────────────

SOURCE_WEIGHTS = {
    "claude_md": 1.0,
    "memory": 0.9,
    "git_recent": 0.8,
    "docs": 0.7,
    "plugins": 0.6,
    "git_old": 0.5,
}


def harvest(project_path: str | pathlib.Path, objective: str, budget: int = 2000) -> str:
    """Main entry point. Returns structured markdown <budget tokens."""
    project_path = pathlib.Path(project_path)
    items: list[dict[str, Any]] = []
    items.extend(harvest_claude_md(project_path))
    items.extend(harvest_memory(project_path))
    items.extend(harvest_git(project_path))
    items.extend(harvest_docs(project_path))

    if not items:
        return "# Project Context\n\nNo context sources found."

    # SCORE
    corpus_tokens = [tokenize(item["text"]) for item in items]
    query_tokens = tokenize(objective)
    bm25 = BM25(corpus_tokens)

    bm25_ranked = [
        (item["id"], bm25.score(query_tokens, i))
        for i, item in enumerate(items)
    ]
    bm25_ranked.sort(key=lambda x: x[1], reverse=True)

    recency_ranked = [
        (item["id"], item.get("recency", 0.0))
        for item in items
    ]
    recency_ranked.sort(key=lambda x: x[1], reverse=True)

    fused = reciprocal_rank_fusion(bm25_ranked, recency_ranked, k=60)

    item_by_id = {item["id"]: item for item in items}
    weighted = []
    for doc_id, rrf_score in fused:
        item = item_by_id.get(doc_id)
        if not item:
            continue
        sw = SOURCE_WEIGHTS.get(item.get("source", "docs"), 0.5)
        weighted.append({"item": item, "score": rrf_score * sw})

    # COMPACT
    lines = ["# Project Context", ""]
    tokens_used = 10
    for entry in weighted:
        text = entry["item"]["text"]
        line = f"- [{entry['item']['source']}] {text}"
        est = estimate_tokens(line)
        if tokens_used + est > budget:
            break
        lines.append(line)
        tokens_used += est

    lines.append(f"\n_({tokens_used} est. tokens from {len(items)} sources)_")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    p = argparse.ArgumentParser(prog="context_harvester")
    p.add_argument("--project", default=".")
    p.add_argument("--objective", default="general harness optimization")
    p.add_argument("--budget", type=int, default=2000)
    args = p.parse_args()
    print(harvest(args.project, args.objective, args.budget))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests — should PASS**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/test_context_harvester.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/context_harvester.py tests/test_context_harvester.py
git commit -m "feat: add context harvester with BM25 scoring, source harvesters, and RRF merge"
```

---

### Task 2: CLI Wrapper + MCP Integration

**Files:**
- Create: `bin/mh-context`
- Modify: `servers/mh_server.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Create bin/mh-context**

```bash
#!/usr/bin/env bash
set -euo pipefail
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/context_harvester.py" "$@"
```

- [ ] **Step 2: Add MCP tool and resource tests**

Append to `tests/test_mcp_server.py`:

```python
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
```

- [ ] **Step 3: Add tool and resource to mh_server.py**

Add at the end, before `if __name__`:

```python
@mcp.tool()
async def context_harvest(objective: str = "general harness optimization", budget: int = 2000) -> str:
    """Harvest project context — extracts from CLAUDE.md, memory, git, docs, plugins.

    Returns structured markdown scored by relevance to the objective, within token budget.

    Args:
        objective: What you're trying to optimize (used for BM25 relevance scoring).
        budget: Maximum estimated tokens for the output.
    """
    import sys
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from context_harvester import harvest
    return harvest(str(PLUGIN_ROOT), objective, budget)


@mcp.resource("harness://context")
async def context_resource() -> str:
    """Aggregated project context — CLAUDE.md, memory, git patterns, docs."""
    import sys
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from context_harvester import harvest
    return harvest(str(PLUGIN_ROOT), "general harness optimization", 2000)
```

- [ ] **Step 4: Run tests — should PASS**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add bin/mh-context servers/mh_server.py tests/test_mcp_server.py
git commit -m "feat: add context_harvest MCP tool, harness://context resource, mh-context CLI"
```

---

### Task 3: Context-Harvester Agent + Evolve Skill Update

**Files:**
- Create: `agents/context-harvester.md`
- Modify: `skills/harness-evolve/SKILL.md`

- [ ] **Step 1: Create agent definition**

Create `agents/context-harvester.md`:

```markdown
---
name: context-harvester
description: Extract and structure project context from CLAUDE.md, memory, git history, docs, and installed plugins for harness optimization.
model: haiku
effort: low
maxTurns: 5
disallowedTools: Write, Edit, MultiEdit
---
You are a context harvester for Meta-Harness harness optimization.

Your job is to gather and structure project context so the harness-proposer
has the best possible understanding of the project before making changes.

Use the context_harvest MCP tool to extract context, then summarize
the most relevant findings for the given optimization objective.

Focus on:
1. Constraints and conventions from CLAUDE.md and rules
2. Recent development patterns from git history
3. Project memory and accumulated insights
4. Installed plugins and their harness surfaces
5. Architecture and design decisions from docs

Output a structured summary under 2000 tokens.
```

- [ ] **Step 2: Update harness-evolve skill**

In `skills/harness-evolve/SKILL.md`, add the HARVEST phase. After the `## Dynamic context: current frontier` block and before `## Required workflow`, insert:

```markdown
## Dynamic context: project context
```!
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/context_harvester.py --project . --objective "$ARGUMENTS"
```
```

- [ ] **Step 3: Commit**

```bash
git add agents/context-harvester.md skills/harness-evolve/SKILL.md
git commit -m "feat: add context-harvester agent, integrate context into harness-evolve skill"
```

---

### Task 4: Integration Test + Tag v0.3.0

- [ ] **Step 1: Run all tests**

```bash
cd C:/Code/Meta-Harness-YGN && python -m pytest tests/ -v
```

- [ ] **Step 2: Test context harvester CLI**

```bash
cd C:/Code/Meta-Harness-YGN && python scripts/context_harvester.py --project . --objective "improve validation"
```

Expected: Structured markdown with context items from CLAUDE.md, git, etc.

- [ ] **Step 3: Verify MCP server starts**

```bash
cd C:/Code/Meta-Harness-YGN && timeout 2 python servers/mh_server.py 2>&1; echo "Exit: $?"
```

- [ ] **Step 4: Tag and push**

```bash
cd C:/Code/Meta-Harness-YGN && git tag -a v0.3.0 -m "Phase 2: Context engine — BM25 harvester, 6 MCP tools, 4 MCP resources" && git push origin master --tags
```
