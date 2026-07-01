"""Tests for textproc.py: text cleaning, heading extraction, passage extraction."""

import pytest
from textproc import clean_text, extract_headings, extract_semantic_passages


class TestCleanText:
    def test_hyphenated_line_break(self):
        raw = "The drag-\non flew away."
        result = clean_text(raw)
        assert "dragon" in result

    def test_header_removal_repeated(self):
        # 5 pages, same header on 3+ pages → stripped
        pages = [
            "CHAPTER ONE\n\nContent A",
            "CHAPTER ONE\n\nContent B",
            "CHAPTER ONE\n\nContent C",
            "CHAPTER ONE\n\nContent D",
            "CHAPTER ONE\n\nContent E",
        ]
        raw = "\f".join(pages)
        result = clean_text(raw)
        assert "CHAPTER ONE" not in result
        assert "Content A" in result
        assert "Content E" in result

    def test_short_document_no_header_removal(self):
        # 2 pages — threshold not met, headers kept
        raw = "Title\n\nPage 1\fTitle\n\nPage 2"
        result = clean_text(raw)
        assert "Title" in result

    def test_footer_removal(self):
        pages = [
            "Content A\nPage 1 of 10",
            "Content B\nPage 1 of 10",
            "Content C\nPage 1 of 10",
            "Content D\nPage 1 of 10",
        ]
        raw = "\f".join(pages)
        result = clean_text(raw)
        assert "Page 1 of 10" not in result

    def test_whitespace_normalization(self):
        raw = "Line   with    spaces\n\n\n\nToo many breaks"
        result = clean_text(raw)
        assert "Line with spaces" in result
        assert result.count("\n\n") == 1

    def test_null_replacement_removed(self):
        raw = "text\ufffd more"
        assert "\ufffd" not in clean_text(raw)

    def test_sentence_rejoin(self):
        raw = "This is a sentence that\nwraps to the next line."
        result = clean_text(raw)
        assert "sentence that wraps" in result

    def test_trailing_spaces_stripped(self):
        # Trailing spaces are stripped, and the newline is rejoined
        # as a space (sentence rejoin rule).
        raw = "Line with spaces   \nAnother line"
        result = clean_text(raw)
        assert "spaces Another" in result

    def test_empty_input(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""

    def test_single_page(self):
        raw = "Just one page of content."
        result = clean_text(raw)
        assert "Just one page of content" in result

    def test_form_feed_removed(self):
        raw = "Page 1\fPage 2"
        result = clean_text(raw)
        assert "\f" not in result


class TestExtractHeadings:
    def test_chapter_heading(self):
        text = "Chapter 1: The Beginning\n\nSome content here."
        headings = extract_headings(text)
        assert any(h[0] == "Chapter 1: The Beginning" and h[2] == 1 for h in headings)

    def test_part_heading(self):
        text = "Part II: The Journey\n\nContent."
        headings = extract_headings(text)
        assert any(h[0] == "Part II: The Journey" and h[2] == 1 for h in headings)

    def test_section_heading(self):
        text = "Section 3: Combat\n\nContent."
        headings = extract_headings(text)
        assert any(h[0] == "Section 3: Combat" and h[2] == 1 for h in headings)

    def test_appendix_heading(self):
        text = "Appendix A: Tables\n\nContent."
        headings = extract_headings(text)
        assert any(h[0] == "Appendix A: Tables" and h[2] == 1 for h in headings)

    def test_all_caps_heading(self):
        text = "THE DRAGON'S LAIR\n\nDescription of the lair."
        headings = extract_headings(text)
        assert any(h[0] == "THE DRAGON'S LAIR" and h[2] == 2 for h in headings)

    def test_all_caps_multi_word(self):
        text = "COMBAT ENCOUNTERS AND REWARDS\n\nContent."
        headings = extract_headings(text)
        assert any(h[0] == "COMBAT ENCOUNTERS AND REWARDS" and h[2] == 2 for h in headings)

    def test_colon_topic_heading(self):
        text = "Combat Rules:\n\nInitiative is rolled..."
        headings = extract_headings(text)
        assert any(h[0] == "Combat Rules" and h[2] == 3 for h in headings)

    def test_short_caps_not_heading(self):
        text = "HP\n\nSome content."
        headings = extract_headings(text)
        assert not any(h[0] == "HP" for h in headings)

    def test_numeric_not_heading(self):
        text = "42\n\nSome content."
        headings = extract_headings(text)
        assert not any(h[0] == "42" for h in headings)

    def test_single_short_caps_not_heading(self):
        text = "DRAGON\n\nContent."
        headings = extract_headings(text)
        # "DRAGON" is 6 chars, > 5, single word — should be a heading
        assert any(h[0] == "DRAGON" and h[2] == 2 for h in headings)

    def test_heading_positions(self):
        text = "Intro.\n\nCHAPTER 1\n\nBody text.\n\nAPPENDIX\n\nEnd."
        headings = extract_headings(text)
        # CHAPTER 1 should come before APPENDIX
        ch1 = next(h for h in headings if h[0] == "CHAPTER 1")
        app = next(h for h in headings if h[0] == "APPENDIX")
        assert ch1[1] < app[1]

    def test_empty_text(self):
        assert extract_headings("") == []


class TestExtractSemanticPassages:
    def test_finds_matching_paragraphs(self):
        content = "Intro paragraph.\n\nA dragon is a large reptile.\n\nUnrelated text."
        passages, total, headings = extract_semantic_passages(content, ["dragon"])
        assert total >= 1
        assert any("dragon" in p.lower() for p in passages)

    def test_context_expansion(self):
        content = "Before paragraph.\n\nDragon here.\n\nAfter paragraph."
        passages, _, _ = extract_semantic_passages(
            content, ["dragon"], context_paragraphs=1
        )
        combined = "\n\n".join(passages)
        assert "Before" in combined
        assert "After" in combined

    def test_heading_prepended(self):
        content = "COMBAT\n\nDragon attacks with claws."
        passages, _, _ = extract_semantic_passages(content, ["dragon"])
        assert passages[0].startswith("[COMBAT]")

    def test_passage_offset(self):
        content = "Dragon A.\n\nDragon B.\n\nDragon C.\n\nDragon D."
        passages, total, _ = extract_semantic_passages(
            content, ["dragon"], max_passages=2, passage_offset=1
        )
        assert len(passages) <= 2

    def test_partial_term_matching(self):
        content = "The dragonborn approaches."
        passages, total, _ = extract_semantic_passages(content, ["*dragon*"])
        assert total >= 1

    def test_stopwords_ignored(self):
        content = "The dragon is here."
        passages, total, _ = extract_semantic_passages(content, ["the"])
        assert total == 0

    def test_case_insensitive_matching(self):
        content = "A DRAGON appears.\n\nA Dragon flies.\n\na dragon sleeps."
        passages, total, _ = extract_semantic_passages(content, ["dragon"])
        assert total == 1  # all three paragraphs are consecutive → one passage group

    def test_phrase_matching(self):
        content = "The magic missile strikes true.\n\nUnrelated."
        passages, total, _ = extract_semantic_passages(content, ["magic missile"])
        assert total >= 1

    def test_no_matches(self):
        content = "Nothing here.\n\nStill nothing."
        passages, total, _ = extract_semantic_passages(content, ["dragon"])
        assert total == 0
        assert passages == []

    def test_max_passages_limit(self):
        content = "\n\n".join(f"Dragon paragraph {i}.\n\nFiller." for i in range(20))
        passages, total, _ = extract_semantic_passages(
            content, ["dragon"], max_passages=5
        )
        assert len(passages) <= 5

    def test_merged_consecutive_matches(self):
        # With context_paragraphs=0, consecutive matches merge into one
        # group, and non-matching paragraphs break the group.
        content = "Dragon A.\n\nDragon B.\n\nDragon C.\n\nNo match.\n\nDragon D."
        passages, total, _ = extract_semantic_passages(
            content, ["dragon"], context_paragraphs=0
        )
        # First three paragraphs are consecutive matches → one passage group.
        # Fourth is no match, fifth is a separate match → two groups.
        assert total == 2

    def test_empty_content(self):
        passages, total, headings = extract_semantic_passages("", ["dragon"])
        assert total == 0
        assert passages == []
