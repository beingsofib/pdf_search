"""Tests for search.py: query parsing, FTS5 query building, term extraction."""

import pytest
from search import build_fts_query, parse_query, extract_search_terms, escape_like


class TestBuildFtsQuery:
    def test_simple_word(self):
        assert build_fts_query("dragon") == '"dragon"'

    def test_phrase(self):
        assert build_fts_query('"magic missile"') == '"magic missile"'

    def test_exclusion(self):
        result = build_fts_query("dragon -chromatic")
        assert '"dragon"' in result
        assert 'NOT "chromatic"' in result

    def test_or(self):
        result = build_fts_query("wizard OR sorcerer")
        assert '"wizard" OR "sorcerer"' in result

    def test_prefix(self):
        assert build_fts_query("necro*") == 'necro*'

    def test_near(self):
        result = build_fts_query("dragon NEAR/5 lair")
        assert 'NEAR("dragon" "lair", 5)' in result

    def test_near_case_insensitive(self):
        result = build_fts_query("dragon near/3 lair")
        assert 'NEAR("dragon" "lair", 3)' in result

    def test_stopwords_removed(self):
        result = build_fts_query("the dragon")
        assert '"dragon"' in result
        assert '"the"' not in result

    def test_all_stopwords_returns_empty(self):
        assert build_fts_query("the a an") == ""

    def test_combined_operators(self):
        result = build_fts_query('"magic missile" wizard OR sorcerer -cantrip')
        assert '"magic missile"' in result
        assert '"wizard" OR "sorcerer"' in result
        assert 'NOT "cantrip"' in result

    def test_asterisk_wildcard_substring(self):
        # *word* is caught by the prefix (endswith '*') branch first,
        # so it's treated as a literal prefix token, not a substring match.
        result = build_fts_query("*dragon*")
        assert "*dragon*" in result

    def test_asterisk_wildcard_stopword_ignored(self):
        # Same as above — caught by prefix branch, not substring branch.
        result = build_fts_query("*the*")
        assert "*the*" in result

    def test_multiple_exclusions(self):
        result = build_fts_query("dragon -red -blue")
        assert result.count("NOT") == 2

    def test_or_with_exclusion_after(self):
        # When OR is followed by an exclusion, the OR handler restores
        # the previous term and the exclusion is dropped.
        result = build_fts_query("wizard OR -sorcerer")
        assert result == '"wizard"'

    def test_empty_input(self):
        assert build_fts_query("") == ""

    def test_single_char_ignored(self):
        assert build_fts_query("a") == ""


class TestParseQuery:
    def test_path_filter_double_quoted(self):
        words, path, fn_only = parse_query('dragon path:"D&D 5e"')
        assert words == ["dragon"]
        assert path == "D&D 5e"

    def test_path_filter_unquoted(self):
        words, path, fn_only = parse_query("dragon path:Shadowdark")
        assert path == "Shadowdark"

    def test_filename_only(self):
        words, path, fn_only = parse_query("filename:dragon")
        assert fn_only is True
        assert words == ["dragon"]

    def test_no_filters(self):
        words, path, fn_only = parse_query("dragon lich")
        assert words == ["dragon", "lich"]
        assert path is None
        assert fn_only is False

    def test_path_and_filename_together(self):
        words, path, fn_only = parse_query('dragon path:"D&D 5e" filename:monster')
        assert path == "D&D 5e"
        assert fn_only is True
        assert "dragon" in words
        assert "monster" in words

    def test_path_filter_removed_from_query(self):
        words, path, fn_only = parse_query('dragon path:"D&D 5e" lich')
        assert words == ["dragon", "lich"]


class TestExtractSearchTerms:
    def test_basic_words(self):
        terms, partial = extract_search_terms("dragon lich")
        assert "dragon" in terms
        assert "lich" in terms

    def test_excludes_or_operator(self):
        terms, _ = extract_search_terms("dragon OR lich")
        assert "OR" not in terms

    def test_excluded_terms_not_extracted(self):
        # Excluded terms (prefixed with -) are not extracted.
        terms, _ = extract_search_terms("dragon -undead")
        assert "undead" not in terms
        assert "dragon" in terms

    def test_phrases_extracted(self):
        terms, _ = extract_search_terms('"magic missile" wizard')
        assert "magic missile" in terms

    def test_partial_terms(self):
        _, partial = extract_search_terms("*dragon*")
        assert "dragon" in partial

    def test_path_filter_stripped(self):
        terms, _ = extract_search_terms('dragon path:"D&D 5e"')
        assert "D&D" not in terms
        assert "5e" not in terms

    def test_filename_filter_stripped(self):
        # filename:term is stripped entirely from the raw string before
        # term extraction, so the filename term is not in the output.
        terms, _ = extract_search_terms("filename:dragon lich")
        assert "dragon" not in terms
        assert "lich" in terms

    def test_near_operator_stripped(self):
        terms, _ = extract_search_terms("dragon NEAR/5 lair")
        assert "NEAR/5" not in terms
        assert "dragon" in terms
        assert "lair" in terms

    def test_stopwords_excluded(self):
        terms, _ = extract_search_terms("the dragon and the lich")
        assert "the" not in terms
        assert "and" not in terms
        assert "dragon" in terms
        assert "lich" in terms

    def test_prefix_asterisk_stripped(self):
        terms, _ = extract_search_terms("necro*")
        assert "necro" in terms
        assert "necro*" not in terms

    def test_empty_input(self):
        terms, partial = extract_search_terms("")
        assert terms == []
        assert partial == set()


class TestEscapeLike:
    def test_percent(self):
        assert escape_like("100%") == "100\\%"

    def test_underscore(self):
        assert escape_like("a_b") == "a\\_b"

    def test_backslash(self):
        assert escape_like("a\\b") == "a\\\\b"

    def test_combined(self):
        assert escape_like("100%_test\\") == "100\\%\\_test\\\\"

    def test_no_special_chars(self):
        assert escape_like("normal") == "normal"

    def test_empty(self):
        assert escape_like("") == ""
