"""Tests for TigerPackage core functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.core.package import (
    TigerPackage,
    FileEntry,
    BlockEntry,
    _read_uint16,
    _read_uint32,
)


def test_read_uint16():
    """Test _read_uint16 function."""
    data = b"\x01\x00\x02\x00\x03\x00"
    assert _read_uint16(data, 0) == 1
    assert _read_uint16(data, 2) == 2
    assert _read_uint16(data, 4) == 3


def test_read_uint32():
    """Test _read_uint32 function."""
    data = b"\x01\x00\x00\x00\x02\x00\x00\x00"
    assert _read_uint32(data, 0) == 1
    assert _read_uint32(data, 4) == 2


def test_tiger_package_init():
    """Test TigerPackage initialization."""
    with patch("src.core.package.OodleManager"):
        pkg = TigerPackage("test.pkg")
        assert pkg.filepath == Path("test.pkg")


def test_tiger_package_detect_package_id():
    """Test package ID detection from filename."""
    with patch("src.core.package.OodleManager"):
        pkg = TigerPackage("game_audio_1234_01.pkg")
        assert pkg.package_id_str == "1234"


def test_file_entry_dataclass():
    """Test FileEntry dataclass structure."""
    entry = FileEntry(
        index=0,
        name="test",
        file_type=1,
        file_subtype=0,
        reference_id=0,
        reference_package_id=0,
        starting_block=0,
        starting_block_offset=0,
        file_size=1024,
        flags=0,
        raw_a=0,
        raw_b=0,
        raw_c=0,
        raw_d=0,
    )
    assert entry.index == 0
    assert entry.name == "test"
    assert entry.file_size == 1024


def test_block_entry_dataclass():
    """Test BlockEntry dataclass structure."""
    entry = BlockEntry(
        index=0,
        offset=1024,
        size=2048,
        patch_id=1,
        flags=0,
        gcm_tag=b"\x00" * 16,
    )
    assert entry.offset == 1024
    assert entry.size == 2048
    assert entry.patch_id == 1



