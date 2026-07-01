"""Search: query parsing, FTS5 query building, and full-text search."""

import re
import logging
from html import escape as html_escape, unescape as html_unescape

logger = logging.getLogger(__name__)

try:
    from .db import get_db, make_result
    from .textproc import STOPWORDS
except ImportError:
    from db import get_db, make_result
    from textproc import STOPWORDS


def escape_like(value):
    """Escape LIKE wildcard characters in a value."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def parse_query(query):
    """Parse search query. Returns (search_words, path_filter, filename_only)."""
    words = []
    path_filter = None
    filename_only = False

    path_match = re.search(r'path:"([^"]+)"|path:(\S+)', query)
    if path_match:
        path_filter = path_match.group(1) or path_match.group(2)
        query = re.sub(r'path:"[^"]+"', '', query)
        query = re.sub(r'path:\S+', '', query)

    for token in query.split():
        if token.startswith('filename:'):
            words.append(token[9:])
            filename_only = True
        elif token.strip():
            words.append(token)

    return words, path_filter, filename_only


def build_fts_query(raw):
    """Translate user search syntax into an FTS5 query string.

    Supported syntax:
      "exact phrase"   — phrase match
      -word            — exclude term (NOT)
      word1 OR word2   — match either term
      word*            — prefix match
      word1 NEAR/N word2 — proximity search
    """
    fts_parts = []

    # 1. Extract NEAR expressions (e.g. dragon NEAR/5 lair)
    near_re = r'(\S+)\s+NEAR/(\d+)\s+(\S+)'
    for m in re.finditer(near_re, raw, re.IGNORECASE):
        fts_parts.append(f'NEAR("{m.group(1)}" "{m.group(3)}", {m.group(2)})')
    raw = re.sub(near_re, '', raw, flags=re.IGNORECASE)

    # 2. Extract quoted phrases
    for m in re.finditer(r'"([^"]+)"', raw):
        fts_parts.append(f'"{m.group(1)}"')
    raw = re.sub(r'"[^"]*"', '', raw)

    # 3. Process remaining tokens
    tokens = raw.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.upper() == 'OR' and fts_parts and i + 1 < len(tokens):
            prev = fts_parts.pop()
            nxt = tokens[i + 1]
            if nxt.startswith('-'):
                fts_parts.append(prev)
            elif nxt.endswith('*'):
                fts_parts.append(f'{prev} OR {nxt}')
            else:
                fts_parts.append(f'{prev} OR "{nxt}"')
            i += 2
            continue

        if token.startswith('-') and len(token) > 1:
            fts_parts.append(f'NOT "{token[1:]}"')
            i += 1
            continue

        if token.endswith('*') and len(token) > 1:
            fts_parts.append(token)
            i += 1
            continue

        if token.startswith('*') and token.endswith('*') and len(token) > 2:
            word = token[1:-1]
            if word.lower() not in STOPWORDS and len(word) > 1:
                fts_parts.append(f'"{word}"')
            i += 1
            continue

        if token.lower() not in STOPWORDS and len(token) > 1:
            fts_parts.append(f'"{token}"')

        i += 1

    return ' '.join(fts_parts)


def extract_search_terms(query):
    """Extract normalized search terms from a raw query string.

    Strips operators, path/filename filters, and stopwords.
    Returns (terms, partial_terms) where partial_terms are *word* substring matches.
    """
    # Strip path/filename filters
    raw = re.sub(r'path:"[^"]+"|path:\S+', '', query)
    raw = re.sub(r'filename:\S+', '', raw)

    # Extract quoted phrases
    phrases = re.findall(r'"([^"]+)"', raw)
    raw = re.sub(r'"[^"]*"', '', raw)

    # Extract partial-match terms (*word*)
    partial_terms = set()
    for token in raw.split():
        if token.startswith('*') and token.endswith('*') and len(token) > 2:
            partial_terms.add(token[1:-1].lower())

    # Build terms list: phrases + non-operator tokens
    terms = list(phrases)
    for token in raw.split():
        if (token.upper() != 'OR' and not token.startswith('-')
                and not re.match(r'NEAR/\d+', token, re.IGNORECASE)
                and len(token) > 1
                and token.lower() not in STOPWORDS):
            terms.append(token.rstrip('*').lower())

    return terms, partial_terms


def _highlight_excerpt(excerpt, terms, partial_terms=None):
    """Escape an excerpt and wrap matching terms in <mark> tags."""
    if not excerpt:
        return ''
    text = html_escape(excerpt.strip())
    partial_terms = partial_terms or set()
    for term in terms:
        escaped = re.escape(html_escape(term))
        if term.lower() in partial_terms:
            pattern = re.compile(escaped, re.IGNORECASE)
        else:
            pattern = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)
        text = pattern.sub(lambda m: f'<mark>{m.group()}</mark>', text)
    return '...' + text + '...'


def do_search(query):
    """Run a full-text search. Returns a list of result dicts."""
    search_words, path_filter, filename_only = parse_query(query)
    raw = ' '.join(search_words)

    fts_query = build_fts_query(raw)
    if not fts_query:
        return []

    # Build filename query: strip NOT/NEAR/OR, keep phrases and plain words
    fn_phrases = re.findall(r'"([^"]+)"', raw)
    fn_remaining = re.sub(r'"[^"]*"', '', raw)
    fn_words = [w for w in fn_remaining.split()
                if not w.startswith('-') and w.upper() != 'OR'
                and not re.match(r'NEAR/\d+', w, re.IGNORECASE)
                and len(w) > 1 and w.lower() not in STOPWORDS]
    filename_parts = [f'filename:"{p}"' for p in fn_phrases]
    filename_parts += [f'filename:"{w.rstrip("*")}"' for w in fn_words]
    filename_query = ' '.join(filename_parts) if filename_parts else fts_query

    path_clause = ""
    params_extra = []
    if path_filter:
        path_clause = " AND d.pdf_path LIKE ? ESCAPE '\\'"
        params_extra = [f'%{escape_like(path_filter)}%']

    conn = get_db()
    c = conn.cursor()
    results = []
    seen_ids = set()
    ranked_rows = []

    try:
        # Pass 1: rank without snippets (fast) — filename matches first
        c.execute(f"""
            SELECT d.id, d.filename, d.pdf_path, d.file_size, d.modified_date,
                   -1000.0 as score
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ?{path_clause}
            ORDER BY score
        """, [filename_query] + params_extra)

        for row in c.fetchall():
            seen_ids.add(row['id'])
            ranked_rows.append(row)

        # Content matches
        if not filename_only:
            c.execute(f"""
                SELECT d.id, d.filename, d.pdf_path, d.file_size, d.modified_date,
                       bm25(documents_fts, 10000.0, 1.0) as score
                FROM documents_fts
                JOIN documents d ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ?{path_clause}
                ORDER BY score
            """, [fts_query] + params_extra)

            for row in c.fetchall():
                if row['id'] not in seen_ids:
                    ranked_rows.append(row)

        # Pass 2: extract snippet windows in SQL (avoids slow FTS5 snippet())
        if ranked_rows:
            terms, partial_terms = extract_search_terms(raw)
            phrase_match = re.search(r'"([^"]+)"', raw)
            first_term = phrase_match.group(1).lower() if phrase_match else (terms[0] if terms else '')

            ids = [row['id'] for row in ranked_rows]
            placeholders = ','.join('?' * len(ids))
            c.execute(f"""
                SELECT rowid as id, content
                FROM documents_fts
                WHERE rowid IN ({placeholders})
            """, ids)

            if first_term:
                if first_term in partial_terms:
                    _ft_re = re.compile(re.escape(first_term), re.IGNORECASE)
                else:
                    _ft_re = re.compile(r'\b' + re.escape(first_term) + r'\b', re.IGNORECASE)
            else:
                _ft_re = None

            excerpt_map = {}
            for row in c.fetchall():
                content = html_unescape((row['content'] or '').replace('\ufffd', '').replace('\f', ''))
                pos = 0
                if _ft_re and content:
                    m = _ft_re.search(content)
                    if m:
                        pos = m.start()
                excerpt_map[row['id']] = content[max(0, pos - 80):pos + 200]

            for row in ranked_rows:
                result = make_result(row)
                excerpt = excerpt_map.get(row['id'], '')
                result['snippet'] = _highlight_excerpt(excerpt, terms, partial_terms)
                results.append(result)
    except Exception:
        logger.exception("Search error for query: %s", query)

    return results
