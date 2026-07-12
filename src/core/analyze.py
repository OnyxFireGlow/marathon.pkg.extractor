"""
Утилита анализа извлечённых .bin файлов.
Определяет форматы по сигнатурам, выводит статистику.
"""

import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.utils.filesystem import FileSystemManager

console = Console()

debug_logger = logging.getLogger("analyze_debug")
debug_logger.setLevel(logging.DEBUG)

BANNER = """[bold cyan]
╔══════════════════════════════════════════════════╗
║     Marathon 2026 - File Analyzer               ║
╚══════════════════════════════════════════════════╝[/bold cyan]"""


SIGNATURES = {
    # Аудио
    b"RIFF": ("WAV/WEM (WWise Audio)", ".wav"),
    b"OggS": ("Ogg Vorbis", ".ogg"),
    b"ftyp": ("MP4/MPEG-4", ".mp4"),
    b"\xff\xfb": ("MPEG Audio (MP3)", ".mp3"),
    b"\xff\xf3": ("MPEG Audio (MP3)", ".mp3"),
    b"\xff\xf2": ("MPEG Audio (MP3)", ".mp3"),
    b"ID3": ("MP3 with ID3 tag", ".mp3"),
    # WWise
    b"BKHD": ("WWise SoundBank", ".bnk"),
    b"AKBK": ("WWise Audio Bank", ".bnk"),
    # Видео
    b"CRID": ("CriWare USM Video", ".usm"),
    b"\x00\x00\x00\x18ftyp": ("MP4 Video", ".mp4"),
    b"matroska": ("Matroska/WebM Video", ".mkv"),
    b"\x00\x00\x01\xba": ("MPEG-PS Video", ".mpg"),
    b"\x00\x00\x01\xb3": ("MPEG Video", ".mpg"),
    b"RIFF\x00\x00\x00\x00AVI ": ("AVI Video", ".avi"),
    b"\x1aE\xdf\xa3": ("WebM Video", ".webm"),
    b"MOOV": ("QuickTime Video", ".mov"),
    b"moov": ("QuickTime Video", ".mov"),
    b"CRIUSM": ("CriWare USM Video", ".usm"),
    # Сжатие
    b"\x1f\x8b": ("GZip", ".gz"),
    b"BZh": ("BZip2", ".bz2"),
    b"\x28\xb5\x2f\xfd": ("Zstandard", ".zst"),
    b"\x78\x9c": ("zlib/DEFLATE", ".zz"),
    # Текстуры
    b"DDS ": ("DirectDraw Surface", ".dds"),
    b"\x89PNG": ("PNG Image", ".png"),
    # Bungie
    b"\x07\x00\x00\x00": ("Tiger Package Header", ".pkg"),
    b"\x09\x00\x00\x00": ("Tiger Package v9", ".pkg"),
    b"\x0a\x00\x00\x00": ("Tiger Package v10", ".pkg"),
}


def _get_format_info(header: bytes) -> tuple[str, str]:
    """Определяет формат файла по заголовку."""
    for sig_bytes, (name, ext) in SIGNATURES.items():
        if header.startswith(sig_bytes):
            return name, ext

    hex_sig = header[:4].hex(" ")
    return f"Неизвестный ({hex_sig})", ".bin"


def analyze_directory(
    directory: str | Path,
    recursive: bool = False,
    verbose: bool = False,
    debug_log: str | None = None,
) -> Optional[dict]:
    """
    Анализирует все .bin файлы в директории.

    Args:
        directory: Путь к директории
        recursive: Рекурсивно обходить поддиректории
        verbose: Показывать сигнатуры неизвестных форматов
        debug_log: Путь к файлу для записи неизвестных форматов

    Returns:
        Словарь со статистикой или None
    """
    directory = Path(directory)

    if not directory.exists():
        console.print(f"[red]Директория не найдена: {directory}[/red]")
        return None

    # Настройка debug-лога
    if debug_log:
        file_handler = logging.FileHandler(debug_log, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        debug_logger.addHandler(file_handler)

    # Сбор файлов
    pattern = "**/*.bin" if recursive else "*.bin"
    bin_files = list(directory.glob(pattern))

    if not bin_files:
        console.print(f"[yellow].bin файлы не найдены в {directory}[/yellow]")
        return None

    total_count = len(bin_files)
    total_size = 0
    empty_count = 0
    signatures = Counter()
    sizes = []
    known_groups = defaultdict(list)  # Только известные форматы
    unknown_groups = defaultdict(list)  # Только неизвестные

    console.print(f"\n[bold]📁 {directory.name}[/bold] — {total_count:,} файлов")

    for filepath in bin_files:
        size = filepath.stat().st_size
        total_size += size
        sizes.append(size)

        if size == 0:
            empty_count += 1
            signatures["[пустой]"] += 1
            continue

        try:
            with open(filepath, "rb") as f:
                header = f.read(64)
        except Exception:
            signatures["[ошибка чтения]"] += 1
            continue

        format_name, _ = _get_format_info(header)
        signatures[format_name] += 1

        item = {"path": filepath, "size": size, "header": header[:16]}

        if format_name.startswith("Неизвестный"):
            unknown_groups[format_name].append(item)
        else:
            known_groups[format_name].append(item)

    # Вывод общей статистики
    _print_summary(total_count, total_size, empty_count, sizes)

    # Вывод известных форматов
    _print_known_formats(known_groups, total_count)

    # Вывод сводки по неизвестным
    _print_unknown_summary(unknown_groups, total_count, verbose)

    # Запись неизвестных в лог
    if debug_log and unknown_groups:
        _write_unknown_log(unknown_groups, debug_log, directory)

    # Рекомендации (только для известных форматов)
    _print_recommendations(known_groups)

    return {
        "total_count": total_count,
        "total_size": total_size,
        "empty_count": empty_count,
        "known": dict(known_groups),
        "unknown": dict(unknown_groups),
    }


def analyze_all_extracted(
    extracted_dir: str = "extracted",
    verbose: bool = False,
    debug_log: str | None = None,
):
    """Анализирует все подпапки в extracted/."""
    fs = FileSystemManager()
    extracted_path = fs.find_project_dir(extracted_dir)

    if not extracted_path:
        extracted_path = Path(extracted_dir)
        if not extracted_path.exists():
            console.print(f"[red]Папка '{extracted_dir}' не найдена[/red]")
            return None

    console.print(f"[dim]Анализирую: {extracted_path}[/dim]")

    # Анализируем общую папку
    all_results = analyze_directory(
        extracted_path, recursive=False, verbose=verbose, debug_log=debug_log
    )

    # Анализируем подпапки
    for subdir in sorted(extracted_path.iterdir()):
        if subdir.is_dir():
            analyze_directory(
                subdir, recursive=False, verbose=verbose, debug_log=debug_log
            )

    return all_results


# ============================================================
#  Функции форматирования вывода
# ============================================================


def _print_summary(total_count: int, total_size: int, empty_count: int, sizes: list):
    """Выводит сводную статистику."""
    table = Table(title="📊 Общая статистика", show_header=False)
    table.add_column(style="cyan")
    table.add_column(style="green")

    table.add_row("Всего файлов", f"{total_count:,}")
    table.add_row(
        "Пустых", f"{empty_count:,} ({empty_count * 100 // max(total_count, 1)}%)"
    )
    table.add_row("С данными", f"{total_count - empty_count:,}")
    table.add_row(
        "Общий размер", f"{total_size:,} B ({total_size / (1024 * 1024):.1f} MB)"
    )

    if sizes:
        sorted_sizes = sorted(sizes)
        table.add_row(
            "Размер (мин/медиана/макс)",
            f"{sorted_sizes[0]:,} / {sorted_sizes[len(sorted_sizes) // 2]:,} / {sorted_sizes[-1]:,} B",
        )

    console.print(table)


def _print_known_formats(known_groups: dict, total_count: int):
    """Выводит таблицу известных форматов."""
    if not known_groups:
        console.print("[yellow]Известных форматов не обнаружено[/yellow]")
        return

    table = Table(title="🔍 Обнаруженные форматы")
    table.add_column("Формат", style="cyan")
    table.add_column("Файлов", style="green", justify="right")
    table.add_column("%", style="yellow", justify="right")
    table.add_column("Размер", style="magenta", justify="right")

    for format_name, items in sorted(
        known_groups.items(), key=lambda x: len(x[1]), reverse=True
    ):
        count = len(items)
        pct = count * 100 // max(total_count, 1)
        total_fsize = sum(item["size"] for item in items)
        size_str = (
            f"{total_fsize / (1024 * 1024):.1f} MB"
            if total_fsize > 1024 * 1024
            else f"{total_fsize / 1024:.1f} KB"
        )

        table.add_row(format_name, f"{count:,}", f"{pct}%", size_str)

    console.print(table)

    # Примеры заголовков для каждого формата
    console.print("\n[bold]📋 Примеры заголовков:[/bold]")
    for format_name, items in list(known_groups.items())[:5]:
        console.print(f"  [cyan]{format_name}[/cyan]")
        for item in items[:2]:
            fname = item["path"].name
            hex_preview = item["header"][:16].hex(" ")
            ascii_preview = "".join(
                chr(b) if 32 <= b < 127 else "." for b in item["header"][:16]
            )
            console.print(f"    {fname}: {hex_preview}")
            console.print(f"    {' ' * len(fname)}  [dim]{ascii_preview}[/dim]")


def _print_unknown_summary(unknown_groups: dict, total_count: int, verbose: bool):
    """Выводит сводку по неизвестным форматам."""
    if not unknown_groups:
        return

    total_unknown = sum(len(items) for items in unknown_groups.values())
    total_unknown_size = sum(
        sum(item["size"] for item in items) for items in unknown_groups.values()
    )

    console.print(
        f"\n[yellow]⚠ Неизвестных форматов: {total_unknown} файлов "
        f"({total_unknown * 100 // max(total_count, 1)}%) "
        f"— {total_unknown_size / (1024 * 1024):.1f} MB[/yellow]"
    )

    if verbose:
        console.print("[dim]Сигнатуры неизвестных форматов:[/dim]")
        for sig_name in sorted(
            unknown_groups.keys(), key=lambda x: len(unknown_groups[x]), reverse=True
        )[:10]:
            count = len(unknown_groups[sig_name])
            console.print(f"  [dim]• {sig_name}: {count} файлов[/dim]")

        if len(unknown_groups) > 10:
            console.print(f"  [dim]... и ещё {len(unknown_groups) - 10}[/dim]")

    if not verbose:
        console.print("[dim]Используйте --verbose для просмотра сигнатур[/dim]")


def _write_unknown_log(unknown_groups: dict, log_path: str, directory: Path):
    """Записывает неизвестные форматы в лог-файл."""
    debug_logger.info(f"=== Неизвестные форматы в {directory} ===\n")

    for sig_name, items in sorted(
        unknown_groups.items(), key=lambda x: len(x[1]), reverse=True
    ):
        debug_logger.info(f"\n{sig_name} ({len(items)} файлов):")
        for item in items:
            hex_preview = item["header"][:16].hex(" ")
            debug_logger.info(
                f"  {item['path'].name}: {hex_preview} ({item['size']:,} B)"
            )

    console.print(f"[dim]Подробный лог неизвестных форматов: {log_path}[/dim]")


def _print_recommendations(known_groups: dict):
    """Выводит рекомендации по известным форматам."""
    if not known_groups:
        return

    console.print("\n[bold]💡 Рекомендации:[/bold]")

    known_names = set(known_groups.keys())

    if "WAV/WEM (WWise Audio)" in known_names:
        console.print(
            Panel(
                "✓ Найдены [green]WAV/WEM аудиофайлы[/green]\n"
                "Конвертация в WAV:\n"
                "  • vgmstream-cli -o output.wav input.bin\n"
                "  • ww2ogg input.bin && revorb input.ogg output.wav",
                title="Аудио",
            )
        )

    if "WWise SoundBank" in known_names:
        console.print(
            Panel(
                "✓ Найдены [green]WWise SoundBank (.bnk)[/green]\n"
                "Извлечение аудио из банков:\n"
                "  • bnkextr.exe input.bnk\n"
                "  • foobar2000 + плагин vgmstream",
                title="Банки",
            )
        )

    if "GZip" in known_names or "zlib/DEFLATE" in known_names:
        console.print(
            Panel(
                "✓ Найдены [green]сжатые данные[/green]\n"
                "Возможно, это сжатые текстуры или модели.\n"
                "Попробуйте распаковать утилитой zlib или gzip.",
                title="Сжатие",
            )
        )


def print_banner():
    """Выводит баннер анализатора."""
    console.print(BANNER)


# ============================================================
#  Точка входа для самостоятельного запуска
# ============================================================

if __name__ == "__main__":
    import sys

    print_banner()

    # Простые аргументы
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    debug = "--debug" in sys.argv or "-d" in sys.argv

    debug_log = "unknown_formats.log" if debug else None

    # Ищем путь к папке
    target = "extracted"
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            target = arg
            break

    analyze_all_extracted(target, verbose=verbose, debug_log=debug_log)
