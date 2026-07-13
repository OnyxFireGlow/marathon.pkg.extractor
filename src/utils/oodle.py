"""
Oodle library manager for Marathon 2026 Package Extractor.
"""

import os
from ctypes import c_char_p, c_int, cdll, create_string_buffer
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("oodle")


class OodleManager:
    """
    Manages Oodle library loading and usage.
    Supports versions 8 and 9.
    """

    KNOWN_DLL_NAMES = [
        "oo2core_9_win64.dll",
        "oo2core_8_win64.dll",
        "oo2core_7_win64.dll",
    ]

    SEARCH_PATHS = [".", "./lib/", "../lib/"]

    def __init__(self, dll_path: Optional[str] = None, quiet: bool = True):
        """
        Initialize Oodle manager.

        Args:
            dll_path: Direct path to DLL. If None, auto-search.
            quiet: Suppress output messages.
        """
        self.quiet = quiet
        self.dll_path = None
        self._handle = None

        if dll_path and os.path.exists(dll_path):
            self._load_dll(dll_path)
        else:
            try:
                self._auto_find_dll()
            except FileNotFoundError:
                if quiet:
                    pass
                else:
                    raise

    def _auto_find_dll(self):
        """Auto-search for Oodle DLL in known locations."""
        for search_path in self.SEARCH_PATHS:
            for dll_name in self.KNOWN_DLL_NAMES:
                full_path = os.path.join(search_path, dll_name)
                if os.path.exists(full_path):
                    self._load_dll(full_path)
                    return

        for dll_name in self.KNOWN_DLL_NAMES:
            if os.path.exists(dll_name):
                self._load_dll(dll_name)
                return

        raise FileNotFoundError(
            "Oodle DLL not found.\n"
            "Place one of these files in ./lib/:\n"
            + "\n".join(f"  - {dll}" for dll in self.KNOWN_DLL_NAMES)
        )

    def _load_dll(self, path: str):
        """Loads DLL and checks for required functions."""
        try:
            self._handle = cdll.LoadLibrary(path)
        except OSError as e:
            raise OSError(f"Failed to load Oodle DLL from {path}: {e}")

        try:
            _ = self._handle.OodleLZ_Decompress
        except AttributeError:
            raise RuntimeError(f"Library {path} missing OodleLZ_Decompress")

        self.dll_path = path
        if not self.quiet:
            logger.info(f"Oodle DLL loaded: {os.path.basename(path)}")

    def decompress(self, data: bytes, output_size: Optional[int] = None) -> bytes:
        """Decompress Oodle-compressed data."""
        if output_size is None:
            output_size = max(len(data) * 4, 0x40000)

        output_buffer = create_string_buffer(output_size)

        result = self._handle.OodleLZ_Decompress(
            c_char_p(data),
            c_int(len(data)),
            output_buffer,
            c_int(output_size),
            c_int(0),
            c_int(0),
            c_int(0),
            None,
            None,
            None,
            None,
            None,
            None,
            c_int(3),
        )

        if result == 0:
            return data

        if result < 0:
            raise RuntimeError(f"Oodle decompression error: {result}")

        return output_buffer.raw[:result]

    @property
    def is_loaded(self) -> bool:
        """Check if library is loaded."""
        return self._handle is not None
