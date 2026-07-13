"""Tests for file signatures detection."""

import pytest
from pathlib import Path

from src.core.signatures import (
    SIGNATURES,
    detect_format,
    get_extension,
    is_known_format,
    get_known_formats,
)


def test_wav_signature():
    """Test WAV file signature detection."""
    header = b"RIFF\x00\x00\x00\x00WAVEfmt "
    name, ext = detect_format(header)
    assert name == "WAV/WEM (WWise Audio)"
    assert ext == ".wem"


def test_ogg_signature():
    """Test Ogg Vorbis signature detection."""
    header = b"OggS\x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert name == "Ogg Vorbis"
    assert ext == ".ogg"


def test_png_signature():
    """Test PNG signature detection."""
    header = b"\x89PNG\r\n\x1a\n"
    name, ext = detect_format(header)
    assert name == "PNG Image"
    assert ext == ".png"


def test_dds_signature():
    """Test DDS signature detection."""
    header = b"DDS \x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert name == "DirectDraw Surface"
    assert ext == ".dds"


def test_usm_signature():
    """Test USM video signature detection."""
    header = b"CRID\x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert name == "CriWare USM Video"
    assert ext == ".usm"


def test_pkg_signature():
    """Test Tiger Package signature detection."""
    header = b"\x07\x00\x00\x00\x00\x00\x00\x00"
    name, ext = detect_format(header)
    assert name == "Tiger Package Header"
    assert ext == ".pkg"


def test_unknown_signature():
    """Test unknown signature handling."""
    header = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    name, ext = detect_format(header)
    assert name.startswith("Неизвестный")
    assert ext == ".bin"


def test_is_known_format():
    """Test is_known_format function."""
    assert is_known_format(b"RIFF") is True
    assert is_known_format(b"OggS") is True
    assert is_known_format(b"\x00\x01\x02\x03") is False


def test_get_extension():
    """Test get_extension function."""
    assert get_extension(b"RIFF") == ".wem"
    assert get_extension(b"OggS") == ".ogg"
    assert get_extension(b"CRID") == ".usm"


def test_get_known_formats():
    """Test get_known_formats returns correct dictionary."""
    formats = get_known_formats()
    assert isinstance(formats, dict)
    assert ".wem" in formats
    assert ".ogg" in formats
    assert ".png" in formats
    assert ".dds" in formats


def test_all_signatures_have_extension():
    """Test that all signatures have valid extensions."""
    for sig, (name, ext) in SIGNATURES.items():
        assert ext.startswith(".")
        assert len(ext) > 1
