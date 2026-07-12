"""
Module for parsing and extracting data from .pkg files.
"""

import mmap
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from multiprocessing import cpu_count
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _read_uint16(data: bytes | mmap.mmap, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], byteorder="little")


def _read_uint32(data: bytes | mmap.mmap, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], byteorder="little")


def _extract_entry_worker(
    entry_index: int,
    entry_name: str,
    starting_block: int,
    starting_block_offset: int,
    file_size: int,
    worker_data: dict,
) -> Optional[bytes]:
    """
    Worker for parallel extraction.
    Runs in separate process - NO OUTPUT to avoid spam.
    """
    import os

    from Crypto.Cipher import AES

    if file_size == 0:
        return None

    blocks = worker_data["blocks"]
    patch_data = {
        pid: bytes.fromhex(data) for pid, data in worker_data["patch_data"].items()
    }
    block_size = worker_data["block_size"]
    nonce = bytes.fromhex(worker_data["nonce"])
    aes_key_0 = bytes.fromhex(worker_data["aes_key_0"])
    aes_key_1 = bytes.fromhex(worker_data["aes_key_1"])

    # Load Oodle silently
    oodle = None
    dll_path = worker_data.get("oodle_dll_path")
    if dll_path and os.path.exists(dll_path):
        try:
            # Use quiet=True to suppress output
            from src.utils.oodle import OodleManager

            oodle = OodleManager(dll_path, quiet=True)
        except Exception:
            pass

    def read_block(block_index: int) -> Optional[bytes]:
        if block_index >= len(blocks):
            return None

        block = blocks[block_index]

        if block["patch_id"] not in patch_data:
            return None

        patch = patch_data[block["patch_id"]]

        if block["offset"] >= len(patch):
            return None

        read_size = min(block["size"], len(patch) - block["offset"])
        block_data = patch[block["offset"] : block["offset"] + read_size]

        if block["flags"] & 0x2:
            key = aes_key_1 if (block["flags"] & 0x4) else aes_key_0
            gcm_tag = bytes.fromhex(block.get("gcm_tag", ""))

            if len(gcm_tag) == 16 and gcm_tag != b"\x00" * 16:
                try:
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                    block_data = cipher.decrypt_and_verify(block_data, gcm_tag)
                except ValueError:
                    return None
            else:
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                block_data = cipher.decrypt(block_data)

        if block["flags"] & 0x1 and oodle:
            try:
                block_data = oodle.decompress(block_data, output_size=block_size)
            except RuntimeError:
                return None

        return block_data

    file_buffer = bytearray()
    current_offset = 0
    current_block = starting_block

    while current_offset < file_size:
        block_data = read_block(current_block)
        if block_data is None:
            return None

        remaining_bytes = file_size - current_offset

        if current_block == starting_block:
            block_start = starting_block_offset
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


class TigerPackage:
    """Парсер и экстрактор для .pkg файлов Tiger Engine."""

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

        self._main_data: Optional[mmap.mmap] = None
        self._patch_data: Dict[int, bytes] = {}
        self._patch_ids: List[int] = []
        self._nonce: Optional[bytes] = None

        self.oodle = oodle_manager or OodleManager(quiet=True)
        self._detect_package_id()

    def _detect_package_id(self):
        """Определяет Package ID из имени файла."""
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
        """Загружает пакет с использованием memory-mapped файла."""
        self.logger.info(f"Loading: {self.filename}")

        try:
            with open(self.filepath, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    self._main_data = mm
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
            return False

    def _parse_header(self):
        """Парсинг заголовка пакета."""
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
        """Находит все патчи для этого пакета."""
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
        """Загружает данные патчей."""
        self._patch_data = {}

        for patch_id in self._patch_ids:
            if patch_id == self.header["patch_id"]:
                self._patch_data[patch_id] = bytes(self._main_data)
            else:
                patch_path = self._get_patch_path(patch_id)
                if patch_path.exists():
                    with open(patch_path, "rb") as f:
                        self._patch_data[patch_id] = f.read()
                    self.logger.debug(f"Loaded patch: {patch_path.name}")

        self.logger.info(f"Loaded {len(self._patch_data)} patches")

    def _parse_entry_table(self):
        """Парсинг таблицы записей."""
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
        """Парсинг таблицы блоков."""
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
        """Генерирует nonce для AES-GCM."""
        nonce = bytearray(
            [0x84, 0xDF, 0x11, 0xC0, 0xAC, 0xAB, 0xFA, 0x20, 0x33, 0x11, 0x26, 0x99]
        )

        package_id = self.header["package_id"]
        nonce[0] ^= (package_id >> 8) & 0xFF
        nonce[1] = 0xEA
        nonce[11] ^= package_id & 0xFF

        self._nonce = bytes(nonce)

    def _read_block(self, block_index: int) -> Optional[bytes]:
        """Читает и обрабатывает один блок."""
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
                self.AES_KEY_1
                if (block.flags & BlockFlags.USE_KEY_1)
                else self.AES_KEY_0
            )

            if len(block.gcm_tag) == 16 and block.gcm_tag != b"\x00" * 16:
                try:
                    cipher = AES.new(key, AES.MODE_GCM, nonce=self._nonce)
                    block_data = cipher.decrypt_and_verify(block_data, block.gcm_tag)
                except ValueError:
                    return None
            else:
                cipher = AES.new(key, AES.MODE_GCM, nonce=self._nonce)
                block_data = cipher.decrypt(block_data)

        if block.flags & BlockFlags.COMPRESSED:
            if not self.oodle or not self.oodle.is_loaded:
                return None
            try:
                block_data = self.oodle.decompress(block_data, output_size=BLOCK_SIZE)
            except RuntimeError:
                return None

        return block_data

    def extract_entry(self, entry: FileEntry) -> Optional[bytes]:
        """Извлекает данные конкретной записи."""
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

    def get_entries_by_type(self, type_filter: Optional[int] = None) -> List[FileEntry]:
        if type_filter is None:
            return self.entries
        return [e for e in self.entries if e.file_type == type_filter]

    def extract_all(self, type_filter: Optional[int] = None) -> Dict[str, bytes]:
        """Извлекает все файлы последовательно."""
        entries = self.get_entries_by_type(type_filter)
        results = {}
        total = len(entries)

        with tqdm(
            total=total,
            desc="Extracting",
            unit="files",
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        ) as pbar:
            for entry in entries:
                data = self.extract_entry(entry)
                if data is not None:
                    results[entry.name] = data
                pbar.update(1)

        return results

    def extract_all_parallel(
        self,
        type_filter: Optional[int] = None,
        max_workers: Optional[int] = None,
    ) -> Dict[str, bytes]:
        """Extracts all files in parallel."""
        entries = self.get_entries_by_type(type_filter)

        if max_workers is None:
            max_workers = min(cpu_count(), self.max_workers)

        self.logger.info(
            f"Parallel extraction: {max_workers} workers, {len(entries)} entries"
        )

        worker_data = {
            "blocks": [
                {
                    "offset": b.offset,
                    "size": b.size,
                    "patch_id": b.patch_id,
                    "flags": b.flags,
                    "gcm_tag": b.gcm_tag.hex(),
                }
                for b in self.blocks
            ],
            "patch_data": {pid: data.hex() for pid, data in self._patch_data.items()},
            "block_size": BLOCK_SIZE,
            "nonce": self._nonce.hex(),
            "aes_key_0": self.AES_KEY_0.hex(),
            "aes_key_1": self.AES_KEY_1.hex(),
            "oodle_dll_path": str(self.oodle.dll_path)
            if self.oodle and self.oodle.dll_path
            else None,
        }

        results = {}
        batch_size = DEFAULT_CONFIG["batch_size"]
        futures = {}

        # Single progress bar for all workers
        with tqdm(
            total=len(entries),
            desc="Extracting (parallel)",
            unit="files",
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            position=0,
            leave=True,
        ) as pbar:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                for i in range(0, len(entries), batch_size):
                    batch = entries[i : i + batch_size]

                    for entry in batch:
                        future = executor.submit(
                            _extract_entry_worker,
                            entry_index=entry.index,
                            entry_name=entry.name,
                            starting_block=entry.starting_block,
                            starting_block_offset=entry.starting_block_offset,
                            file_size=entry.file_size,
                            worker_data=worker_data,
                        )
                        futures[future] = entry.name

                    for future in as_completed(futures):
                        name = futures[future]
                        try:
                            data = future.result(timeout=120)
                            if data is not None:
                                results[name] = data
                        except Exception as e:
                            self.logger.warning(f"Failed to extract {name}: {e}")
                        pbar.update(1)

                    futures.clear()

        self.logger.info(f"Extracted {len(results)} files")
        return results
