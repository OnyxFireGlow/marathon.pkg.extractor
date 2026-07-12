"""
Утилита конвертации извлечённых .bin файлов в правильные форматы.
Поддерживает: WEM → WAV (vgmstream), USM → MP4 (ffmpeg),
             и переименование по сигнатурам.
"""

import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table

console = Console()

BANNER = """[bold cyan]
╔══════════════════════════════════════════════════╗
║     Marathon 2026 - Format Converter            ║
╚══════════════════════════════════════════════════╝[/bold cyan]"""

SIGNATURE_TO_EXT = {
    # Аудио
    b"RIFF": ".wem",
    b"OggS": ".ogg",
    b"ftyp": ".mp4",
    b"\xff\xfb": ".mp3",
    b"\xff\xf3": ".mp3",
    b"\xff\xf2": ".mp3",
    b"ID3": ".mp3",
    b"BKHD": ".bnk",
    b"AKBK": ".bnk",
    # Видео
    b"CRID": ".usm",
    b"matroska": ".mkv",
    b"\x00\x00\x01\xba": ".mpg",
    b"\x00\x00\x01\xb3": ".mpg",
    b"\x1aE\xdf\xa3": ".webm",
    b"MOOV": ".mov",
    b"moov": ".mov",
    # Сжатие
    b"\x1f\x8b": ".gz",
    b"BZh": ".bz2",
    b"\x78\x9c": ".zz",
    # Текстуры
    b"DDS ": ".dds",
    b"\x89PNG": ".png",
    # Bungie
    b"\x07\x00\x00\x00": ".pkg",
    b"\x09\x00\x00\x00": ".pkg",
    b"\x0a\x00\x00\x00": ".pkg",
}

# ============================================================
#  Правила конвертации через внешние утилиты
# ============================================================

CONVERSION_RULES = {
    ".wem": {
        "to": ".wav",
        "tool": "vgmstream",
        "command": 'vgmstream-cli.exe -o "{output}" "{input}"',
        "description": "WWise Audio → WAV",
        "timeout": 30,
    },
    ".usm": {
        "to": ".mp4",
        "tool": "ffmpeg",
        "command": 'ffmpeg -y -i "{input}" -c:v copy -c:a aac "{output}"',
        "description": "CriWare USM Video → MP4",
        "timeout": 300,
    },
}


def _find_tool(tool_name: str) -> Optional[Path]:
    """Ищет исполняемый файл инструмента."""

    if tool_name == "vgmstream":
        candidates = [
            Path("lib/vgmstream-cli.exe"),
            Path("vgmstream-cli.exe"),
            # Добавляем поиск от корня проекта
            Path(__file__).resolve().parent.parent.parent / "lib" / "vgmstream-cli.exe",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()
        return None

    if tool_name == "ffmpeg":
        result = shutil.which("ffmpeg")
        if result:
            return Path(result)
        candidates = [
            Path("lib/ffmpeg.exe"),
            Path("ffmpeg.exe"),
            Path(__file__).resolve().parent.parent.parent / "lib" / "ffmpeg.exe",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()
        return None

    return None


def _convert_with_tool(source_path: Path, dest_path: Path, ext: str) -> bool:
    """
    Конвертирует файл через внешнюю утилиту.

    Args:
        source_path: Исходный файл (уже с правильным расширением)
        dest_path: Путь для сохранения результата
        ext: Исходное расширение (ключ в CONVERSION_RULES)

    Returns:
        True если конвертация успешна
    """
    rule = CONVERSION_RULES.get(ext)
    if not rule:
        return False

    tool = rule["tool"]
    tool_path = _find_tool(tool)

    if not tool_path:
        return False

    # Для vgmstream используем полный путь
    if tool == "vgmstream":
        cmd = (
            rule["command"]
            .format(tool=str(tool_path), input=str(source_path), output=str(dest_path))
            .replace("vgmstream-cli.exe", str(tool_path))
        )
    else:
        cmd = rule["command"].format(input=str(source_path), output=str(dest_path))

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, timeout=rule.get("timeout", 60)
        )

        if (
            result.returncode == 0
            and dest_path.exists()
            and dest_path.stat().st_size > 0
        ):
            return True
        else:
            stderr = result.stderr.decode("utf-8", errors="ignore").strip()
            if stderr:
                console.print(f"[dim]  {tool}: {stderr[:120]}[/dim]")
            return False

    except subprocess.TimeoutExpired:
        console.print(
            f"[yellow]  Таймаут ({rule.get('timeout')}с): {source_path.name}[/yellow]"
        )
        return False
    except Exception as e:
        console.print(f"[red]  Ошибка: {e}[/red]")
        return False


# ============================================================
#  Определение формата
# ============================================================


def detect_format(filepath: Path) -> Optional[str]:
    """Определяет расширение файла по сигнатуре первых 16 байт."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
    except Exception:
        return None

    for sig_bytes, ext in SIGNATURE_TO_EXT.items():
        if header.startswith(sig_bytes):
            return ext

    return None


# ============================================================
#  Поиск файлов
# ============================================================


def find_bin_files(directory: Path, recursive: bool = True) -> list[Path]:
    """Находит все .bin файлы в директории."""
    pattern = "**/*.bin" if recursive else "*.bin"
    return list(directory.glob(pattern))


# ============================================================
#  Конвертация директории
# ============================================================


def convert_directory(
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    convert_media: bool = False,
    dry_run: bool = False,
    recursive: bool = True,
    interactive: bool = True,
) -> dict:
    """
    Конвертирует .bin файлы в правильные форматы.

    Args:
        input_dir: Входная директория с .bin файлами
        output_dir: Выходная директория (None — переименование на месте)
        convert_media: Запускать конвертацию WEM→WAV, USM→MP4
        dry_run: Только показать план без изменений
        recursive: Рекурсивно обходить поддиректории
        interactive: Спрашивать подтверждение

    Returns:
        Словарь со статистикой
    """
    input_dir = Path(input_dir)

    if not input_dir.exists():
        console.print(f"[red]Директория не найдена: {input_dir}[/red]")
        return {}

    bin_files = find_bin_files(input_dir, recursive)

    if not bin_files:
        console.print(f"[yellow].bin файлы не найдены в {input_dir}[/yellow]")
        return {}

    console.print(f"\n[bold]📁 {input_dir.name}[/bold] — {len(bin_files):,} файлов")

    # Группируем по форматам
    format_groups = defaultdict(list)
    unknown = []

    for filepath in bin_files:
        ext = detect_format(filepath)
        if ext:
            format_groups[ext].append(filepath)
        else:
            unknown.append(filepath)

    # План
    _print_plan(format_groups, unknown, convert_media, dry_run)

    if dry_run:
        return {"planned": dict(format_groups), "unknown": unknown}

    # Подтверждение
    if interactive and not Confirm.ask("\nПродолжить?", default=True):
        console.print("[dim]Отменено[/dim]")
        return {}

    # Проверка доступности инструментов
    available_tools = {}
    if convert_media:
        for ext in format_groups:
            if ext in CONVERSION_RULES:
                tool = CONVERSION_RULES[ext]["tool"]
                if tool not in available_tools:
                    path = _find_tool(tool)
                    available_tools[tool] = path is not None
                    if path:
                        console.print(f"[green]✓[/green] {tool}: {path}")
                    else:
                        console.print(f"[yellow]✗[/yellow] {tool}: не найден")

    # Конвертация
    stats = {
        "renamed": 0,
        "converted": 0,
        "skipped": 0,
        "unknown": len(unknown),
        "details": [],
    }

    total = sum(len(files) for files in format_groups.values())

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Конвертация", total=total)

        for ext, files in sorted(
            format_groups.items(), key=lambda x: len(x[1]), reverse=True
        ):
            progress.update(task, description=f"[cyan]{ext}")

            for filepath in files:
                new_path = _rename_file(filepath, ext, output_dir, stats)

                # Конвертация медиа
                if convert_media and ext in CONVERSION_RULES and new_path:
                    tool = CONVERSION_RULES[ext]["tool"]
                    if available_tools.get(tool, False):
                        dest_ext = CONVERSION_RULES[ext]["to"]
                        dest_path = new_path.with_suffix(dest_ext)
                        if _convert_with_tool(new_path, dest_path, ext):
                            stats["converted"] += 1
                            if stats["details"]:
                                stats["details"][-1]["converted_to"] = str(dest_path)

                progress.advance(task)

    _print_results(stats)
    return stats


def _rename_file(
    filepath: Path, ext: str, output_dir: Path | None, stats: dict
) -> Optional[Path]:
    """Переименовывает или копирует файл с правильным расширением."""

    if output_dir:
        new_path = output_dir / filepath.with_suffix(ext).name
        new_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        new_path = filepath.with_suffix(ext)

    try:
        if output_dir:
            shutil.copy2(filepath, new_path)
        else:
            filepath.rename(new_path)

        stats["renamed"] += 1
        stats["details"].append(
            {"original": str(filepath), "result": str(new_path), "action": "renamed"}
        )
        return new_path

    except Exception as e:
        console.print(f"[red]Ошибка: {filepath.name}: {e}[/red]")
        stats["skipped"] += 1
        return None


# ============================================================
#  Конвертация всех подпапок в extracted/
# ============================================================


def convert_all_extracted(
    extracted_dir: str = "extracted",
    output_dir: str | None = None,
    convert_media: bool = False,
    dry_run: bool = False,
):
    """
    Конвертирует файлы во всех подпапках extracted/.
    Результаты сохраняются в extracted/converted/.
    """
    from src.utils.filesystem import FileSystemManager

    fs = FileSystemManager()
    extracted_path = fs.find_project_dir(extracted_dir)

    if not extracted_path:
        extracted_path = Path(extracted_dir)
        if not extracted_path.exists():
            console.print(f"[red]Папка '{extracted_dir}' не найдена[/red]")
            return None

    # Выходная папка по умолчанию: extracted/converted
    if output_dir is None:
        output_path = extracted_path / "converted"
    else:
        output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Входная папка: {extracted_path}[/dim]")
    console.print(f"[dim]Выходная папка: {output_path}[/dim]")

    # Конвертируем каждую подпапку
    for subdir in sorted(extracted_path.iterdir()):
        if subdir.name == "converted":
            continue
        if subdir.is_dir():
            out_sub = output_path / subdir.name
            convert_directory(
                subdir,
                out_sub,
                convert_media=convert_media,
                dry_run=dry_run,
                recursive=False,
                interactive=False,
            )


# ============================================================
#  Вывод
# ============================================================


def _print_plan(format_groups: dict, unknown: list, convert_media: bool, dry_run: bool):
    """Выводит план конвертации."""

    table = Table(title="📋 План конвертации")
    table.add_column("Формат", style="cyan")
    table.add_column("Файлов", style="green", justify="right")
    table.add_column("Действие", style="yellow")

    for ext, files in sorted(
        format_groups.items(), key=lambda x: len(x[1]), reverse=True
    ):
        action = f"Переименовать в *{ext}"
        if convert_media and ext in CONVERSION_RULES:
            rule = CONVERSION_RULES[ext]
            action += f" → {rule['to']} ({rule['tool']})"
        table.add_row(ext, str(len(files)), action)

    if unknown:
        table.add_row(
            "[red]Неизвестный[/red]", str(len(unknown)), "[red]Пропущено[/red]"
        )

    console.print(table)

    if dry_run:
        console.print("\n[yellow]Режим просмотра — файлы не будут изменены[/yellow]")

    if convert_media:
        console.print("\n[dim]Будет выполнена конвертация:[/dim]")
        for ext, rule in CONVERSION_RULES.items():
            if ext in format_groups:
                console.print(
                    f"  [dim]• {rule['description']} (через {rule['tool']})[/dim]"
                )


def _print_results(stats: dict):
    """Выводит результаты конвертации."""

    table = Table(title="✅ Результаты")
    table.add_column("Действие", style="cyan")
    table.add_column("Количество", style="green", justify="right")

    table.add_row("Переименовано", str(stats["renamed"]))
    table.add_row("Конвертировано", str(stats["converted"]))
    table.add_row("Пропущено (ошибки)", str(stats["skipped"]))
    table.add_row("Неизвестных (пропущено)", str(stats["unknown"]))

    total = stats["renamed"] + stats["converted"]
    table.add_row("[bold]Всего обработано[/bold]", f"[bold]{total}[/bold]")

    console.print(table)


def print_banner():
    """Выводит баннер конвертера."""
    console.print(BANNER)


# ============================================================
#  Самостоятельный запуск
# ============================================================

if __name__ == "__main__":
    import sys

    print_banner()

    dry_run = "--dry-run" in sys.argv
    convert_media = "--convert-media" in sys.argv or "--convert-audio" in sys.argv

    target = "extracted"
    output = None

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "-o" and i + 1 < len(args):
            output = args[i + 1]
        elif not arg.startswith("-"):
            target = arg

    convert_all_extracted(target, output, convert_media=convert_media, dry_run=dry_run)
