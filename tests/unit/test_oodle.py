"""Tests for OodleManager."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.utils.oodle import OodleManager


def test_oodle_manager_init_with_path():
    """Test OodleManager initialization with explicit path."""
    with patch("src.utils.oodle.os.path.exists", return_value=True), \
         patch("src.utils.oodle.cdll") as mock_cdll:
        
        mock_dll = MagicMock()
        mock_cdll.LoadLibrary.return_value = mock_dll
        mock_dll.OodleLZ_Decompress = MagicMock()
        
        manager = OodleManager(dll_path="fake_path.dll", quiet=True)
        assert manager.dll_path == "fake_path.dll"


def test_oodle_manager_is_loaded():
    """Test is_loaded property."""
    with patch("src.utils.oodle.cdll") as mock_cdll:
        mock_dll = MagicMock()
        mock_cdll.LoadLibrary.return_value = mock_dll
        mock_dll.OodleLZ_Decompress = MagicMock()
        
        manager = OodleManager(dll_path="fake_path.dll", quiet=True)
        assert manager.is_loaded is True


def test_oodle_manager_not_loaded():
    """Test is_loaded when library not loaded."""
    with patch("src.utils.oodle.os.path.exists", return_value=False):
        manager = OodleManager(quiet=True)
        assert manager.is_loaded is False
