"""Tests for research.py: context size parsing, trimming, view transforms."""

import pytest
from unittest.mock import patch, MagicMock
from research import _parse_context_size, apply_context_trimming, apply_view, run_multi_query


class TestParseContextSize:
    def test_k_suffix(self):
        assert _parse_context_size("8k") == 8000
        assert _parse_context_size("32k") == 32000

    def test_uppercase_k(self):
        assert _parse_context_size("4K") == 4000

    def test_raw_number(self):
        assert _parse_context_size("16000") == 16000

    def test_empty_string(self):
        assert _parse_context_size("") is None

    def test_none(self):
        assert _parse_context_size(None) is None

    def test_whitespace(self):
        assert _parse_context_size(" 8k ") == 8000


class TestApplyContextTrimming:
    def test_trims_to_budget(self):
        data = {
            "results": [
                {"passages": ["A" * 1000, "B" * 1000, "C" * 1000]}
            ]
        }
        # 100 tokens → ~280 chars budget at 70%
        result = apply_context_trimming(data, 100)
        assert len(result["results"][0]["passages"]) < 3

    def test_no_trim_when_under_budget(self):
        data = {"results": [{"passages": ["short passage"]}]}
        result = apply_context_trimming(data, 8000)
        assert len(result["results"][0]["passages"]) == 1

    def test_empty_results(self):
        data = {"results": []}
        result = apply_context_trimming(data, 8000)
        assert result == data

    def test_no_context_tokens(self):
        data = {"results": [{"passages": ["a", "b", "c"]}]}
        result = apply_context_trimming(data, None)
        assert len(result["results"][0]["passages"]) == 3

    def test_multiple_documents(self):
        data = {
            "results": [
                {"passages": ["A" * 500, "B" * 500]},
                {"passages": ["C" * 500, "D" * 500]},
            ]
        }
        # Budget allows ~2 passages
        result = apply_context_trimming(data, 200)
        total_passages = sum(len(doc["passages"]) for doc in result["results"])
        assert total_passages < 4

    def test_metadata_added(self):
        data = {"results": [{"passages": ["a", "b", "c"]}]}
        result = apply_context_trimming(data, 8000)
        assert "context_budget" in result
        assert "context_trimmed" in result


class TestApplyView:
    def test_coverage_view(self):
        data = {
            "results": [
                {"total_passages": 10, "passages": ["a", "b", "c"]},
                {"total_passages": 5, "passages": ["x", "y", "z", "w", "v"]},
            ]
        }
        result = apply_view(data, "coverage")
        assert result["results"][0]["coverage_pct"] == 30
        assert result["results"][1]["coverage_pct"] == 100
        assert result["coverage_summary"]["fully_read"] == 1
        assert result["coverage_summary"]["partial"] == 1
        assert result["coverage_summary"]["total_docs"] == 2

    def test_coverage_view_zero_passages(self):
        data = {
            "results": [
                {"total_passages": 0, "passages": []},
            ]
        }
        result = apply_view(data, "coverage")
        assert result["results"][0]["coverage_pct"] == 0

    def test_llm_view(self):
        data = {
            "results": [
                {
                    "total_passages": 3,
                    "passages": [
                        "[COMBAT]\nDragon attacks with claws.",
                        "Plain passage without heading.",
                        "[MAGIC]\nFireball explodes.",
                    ],
                }
            ]
        }
        result = apply_view(data, "llm")
        passages = result["results"][0]["passages"]
        assert isinstance(passages[0], dict)
        assert passages[0]["section"] == "COMBAT"
        assert "Dragon attacks" in passages[0]["text"]
        assert passages[1]["section"] == ""
        assert passages[2]["section"] == "MAGIC"
        assert result["results"][0]["coverage_pct"] == 100

    def test_llm_view_empty_passages(self):
        data = {"results": [{"total_passages": 0, "passages": []}]}
        result = apply_view(data, "llm")
        assert result["results"][0]["passages"] == []

    def test_default_view_noop(self):
        data = {
            "results": [
                {"total_passages": 5, "passages": ["a", "b"]},
            ]
        }
        result = apply_view(data, "default")
        assert result == data

    def test_unknown_view_noop(self):
        data = {"results": [{"total_passages": 1, "passages": ["x"]}]}
        result = apply_view(data, "nonexistent")
        assert result == data


class TestRunMultiQuery:
    def test_path_appended_to_each_query(self):
        """When path is provided, each query gets path:"..." appended."""
        captured_queries = []

        def fake_do_search(q):
            captured_queries.append(q)
            return []

        with patch("research.do_search", fake_do_search), \
             patch("research.get_db"):
            run_multi_query("dragon|lich|undead", path="D&D 5e")

        assert len(captured_queries) == 3
        assert all('path:"D&D 5e"' in q for q in captured_queries)
        assert "dragon path:" in captured_queries[0]
        assert "lich path:" in captured_queries[1]
        assert "undead path:" in captured_queries[2]

    def test_no_path_passes_queries_unchanged(self):
        """When path is None, queries are passed through as-is."""
        captured_queries = []

        def fake_do_search(q):
            captured_queries.append(q)
            return []

        with patch("research.do_search", fake_do_search), \
             patch("research.get_db"):
            run_multi_query("dragon|lich")

        assert captured_queries == ["dragon", "lich"]

    def test_empty_path_passes_queries_unchanged(self):
        """When path is empty string, queries are passed through as-is."""
        captured_queries = []

        def fake_do_search(q):
            captured_queries.append(q)
            return []

        with patch("research.do_search", fake_do_search), \
             patch("research.get_db"):
            run_multi_query("dragon|lich", path="")

        assert captured_queries == ["dragon", "lich"]

    def test_path_with_special_chars(self):
        """Path with pipe character doesn't break query splitting."""
        captured_queries = []

        def fake_do_search(q):
            captured_queries.append(q)
            return []

        with patch("research.do_search", fake_do_search), \
             patch("research.get_db"):
            run_multi_query("dragon|lich", path="D&D | 5e")

        assert len(captured_queries) == 2
        assert 'path:"D&D | 5e"' in captured_queries[0]
        assert 'path:"D&D | 5e"' in captured_queries[1]
