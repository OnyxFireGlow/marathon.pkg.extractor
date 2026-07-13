# src/core/__init__.py
"""Core modules for package extraction."""

from src.core.package import TigerPackage
from src.core.converter import convert_directory, convert_all_extracted, detect_format
from src.core.signatures import (
    detect_format as detect_signature,
    get_extension,
    is_known_format,
    get_known_formats,
)

__all__ = [
    "TigerPackage",
    "convert_directory",
    "convert_all_extracted",
    "detect_format",
    "get_extension",
    "is_known_format",
    "get_known_formats",
]
