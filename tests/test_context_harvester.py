"""Tests for context_harvester.py — BM25, tokenizer, scoring, pipeline."""
import os
import tempfile
import pathlib
import pytest

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

    def test_snake_case_split(self):
        from scripts.context_harvester import tokenize
        tokens = tokenize("read_frontier_data")
        assert "read" in tokens
        assert "frontier" in tokens

    def test_markdown_stripped(self):
        from scripts.context_harvester import tokenize
        tokens = tokenize("## Heading\n```python\ncode here\n```")
        assert "heading" in tokens
        assert "code" in tokens

    def test_short_tokens_filtered(self):
        from scripts.context_harvester import tokenize
        tokens = tokenize("a b cd ef")
        assert "a" not in tokens
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
        assert scores[0][0] == 0

    def test_empty_query(self):
        from scripts.context_harvester import BM25, tokenize
        corpus = [tokenize("some text")]
        bm25 = BM25(corpus)
        assert bm25.score([], 0) == 0.0

    def test_idf_never_negative(self):
        from scripts.context_harvester import BM25, tokenize
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
        assert 5 <= result <= 15

    def test_budget_safe(self):
        from scripts.context_harvester import estimate_tokens
        text = "word " * 1500
        assert estimate_tokens(text) >= 1500


class TestRRF:
    def test_fuses_two_lists(self):
        from scripts.context_harvester import reciprocal_rank_fusion
        list1 = [("a", 10.0), ("b", 5.0), ("c", 1.0)]
        list2 = [("b", 10.0), ("c", 5.0), ("a", 1.0)]
        fused = reciprocal_rank_fusion(list1, list2, k=60)
        ids = [x[0] for x in fused]
        # b appears 1st and 1st → highest combined; a is 1st+3rd; c is 3rd+2nd
        # Actually: a is rank1 in list1 + rank3 in list2, b is rank2+rank1, c is rank3+rank2
        # b should rank highest (rank 2 in l1 + rank 1 in l2 = 1/62 + 1/61)
        # a: 1/61 + 1/63, b: 1/62 + 1/61, so a > b slightly... let me check
        # a: 1/61 + 1/63 = 0.01639 + 0.01587 = 0.03226
        # b: 1/62 + 1/61 = 0.01613 + 0.01639 = 0.03252
        # b > a, correct
        assert ids[0] == "b"


class TestHarvestPipeline:
    def test_harvest_on_current_project(self):
        from scripts.context_harvester import harvest
        # Run against the actual project directory
        result = harvest("C:/Code/Meta-Harness-YGN", "improve validation")
        assert "# Project Context" in result
        assert len(result) > 50

    def test_harvest_respects_budget(self):
        from scripts.context_harvester import harvest, estimate_tokens
        result = harvest("C:/Code/Meta-Harness-YGN", "test", budget=500)
        tokens = estimate_tokens(result)
        # Should be roughly within budget (with some overhead for headers)
        assert tokens < 700  # generous margin for formatting

    def test_harvest_nonexistent_dir(self):
        from scripts.context_harvester import harvest
        result = harvest("/nonexistent/path", "test")
        assert "No context" in result or "Project Context" in result


class TestImperativeExtraction:
    def test_extracts_must_rules(self):
        from scripts.context_harvester import extract_imperative_rules
        text = "Some intro text.\n- Must run tests before commit.\n- This is normal text.\n- Never edit application code."
        rules = extract_imperative_rules(text)
        assert len(rules) == 2
        assert "Must run tests" in rules[0]
        assert "Never edit" in rules[1]

    def test_ignores_short_lines(self):
        from scripts.context_harvester import extract_imperative_rules
        text = "Must do.\nAlways check things carefully before proceeding."
        rules = extract_imperative_rules(text)
        assert len(rules) == 1  # "Must do." is too short
