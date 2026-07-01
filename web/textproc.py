"""Text processing: cleaning, heading extraction, semantic passage extraction."""

import re
from collections import Counter

STOPWORDS = frozenset({
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
    'to', 'was', 'will', 'with'
})


def clean_text(raw):
    """Fast regex cleanup of raw pdftotext output."""
    if not raw:
        return ''

    # Remove repeated header/footer lines (appear on multiple form-feed pages)
    pages = raw.split('\f')
    if len(pages) > 2:
        line_counts = Counter()
        for page in pages:
            lines = page.strip().splitlines()
            candidates = lines[:3] + lines[-3:]
            for line in candidates:
                stripped = line.strip()
                if stripped:
                    line_counts[stripped] += 1
        threshold = max(3, len(pages) * 0.4)
        repeated = {line for line, count in line_counts.items() if count >= threshold}
        if repeated:
            cleaned_pages = []
            for page in pages:
                lines = page.splitlines()
                cleaned_pages.append('\n'.join(
                    line for line in lines if line.strip() not in repeated
                ))
            raw = '\n'.join(cleaned_pages)

    raw = raw.replace('\f', '').replace('\ufffd', '')
    raw = re.sub(r'(\w)-\n(\w)', r'\1\2', raw)
    raw = re.sub(r'[ \t]+$', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'[^\S\n]+', ' ', raw)
    raw = re.sub(r'([a-z,;:\-])\n(?!\n)(\S)', r'\1 \2', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw)

    return raw.strip()


def extract_headings(text):
    """Extract section headings from cleaned PDF text.

    Returns list of (heading_text, char_position, level) tuples.
    Level 1 = major (Chapter, Part, etc.), Level 2 = ALL CAPS,
    Level 3 = topic headings (lines ending with colon).
    """
    headings = []
    lines = text.split('\n')
    pos = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            pos += len(line) + 1
            continue

        if re.match(r'^(Chapter|Part|Section|Book|Appendix|Volume|Act|Scene)\s+\w', stripped, re.IGNORECASE):
            headings.append((stripped, pos, 1))
        elif stripped.isupper() and len(stripped) > 3:
            word_count = len(stripped.split())
            if word_count >= 3 or (word_count == 1 and len(stripped) > 5):
                if not stripped.isdigit():
                    headings.append((stripped, pos, 2))
        elif stripped.endswith(':') and i + 1 < len(lines) and not lines[i + 1].strip():
            headings.append((stripped.rstrip(':'), pos, 3))

        pos += len(line) + 1

    return headings


def extract_semantic_passages(content, terms, max_passages=10, passage_offset=0, context_paragraphs=1):
    """Extract passages using paragraph boundaries instead of fixed windows.

    Finds paragraphs containing search terms and returns coherent passage groups
    with section context. Each passage is a group of consecutive paragraphs
    centered around matches, expanded by context_paragraphs on each side.

    Returns (passages, total_passages, headings).
    """
    cleaned = clean_text(content)
    headings = extract_headings(cleaned)
    paragraphs = cleaned.split('\n\n')

    # Build char position index for each paragraph
    para_positions = []
    pos = 0
    for para in paragraphs:
        para_positions.append((pos, pos + len(para)))
        pos += len(para) + 2

    # Extract partial terms (*word*) for substring matching
    partial_terms = set()
    for term in terms:
        t = term.strip('"*').lower()
        if term.startswith('*') and term.endswith('*') and len(term) > 2:
            partial_terms.add(t)

    # Find which paragraphs contain matches
    matched_indices = set()
    for term in terms:
        term_clean = term.strip('"*').lower()
        if not term_clean or term_clean in STOPWORDS:
            continue
        if term_clean in partial_terms:
            pattern = re.compile(re.escape(term_clean), re.IGNORECASE)
        else:
            pattern = re.compile(r'\b' + re.escape(term_clean) + r'\b', re.IGNORECASE)

        for i, para in enumerate(paragraphs):
            if pattern.search(para):
                matched_indices.add(i)

    # Expand to include context paragraphs
    expanded_indices = set()
    for idx in matched_indices:
        for offset in range(-context_paragraphs, context_paragraphs + 1):
            expanded_indices.add(idx + offset)

    valid_indices = sorted(i for i in expanded_indices if 0 <= i < len(paragraphs))

    # Merge consecutive indices into passage groups
    passage_groups = []
    current_group = []
    for idx in valid_indices:
        if not current_group or idx == current_group[-1] + 1:
            current_group.append(idx)
        else:
            passage_groups.append(current_group)
            current_group = [idx]
    if current_group:
        passage_groups.append(current_group)

    total_passages = len(passage_groups)
    selected_groups = passage_groups[passage_offset:passage_offset + max_passages]

    passages = []
    for group in selected_groups:
        group_start_pos = para_positions[group[0]][0]
        section = ''
        for heading_text, heading_pos, level in reversed(headings):
            if heading_pos <= group_start_pos:
                section = heading_text
                break

        passage_text = '\n\n'.join(paragraphs[i] for i in group)
        if section:
            passage_text = f"[{section}]\n{passage_text}"

        passages.append(passage_text)

    return passages, total_passages, headings
