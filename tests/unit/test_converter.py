"""Tests for file converter functionality."""

import pytest
from pathlib import Path

from src.core.signatures import detect_format


def test_detect_wem_format():
    header = b"RIFF\x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert ext == ".wem"


def test_detect_ogg_format():
    header = b"OggS\x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert ext == ".ogg"


def test_detect_usm_format():
    header = b"CRID\x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert ext == ".usm"


def test_detect_png_format():
    header = b"\x89PNG\r\n\x1a\n"
    name, ext = detect_format(header)
    assert ext == ".png"


def test_detect_dds_format():
    header = b"DDS \x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert ext == ".dds"


def test_detect_pkg_format():
    header = b"\x07\x00\x00\x00\x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert ext == ".pkg"


def test_detect_unknown_format():
    header = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    name, ext = detect_format(header)
    assert ext == ".bin"
