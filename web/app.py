#!/usr/bin/env python3
"""
PDF Search web interface — Flask routes.

All heavy lifting is delegated to focused modules:
  db.py        — database helpers
  textproc.py  — text cleaning, heading extraction, passage extraction
  search.py    — query parsing, FTS5 query building, full-text search
  research.py  — multi-query dedup, context trimming, view transforms
  indexer.py   — background indexer with status tracking
"""

import logging
import os
import re
import sys
import threading

from html import escape as html_escape
from flask import Flask, render_template, request, send_file, jsonify, abort, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    from .db import get_db, format_size, make_result, PDF_DIR_PREFIX, init_app
    from .textproc import clean_text, STOPWORDS, extract_semantic_passages
    from .search import do_search, escape_like, extract_search_terms
    from .research import run_multi_query, apply_context_trimming, apply_view, _parse_context_size
    from .indexer import status as _indexer_status, run as _run_indexer, start_periodic
except ImportError:
    from db import get_db, format_size, make_result, PDF_DIR_PREFIX, init_app
    from textproc import clean_text, STOPWORDS, extract_semantic_passages
    from search import do_search, escape_like, extract_search_terms
    from research import run_multi_query, apply_context_trimming, apply_view, _parse_context_size
    from indexer import status as _indexer_status, run as _run_indexer, start_periodic

app = Flask(__name__)
init_app(app)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as count FROM documents")
        total_docs = c.fetchone()['count']
    except Exception:
        total_docs = 0
    return render_template('index.html', total_docs=total_docs,
                           site_title=config.SITE_TITLE)


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': [], 'count': 0, 'query': ''})
    results = do_search(query)
    return jsonify({'results': results, 'count': len(results), 'query': query})


@app.route('/browse')
def browse():
    path = request.args.get('path', '').strip()
    full_path = PDF_DIR_PREFIX + path + '/' if path else PDF_DIR_PREFIX

    results = []
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT id, filename, pdf_path, file_size, modified_date
            FROM documents WHERE pdf_path LIKE ? ESCAPE '\\'
            ORDER BY filename
        """, (escape_like(full_path) + '%',))

        for row in c.fetchall():
            rel_from_folder = row['pdf_path'][len(full_path):]
            if '/' not in rel_from_folder:
                results.append(make_result(row))
    except Exception:
        pass
    return jsonify({'results': results, 'count': len(results), 'path': path})


@app.route('/pdf/<int:doc_id>')
def serve_pdf(doc_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT pdf_path, filename FROM documents WHERE id = ?", (doc_id,))
    row = c.fetchone()
    if not row:
        return "PDF not found", 404
    if not os.path.exists(row['pdf_path']):
        return "PDF file not found on disk", 404
    return send_file(row['pdf_path'], mimetype='application/pdf', as_attachment=False)


@app.route('/stats')
def stats():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as count FROM documents")
        total_docs = c.fetchone()['count']
        c.execute("SELECT SUM(file_size) as total_size FROM documents")
        total_size = c.fetchone()['total_size'] or 0
    except Exception:
        total_docs = 0
        total_size = 0
    return jsonify({'total_documents': total_docs, 'total_size': format_size(total_size)})


@app.route('/folders')
def folders():
    path = request.args.get('path', '').strip()
    full_base = PDF_DIR_PREFIX + path + '/' if path else PDF_DIR_PREFIX

    folders_dict = {}
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT pdf_path FROM documents WHERE pdf_path LIKE ? ESCAPE '\\'",
                  (escape_like(full_base) + '%',))

        for row in c.fetchall():
            rel = row['pdf_path'][len(full_base):]
            if '/' in rel:
                folder = rel.split('/')[0]
                folders_dict[folder] = folders_dict.get(folder, 0) + 1
    except Exception:
        pass

    folders_list = [{'name': k, 'count': v} for k, v in sorted(folders_dict.items())]
    return jsonify({'folders': folders_list, 'current_path': path})


@app.route('/reindex', methods=['POST'])
def reindex():
    origin = request.headers.get('Origin', '')
    if origin and not origin.startswith(('http://localhost', 'http://127.0.0.1')):
        return jsonify({'error': 'forbidden'}), 403
    if _indexer_status['running']:
        return jsonify({'status': 'already_running'})
    t = threading.Thread(target=_run_indexer, args=(config.DB_PATH, config.PDF_DIR), daemon=True)
    t.start()
    return jsonify({'status': 'started'})


@app.route('/reindex/status')
def reindex_status():
    return jsonify(_indexer_status)


@app.route('/text/<int:doc_id>')
def text_view(doc_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, filename, pdf_path FROM documents WHERE id = ?", (doc_id,))
    doc = c.fetchone()
    if not doc:
        abort(404)
    c.execute("SELECT content FROM documents_fts WHERE rowid = ?", (doc_id,))
    fts_row = c.fetchone()
    if not fts_row or not fts_row['content']:
        abort(404)

    cleaned = clean_text(fts_row['content'])
    content_html = ''.join(
        '<p>' + html_escape(para).replace('\n', '<br>') + '</p>'
        for para in cleaned.split('\n\n') if para.strip()
    )

    query = request.args.get('q', '').strip()
    highlight_terms = []
    partial_highlight_terms = []
    if query:
        terms, partial_terms = extract_search_terms(query)
        highlight_terms = terms
        partial_highlight_terms = list(partial_terms)

    return render_template('text.html', filename=doc['filename'], doc_id=doc_id,
                           content_html=content_html, site_title=config.SITE_TITLE,
                           highlight_terms=highlight_terms,
                           partial_highlight_terms=partial_highlight_terms)


@app.route('/text/<int:doc_id>/download')
def text_download(doc_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
    doc = c.fetchone()
    if not doc:
        abort(404)
    c.execute("SELECT content FROM documents_fts WHERE rowid = ?", (doc_id,))
    fts_row = c.fetchone()
    if not fts_row or not fts_row['content']:
        abort(404)
    cleaned = clean_text(fts_row['content'])
    download_name = re.sub(r'\.pdf$', '', doc['filename'], flags=re.IGNORECASE) + '.txt'
    return Response(
        cleaned,
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="{download_name}"'}
    )


@app.route('/api/research')
def research_api():
    query = request.args.get('q', '').strip()
    queries = request.args.get('queries', '').strip()
    if not query and not queries:
        return jsonify({'error': 'missing q or queries parameter'}), 400

    limit = min(int(request.args.get('limit', 20)), 20)
    offset = max(int(request.args.get('offset', 0)), 0)
    max_passages = min(int(request.args.get('passages', 10)), 50)
    passage_offset = max(int(request.args.get('passage_offset', 0)), 0)
    context_paragraphs = max(int(request.args.get('context', 1)), 0)
    try:
        context_tokens = _parse_context_size(request.args.get('context_tokens', ''))
    except ValueError:
        return jsonify({'error': 'invalid context_tokens value'}), 400
    view = request.args.get('view', 'default')
    path_filter = request.args.get('path', '').strip()

    # Multi-query mode
    if queries:
        data = run_multi_query(
            queries, limit=limit, offset=offset,
            max_passages=max_passages, passage_offset=passage_offset,
            context_paragraphs=context_paragraphs,
            path=path_filter,
        )
    else:
        if path_filter:
            query = f'{query} path:"{path_filter}"'
        all_results = do_search(query)
        search_results = all_results[offset:offset + limit]

        if not search_results:
            data = {'query': query, 'total': len(all_results), 'offset': offset, 'limit': limit, 'results': []}
        else:
            terms, _ = extract_search_terms(query)

            conn = get_db()
            c = conn.cursor()
            results = []

            for sr in search_results:
                c.execute("SELECT content FROM documents_fts WHERE rowid = ?", (sr['id'],))
                row = c.fetchone()
                if not row or not row['content']:
                    continue

                passages, total_passages, headings = extract_semantic_passages(
                    row['content'], terms,
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

            data = {'query': query, 'total': len(all_results), 'offset': offset, 'limit': limit, 'results': results}

    # Apply context-size trimming and view transformations
    data = apply_context_trimming(data, context_tokens)
    data = apply_view(data, view)

    return jsonify(data)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        threading.Thread(target=start_periodic, args=(config.DB_PATH, config.PDF_DIR), daemon=True).start()
    app.run(host=config.HOST, port=config.PORT, debug=False)
