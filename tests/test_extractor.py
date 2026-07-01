"""Tests for extractor.py: database initialization."""

import os
import sqlite3
import tempfile

import pytest

# extractor imports config at module level, so we need to ensure
# the path is set up before importing
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from extractor import init_db


class TestInitDb:
    def test_creates_tables(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            conn = sqlite3.connect(db_path)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t[0] for t in tables}
            assert "documents" in table_names
            assert "documents_fts" in table_names
            assert "failed_extractions" in table_names
            assert "schema_version" in table_names
            conn.close()
        finally:
            os.unlink(db_path)

    def test_idempotent(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            init_db(db_path)  # should not raise
        finally:
            os.unlink(db_path)

    def test_documents_schema(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            conn = sqlite3.connect(db_path)
            columns = conn.execute("PRAGMA table_info(documents)").fetchall()
            col_names = {c[1] for c in columns}
            assert "id" in col_names
            assert "pdf_path" in col_names
            assert "filename" in col_names
            assert "extracted_date" in col_names
            assert "file_size" in col_names
            assert "modified_date" in col_names
            conn.close()
        finally:
            os.unlink(db_path)

    def test_failed_extractions_schema(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            conn = sqlite3.connect(db_path)
            columns = conn.execute("PRAGMA table_info(failed_extractions)").fetchall()
            col_names = {c[1] for c in columns}
            assert "pdf_path" in col_names
            assert "file_size" in col_names
            assert "modified_date" in col_names
            assert "failed_date" in col_names
            conn.close()
        finally:
            os.unlink(db_path)

    def test_adds_modified_date_to_existing_db(self):
        """Simulate an old database without the modified_date column."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            # Create old-style schema without modified_date
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pdf_path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    extracted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_size INTEGER
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE documents_fts USING fts5(
                    filename, content, content_rowid=id
                )
            """)
            conn.execute("""
                CREATE TABLE failed_extractions (
                    pdf_path TEXT UNIQUE NOT NULL,
                    file_size INTEGER,
                    modified_date TIMESTAMP,
                    failed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()

            # Now run init_db — should add the column without error
            init_db(db_path)

            conn = sqlite3.connect(db_path)
            columns = conn.execute("PRAGMA table_info(documents)").fetchall()
            col_names = {c[1] for c in columns}
            assert "modified_date" in col_names
            conn.close()
        finally:
            os.unlink(db_path)
