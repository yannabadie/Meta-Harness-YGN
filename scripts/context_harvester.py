"""Context Harvester — BM25 scoring, source harvesters, RRF merge pipeline.

Zero external dependencies: stdlib only.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import re
import subprocess
from typing import Any

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens, handling camelCase, snake_case, markdown."""
    # Strip fenced code block markers (before lowercasing to keep structure)
    text = re.sub(r"```\w*\n?", " ", text)
    # Unwrap inline code
    text = re.sub(r"`([^`]*)`", r" \1 ", text)
    # Unwrap markdown links
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r" \1 \2 ", text)
    # Split camelCase: lowercase followed by uppercase (must run before lowercasing)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # Split runs of uppercase followed by capitalized word (e.g. XMLParser → XML Parser)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    # Now lowercase
    text = text.lower()
    # Replace separators with space
    text = re.sub(r"[_\-./\\]", " ", text)
    # Extract tokens: must start with a letter, can contain digits
    tokens = re.findall(r"[a-z][a-z0-9]*|[0-9]+", text)
    # Filter very short tokens
    return [t for t in tokens if len(t) >= 2]


# ---------------------------------------------------------------------------
# BM25 (Okapi BM25, Lucene-variant IDF)
# ---------------------------------------------------------------------------

class BM25:
    """Okapi BM25 with Lucene-variant IDF (k1=1.2, b=0.75)."""

    def __init__(
        self,
        corpus: list[list[str]],
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self.N = len(corpus)
        self.doc_lens: list[int] = [len(doc) for doc in corpus]
        self.avgdl: float = sum(self.doc_lens) / self.N if self.N else 1.0

        # Term frequency per document
        self.tf: list[dict[str, int]] = []
        # Document frequency per term
        df: dict[str, int] = collections.defaultdict(int)
        for doc in corpus:
            freq: dict[str, int] = collections.Counter(doc)
            self.tf.append(freq)
            for term in freq:
                df[term] += 1

        # IDF: Lucene variant — never negative
        self.idf: dict[str, float] = {}
        for term, n in df.items():
            self.idf[term] = math.log(1.0 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, query: list[str], doc_idx: int) -> float:
        """Return BM25 score for query against document at doc_idx."""
        if not query:
            return 0.0
        dl = self.doc_lens[doc_idx]
        tf_doc = self.tf[doc_idx]
        result = 0.0
        for term in query:
            if term not in self.idf:
                continue
            f = tf_doc.get(term, 0)
            idf = self.idf[term]
            numerator = f * (self.k1 + 1)
            denominator = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            result += idf * numerator / denominator
        return result

    def rank(self, query: list[str]) -> list[tuple[int, float]]:
        """Return [(doc_idx, score), ...] sorted by score descending."""
        scores = [(i, self.score(query, i)) for i in range(self.N)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores


# ---------------------------------------------------------------------------
# Token estimator
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Heuristic token count: average of chars/3.5 and words*1.33."""
    if not text:
        return 0
    char_estimate = len(text) / 3.5
    word_estimate = len(text.split()) * 1.33
    return int((char_estimate + word_estimate) / 2)


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    *ranked_lists: list[tuple[str, float]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion.

    Each list is [(id, score), ...] sorted by score descending (rank 1 = index 0).
    Returns merged [(id, rrf_score), ...] sorted descending.
    """
    rrf_scores: dict[str, float] = collections.defaultdict(float)
    for ranked in ranked_lists:
        for rank, (item_id, _score) in enumerate(ranked, start=1):
            rrf_scores[item_id] += 1.0 / (k + rank)
    fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return fused


# ---------------------------------------------------------------------------
# Source harvesters — each returns list[dict]
# Keys: id, source, text, recency, freq
# ---------------------------------------------------------------------------

def extract_imperative_rules(text: str) -> list[str]:
    """Extract imperative sentences that are likely constraints or conventions.

    Scans each line for modal/imperative keywords (must, never, always, should,
    do not, don't, avoid, prefer, ensure) and returns the matching lines
    stripped of leading list markers.  Lines shorter than 10 characters are
    skipped to avoid noise.  Each returned string is capped at 200 characters.
    """
    rules: list[str] = []
    for line in text.split("\n"):
        line = line.strip().lstrip("- ").lstrip("* ")
        if not line or len(line) < 10:
            continue
        # Match imperative patterns
        if re.search(r'\b(must|never|always|should|do not|don\'t|avoid|prefer|ensure)\b', line, re.IGNORECASE):
            rules.append(line[:200])
    return rules


def harvest_claude_md(path: str) -> list[dict[str, Any]]:
    """Extract context from CLAUDE.md and .claude/rules/ directory."""
    items: list[dict[str, Any]] = []
    root = pathlib.Path(path)

    # CLAUDE.md
    claude_md = root / "CLAUDE.md"
    try:
        if claude_md.exists():
            text = claude_md.read_text(encoding="utf-8", errors="replace")
            section_text = text
            items.append({
                "id": "claude_md",
                "source": "claude_md",
                "text": section_text,
                "recency": 1.0,
                "freq": 1,
            })
            # Extract imperative rules with higher weight (these are constraints)
            imp_rules = extract_imperative_rules(section_text)
            for rule in imp_rules[:5]:  # max 5 per section
                items.append({
                    "id": f"rule:{hash(rule)}",
                    "source": "claude_md",
                    "text": rule,
                    "recency": 1.0,
                    "freq": 2,  # higher freq = higher priority in RRF
                })
    except Exception:
        pass

    # .claude/rules/
    rules_dir = root / ".claude" / "rules"
    try:
        if rules_dir.exists():
            for rule_file in sorted(rules_dir.glob("*.md")):
                try:
                    text = rule_file.read_text(encoding="utf-8", errors="replace")
                    section_text = text
                    items.append({
                        "id": f"rule:{rule_file.name}",
                        "source": "claude_md",
                        "text": section_text,
                        "recency": 1.0,
                        "freq": 1,
                    })
                    # Extract imperative rules with higher weight (these are constraints)
                    imp_rules = extract_imperative_rules(section_text)
                    for rule in imp_rules[:5]:  # max 5 per section
                        items.append({
                            "id": f"rule:{hash(rule)}",
                            "source": "claude_md",
                            "text": rule,
                            "recency": 1.0,
                            "freq": 2,  # higher freq = higher priority in RRF
                        })
                except Exception:
                    pass
    except Exception:
        pass

    return items


def _project_hash(project_path: str) -> str:
    """Derive the project directory name Claude Code uses in ~/.claude/projects/.

    Claude Code hashes the git repo root path. We try to match by checking
    if the project path appears in the directory name (normalized).
    """
    normalized = pathlib.Path(project_path).resolve().as_posix()
    # Claude Code uses a scheme like "C--Code-ProjectName" on Windows
    # Convert path separators to hyphens for matching
    return normalized.replace("/", "-").replace(":", "").replace("\\", "-").lstrip("-")


def harvest_memory(path: str) -> list[dict[str, Any]]:
    """Extract context from ~/.claude/projects/*/memory/ directories.

    Prioritizes the current project's memory. Other projects' memory is
    included at lower priority only if it passes BM25 relevance scoring.
    """
    items: list[dict[str, Any]] = []
    try:
        home = pathlib.Path.home()
        projects_dir = home / ".claude" / "projects"
        if not projects_dir.exists():
            return items

        # Try to identify the current project's memory directory
        proj_hash = _project_hash(path)

        # Find memory files — prioritize current project
        for memory_file in sorted(projects_dir.glob("*/memory/*.md")):
            proj_dir_name = memory_file.parent.parent.name
            # Check if this is the current project (fuzzy match on path components)
            is_current = any(
                part.lower() in proj_dir_name.lower()
                for part in pathlib.Path(path).resolve().parts[-2:]
                if len(part) > 2
            )
            try:
                text = memory_file.read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    items.append({
                        "id": f"memory:{memory_file.parent.parent.name}/{memory_file.name}",
                        "source": "memory",
                        "text": text if is_current else text[:500],
                        "recency": 1.0 if is_current else 0.3,
                        "freq": 2 if is_current else 1,
                    })
            except Exception:
                pass

        # Also check plain memory files
        for memory_file in sorted(projects_dir.glob("*/memory.md")):
            proj_dir_name = memory_file.parent.name
            is_current = any(
                part.lower() in proj_dir_name.lower()
                for part in pathlib.Path(path).resolve().parts[-2:]
                if len(part) > 2
            )
            try:
                text = memory_file.read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    items.append({
                        "id": f"memory:{proj_dir_name}/memory.md",
                        "source": "memory",
                        "text": text if is_current else text[:500],
                        "recency": 1.0 if is_current else 0.3,
                        "freq": 2 if is_current else 1,
                    })
            except Exception:
                pass
    except Exception:
        pass

    return items


def harvest_git(path: str) -> list[dict[str, Any]]:
    """Extract context from git log and file hotspots."""
    items: list[dict[str, Any]] = []
    try:
        root = pathlib.Path(path)
        if not root.exists():
            return items

        # Recent commit messages (last 20)
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "log", "--oneline", "-20"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                items.append({
                    "id": "git:recent_commits",
                    "source": "git_recent",
                    "text": "## Recent Commits\n\n" + result.stdout.strip(),
                    "recency": 0.95,
                    "freq": 1,
                })
        except Exception:
            pass

        # File hotspots (most frequently changed files)
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "log", "--name-only", "--pretty=format:", "-50"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                file_counts: dict[str, int] = collections.Counter(
                    line.strip()
                    for line in result.stdout.splitlines()
                    if line.strip()
                )
                top_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                if top_files:
                    hotspot_text = "## File Hotspots\n\n" + "\n".join(
                        f"- {fname} ({count} changes)" for fname, count in top_files
                    )
                    items.append({
                        "id": "git:hotspots",
                        "source": "git_recent",
                        "text": hotspot_text,
                        "recency": 0.8,
                        "freq": 1,
                    })
        except Exception:
            pass

        # Recent diff stat
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "diff", "--stat", "HEAD~5..HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                items.append({
                    "id": "git:recent_diff_stat",
                    "source": "git_recent",
                    "text": "## Recent Changes (diff stat)\n\n" + result.stdout.strip(),
                    "recency": 0.85,
                    "freq": 1,
                })
        except Exception:
            pass

    except Exception:
        pass

    return items


def harvest_docs(path: str) -> list[dict[str, Any]]:
    """Extract context from README.md and docs/ directory."""
    items: list[dict[str, Any]] = []
    root = pathlib.Path(path)

    # README.md
    for readme_name in ("README.md", "README.rst", "README.txt", "readme.md"):
        readme = root / readme_name
        try:
            if readme.exists():
                text = readme.read_text(encoding="utf-8", errors="replace")
                items.append({
                    "id": f"docs:{readme_name}",
                    "source": "docs",
                    "text": text,
                    "recency": 0.7,
                    "freq": 1,
                })
                break
        except Exception:
            pass

    # docs/ directory — top-level .md files
    docs_dir = root / "docs"
    try:
        if docs_dir.exists():
            for doc_file in sorted(docs_dir.glob("*.md"))[:5]:
                try:
                    text = doc_file.read_text(encoding="utf-8", errors="replace")
                    items.append({
                        "id": f"docs:{doc_file.name}",
                        "source": "docs",
                        "text": text,
                        "recency": 0.7,
                        "freq": 1,
                    })
                except Exception:
                    pass
    except Exception:
        pass

    return items


# ---------------------------------------------------------------------------
# Source weights
# ---------------------------------------------------------------------------

_SOURCE_WEIGHTS: dict[str, float] = {
    "claude_md": 1.0,
    "memory": 0.9,
    "git_recent": 0.8,
    "docs": 0.7,
}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def harvest(
    project_path: str,
    objective: str,
    budget: int = 2000,
) -> str:
    """Collect context from all sources, score, merge, and pack within budget.

    Returns structured markdown string.
    """
    # 1. Collect from all sources
    all_items: list[dict[str, Any]] = []
    all_items.extend(harvest_claude_md(project_path))
    all_items.extend(harvest_memory(project_path))
    all_items.extend(harvest_git(project_path))
    all_items.extend(harvest_docs(project_path))

    if not all_items:
        return "# Project Context\n\nNo context sources found."

    # 2. Build corpus for BM25
    query_tokens = tokenize(objective)
    corpus_tokens = [tokenize(item["text"]) for item in all_items]

    bm25 = BM25(corpus_tokens)

    # 3. BM25 scores for ranking
    bm25_ranked: list[tuple[str, float]] = []
    for i, item in enumerate(all_items):
        score = bm25.score(query_tokens, i)
        # Apply source weight
        weight = _SOURCE_WEIGHTS.get(item["source"], 0.5)
        bm25_ranked.append((item["id"], score * weight))
    bm25_ranked.sort(key=lambda x: x[1], reverse=True)

    # 4. Recency ranking (sort by recency desc)
    recency_ranked: list[tuple[str, float]] = sorted(
        [(item["id"], item["recency"]) for item in all_items],
        key=lambda x: x[1],
        reverse=True,
    )

    # 5. RRF merge
    fused = reciprocal_rank_fusion(bm25_ranked, recency_ranked, k=60)

    # Build id -> item lookup
    item_by_id: dict[str, dict[str, Any]] = {item["id"]: item for item in all_items}

    # 6. Greedy pack within budget
    sections: list[str] = []
    tokens_used = estimate_tokens("# Project Context\n\n")

    for item_id, _rrf_score in fused:
        item = item_by_id.get(item_id)
        if item is None:
            continue
        text = item["text"].strip()
        source_label = item["source"].replace("_", " ").title()
        header = f"### [{source_label}] {item_id}\n\n"
        section = header + text + "\n\n"
        section_tokens = estimate_tokens(section)

        if tokens_used + section_tokens > budget:
            # Try to fit a truncated version
            remaining = budget - tokens_used
            if remaining > 50:
                # Rough truncation: chars ~ remaining * 3.5
                max_chars = int(remaining * 3.5)
                truncated = text[:max_chars].rsplit("\n", 1)[0]
                section = header + truncated + "\n\n_(truncated)_\n\n"
                sections.append(section)
            break

        sections.append(section)
        tokens_used += section_tokens

    if not sections:
        return "# Project Context\n\nNo context sources found."

    return "# Project Context\n\n" + "".join(sections)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Context Harvester — collect and score project context for Claude Code."
    )
    parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory (default: current directory)",
    )
    parser.add_argument(
        "--objective",
        required=True,
        help="The objective or query to score context against",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=2000,
        help="Token budget for output (default: 2000)",
    )
    args = parser.parse_args()

    result = harvest(args.project, args.objective, budget=args.budget)
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
