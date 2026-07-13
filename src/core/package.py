"""
Module for parsing and extracting data from .pkg files.
"""


import mmap
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from multiprocessing import cpu_count
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Set

from Crypto.Cipher import AES
from tqdm import tqdm

from src.core.constants import (
    AES_KEYS,
    BLOCK_ENTRY_SIZE,
    BLOCK_SIZE,
    DEFAULT_CONFIG,
    BlockFlags,
    PkgOffsets,
)
from src.utils.logger import get_logger
from src.utils.oodle import OodleManager


@dataclass
class FileEntry:
    index: int
    name: str
    file_type: int
    file_subtype: int
    reference_id: int
    reference_package_id: int
    starting_block: int
    starting_block_offset: int
    file_size: int
    flags: int
    raw_a: int = field(repr=False)
    raw_b: int = field(repr=False)
    raw_c: int = field(repr=False)
    raw_d: int = field(repr=False)


@dataclass
class BlockEntry:
    index: int
    offset: int
    size: int
    patch_id: int
    flags: int
    gcm_tag: bytes


def _read_uint16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], byteorder="little")


def _read_uint32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], byteorder="little")


class TigerPackage:
    """Parser and extractor for Tiger Engine .pkg files."""

    AES_KEY_0 = AES_KEYS["KEY_0"]
    AES_KEY_1 = AES_KEYS["KEY_1"]

    def __init__(
        self,
        filepath: str | Path,
        oodle_manager: Optional[OodleManager] = None,
        verbose: bool = False,
        max_workers: Optional[int] = None,
    ):
        self.filepath = Path(filepath)
        self.filename = self.filepath.name
        self.base_name = self.filepath.stem
        self.verbose = verbose
        self.max_workers = max_workers or DEFAULT_CONFIG["max_workers"]

        self.logger = get_logger(
            f"pkg.{self.base_name}", "DEBUG" if verbose else "INFO"
        )

        self.header: Optional[Dict[str, Any]] = None
        self.entries: List[FileEntry] = []
        self.blocks: List[BlockEntry] = []
        self.package_id_str: str = ""

        self._file: Optional[BinaryIO] = None
        self._main_data: Optional[mmap.mmap] = None
        self._patch_data: Dict[int, bytes] = {}
        self._patch_ids: List[int] = []
        self._nonce: Optional[bytes] = None
        self._block_cache: Dict[int, bytes] = {}

        self.oodle = oodle_manager or OodleManager(quiet=True)
        self._detect_package_id()

    def __enter__(self):
        self.load()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        for key in list(self._patch_data.keys()):
            if isinstance(self._patch_data[key], mmap.mmap):
                self._patch_data[key].close()
        if self._main_data is not None:
            self._main_data.close()
            self._main_data = None
        if self._file is not None:
            self._file.close()
            self._file = None

    def _detect_package_id(self):
        name = self.base_name
        parts = name.split("_")

        hex_id = None
        for part in parts:
            if len(part) == 4 and all(c in "0123456789abcdefABCDEF" for c in part):
                hex_id = part
                break

        self.package_id_str = (
            hex_id.lower() if hex_id else parts[-3] if len(parts) >= 3 else parts[0]
        )
        self.logger.debug(f"Package ID string: {self.package_id_str}")

    def load(self) -> bool:
        """Loads the package using a memory-mapped file."""
        self.logger.info(f"Loading: {self.filename}")

        try:
            self._file = open(self.filepath, "rb")
            self._main_data = mmap.mmap(
                self._file.fileno(), 0, access=mmap.ACCESS_READ
            )

            self._parse_header()
            self._find_patches()
            self._load_patches()
            self._parse_entry_table()
            self._parse_block_table()
            self._generate_nonce()

            self.logger.info(
                f"Loaded: {len(self.entries)} entries, {len(self.blocks)} blocks"
            )
            return True

        except Exception as e:
            self.logger.error(f"Load error: {e}")
            self.close()
            return False

    def _parse_header(self):
        data = self._main_data

        self.header = {
            "package_id": _read_uint16(data, PkgOffsets.PACKAGE_ID),
            "package_id_hex": data[PkgOffsets.PACKAGE_ID : PkgOffsets.PACKAGE_ID + 2]
            .hex()
            .upper(),
            "patch_id": _read_uint16(data, PkgOffsets.PATCH_ID),
            "entry_table_offset": _read_uint32(data, PkgOffsets.ENTRY_TABLE_OFFSET),
            "entry_table_size": _read_uint32(data, PkgOffsets.ENTRY_TABLE_SIZE),
            "block_table_offset": _read_uint32(data, PkgOffsets.BLOCK_TABLE_OFFSET),
            "block_table_size": _read_uint32(data, PkgOffsets.BLOCK_TABLE_SIZE),
        }

        if self.verbose:
            self.logger.debug(f"Package ID: 0x{self.header['package_id_hex']}")
            self.logger.debug(f"Patch ID: {self.header['patch_id']}")
            self.logger.debug(f"Entry table: {self.header['entry_table_size']} entries")
            self.logger.debug(f"Block table: {self.header['block_table_size']} blocks")

    def _find_patches(self):
        search_dir = self.filepath.parent
        self._patch_ids = []

        for file in search_dir.glob("*.pkg"):
            if self.package_id_str in file.name:
                try:
                    parts = file.stem.split("_")
                    patch_id = int(parts[-1])
                    self._patch_ids.append(patch_id)
                except (ValueError, IndexError):
                    continue

        self._patch_ids.sort()
        self.logger.debug(f"Found {len(self._patch_ids)} patches")

    def _get_patch_path(self, patch_id: int) -> Path:
        return self.filepath.parent / f"{self.base_name[:-2]}_{patch_id}.pkg"

    def _load_patches(self):
        self._patch_data = {}

        for patch_id in self._patch_ids:
            if patch_id == self.header["patch_id"]:
                self._patch_data[patch_id] = self._main_data
            else:
                patch_path = self._get_patch_path(patch_id)
                if patch_path.exists():
                    with open(patch_path, "rb") as f:
                        self._patch_data[patch_id] = f.read()
                    self.logger.debug(f"Loaded patch: {patch_path.name}")

        self.logger.info(f"Loaded {len(self._patch_data)} patches")

    def _parse_entry_table(self):
        self.entries = []
        data = self._main_data
        offset = self.header["entry_table_offset"]
        entry_count = self.header["entry_table_size"]

        for i in range(entry_count):
            pos = offset + i * 16

            entry_a = _read_uint32(data, pos)
            entry_b = _read_uint32(data, pos + 4)
            entry_c = _read_uint32(data, pos + 8)
            entry_d = _read_uint32(data, pos + 12)

            ref_id = entry_a & 0x1FFF
            ref_pkg_id = (entry_a >> 13) & 0x3FF
            ref_unk = (entry_a >> 23) & 0x1FF

            ref_digits = ref_unk & 0x3
            if ref_digits != 1:
                ref_pkg_id = ref_pkg_id | (0x100 << ref_digits)

            file_type = (entry_b >> 9) & 0x7F
            file_subtype = (entry_b >> 6) & 0x7

            starting_block = entry_c & 0x3FFF
            starting_offset = ((entry_c >> 14) & 0x3FFF) << 4

            file_size = ((entry_d & 0x3FFFFFF) << 4) | ((entry_c >> 28) & 0xF)
            flags = (entry_d >> 26) & 0x3F

            name = f"{self.header['package_id_hex']}-{i:04X}"

            self.entries.append(
                FileEntry(
                    index=i,
                    name=name,
                    file_type=file_type,
                    file_subtype=file_subtype,
                    reference_id=ref_id,
                    reference_package_id=ref_pkg_id,
                    starting_block=starting_block,
                    starting_block_offset=starting_offset,
                    file_size=file_size,
                    flags=flags,
                    raw_a=entry_a,
                    raw_b=entry_b,
                    raw_c=entry_c,
                    raw_d=entry_d,
                )
            )

        self.logger.debug(f"Parsed {len(self.entries)} entries")

    def _parse_block_table(self):
        self.blocks = []
        data = self._main_data
        offset = self.header["block_table_offset"]
        block_count = self.header["block_table_size"]
        data_size = len(data)

        for i in range(block_count):
            pos = offset + i * BLOCK_ENTRY_SIZE
            if pos + BLOCK_ENTRY_SIZE > data_size:
                break

            offset_val = _read_uint32(data, pos)
            size_val = _read_uint32(data, pos + 4)
            patch_val = _read_uint16(data, pos + 8)
            flags_val = _read_uint16(data, pos + 10)
            gcm_tag = data[pos + 32 : pos + 48]

            if offset_val > 0x20000000 or size_val == 0:
                continue

            self.blocks.append(
                BlockEntry(
                    index=i,
                    offset=offset_val,
                    size=size_val,
                    patch_id=patch_val if patch_val in self._patch_ids else 0,
                    flags=flags_val,
                    gcm_tag=gcm_tag,
                )
            )

        self.logger.debug(f"Loaded {len(self.blocks)} blocks")

    def _generate_nonce(self):
        nonce = bytearray(
            [0x84, 0xDF, 0x11, 0xC0, 0xAC, 0xAB, 0xFA, 0x20, 0x33, 0x11, 0x26, 0x99]
        )

        package_id = self.header["package_id"]
        nonce[0] ^= (package_id >> 8) & 0xFF
        nonce[1] = 0xEA
        nonce[11] ^= package_id & 0xFF

        self._nonce = bytes(nonce)

        self._cipher_key0 = AES.new(self.AES_KEY_0, AES.MODE_GCM, nonce=self._nonce)
        self._cipher_key1 = AES.new(self.AES_KEY_1, AES.MODE_GCM, nonce=self._nonce)

    def _read_block(self, block_index: int) -> Optional[bytes]:
        if block_index in self._block_cache:
            return self._block_cache[block_index]

        if block_index >= len(self.blocks):
            return None

        block = self.blocks[block_index]

        if block.patch_id not in self._patch_data:
            return None

        patch_data = self._patch_data[block.patch_id]

        if block.offset >= len(patch_data):
            return None

        read_size = min(block.size, len(patch_data) - block.offset)
        block_data = patch_data[block.offset : block.offset + read_size]

        if block.flags & BlockFlags.ENCRYPTED:
            key = (
                self._cipher_key1
                if (block.flags & BlockFlags.USE_KEY_1)
                else self._cipher_key0
            )

            if len(block.gcm_tag) == 16 and block.gcm_tag != b"\x00" * 16:
                try:
                    block_data = key.decrypt_and_verify(block_data, block.gcm_tag)
                except (ValueError, KeyError):
                    return None
            else:
                block_data = key.decrypt(block_data)

        if block.flags & BlockFlags.COMPRESSED:
            if not self.oodle or not self.oodle.is_loaded:
                return None
            try:
                block_data = self.oodle.decompress(block_data, output_size=BLOCK_SIZE)
            except RuntimeError:
                return None

        self._block_cache[block_index] = block_data
        return block_data

    def extract_entry(self, entry: FileEntry) -> Optional[bytes]:
        if entry.file_size == 0:
            return None

        file_buffer = bytearray()
        current_offset = 0
        current_block = entry.starting_block

        while current_offset < entry.file_size:
            block_data = self._read_block(current_block)
            if block_data is None:
                return None

            remaining_bytes = entry.file_size - current_offset

            if current_block == entry.starting_block:
                block_start = entry.starting_block_offset
                block_remaining = len(block_data) - block_start
                copy_size = min(block_remaining, remaining_bytes)
                file_buffer.extend(block_data[block_start : block_start + copy_size])
                current_offset += copy_size
            elif remaining_bytes < len(block_data):
                file_buffer.extend(block_data[:remaining_bytes])
                current_offset += remaining_bytes
            else:
                file_buffer.extend(block_data)
                current_offset += len(block_data)

            current_block += 1

        return bytes(file_buffer)

    def extract_all(self, output_dir: Path) -> Dict[str, bytes]:
        """Extract all files sequentially, writing directly to disk."""
        results = {}
        total = len(self.entries)

        output_dir.mkdir(parents=True, exist_ok=True)

        with tqdm(
            total=total,
            desc="Extracting",
            unit="files",
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar:
            for entry in self.entries:
                data = self.extract_entry(entry)
                if data is not None:
                    file_path = output_dir / f"{entry.name}.bin"
                    file_path.write_bytes(data)
                    results[entry.name] = data
                pbar.update(1)

        return results

    def extract_all_sequential(self) -> Dict[str, bytes]:
        """Extract all files sequentially, keeping results in memory."""
        results = {}
        total = len(self.entries)

        with tqdm(
            total=total,
            desc="Extracting",
            unit="files",
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar:
            for entry in self.entries:
                data = self.extract_entry(entry)
                if data is not None:
                    results[entry.name] = data
                pbar.update(1)

        return results

    def _predict_blocks_needed(self) -> int:
        """Estimate how many unique blocks will be needed for all entries."""
        needed: Set[int] = set()
        for entry in self.entries:
            if entry.file_size == 0:
                continue
            current_block = entry.starting_block
            current_offset = 0
            while current_offset < entry.file_size:
                needed.add(current_block)
                current_offset += BLOCK_SIZE
                current_block += 1
        return len(needed)

    def extract_all_parallel(
        self,
        output_dir: Path,
        max_workers: Optional[int] = None,
    ) -> Dict[str, bytes]:
        """Extract all files in parallel using ThreadPoolExecutor."""
        if max_workers is None:
            max_workers = min(cpu_count(), self.max_workers)

        self.logger.info(
            f"Parallel extraction: {max_workers} workers, {len(self.entries)} entries"
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        results: Dict[str, bytes] = {}

        with tqdm(
            total=len(self.entries),
            desc="Extracting (parallel)",
            unit="files",
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self.extract_entry, entry): entry
                    for entry in self.entries
                }

                for future in as_completed(futures):
                    entry = futures[future]
                    try:
                        data = future.result(timeout=120)
                        if data is not None:
                            file_path = output_dir / f"{entry.name}.bin"
                            file_path.write_bytes(data)
                            results[entry.name] = data
                    except Exception as e:
                        self.logger.warning(f"Failed to extract {entry.name}: {e}")
                    pbar.update(1)

        self.logger.info(f"Extracted {len(results)} files")
        return results
