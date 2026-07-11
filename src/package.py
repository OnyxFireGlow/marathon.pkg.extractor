"""Модуль для парсинга и извлечения данных из .pkg файлов Tiger Engine."""

import binascii
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from multiprocessing import cpu_count
from pathlib import Path
from typing import Dict, List, Optional

from Crypto.Cipher import AES

from .utils.oodle import OodleManager

# ===== Вспомогательные функции =====


def _read_uint16(data: bytes, offset: int) -> int:
    """Чтение 16-битного беззнакового целого (little-endian)."""
    return int.from_bytes(data[offset : offset + 2], byteorder="little")


def _read_uint32(data: bytes, offset: int) -> int:
    """Чтение 32-битного беззнакового целого (little-endian)."""
    return int.from_bytes(data[offset : offset + 4], byteorder="little")


# ===== Структуры данных =====


@dataclass
class PackageHeader:
    """Заголовок пакета Tiger Engine."""

    package_id: int
    package_id_hex: str
    patch_id: int
    entry_table_offset: int
    entry_table_size: int
    block_table_offset: int
    block_table_size: int

    @property
    def entry_table_length(self) -> int:
        return self.entry_table_size * 0x16


@dataclass
class FileEntry:
    """Метаданные одного файла внутри пакета."""

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
    # Ссылка на исходную запись для извлечения
    _raw_a: int = field(repr=False)
    _raw_b: int = field(repr=False)
    _raw_c: int = field(repr=False)
    _raw_d: int = field(repr=False)


@dataclass
class BlockEntry:
    """Метаданные одного блока данных."""

    index: int
    offset: int
    size: int
    patch_id: int
    flags: int
    hash: bytes
    gcm_tag: bytes


# ===== Основной класс =====


class TigerPackage:
    """
    Парсер и экстрактор для .pkg файлов Tiger Engine.

    Основан на реверс-инжиниринге Destiny 2 и адаптирован для Marathon 2026.
    """

    BLOCK_SIZE = 0x40000  # 256 KB

    # Ключи шифрования из Destiny 2 (проверить для Marathon!)
    AES_KEY_0 = binascii.unhexlify("D62AB2C10CC01BC535DB7B8655C7DC3B")
    AES_KEY_1 = binascii.unhexlify("3A4A5D3673A660587E63E676E40892B5")

    def __init__(self, filepath: str, oodle_manager: OodleManager = None):
        """
        Args:
            filepath: Путь к .pkg файлу
            oodle_manager: Менеджер Oodle (если None — будет создан новый)
        """
        self.filepath = Path(filepath)
        self.filename = self.filepath.name
        self.base_name = self.filepath.stem

        self.header: Optional[PackageHeader] = None
        self.entries: List[FileEntry] = []
        self.blocks: List[BlockEntry] = []

        # Определяем Package ID из имени файла
        self._detect_package_id()

        # Загружаем или создаём Oodle менеджер
        self.oodle = oodle_manager or OodleManager()

        # Данные пакета и патчей
        self._main_data: Optional[bytes] = None
        self._patch_ids: List[int] = []
        self._patch_data: Dict[int, bytes] = {}

        # Nonce для AES
        self._nonce: Optional[bytes] = None

    def _detect_package_id(self):
        """Определяет Package ID из имени файла."""
        name = self.base_name

        # Формат: XXXX-XXXX_0.pkg или XXXX_en_0.pkg
        if "_en_" in name:
            self.package_id_str = name[-13:-9]
        else:
            self.package_id_str = name[-10:-6]

    def load(self) -> bool:
        """
        Загружает и парсит пакет.

        Returns:
            True при успешной загрузке
        """
        print(f"\n[·] Загрузка пакета: {self.filename}")

        # Читаем основной файл
        with open(self.filepath, "rb") as f:
            self._main_data = f.read()

        # Парсим заголовок
        self._parse_header()

        # Ищем все патчи
        self._find_patches()

        # Загружаем патчи
        print("[·] Загрузка патчей...")
        for patch_id in self._patch_ids:
            if patch_id == self.header.patch_id:
                self._patch_data[patch_id] = self._main_data
            else:
                patch_path = self._get_patch_path(patch_id)
                if patch_path.exists():
                    with open(patch_path, "rb") as f:
                        self._patch_data[patch_id] = f.read()
                else:
                    print(f"  [!] Патч не найден: {patch_path.name}")

        # Парсим таблицы
        self._parse_entry_table()
        self._parse_block_table()

        # Генерируем nonce
        self._generate_nonce()

        print(f"[✓] Загружено записей: {len(self.entries)}")
        print(f"[✓] Загружено блоков: {len(self.blocks)}")
        print(f"[✓] Доступно патчей: {len(self._patch_data)}")

        return True

    def _parse_header(self):
        """Парсинг заголовка пакета."""
        data = self._main_data

        self.header = PackageHeader(
            package_id=_read_uint16(data, 0x10),
            package_id_hex=binascii.hexlify(data[0x10:0x12]).decode().upper(),
            patch_id=_read_uint16(data, 0x30),
            entry_table_offset=_read_uint32(data, 0x44),
            entry_table_size=_read_uint32(data, 0x60),
            block_table_offset=_read_uint32(data, 0x6C),
            block_table_size=_read_uint32(data, 0x68),
        )

        print(f"  Package ID: 0x{self.header.package_id_hex}")
        print(f"  Patch ID: {self.header.patch_id}")
        print(f"  Entry table: {self.header.entry_table_size} entries")
        print(f"  Block table: {self.header.block_table_size} blocks")

    def _find_patches(self):
        """Находит все патчи для этого пакета в той же директории."""
        search_dir = self.filepath.parent

        self._patch_ids = []

        for file in search_dir.glob("*.pkg"):
            if self.package_id_str in file.name:
                try:
                    # Извлекаем ID патча из имени
                    parts = file.stem.split("_")
                    patch_id = int(parts[-1])
                    self._patch_ids.append(patch_id)
                except ValueError:
                    continue

        self._patch_ids.sort()

    def _get_patch_path(self, patch_id: int) -> Path:
        """Возвращает путь к файлу патча."""
        return self.filepath.parent / f"{self.base_name[:-2]}_{patch_id}.pkg"

    def _parse_entry_table(self):
        """Парсинг таблицы записей (файлов внутри пакета)."""
        self.entries = []

        offset = self.header.entry_table_offset

        for i in range(self.header.entry_table_size):
            pos = offset + i * 16  # каждая запись 16 байт

            entry_a = _read_uint32(self._main_data, pos)
            entry_b = _read_uint32(self._main_data, pos + 4)
            entry_c = _read_uint32(self._main_data, pos + 8)
            entry_d = _read_uint32(self._main_data, pos + 12)

            # Декодируем поля согласно спецификации
            ref_id = entry_a & 0x1FFF  # 13 бит
            ref_pkg_id = (entry_a >> 13) & 0x3FF  # 10 бит (с коррекцией)
            ref_unk = (entry_a >> 23) & 0x1FF  # 9 бит

            # Коррекция RefPackageID (из оригинального кода)
            ref_digits = ref_unk & 0x3
            if ref_digits == 1:
                ref_pkg_id = ref_pkg_id
            else:
                ref_pkg_id = ref_pkg_id | (0x100 << ref_digits)

            file_type = (entry_b >> 9) & 0x7F  # 7 бит
            file_subtype = (entry_b >> 6) & 0x7  # 3 бита

            starting_block = entry_c & 0x3FFF  # 14 бит
            starting_offset = ((entry_c >> 14) & 0x3FFF) << 4  # 14 бит со сдвигом

            file_size = ((entry_d & 0x3FFFFFF) << 4) | ((entry_c >> 28) & 0xF)  # 30 бит
            flags = (entry_d >> 26) & 0x3F  # 6 бит

            # Генерируем имя файла
            name = f"{self.header.package_id_hex}-{i:04X}"

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
                    _raw_a=entry_a,
                    _raw_b=entry_b,
                    _raw_c=entry_c,
                    _raw_d=entry_d,
                )
            )

    def _parse_block_table(self):
        """Парсинг таблицы блоков. Формат: 72 байта на блок (36 данные + 36 хеш/GCM)."""
        self.blocks = []

        offset = self.header.block_table_offset
        data_size = len(self._main_data)

        BLOCK_ENTRY_SIZE = 72  # 36 байт данные + 36 байт хеш/GCM

        for i in range(self.header.block_table_size):
            pos = offset + i * BLOCK_ENTRY_SIZE

            if pos + 36 > data_size:  # Нам нужны только первые 36 байт для данных
                print(f"[!] Блок {i} выходит за пределы файла")
                break

            data = self._main_data

            size_val = _read_uint32(data, pos)
            offset_val = _read_uint32(data, pos + 4)
            patch_val = _read_uint16(data, pos + 8)
            flags_val = _read_uint16(data, pos + 10)

            # Хеш/GCM часть (следующие 36 байт)
            hash_data = data[pos + 36 : pos + 72] if pos + 72 <= data_size else b""

            # Проверка валидности: offset должен быть в разумных пределах
            # Для аудио-пакетов offset обычно 0x40000 с флагом 0
            if offset_val > 0x20000000:  # больше 512 МБ — точно не offset
                continue

            # size должен быть больше 0
            if size_val == 0:
                continue

            block_entry = BlockEntry(
                index=i,
                size=size_val,
                offset=offset_val,
                patch_id=patch_val if patch_val in self._patch_ids else 0,
                flags=flags_val,
                hash=hash_data[:20] if len(hash_data) >= 20 else hash_data,
                gcm_tag=hash_data[20:36] if len(hash_data) >= 36 else b"",
            )

            self.blocks.append(block_entry)

        print(
            f"[·] Загружено блоков: {len(self.blocks)} (из {self.header.block_table_size} записей)"
        )

    def _detect_block_size(self) -> int | None:
        """Пытается определить размер записи в блочной таблице."""
        offset = self.header.block_table_offset
        available = len(self._main_data) - offset

        for bs in [48, 32, 64, 40]:
            entries_fit = available // bs
            if entries_fit == self.header.block_table_size:
                print(f"[·] Определён размер блока: {bs} байт")
                return bs

        return None

    def _generate_nonce(self):
        """Генерирует nonce для AES-GCM дешифровки."""
        nonce = bytearray(
            [
                0x84,
                0xDF,
                0x11,
                0xC0,
                0xAC,
                0xAB,
                0xFA,
                0x20,
                0x33,
                0x11,
                0x26,
                0x99,
            ]
        )

        package_id = self.header.package_id
        nonce[0] ^= (package_id >> 8) & 0xFF
        nonce[1] = 0xEA
        nonce[11] ^= package_id & 0xFF

        self._nonce = bytes(nonce)

    def extract_entry(self, entry: FileEntry) -> Optional[bytes]:
        """
        Извлекает и расшифровывает данные конкретной записи.
        """
        if entry.file_size == 0:
            return None

        current_block = entry.starting_block
        block_offset = entry.starting_block_offset

        # Вычисляем количество блоков для чтения
        total_size = block_offset + entry.file_size
        block_count = (total_size - 1) // self.BLOCK_SIZE
        last_block = current_block + block_count

        # Защита от бесконечного цикла
        max_iterations = 10000
        iterations = 0

        file_buffer = bytearray()

        while current_block <= last_block:
            iterations += 1
            if iterations > max_iterations:
                print(f"  [!] Превышено max_iterations для entry {entry.name}")
                break

            if current_block >= len(self.blocks):
                print(
                    f"  [!] Блок {current_block} за пределами таблицы (всего {len(self.blocks)})"
                )
                return None

            block = self.blocks[current_block]

            if block.patch_id not in self._patch_data:
                print(f"  [!] Отсутствует патч {block.patch_id}")
                return None

            patch_data = self._patch_data[block.patch_id]

            # Проверяем offset и size
            if block.offset >= len(patch_data):
                current_block += 1
                continue

            read_size = min(block.size, len(patch_data) - block.offset)
            block_data = patch_data[block.offset : block.offset + read_size]

            # Дешифровка (флаг 0x2)
            if block.flags & 0x2:
                key = self.AES_KEY_1 if (block.flags & 0x4) else self.AES_KEY_0
                cipher = AES.new(key, AES.MODE_GCM, nonce=self._nonce)
                block_data = cipher.decrypt(block_data)

            # Пробуем декомпрессию
            if block.flags & 0x1:
                try:
                    block_data = self.oodle.decompress(block_data)
                except RuntimeError:
                    pass  # Не сжато — используем как есть

            if current_block == entry.starting_block:
                file_buffer = bytearray(block_data[block_offset:])
            else:
                file_buffer.extend(block_data)

            current_block += 1

        return bytes(file_buffer[: entry.file_size])

    def get_entries_by_type(self, type_filter: int = None) -> List[FileEntry]:
        """
        Возвращает записи отфильтрованные по типу файла.

        Args:
            type_filter: ID типа (None — вернуть все)
        """
        if type_filter is None:
            return self.entries

        return [e for e in self.entries if e.file_type == type_filter]

    def extract_all(self, type_filter: int = None) -> Dict[str, bytes]:
        """
        Извлекает все файлы из пакета.

        Args:
            type_filter: Фильтр по типу (None — все файлы)

        Returns:
            Словарь {имя_файла: данные}
        """
        entries = self.get_entries_by_type(type_filter)
        results = {}

        total = len(entries)
        for idx, entry in enumerate(entries, 1):
            print(f"\r[·] Извлечение: {idx}/{total} ({idx * 100 // total}%)", end="")

            data = self.extract_entry(entry)
            if data is not None:
                results[entry.name] = data

        print()  # новая строка после прогресса
        return results

    def extract_all_parallel(
        self, type_filter: int = None, max_workers: int = None
    ) -> Dict[str, bytes]:
        """
        Извлекает все файлы из пакета параллельно.

        Args:
            type_filter: Фильтр по типу (None — все файлы)
            max_workers: Количество процессов (None — авто)

        Returns:
            Словарь {имя_файла: данные}
        """
        entries = self.get_entries_by_type(type_filter)

        if max_workers is None:
            max_workers = min(cpu_count(), 8)  # Не больше 8 для дисковой нагрузки

        print(f"[·] Запуск параллельного извлечения в {max_workers} процессов")
        print(f"[·] Всего записей: {len(entries)}")

        # Подготавливаем данные для воркеров
        # Сериализуем всё, что нужно (блоки, патч-данные, nonce, ключи)
        worker_data = {
            "blocks": [
                {
                    "offset": b.offset,
                    "size": b.size,
                    "patch_id": b.patch_id,
                    "flags": b.flags,
                }
                for b in self.blocks
            ],
            "patch_paths": {
                pid: self._get_patch_path(pid)
                if pid != self.header.patch_id
                else str(self.filepath)
                for pid in self._patch_ids
            },
            "block_size": self.BLOCK_SIZE,
            "nonce": self._nonce.hex(),
            "aes_key_0": self.AES_KEY_0.hex(),
            "aes_key_1": self.AES_KEY_1.hex(),
            "oodle_dll_path": self.oodle.dll_path if self.oodle else None,
        }

        results = {}
        completed = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Отправляем задачи пачками по 100 штук
            batch_size = 100
            futures = {}

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

                # Ждём завершения пачки
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        data = future.result()
                        if data is not None:
                            results[name] = data
                    except Exception as e:
                        print(f"\n  [!] Ошибка в {name}: {e}")

                    completed += 1
                    print(
                        f"\r[·] Извлечение: {completed}/{len(entries)} ({completed * 100 // len(entries)}%)",
                        end="",
                    )

                futures.clear()

        print()  # новая строка
        return results


def _extract_entry_worker(
    entry_index: int,
    entry_name: str,
    starting_block: int,
    starting_block_offset: int,
    file_size: int,
    worker_data: dict,
) -> Optional[bytes]:
    """
    Воркер для параллельного извлечения.
    Выполняется в отдельном процессе.
    """
    if file_size == 0:
        return None

    # Восстанавливаем объекты из сериализованных данных
    blocks = worker_data["blocks"]
    patch_paths = worker_data["patch_paths"]
    BLOCK_SIZE = worker_data["block_size"]
    nonce = bytes.fromhex(worker_data["nonce"])
    aes_key_0 = bytes.fromhex(worker_data["aes_key_0"])
    aes_key_1 = bytes.fromhex(worker_data["aes_key_1"])

    # Загружаем Oodle в этом процессе
    oodle = None
    if worker_data.get("oodle_dll_path"):
        oodle = OodleManager(worker_data["oodle_dll_path"])

    # Кеш для данных патчей (чтобы не перечитывать для каждой записи)
    patch_data_cache = {}

    def get_patch_data(patch_id: int) -> Optional[bytes]:
        if patch_id not in patch_data_cache:
            path = patch_paths.get(patch_id)
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    patch_data_cache[patch_id] = f.read()
            else:
                return None
        return patch_data_cache[patch_id]

    # Извлечение
    current_block = starting_block
    block_offset = starting_block_offset

    total_size = block_offset + file_size
    block_count = (total_size - 1) // BLOCK_SIZE
    last_block = current_block + block_count

    file_buffer = bytearray()

    while current_block <= last_block:
        if current_block >= len(blocks):
            return None

        block = blocks[current_block]
        patch_data = get_patch_data(block["patch_id"])

        if patch_data is None:
            return None

        if block["offset"] >= len(patch_data):
            current_block += 1
            continue

        read_size = min(block["size"], len(patch_data) - block["offset"])
        block_data = patch_data[block["offset"] : block["offset"] + read_size]

        # Дешифровка
        if block["flags"] & 0x2:
            key = aes_key_1 if (block["flags"] & 0x4) else aes_key_0
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            block_data = cipher.decrypt(block_data)

        # Декомпрессия
        if block["flags"] & 0x1 and oodle:
            try:
                block_data = oodle.decompress(block_data)
            except RuntimeError:
                pass

        if current_block == starting_block:
            file_buffer = bytearray(block_data[block_offset:])
        else:
            file_buffer.extend(block_data)

        current_block += 1

    return bytes(file_buffer[:file_size])
