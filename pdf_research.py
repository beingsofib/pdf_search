#!/usr/bin/env python3
"""
PDF research tool for LLM use.

Thin CLI wrapper around the PDF search API. All heavy lifting (search,
passage extraction, multi-query dedup, context trimming, view formatting)
is done server-side. This script just passes params and formats output.

Usage:
  python3 pdf_research.py search "query" [options]
  python3 pdf_research.py research "query" [options]
  python3 pdf_research.py folders [path]
  python3 pdf_research.py browse [path]
  python3 pdf_research.py stats
  python3 pdf_research.py coverage "query" [options]
  python3 pdf_research.py summarize "query" [options]
"""

import sys
import json
import urllib.request
import urllib.parse
import os

# Use config for port/host if available
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import config
    _PORT = config.PORT
    _HOST = "localhost"
except ImportError:
    _PORT = 5000
    _HOST = "localhost"

BASE_URL = f"http://{_HOST}:{_PORT}"


def _get(endpoint, params=None):
    url = BASE_URL + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


# --- API calls (thin wrappers — all logic is server-side) ---

def research(query=None, queries=None, limit=20, offset=0, passages=10,
             passage_offset=0, context=None, view=None, path=None):
    """Full-text search with passage extraction. All logic is server-side."""
    params = {}
    if query:
        params["q"] = query
    if queries:
        params["queries"] = queries
    if path:
        params["path"] = path
    if limit:
        params["limit"] = str(limit)
    if offset:
        params["offset"] = str(offset)
    if passages:
        params["passages"] = str(passages)
    if passage_offset:
        params["passage_offset"] = str(passage_offset)
    if context:
        params["context_tokens"] = context
    if view:
        params["view"] = view
    return _get("/api/research", params)


def search(query, limit=20, offset=0):
    """Search returning document metadata and snippets (no full passages)."""
    return _get("/search", {"q": query, "limit": str(limit), "offset": str(offset)})


def folders(path=""):
    """List subdirectories at the given path with file counts."""
    params = {}
    if path:
        params["path"] = path
    return _get("/folders", params)


def browse(path=""):
    """List PDF files directly in the given folder path."""
    params = {}
    if path:
        params["path"] = path
    return _get("/browse", params)


def stats():
    """Return database statistics (total documents, total size)."""
    return _get("/stats")


def text(doc_id):
    """Return the full extracted text of a document by ID."""
    return _get(f"/text/{doc_id}", {"raw": "1"})


# --- Output formatters ---

def print_research(data):
    total = data["total"]
    offset = data["offset"]
    limit = data["limit"]
    shown = len(data["results"])
    print(f"Query: {data['query']}")
    print(f"Total matching documents: {total}  (offset={offset}, limit={limit}, showing {shown})")
    if total > offset + limit:
        print(f"  -> More results available: use --offset {offset + limit}")
    print()
    for doc in data["results"]:
        tp = doc["total_passages"]
        po = doc["passage_offset"]
        shown_p = len(doc["passages"])
        print(f"=== {doc['path']}  [id={doc['id']}, passages={tp}] ===")
        if tp > po + shown_p:
            print(f"  -> More passages: use --passage-offset {po + shown_p}")
        for i, passage in enumerate(doc["passages"], po + 1):
            # Handle both string passages (default view) and dict passages (llm view)
            if isinstance(passage, dict):
                text = passage.get("text", "")
            else:
                text = passage
            print(f"  [{i}] {text.strip()}")
            print()


def print_folders(data):
    path = data.get("current_path", "")
    label = f'/{path}' if path else '(root)'
    print(f"Folders in {label}:")
    for f in data["folders"]:
        print(f"  {f['name']}/  ({f['count']} files)")
    if not data["folders"]:
        print("  (none)")


def print_browse(data):
    path = data.get("path", "")
    label = f'/{path}' if path else '(root)'
    print(f"Files in {label}:  ({data['count']} total)")
    for doc in data["results"]:
        print(f"  [{doc['id']}] {doc['filename']}  {doc['size']}  {doc['modified']}")


def print_stats(data):
    print(f"Total documents: {data['total_documents']}")
    print(f"Total size:      {data['total_size']}")


def print_coverage(data):
    """Print coverage report using API's view=coverage response."""
    total = data["total"]
    print(f"Query: {data['query']}")
    print(f"Total matching documents: {total}  (showing {len(data['results'])} of {data['limit'] if total > data['limit'] else total})")
    print()
    print(f"{'Document':<60} {'Passages':>8} {'Shown':>6} {'Coverage':>8}")
    print("-" * 82)
    for doc in data["results"]:
        tp = doc["total_passages"]
        shown_p = doc.get("passages_returned", len(doc["passages"]))
        pct = doc.get("coverage_pct", 0)
        label = doc["path"][:58] + ".." if len(doc["path"]) > 58 else doc["path"]
        status = "DONE" if shown_p >= tp else f"{pct:>7}%"
        print(f"{label:<60} {tp:>8} {shown_p:>6} {status:>8}")
    print()
    summary = data.get("coverage_summary", {})
    fully = summary.get("fully_read", 0)
    partial = summary.get("partial", 0)
    total_docs = summary.get("total_docs", len(data["results"]))
    print(f"Fully read: {fully}  Partial: {partial}  Total docs: {total_docs}")
    if partial > 0:
        print(f"  -> Use --passage-offset to read more passages from partial docs")


def print_summarize(data):
    """Print a quick survey of documents covering a topic."""
    total = data["total"]
    print(f"Query: {data['query']}")
    print(f"Total matching documents: {total}\n")
    for doc in data["results"]:
        tp = doc["total_passages"]
        headings = doc.get("headings", [])
        print(f"  [{doc['id']}] {doc['path']}")
        print(f"       Passages: {tp}")
        if headings:
            preview = headings[:3]
            suffix = "..." if len(headings) > 3 else ""
            print(f"       Sections: {' | '.join(preview)}{suffix}")
        print()


# --- CLI helpers ---

def print_search(data):
    """Print search results with snippets."""
    print(f"Query: {data['query']}")
    print(f"Total: {data['count']}\n")
    for r in data["results"]:
        print(f"  [{r['id']}] {r['path']}  {r['size']}")
        if r.get("snippet"):
            print(f"       {r['snippet']}")
        print()


def _build_research_params(args, view=None):
    """Build research API params from argparse args."""
    params = {}
    if args.queries:
        params["queries"] = args.queries
    else:
        params["query"] = args.query_or_path
    if args.path:
        params["path"] = args.path
    params["limit"] = args.limit
    params["offset"] = args.offset
    params["passages"] = args.passages
    params["passage_offset"] = args.passage_offset
    if args.context:
        params["context"] = args.context
    if view:
        params["view"] = view
    return params


def _make_query(args):
    """Build a query string with optional path filter."""
    q = args.query_or_path
    if args.path:
        q = f'{q} path:"{args.path}"'
    return q


# --- CLI ---

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Query the local PDF research API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  search   QUERY            Keyword/phrase search with short snippets
  research QUERY            Deep search with full passage extraction
  folders  [PATH]           List subdirectories at PATH (default: root)
  browse   [PATH]           List PDF files in PATH (default: root)
  stats                     Database statistics
  coverage QUERY            Coverage report (which docs are fully/partially read)
  summarize QUERY           Quick survey of docs covering a topic

Search syntax:
  "exact phrase"            phrase match
  -word                     exclude term
  word1 OR word2            either term
  word*                     prefix match
  path:"Folder Name"        restrict to folder
  filename:term             match filename only
  word1 NEAR/5 word2        proximity match

Features (all handled server-side):
  --queries "q1|q2|q3"     Multi-query: dedup, merge passages in one call
  --context 8k              Context-size-aware: 4k, 8k, 16k, 32k, or raw tokens
  --llm                     Structured JSON with headings, coverage, metadata
  coverage                  Coverage report with read status per doc
  summarize                 Quick survey with doc titles and section headings

Research workflow:
  1. folders          — discover available collections
  2. summarize "topic" — quick survey of what's available
  3. research "topic"  — deep reading with passage extraction
  4. --queries "t1|t2" — cover multiple angles in one call
  5. --context 8k      — auto-size output for your LLM's context window
  6. --llm             — structured JSON for LLM consumption
  7. coverage "topic"  — track which sources have been fully read
  8. --offset / --passage-offset — paginate through results
""")

    parser.add_argument("command", choices=["search", "research", "folders", "browse", "stats", "coverage", "summarize"],
                        help="Operation to perform")
    parser.add_argument("query_or_path", nargs="?", default="",
                        help="Search query (for search/research) or path (for folders/browse)")
    parser.add_argument("--path", default=None,
                        help="Folder filter for search/research (e.g. 'Shadow of the Weird Wizard')")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max documents to return (default: 20)")
    parser.add_argument("--offset", type=int, default=0,
                        help="Document offset for pagination")
    parser.add_argument("--passages", type=int, default=10,
                        help="Max passages per document (default: 10)")
    parser.add_argument("--passage-offset", type=int, default=0, dest="passage_offset",
                        help="Passage offset for pagination within a document")
    parser.add_argument("--queries", default=None,
                        help="Multiple queries separated by '|' for batch research")
    parser.add_argument("--context", default=None,
                        help="Target context size for LLM: 4k, 8k, 16k, 32k, or raw number")
    parser.add_argument("--llm", action="store_true",
                        help="Output structured JSON optimized for LLM consumption")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of formatted text")

    args = parser.parse_args()

    try:
        # Dispatch: each branch sets (data, fmt)
        if args.command == "research":
            view = "llm" if args.llm else None
            data = research(**_build_research_params(args, view))
            fmt = print_research

        elif args.command == "search":
            data = search(_make_query(args), limit=args.limit, offset=args.offset)
            fmt = print_search

        elif args.command == "folders":
            data = folders(args.query_or_path)
            fmt = print_folders

        elif args.command == "browse":
            data = browse(args.query_or_path)
            fmt = print_browse

        elif args.command == "stats":
            data = stats()
            fmt = print_stats

        elif args.command == "coverage":
            data = research(**_build_research_params(args, view="coverage"))
            fmt = print_coverage

        elif args.command == "summarize":
            params = _build_research_params(args)
            params["passages"] = 1
            params["passage_offset"] = 0
            data = research(**params)
            fmt = print_summarize

        # Output
        if args.llm or args.json:
            print(json.dumps(data, indent=2))
        else:
            fmt(data)

    except urllib.error.URLError as e:
        print(f"Error: cannot reach API at {BASE_URL} — is the server running?", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        sys.exit(1)
