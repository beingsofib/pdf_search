"""Tests for db.py: utility functions."""

import pytest
from db import format_size


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500.0 B"

    def test_kb(self):
        assert format_size(2048) == "2.0 KB"

    def test_mb(self):
        assert format_size(5_000_000) == "4.8 MB"

    def test_gb(self):
        assert format_size(2_000_000_000) == "1.9 GB"

    def test_none(self):
        assert format_size(None) == "0 B"

    def test_zero(self):
        assert format_size(0) == "0.0 B"

    def test_exact_boundary(self):
        assert format_size(1024) == "1.0 KB"
