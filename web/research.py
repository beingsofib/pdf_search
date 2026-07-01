"""Research API: multi-query dedup, passage extraction, context trimming, view transforms."""

import re

try:
    from .db import get_db
    from .search import do_search, extract_search_terms
    from .textproc import extract_semantic_passages
except ImportError:
    from db import get_db
    from search import do_search, extract_search_terms
    from textproc import extract_semantic_passages


def _parse_context_size(context_str):
    """Parse context size string like '8k', '32k', or '16000' into token count."""
    if not context_str:
        return None
    context_str = context_str.strip().lower()
    if context_str.endswith('k'):
        return int(context_str[:-1]) * 1000
    return int(context_str)


def run_multi_query(queries_str, limit=20, offset=0, max_passages=10, passage_offset=0, context_paragraphs=1, path=None):
    """Run multiple pipe-separated queries, deduplicate by doc ID, merge passages.

    Returns the same structure as a single research query.
    """
    query_list = [q.strip() for q in queries_str.split("|") if q.strip()]
    if not query_list:
        return {"query": queries_str, "total": 0, "offset": offset, "limit": limit, "results": []}

    # Append path filter to each query if provided
    if path:
        query_list = [f'{q} path:"{path}"' for q in query_list]

    all_docs = {}
    all_terms = set()

    for q in query_list:
        search_results = do_search(q)
        terms, _ = extract_search_terms(q)
        all_terms.update(terms)

        for sr in search_results:
            if sr['id'] not in all_docs:
                all_docs[sr['id']] = sr

    sorted_docs = sorted(all_docs.values(), key=lambda d: d['id'])
    total = len(sorted_docs)
    page_docs = sorted_docs[offset:offset + limit]

    conn = get_db()
    c = conn.cursor()
    results = []

    for sr in page_docs:
        c.execute("SELECT content FROM documents_fts WHERE rowid = ?", (sr['id'],))
        row = c.fetchone()
        if not row or not row['content']:
            continue

        passages, total_passages, headings = extract_semantic_passages(
            row['content'], list(all_terms),
            max_passages=max_passages,
            passage_offset=passage_offset,
            context_paragraphs=context_paragraphs,
        )

        if passages or total_passages > 0:
            results.append({
                'id': sr['id'],
                'filename': sr['filename'],
                'path': sr['path'],
                'total_passages': total_passages,
                'passage_offset': passage_offset,
                'passages': passages,
                'headings': [h[0] for h in headings],
            })

    return {
        'query': ' | '.join(query_list),
        'total': total,
        'offset': offset,
        'limit': limit,
        'results': results,
    }


def apply_context_trimming(data, context_tokens):
    """Trim passages to fit within a token budget."""
    if not context_tokens or not data.get('results'):
        return data

    char_budget = int(context_tokens * 4 * 0.7)
    total_chars = 0
    trimmed = 0
    for doc in data['results']:
        kept = []
        for passage in doc['passages']:
            passage_chars = len(passage) + 50
            if total_chars + passage_chars <= char_budget:
                kept.append(passage)
                total_chars += passage_chars
            else:
                trimmed += 1
        doc['passages'] = kept
    data['context_budget'] = context_tokens
    data['context_trimmed'] = trimmed
    return data


def apply_view(data, view):
    """Apply view transformation to research results."""
    if view == 'coverage':
        fully_read = 0
        partial = 0
        for doc in data['results']:
            tp = doc['total_passages']
            shown = len(doc['passages'])
            doc['coverage_pct'] = (shown * 100 // tp) if tp > 0 else 0
            doc['passages_returned'] = shown
            if tp > 0 and shown >= tp:
                fully_read += 1
            elif tp > 0:
                partial += 1
        data['coverage_summary'] = {
            'fully_read': fully_read,
            'partial': partial,
            'total_docs': len(data['results']),
        }

    elif view == 'llm':
        for doc in data['results']:
            tp = doc['total_passages']
            shown = len(doc['passages'])
            doc['coverage_pct'] = (shown * 100 // tp) if tp > 0 else 0
            doc['passages_returned'] = shown
            structured = []
            for passage in doc['passages']:
                section = ''
                if passage.startswith('['):
                    first_newline = passage.find('\n')
                    if first_newline > 0:
                        section = passage[1:first_newline].strip('[]')
                structured.append({
                    'text': passage,
                    'section': section,
                })
            doc['passages'] = structured

    return data
