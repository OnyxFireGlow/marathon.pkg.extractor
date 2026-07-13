"""Tests for dependency management system."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.utils.downloader import DependencyManager


def test_dependency_manager_init():
    """Test DependencyManager initialization."""
    manager = DependencyManager()
    assert manager.lib_dir.exists()


def test_dependency_manager_check_unknown():
    """Test checking unknown dependency."""
    manager = DependencyManager()
    exists, path = manager.check_dependency("unknown_dep")
    assert exists is False
    assert path is None


def test_dependency_manager_cache():
    """Test dependency caching."""
    manager = DependencyManager()
    exists1, path1 = manager.check_dependency("oo2core")
    exists2, path2 = manager.check_dependency("oo2core")
    assert path1 == path2
