"""
Валидация AES-GCM ключей для Marathon 2026 .pkg файлов.
Проверяет корректность ключей тремя независимыми способами:
  1. GCM authentication tag
  2. Magic bytes после дешифровки
  3. Энтропийный анализ
Также умеет сканировать .exe на предмет потенциальных ключей.

Основан на структурах из tiger-pkg (Rust):
  BlockHeader: 48 байт
    +0x00: offset (u32)
    +0x04: size (u32)
    +0x08: patch_id (u16)
    +0x0A: flags (u16)
    +0x0C: hash (20 байт)
    +0x20: gcm_tag (16 байт)
"""

import binascii
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Optional

from Crypto.Cipher import AES
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Ключи по умолчанию (из Destiny 2 — подтверждены tiger-pkg для Marathon)
DEFAULT_KEYS = {
    "KEY_0": binascii.unhexlify("D62AB2C10CC01BC535DB7B8655C7DC3B"),
    "KEY_1": binascii.unhexlify("3A4A5D3673A660587E63E676E40892B5"),
}

# Magic bytes, которые должны появиться после успешной дешифровки
MAGIC_SIGNATURES = {
    b"RIFF": "WAV/WEM (WWise)",
    b"OggS": "Ogg Vorbis",
    b"\x89PNG": "PNG",
    b"DDS ": "DDS texture",
    b"BKHD": "WWise SoundBank",
    b"AKBK": "WWise Audio Bank",
    b"ftyp": "MP4 video",
    b"\x07\x00\x00\x00": "Nested Tiger Package v7",
    b"\x09\x00\x00\x00": "Nested Tiger Package v9",
    b"\x0a\x00\x00\x00": "Nested Tiger Package v10",
    b"\x1f\x8b": "GZip",
    b"\x78\x9c": "zlib/DEFLATE",
    b"\x28\xb5\x2f\xfd": "Zstandard",
    b"ID3": "MP3 (ID3)",
}


def _read_uint16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def _read_uint32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def calculate_entropy(data: bytes) -> float:
    """Энтропия Шеннона (0..8 бит/байт)."""
    if not data:
        return 0.0
    freq = Counter(data)
    length = len(data)
    return -sum((c / length) * math.log2(c / length) for c in freq.values())


def generate_nonce(package_id: int) -> bytes:
    """
    Генерация nonce для AES-GCM.
    Формула подтверждена tiger-pkg (см. PkgGcmState::shift_nonce).
    """
    nonce = bytearray(
        [0x84, 0xDF, 0x11, 0xC0, 0xAC, 0xAB, 0xFA, 0x20, 0x33, 0x11, 0x26, 0x99]
    )
    nonce[0] ^= (package_id >> 8) & 0xFF
    nonce[1] = 0xEA  # Для Marathon/D2 Beyond Light+
    nonce[11] ^= package_id & 0xFF
    return bytes(nonce)


class KeyValidator:
    """
    Проверяет валидность AES-GCM ключей на .pkg файле.

    Структура BlockHeader (48 байт, из tiger-pkg):
        offset:    u32 @ +0x00
        size:      u32 @ +0x04
        patch_id:  u16 @ +0x08
        flags:     u16 @ +0x0A
        hash:      [u8; 20] @ +0x0C
        gcm_tag:   [u8; 16] @ +0x20
    """

    BLOCK_ENTRY_SIZE = 48  # Подтверждено tiger-pkg

    def __init__(self, pkg_path: Path, keys: Optional[dict] = None):
        self.pkg_path = pkg_path
        self.keys = keys or DEFAULT_KEYS.copy()
        self.data: Optional[bytes] = None
        self.package_id: Optional[int] = None
        self.nonce: Optional[bytes] = None
        self.blocks: list = []

    # ----------------------------------------------------------
    # Загрузка
    # ----------------------------------------------------------
    def load(self) -> bool:
        """Загружает .pkg и парсит заголовок + таблицу блоков."""
        console.print(f"[dim]Загрузка {self.pkg_path.name}...[/dim]")
        self.data = self.pkg_path.read_bytes()

        # Парсим заголовок
        self.package_id = _read_uint16(self.data, 0x10)
        patch_id = _read_uint16(self.data, 0x30)

        # === ДИАГНОСТИКА ЗАГОЛОВКА ===
        console.print(
            "\n[bold yellow]ДИАГНОСТИКА ЗАГОЛОВКА (первые 0x80 байт):[/bold yellow]"
        )
        header_hex = self.data[:0x80].hex(" ")
        for i in range(0, 0x80, 16):
            console.print(f"  [dim]{i:04X}:[/dim] {header_hex[i * 3 : (i + 16) * 3]}")

        # Показываем ключевые значения
        console.print("\n[bold]Ключевые значения заголовка:[/bold]")
        for offset in [0x10, 0x30, 0x44, 0x48, 0x60, 0x64, 0x68, 0x6C, 0x70]:
            val16 = _read_uint16(self.data, offset)
            val32 = _read_uint32(self.data, offset)
            console.print(
                f"  [cyan]0x{offset:02X}:[/cyan] u16=0x{val16:04X} ({val16}), u32=0x{val32:08X} ({val32})"
            )

        # Пробуем разные смещения для block_table_offset и block_table_size
        console.print("\n[bold]Поиск block_table_offset и block_table_size:[/bold]")

        bt_offset = _read_uint32(self.data, 0x6C)
        bt_size = _read_uint32(self.data, 0x68)

        if bt_offset > 0 and bt_size > 0:
            console.print(
                f"\n[bold]Сырые данные первых 3 блоков (block_table_offset=0x{bt_offset:X}):[/bold]"
            )
            for i in range(min(3, bt_size)):
                pos = bt_offset + i * 48
                raw = self.data[pos : pos + 48]
                console.print(f"\n  [cyan]Блок {i} (0x{pos:08X}):[/cyan]")
                console.print(f"    hex: {raw.hex(' ')}")

                # Пробуем интерпретировать как разные структуры
                # Вариант A: offset@+0, size@+4, patch@+8, flags@+10
                a_offset = _read_uint32(raw, 0)
                a_size = _read_uint32(raw, 4)
                a_patch = _read_uint16(raw, 8)
                a_flags = _read_uint16(raw, 10)
                console.print(
                    f"    [Вариант A +0] offset=0x{a_offset:08X} size=0x{a_size:08X} patch={a_patch} flags=0x{a_flags:04X}"
                )

                # Вариант B: offset@+4, size@+8, patch@+12, flags@+14 (Destiny 2)
                b_offset = _read_uint32(raw, 4)
                b_size = _read_uint32(raw, 8)
                b_patch = _read_uint16(raw, 12)
                b_flags = _read_uint16(raw, 14)
                console.print(
                    f"    [Вариант B +4] offset=0x{b_offset:08X} size=0x{b_size:08X} patch={b_patch} flags=0x{b_flags:04X}"
                )

                # GCM tag в разных местах
                console.print(f"    GCM@+36..+52: {raw[36:52].hex(' ')}")
                console.print(f"    GCM@+32..+48: {raw[32:48].hex(' ')}")

        # Известные смещения для разных версий
        candidates = [
            (0x44, 0x60),  # entry_table_offset, entry_table_size
            (0x6C, 0x68),  # block_table_offset, block_table_size (Destiny 2)
            (0x68, 0x6C),  # поменяны местами?
            (0x64, 0x68),  # другой вариант
            (0x68, 0x64),  # ещё вариант
        ]

        for off_offset, off_size in candidates:
            bt_offset = _read_uint32(self.data, off_offset)
            bt_size = _read_uint32(self.data, off_size)

            if (
                bt_size > 0
                and bt_size < 100000
                and bt_offset > 0
                and bt_offset < len(self.data)
            ):
                # Проверяем, что по этому смещению что-то похожее на блоки
                if bt_offset + bt_size * 48 <= len(self.data):
                    sample = self.data[bt_offset : bt_offset + 48]
                    sample_offset = _read_uint32(sample, 4)
                    sample_size = _read_uint32(sample, 8)

                    console.print(
                        f"  offset=0x{off_offset:02X}, size=0x{off_size:02X}: "
                        f"bt_offset=0x{bt_offset:X} bt_size={bt_size} "
                        f"sample: offset=0x{sample_offset:X} size=0x{sample_size:X}"
                    )

        console.print()
        # === КОНЕЦ ДИАГНОСТИКИ ===

        # Пока используем старые смещения
        block_table_offset = _read_uint32(self.data, 0x6C)
        block_table_size = _read_uint32(self.data, 0x68)

        self.nonce = generate_nonce(self.package_id)

        # Информация о пакете
        table = Table(title=f"📦 {self.pkg_path.name}", show_header=False)
        table.add_column(style="cyan")
        table.add_column(style="green")
        table.add_row("Package ID", f"0x{self.package_id:04X}")
        table.add_row("Patch ID", str(patch_id))
        table.add_row("Nonce", self.nonce.hex().upper())
        table.add_row("Блоков в таблице", f"{block_table_size:,}")
        console.print(table)

        # Парсим таблицу блоков (48 байт на блок)
        for i in range(block_table_size):
            pos = block_table_offset + i * self.BLOCK_ENTRY_SIZE
            if pos + self.BLOCK_ENTRY_SIZE > len(self.data):
                break

            offset_val = _read_uint32(self.data, pos)
            size_val = _read_uint32(self.data, pos + 4)
            patch_val = _read_uint16(self.data, pos + 8)
            flags_val = _read_uint16(self.data, pos + 10)
            gcm_tag = self.data[pos + 32 : pos + 48]

            # Валидация offset и size
            if offset_val > 0x20000000 or size_val == 0:
                continue
            if offset_val + size_val > len(self.data):
                continue

            self.blocks.append(
                {
                    "index": i,
                    "offset": offset_val,
                    "size": size_val,
                    "patch_id": patch_val,
                    "flags": flags_val,
                    "gcm_tag": gcm_tag,
                }
            )

        console.print(
            f"[bold]Валидных блоков:[/bold] [green]{len(self.blocks):,}[/green]"
        )

        # Диагностика флагов
        flag_counts = Counter(b["flags"] for b in self.blocks)
        encrypted = sum(1 for b in self.blocks if b["flags"] & 0x2)
        compressed = sum(1 for b in self.blocks if b["flags"] & 0x1)

        console.print(
            f"[dim]Распределение флагов: {dict(sorted(flag_counts.items()))}[/dim]"
        )
        console.print(f"[dim]Зашифрованных (0x2): {encrypted}[/dim]")
        console.print(f"[dim]Сжатых (0x1): {compressed}[/dim]")

        return len(self.blocks) > 0

    def _get_encrypted_blocks(self, limit: int) -> list:
        """Возвращает зашифрованные блоки (флаг 0x2)."""
        return [b for b in self.blocks if b["flags"] & 0x2][:limit]

    # ----------------------------------------------------------
    # Проверка №1: GCM tag
    # ----------------------------------------------------------
    def validate_gcm_tag(self, limit: int = 50) -> dict:
        console.print(Panel("[bold]Проверка №1: GCM authentication tag[/bold]"))

        encrypted_blocks = self._get_encrypted_blocks(limit)
        if not encrypted_blocks:
            console.print("[yellow]Зашифрованных блоков не найдено[/yellow]")
            console.print(
                "[dim]Возможно, пакет не содержит зашифрованных данных.[/dim]"
            )
            console.print(
                "[dim]Попробуйте другой .pkg файл (например, audio или video).[/dim]"
            )
            return {"tested": 0, "valid": 0, "invalid": 0, "samples": []}

        console.print(
            f"[dim]Проверяем {len(encrypted_blocks)} зашифрованных блоков...[/dim]"
        )

        results = {"tested": 0, "valid": 0, "invalid": 0, "samples": []}

        for block in encrypted_blocks:
            block_data = self.data[block["offset"] : block["offset"] + block["size"]]
            if len(block_data) < 16:
                continue

            key = self.keys["KEY_1"] if (block["flags"] & 0x4) else self.keys["KEY_0"]
            key_name = "KEY_1" if (block["flags"] & 0x4) else "KEY_0"

            # Способ A: GCM-тег из таблицы блоков
            tag_from_table = block["gcm_tag"]
            if len(tag_from_table) == 16 and tag_from_table != b"\x00" * 16:
                try:
                    cipher = AES.new(key, AES.MODE_GCM, nonce=self.nonce)
                    plaintext = cipher.decrypt_and_verify(block_data, tag_from_table)
                    results["tested"] += 1
                    results["valid"] += 1
                    results["samples"].append(
                        {
                            "block": block["index"],
                            "status": "✓ GCM tag verified",
                            "key": key_name,
                            "preview": plaintext[:32],
                        }
                    )
                    continue
                except (ValueError, KeyError):
                    pass

            # Способ B: decrypt без verify, ищем magic
            try:
                cipher = AES.new(key, AES.MODE_GCM, nonce=self.nonce)
                plaintext = cipher.decrypt(block_data)
            except Exception:
                results["tested"] += 1
                results["invalid"] += 1
                continue

            has_magic = any(plaintext.startswith(m) for m in MAGIC_SIGNATURES)

            results["tested"] += 1
            if has_magic:
                results["valid"] += 1
                results["samples"].append(
                    {
                        "block": block["index"],
                        "status": "✓ Magic found (no tag verify)",
                        "key": key_name,
                        "preview": plaintext[:32],
                    }
                )
            else:
                results["invalid"] += 1
                if len(results["samples"]) < 3:
                    results["samples"].append(
                        {
                            "block": block["index"],
                            "status": "✗ No magic",
                            "key": key_name,
                            "preview": plaintext[:32],
                        }
                    )

        self._print_gcm_results(results)
        return results

    def _print_gcm_results(self, results: dict):
        table = Table(title="Результаты GCM-проверки")
        table.add_column("Метрика", style="cyan")
        table.add_column("Значение", style="green", justify="right")
        table.add_row("Проверено блоков", str(results["tested"]))
        table.add_row("Валидных", f"[green]{results['valid']}[/green]")
        table.add_row("Невалидных", f"[red]{results['invalid']}[/red]")
        rate = results["valid"] * 100 // max(results["tested"], 1)
        color = "green" if rate > 0 else "red"
        table.add_row("Успешность", f"[{color}]{rate}%[/{color}]")
        console.print(table)

        if results["samples"]:
            console.print("\n[bold]Примеры:[/bold]")
            for s in results["samples"][:5]:
                color = "green" if "✓" in s["status"] else "red"
                console.print(
                    f"  Блок #{s['block']} [{s.get('key', '?')}]: "
                    f"[{color}]{s['status']}[/{color}]"
                )
                if "preview" in s:
                    console.print(f"    [dim]{s['preview'][:32].hex(' ')}[/dim]")

    # ----------------------------------------------------------
    # Проверка №2: Magic bytes
    # ----------------------------------------------------------
    def validate_magic_bytes(self, limit: int = 100) -> dict:
        console.print(Panel("[bold]Проверка №2: Magic bytes после дешифровки[/bold]"))

        encrypted_blocks = self._get_encrypted_blocks(limit)
        found_magics = Counter()
        samples = []

        for block in encrypted_blocks:
            block_data = self.data[block["offset"] : block["offset"] + block["size"]]
            key = self.keys["KEY_1"] if (block["flags"] & 0x4) else self.keys["KEY_0"]

            try:
                cipher = AES.new(key, AES.MODE_GCM, nonce=self.nonce)
                plaintext = cipher.decrypt(block_data)
            except Exception:
                continue

            for magic, name in MAGIC_SIGNATURES.items():
                if plaintext.startswith(magic):
                    found_magics[name] += 1
                    if len(samples) < 5:
                        samples.append(
                            {
                                "block": block["index"],
                                "magic": name,
                                "preview": plaintext[:32],
                            }
                        )
                    break

        table = Table(title="Найденные сигнатуры")
        table.add_column("Формат", style="cyan")
        table.add_column("Найдено", style="green", justify="right")
        if found_magics:
            for name, count in found_magics.most_common():
                table.add_row(name, str(count))
        else:
            table.add_row("[red]Ничего не найдено[/red]", "0")
        console.print(table)

        if samples:
            console.print("\n[bold]Примеры:[/bold]")
            for s in samples:
                console.print(f"  Блок #{s['block']}: [green]{s['magic']}[/green]")
                console.print(f"    [dim]{s['preview'].hex(' ')}[/dim]")

        return {"found": dict(found_magics), "samples": samples}

    # ----------------------------------------------------------
    # Проверка №3: Энтропия
    # ----------------------------------------------------------
    def validate_entropy(self, limit: int = 50) -> dict:
        console.print(Panel("[bold]Проверка №3: Энтропийный анализ[/bold]"))

        encrypted_blocks = self._get_encrypted_blocks(limit)

        if not encrypted_blocks:
            console.print("[yellow]Нет зашифрованных блоков для анализа[/yellow]")
            return {"before": 0, "after": 0, "drop": 0}

        # Берем до 20 блоков для анализа
        sample_blocks = encrypted_blocks[:20]
        entropies_before = []
        entropies_after = []

        for block in sample_blocks:
            block_data = self.data[block["offset"] : block["offset"] + block["size"]]
            entropies_before.append(calculate_entropy(block_data))

            key = self.keys["KEY_1"] if (block["flags"] & 0x4) else self.keys["KEY_0"]
            try:
                cipher = AES.new(key, AES.MODE_GCM, nonce=self.nonce)
                plaintext = cipher.decrypt(block_data)
                entropies_after.append(calculate_entropy(plaintext))
            except Exception:
                entropies_after.append(0)

        avg_before = (
            sum(entropies_before) / len(entropies_before) if entropies_before else 0
        )
        avg_after = (
            sum(entropies_after) / len(entropies_after) if entropies_after else 0
        )

        table = Table(title="Энтропия (бит/байт)")
        table.add_column("Метрика", style="cyan")
        table.add_column("До дешифровки", style="yellow", justify="right")
        table.add_column("После дешифровки", style="green", justify="right")
        table.add_row("Средняя", f"{avg_before:.3f}", f"{avg_after:.3f}")
        if entropies_before:
            table.add_row(
                "Мин", f"{min(entropies_before):.3f}", f"{min(entropies_after):.3f}"
            )
            table.add_row(
                "Макс", f"{max(entropies_before):.3f}", f"{max(entropies_after):.3f}"
            )
        console.print(table)

        drop = avg_before - avg_after
        console.print(f"\nПадение энтропии: [bold]{drop:.3f} бит/байт[/bold]")
        if drop < 0.1:
            console.print(
                "[red]⚠ Энтропия не упала — ключи скорее всего неверные[/red]"
            )
        elif drop < 0.5:
            console.print(
                "[yellow]⚠ Небольшое падение — возможно, ключи частично верные[/yellow]"
            )
        else:
            console.print(
                "[green]✓ Значительное падение — ключи выглядят корректно[/green]"
            )

        return {"before": avg_before, "after": avg_after, "drop": drop}

    # ----------------------------------------------------------
    # Полный валидатор
    # ----------------------------------------------------------
    def full_validate(self) -> dict:
        """Запускает все три проверки и выдаёт вердикт."""
        if not self.load():
            console.print("[red]Не удалось загрузить .pkg файл[/red]")
            return {"verdict": "ERROR"}

        console.print()
        gcm_result = self.validate_gcm_tag()
        console.print()
        magic_result = self.validate_magic_bytes()
        console.print()
        entropy_result = self.validate_entropy()
        console.print()

        # Итоговый вердикт
        console.print(Panel("[bold]ИТОГОВЫЙ ВЕРДИКТ[/bold]", style="bold"))

        verdicts = []
        if gcm_result.get("valid", 0) > 0:
            verdicts.append("[green]✓ GCM-теги сходятся — ключи ТОЧНО верные[/green]")
        if magic_result.get("found"):
            verdicts.append("[green]✓ Magic bytes найдены — ключи верные[/green]")
        if entropy_result.get("drop", 0) > 0.5:
            verdicts.append("[green]✓ Энтропия падает — ключи верные[/green]")

        if not verdicts:
            verdicts.append("[red]✗ НИ ОДИН тест не пройден — ключи НЕВЕРНЫЕ[/red]")

        for v in verdicts:
            console.print(v)

        is_valid = any("верные" in v or "ТОЧНО" in v for v in verdicts)
        return {
            "gcm": gcm_result,
            "magic": magic_result,
            "entropy": entropy_result,
            "verdict": "VALID" if is_valid else "INVALID",
        }


# ==================================================================
# Сканер .exe на предмет AES-ключей
# ==================================================================


def scan_exe_for_keys(exe_path: Path, reference_keys: Optional[dict] = None) -> list:
    """
    Расширенный сканер PE-образа с учётом VMProtect.
    Ищет AES-ключи несколькими эвристиками.
    """
    console.print(f"\n[bold]Сканирование {exe_path.name}...[/bold]")

    data = exe_path.read_bytes()
    if data[:2] != b"MZ":
        console.print("[red]Не PE-образ[/red]")
        return []

    pe_offset = struct.unpack("<I", data[0x3C:0x40])[0]
    num_sections = struct.unpack("<H", data[pe_offset + 6 : pe_offset + 8])[0]
    optional_hdr_size = struct.unpack("<H", data[pe_offset + 20 : pe_offset + 22])[0]
    sections_start = pe_offset + 24 + optional_hdr_size

    sections = []
    for i in range(num_sections):
        sec_offset = sections_start + i * 40
        name = (
            data[sec_offset : sec_offset + 8]
            .rstrip(b"\x00")
            .decode("ascii", errors="ignore")
        )
        vsize = struct.unpack("<I", data[sec_offset + 8 : sec_offset + 12])[0]
        vaddr = struct.unpack("<I", data[sec_offset + 12 : sec_offset + 16])[0]
        rawsize = struct.unpack("<I", data[sec_offset + 16 : sec_offset + 20])[0]
        rawptr = struct.unpack("<I", data[sec_offset + 20 : sec_offset + 24])[0]
        sections.append(
            {
                "name": name,
                "vaddr": vaddr,
                "vsize": vsize,
                "rawptr": rawptr,
                "rawsize": rawsize,
            }
        )

    console.print(f"  Найдено секций: {len(sections)}")
    for s in sections:
        size_str = f"{s['rawsize'] / (1024 * 1024):.1f} MB"
        mark = " [red]⚠ VMProtect![/red]" if s["name"] == ".vmp0" else ""
        console.print(
            f"    {s['name']:8s}  VA=0x{s['vaddr']:08X}  size={size_str}{mark}"
        )

    all_candidates = []

    # Метод 1: Поиск AES S-box
    console.print("\n[bold cyan]Метод 1: Поиск AES S-box[/bold cyan]")
    sbox_positions = _find_aes_sbox(data)
    if sbox_positions:
        console.print(
            f"  [green]✓ Найдено {len(sbox_positions)} позиций AES S-box:[/green]"
        )
        for pos in sbox_positions[:5]:
            console.print(f"    0x{pos:08X}")
    else:
        console.print(
            "  [yellow]AES S-box не найден (возможно, зашифрован VMProtect)[/yellow]"
        )

    # Метод 2: Поиск nonce по шаблону
    console.print("\n[bold cyan]Метод 2: Поиск nonce по шаблону[/bold cyan]")
    nonce_template = bytes(
        [0x84, 0xDF, 0x11, 0xC0, 0xAC, 0xAB, 0xFA, 0x20, 0x33, 0x11, 0x26, 0x99]
    )
    nonce_hits = _find_nonce_pattern(data, nonce_template)
    if nonce_hits:
        console.print(f"  [green]✓ Найдено {len(nonce_hits)} похожих nonce:[/green]")
        for pos, matched, diff in nonce_hits[:5]:
            console.print(
                f"    0x{pos:08X}: {matched.hex(' ').upper()} (отличий: {diff})"
            )
    else:
        console.print("  [yellow]Nonce-шаблон не найден[/yellow]")

    # Метод 3: Поиск пар ключей рядом
    console.print("\n[bold cyan]Метод 3: Поиск пар ключей рядом[/bold cyan]")
    key_pairs = _find_key_pairs(data, sections, min_entropy=5.5)
    if key_pairs:
        console.print(
            f"  [green]✓ Найдено {len(key_pairs)} пар потенциальных ключей:[/green]"
        )
        for pair in key_pairs[:10]:
            console.print(
                f"    [{pair['section']}] 0x{pair['va1']:08X} + 0x{pair['va2']:08X} "
                f"(расстояние: {pair['distance']} байт)"
            )
            console.print(f"      K1: {pair['key1'].hex(' ').upper()}")
            console.print(f"      K2: {pair['key2'].hex(' ').upper()}")
        all_candidates.extend(
            [
                {
                    "hex": p["key1"].hex().upper(),
                    "section": p["section"],
                    "va": p["va1"],
                    "entropy": p["ent1"],
                    "known": False,
                    "method": "pair",
                }
                for p in key_pairs
            ]
        )
    else:
        console.print("  [yellow]Пары ключей не найдены[/yellow]")

    # Метод 4: Классический скан всех секций
    console.print(
        "\n[bold cyan]Метод 4: Скан всех секций (порог энтропии 5.5)[/bold cyan]"
    )
    for sec in sections:
        if sec["rawsize"] == 0 or sec["rawsize"] > 100 * 1024 * 1024:
            console.print(
                f"  [dim]Пропускаю {sec['name']} (размер {sec['rawsize']})[/dim]"
            )
            continue

        sec_data = data[sec["rawptr"] : sec["rawptr"] + sec["rawsize"]]
        console.print(
            f"  [dim]Сканирую {sec['name']} ({len(sec_data):,} байт)...[/dim]"
        )

        for i in range(0, len(sec_data) - 16, 4):
            chunk = sec_data[i : i + 16]
            if chunk == b"\x00" * 16 or len(set(chunk)) < 8:
                continue
            ent = calculate_entropy(chunk)
            if ent < 5.5:
                continue
            is_known = any(chunk == k for k in (reference_keys or {}).values())
            all_candidates.append(
                {
                    "section": sec["name"],
                    "offset": sec["rawptr"] + i,
                    "va": sec["vaddr"] + i,
                    "hex": chunk.hex().upper(),
                    "entropy": ent,
                    "known": is_known,
                    "method": "entropy",
                }
            )

    # Метод 5: Прямой поиск ключей Destiny 2
    console.print("\n[bold cyan]Метод 5: Прямой поиск ключей Destiny 2[/bold cyan]")
    if reference_keys:
        for name, key in reference_keys.items():
            positions = []
            start = 0
            while True:
                pos = data.find(key, start)
                if pos == -1:
                    break
                positions.append(pos)
                start = pos + 1
            if positions:
                console.print(
                    f"  [green]✓ {name} найден в {len(positions)} местах:[/green]"
                )
                for p in positions[:5]:
                    console.print(f"    0x{p:08X}")
            else:
                console.print(f"  [yellow]{name} не найден[/yellow]")

    # Итоги
    seen = set()
    unique = []
    for c in all_candidates:
        if c["hex"] not in seen:
            seen.add(c["hex"])
            unique.append(c)

    unique.sort(key=lambda x: x["entropy"], reverse=True)

    table = Table(title=f"Итого кандидатов: {len(unique)}")
    table.add_column("#", style="dim")
    table.add_column("Метод", style="blue")
    table.add_column("Секция", style="cyan")
    table.add_column("VA", style="yellow")
    table.add_column("Ключ (hex)", style="green")
    table.add_column("Энтропия", style="magenta", justify="right")

    for i, c in enumerate(unique[:50], 1):
        table.add_row(
            str(i),
            c.get("method", "?"),
            c["section"],
            f"0x{c['va']:08X}",
            c["hex"],
            f"{c['entropy']:.3f}",
        )
    console.print(table)

    # Сохраняем
    output_path = exe_path.with_suffix(".keys.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# AES key candidates from {exe_path.name}\n")
        f.write(f"# Total: {len(unique)}\n\n")
        for c in unique:
            f.write(
                f"{c.get('method', '?')}\t{c['section']}\t0x{c['va']:08X}\t"
                f"{c['hex']}\t{c['entropy']:.3f}\n"
            )
    console.print(f"\n[dim]Сохранено в: {output_path}[/dim]")

    return unique


# ============================================================
# Вспомогательные функции для сканера
# ============================================================
def _find_aes_sbox(data: bytes) -> list:
    """Ищет AES S-box — 256 байт с уникальным распределением."""
    sbox_start = bytes([0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5])
    positions = []
    start = 0
    while True:
        pos = data.find(sbox_start, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1
    return positions


def _find_nonce_pattern(data: bytes, template: bytes, max_diff: int = 3) -> list:
    """Ищет 12-байтный nonce с небольшими отличиями от шаблона."""
    hits = []
    anchor = template[:4]
    start = 0
    while True:
        pos = data.find(anchor, start)
        if pos == -1:
            break
        candidate = data[pos : pos + 12]
        if len(candidate) == 12:
            diff = sum(1 for a, b in zip(candidate, template) if a != b)
            if diff <= max_diff:
                hits.append((pos, candidate, diff))
        start = pos + 1
        if len(hits) > 50:
            break
    return hits


def _find_key_pairs(data: bytes, sections: list, min_entropy: float = 5.5) -> list:
    """Ищет две 16-байтные высокоэнтропийные последовательности рядом."""
    pairs = []
    for sec in sections:
        if sec["rawsize"] == 0 or sec["rawsize"] > 100 * 1024 * 1024:
            continue
        sec_data = data[sec["rawptr"] : sec["rawptr"] + sec["rawsize"]]

        high_ent_blocks = []
        for i in range(0, len(sec_data) - 16, 4):
            chunk = sec_data[i : i + 16]
            if len(set(chunk)) < 8:
                continue
            ent = calculate_entropy(chunk)
            if ent >= min_entropy:
                high_ent_blocks.append((i, chunk, ent))

        for idx1, (off1, k1, e1) in enumerate(high_ent_blocks):
            for off2, k2, e2 in high_ent_blocks[idx1 + 1 : idx1 + 20]:
                distance = off2 - off1
                if distance > 64:
                    break
                if distance < 16:
                    continue
                pairs.append(
                    {
                        "section": sec["name"],
                        "va1": sec["vaddr"] + off1,
                        "va2": sec["vaddr"] + off2,
                        "distance": distance,
                        "key1": k1,
                        "key2": k2,
                        "ent1": e1,
                        "ent2": e2,
                    }
                )
                if len(pairs) > 100:
                    return pairs
    return pairs
