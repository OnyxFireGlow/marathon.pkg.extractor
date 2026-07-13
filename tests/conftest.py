"""Pytest configuration for Marathon 2026 Package Extractor."""

import pytest
from pathlib import Path


@pytest.fixture
def test_pkg_path():
    """Path to test .pkg file."""
    return Path("tests/data/sample.pkg")


@pytest.fixture
def extracted_dir(tmp_path):
    """Temporary directory for extracted files."""
    return tmp_path / "extracted"
