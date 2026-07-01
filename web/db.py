"""Database helpers shared across the web app."""

import sqlite3
import sys
import os

from flask import g

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

PDF_DIR_PREFIX = config.PDF_DIR if config.PDF_DIR.endswith('/') else config.PDF_DIR + '/'


def get_db():
    """Return a SQLite connection with row_factory and WAL mode.

    Reuses the connection within a request via Flask's g object.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(config.DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


def close_db(exception=None):
    """Close the database connection at the end of a request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_app(app):
    """Register database teardown with the Flask app."""
    app.teardown_appcontext(close_db)


def format_size(size_bytes):
    """Format bytes to human-readable size."""
    if size_bytes is None:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def make_result(row):
    """Build a result dict from a database row."""
    return {
        'id': row['id'],
        'filename': row['filename'],
        'path': row['pdf_path'].removeprefix(PDF_DIR_PREFIX),
        'size': format_size(row['file_size']),
        'modified': row['modified_date'] or '',
        'snippet': '',
    }
