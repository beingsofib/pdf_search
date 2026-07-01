# PDF Search

Full-text search over a local PDF library with a web interface. Uses SQLite FTS5 for fast searching and `pdftotext` for text extraction. Includes a research API and CLI tool for deep research across the library.

**This tool is intended for local use only.** It has no authentication, no access controls, and serves raw PDF files directly. Do not expose it to the public internet or untrusted networks. Run it on localhost or behind a VPN.

## Features

- Full-text search across thousands of PDFs (~4,700 indexed)
- Indexes 5,000 PDFs in roughly 10 minutes with three workers
- Folder browsing sidebar with filter and resizable width
- Mobile-friendly responsive layout
- Filename matches ranked above content matches (BM25 with 10000x filename weight)
- Sort results by relevance, name, or date (toggle ascending/descending)
- Search syntax: `"exact phrase"`, `-exclude`, `OR`, `prefix*`, `NEAR/N`, `path:"folder"`, `filename:term`
- Text view for each PDF with on-the-fly cleanup (paragraph rejoining, header/footer removal, whitespace normalization)
- Search term highlighting in text view with match count and prev/next navigation
- AJAX-powered results (no page reloads)
- Automatic indexing on startup, hourly, and on demand from the UI
- Live indexing progress in the web UI
- Stale record cleanup on re-index
- Research API (`/api/research`) returns JSON passages for research tools
- `pdf_research.py` — single CLI script for all research operations

## Requirements

- Python 3.8+
- Flask (`pip install flask`)
- pytest (`pip install pytest`) — for running tests
- `pdftotext` (from `poppler-utils`)

Install on Debian/Ubuntu:

```bash
sudo apt install poppler-utils
pip install flask
```

## Setup

1. Copy `config.py.sample` to `config.py` and set `PDF_DIR` to your PDF directory.

```bash
cp config.py.sample config.py
```

2. Start the web server:

```bash
cd web
python3 app.py
```

3. Open `http://localhost:5000` in a browser.

The app automatically indexes your PDFs on startup. Progress is shown in the web UI. Once indexing completes, search is available immediately. New or changed PDFs are picked up automatically every hour, or you can click "update index" in the UI at any time.

You can also run the extractor standalone:

```bash
python3 extractor.py
```

## Project Structure

```
pdf_search/
├── config.py            # Configuration (env vars or defaults)
├── config.py.sample     # Sample config for new installs
├── extractor.py         # PDF text extraction and indexing (parallel, 3 workers)
├── pdf_research.py      # CLI tool for research operations
├── pdf_search.db        # SQLite database with FTS5
├── README.md
├── SKILL.md             # LLM skill for RPG research reports
└── web/
    ├── __init__.py
    ├── app.py           # Flask routes
    ├── db.py            # Database helpers (get_db, close_db, init_app, format_size, make_result)
    ├── indexer.py       # Background indexer with status tracking
    ├── research.py      # Multi-query dedup, context trimming, view transforms
    ├── search.py        # Query parsing, FTS5 query building, full-text search
    ├── textproc.py      # Text cleaning, heading extraction, passage extraction
    └── templates/
        ├── index.html   # Search UI (single-page app)
        └── text.html    # Cleaned text view with highlighting
```

## Configuration

Edit `config.py` or set environment variables:

| Variable | Default | Description |
|---|---|---|
| `PDF_SEARCH_PDF_DIR` | `/mnt/sandisk_usb/Documents/RPGs` | Directory containing PDFs |
| `PDF_SEARCH_DB` | `./pdf_search.db` | SQLite database path |
| `PDF_SEARCH_HOST` | `0.0.0.0` | Web server bind address |
| `PDF_SEARCH_PORT` | `5000` | Web server port |
| `PDF_SEARCH_TITLE` | `PDF Search` | Site title in the web UI |
| `PDF_SEARCH_MAX_WORKERS` | `3` | Parallel workers for PDF extraction |

## Search Syntax

| Syntax | Example | Description |
|---|---|---|
| `"phrase"` | `"magic missile"` | Exact phrase match |
| `-word` | `dragon -chromatic` | Exclude results containing a word |
| `OR` | `wizard OR sorcerer` | Match either term |
| `word*` | `necro*` | Prefix match (necromancer, necromancy, etc.) |
| `NEAR/N` | `dragon NEAR/5 lair` | Words within N words of each other |
| `path:"folder"` | `path:"D&D 5e"` | Filter results to a folder |
| `filename:term` | `filename:dragon` | Search filenames only |

## Database Schema

**documents table**
- `id` — primary key
- `pdf_path` — full path to PDF (unique)
- `filename` — PDF filename
- `file_size` — file size in bytes
- `extracted_date` — when text was extracted
- `modified_date` — file modification time from filesystem

**documents_fts (FTS5 virtual table)**
- `filename` — searchable filename (heavily weighted)
- `content` — searchable text content

**failed_extractions table**
- `pdf_path` — PDF that couldn't be extracted
- `file_size`, `modified_date` — for change detection
- `failed_date` — when extraction was attempted

**schema_version table**
- `version` — current schema version number
- `applied_at` — when the migration was applied

## API Endpoints

- `GET /` — main search interface
- `GET /search?q=query` — JSON search results with snippets
- `GET /browse?path=path` — list files in a folder
- `GET /pdf/<id>` — serve PDF file
- `GET /folders?path=path` — list subdirectories with file counts
- `GET /stats` — database statistics
- `GET /text/<id>` — cleaned text view with optional `?q=` for highlighting
- `GET /text/<id>/download` — download cleaned text as .txt
- `GET /api/research` — passage extraction (`q`, `queries`, `path`, `limit`, `offset`, `passages`, `passage_offset`, `context_tokens`, `view`)
- `POST /reindex` — trigger re-index (local origins only)
- `GET /reindex/status` — indexer status

## Research Tool

`pdf_research.py` is the single CLI for all research operations:

```bash
python3 pdf_research.py research "query" [--path "Folder"] [--passages N] [--offset N] [--passage-offset N]
python3 pdf_research.py search "query"
python3 pdf_research.py folders [path]
python3 pdf_research.py browse [path]
python3 pdf_research.py stats
python3 pdf_research.py coverage "query"
python3 pdf_research.py summarize "query"
```

All commands accept `--json` for raw JSON output.

### Research workflow

1. **Survey** — find which documents cover the topic:
   ```bash
   python3 pdf_research.py folders
   python3 pdf_research.py summarize "topic" --path "Folder"
   ```

2. **Read deeply** — pull passages from the best sources:
   ```bash
   python3 pdf_research.py research "topic" --passages 20
   ```

3. **Multi-angle** — cover multiple search terms in one call:
   ```bash
   python3 pdf_research.py research --queries "term1|term2|term3" --path "Folder"
   ```

4. **Paginate** — use `--offset` for more documents, `--passage-offset` for more passages within a document.

5. **Context-aware** — auto-size output for your LLM:
   ```bash
   python3 pdf_research.py research "topic" --context 8k --llm
   ```

## Security

- LIKE clauses use `ESCAPE` with `escape_like()` to prevent wildcard injection
- FTS query terms are sanitized
- All DB queries use parameterized statements
- Reindex endpoint restricted to local origins

## Known Limitations

- Some PDFs with owner-password encryption cannot be indexed
- FTS5 uses simple tokenizer (splits on whitespace/punctuation)
- No OCR — only PDFs with an existing text layer are searchable

## Testing

```bash
python3 -m pytest tests/ -v
```

108 tests covering query parsing, text cleaning, heading extraction, passage extraction, context trimming, view transforms, multi-query path filtering, and database initialization. No database fixtures required — all tests run against pure functions.

## License

CC0 1.0 Universal. See [LICENSE](LICENSE).
