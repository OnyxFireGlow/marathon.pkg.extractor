"""
Проверка целостности извлечённых аудиофайлов.
Компактный вывод: только сводка и гистограммы, без таблицы на каждый файл.
"""

import struct
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _parse_wav_header(filepath: Path) -> dict | None:
    """Парсит заголовок WAV-файла. Поддерживает PCM, Float и другие форматы."""
    try:
        with open(filepath, "rb") as f:
            data = f.read(128)
        if len(data) < 44:
            return None
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return None

        fmt_code = struct.unpack_from("<H", data, 20)[0]
        channels = struct.unpack_from("<H", data, 22)[0]
        sample_rate = struct.unpack_from("<I", data, 24)[0]
        byte_rate = struct.unpack_from("<I", data, 28)[0]
        bits = struct.unpack_from("<H", data, 34)[0]
        riff_size = struct.unpack_from("<I", data, 4)[0]

        format_names = {
            1: "PCM",
            3: "Float",
            6: "A-law",
            7: "μ-law",
            0xFFFE: "Extensible",
        }

        return {
            "duration": (riff_size - 36) / byte_rate if byte_rate > 0 else 0,
            "channels": channels,
            "sample_rate": sample_rate,
            "bits": bits,
            "format_name": format_names.get(fmt_code, f"code_{fmt_code}"),
            "file_size": filepath.stat().st_size,
        }
    except Exception:
        return None


def _parse_wem_header(filepath: Path) -> dict | None:
    """Парсит заголовок WEM (Wwise) файла."""
    try:
        with open(filepath, "rb") as f:
            data = f.read(64)
        if len(data) < 12 or data[:4] != b"RIFF":
            return None

        fmt_pos = data.find(b"fmt ", 0, 64)
        fmt_code = (
            struct.unpack_from("<H", data, fmt_pos + 8)[0] if fmt_pos != -1 else None
        )

        format_names = {
            0x0001: "PCM",
            0x0002: "ADPCM",
            0xFFFF: "Vorbis",
            0xFFFE: "Wwise",
        }
        fmt_name = (
            format_names.get(fmt_code, f"code_{fmt_code}") if fmt_code else "no_fmt"
        )

        return {
            "format_name": fmt_name,
            "file_size": filepath.stat().st_size,
            "is_wem": True,
        }
    except Exception:
        return None


def analyze_audio_file(filepath: Path) -> dict:
    """Определяет тип аудиофайла и возвращает его параметры."""
    ext = filepath.suffix.lower()

    if ext == ".wav":
        info = _parse_wav_header(filepath)
        if info:
            info["type"] = "WAV"
            return info

    if ext == ".wem":
        info = _parse_wem_header(filepath)
        if info:
            info["type"] = "WEM"
            return info

    return {
        "type": ext.upper().lstrip(".") or "?",
        "format_name": "неизвестно",
        "file_size": filepath.stat().st_size,
    }


def _bar(value: int, maximum: int, width: int = 20) -> str:
    """Рисует ASCII-гистограмму."""
    if maximum == 0:
        return ""
    filled = int(value / maximum * width)
    return "█" * filled + "░" * (width - filled)


def _duration_bucket(duration: float) -> str:
    """Распределяет длительность по категориям."""
    if duration <= 0:
        return "N/A"
    if duration < 0.5:
        return "<0.5с"
    if duration < 1:
        return "0.5–1с"
    if duration < 2:
        return "1–2с"
    if duration < 5:
        return "2–5с"
    if duration < 10:
        return "5–10с"
    if duration < 30:
        return "10–30с"
    if duration < 60:
        return "30–60с"
    return ">60с"


def check_directory(directory: str | Path) -> dict:
    """Анализирует все аудиофайлы в директории. Только сводка, без таблицы."""
    directory = Path(directory)

    if not directory.exists():
        console.print(f"[red]Директория не найдена: {directory}[/red]")
        return {}

    audio_extensions = {".wav", ".wem", ".ogg", ".mp3", ".flac", ".aiff"}
    audio_files = sorted(
        [
            f
            for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in audio_extensions
        ]
    )

    if not audio_files:
        console.print(f"[yellow]Аудиофайлы не найдены в {directory}[/yellow]")
        return {}

    total = 0
    wav_count = 0
    wem_count = 0
    other_count = 0
    errors = 0
    total_size = 0
    total_duration = 0.0

    durations = []
    channels_counter = Counter()
    sample_rates = Counter()
    format_counter = Counter()
    duration_buckets = Counter()

    for filepath in audio_files:
        info = analyze_audio_file(filepath)
        total += 1

        if info is None:
            errors += 1
            continue

        audio_type = info.get("type", "?")
        if audio_type == "WAV":
            wav_count += 1
        elif audio_type == "WEM":
            wem_count += 1
        else:
            other_count += 1

        fmt = info.get("format_name", "?")
        format_counter[fmt] += 1

        size = info.get("file_size", 0)
        total_size += size

        dur = info.get("duration", 0)
        if dur > 0:
            durations.append(dur)
            total_duration += dur
            duration_buckets[_duration_bucket(dur)] += 1

        ch = info.get("channels", 0)
        if ch > 0:
            channels_counter[ch] += 1

        sr = info.get("sample_rate", 0)
        if sr > 0:
            sample_rates[sr] += 1

    # ==== Заголовок ====
    console.print(f"\n[bold]{directory.name}[/bold] — {total} аудиофайлов")

    # ==== Сводка ====
    summary = Table(title="Сводка", show_header=False)
    summary.add_column(style="cyan")
    summary.add_column(style="green")

    summary.add_row(
        "Файлов",
        f"{total} (WAV: {wav_count}, WEM: {wem_count}, др: {other_count}, ошибок: {errors})",
    )
    summary.add_row("Размер", format_size(total_size))

    if durations:
        avg_dur = total_duration / len(durations)
        summary.add_row(
            "Длительность", f"{total_duration:.0f}с ({total_duration / 60:.1f} мин)"
        )
        summary.add_row("  Средняя", f"{avg_dur:.1f}с")
        summary.add_row("  Диапазон", f"{min(durations):.1f}с – {max(durations):.1f}с")

    console.print(summary)

    # ==== Гистограмма длительностей ====
    if duration_buckets:
        bucket_order = [
            "<0.5с",
            "0.5–1с",
            "1–2с",
            "2–5с",
            "5–10с",
            "10–30с",
            "30–60с",
            ">60с",
        ]
        max_count = max(duration_buckets.values())
        dur_table = Table(title="Распределение по длительности")
        dur_table.add_column("Диапазон", style="cyan")
        dur_table.add_column("Файлов", style="green", justify="right")
        dur_table.add_column("Распределение", style="yellow")
        for bucket in bucket_order:
            count = duration_buckets.get(bucket, 0)
            if count > 0:
                dur_table.add_row(bucket, str(count), _bar(count, max_count))
        console.print(dur_table)

    # ==== Форматы ====
    if len(format_counter) > 1:
        fmt_table = Table(title="Форматы")
        fmt_table.add_column("Формат", style="cyan")
        fmt_table.add_column("Кол-во", style="green", justify="right")
        for name, cnt in format_counter.most_common():
            fmt_table.add_row(name, str(cnt))
        console.print(fmt_table)

    # ==== Каналы ====
    if channels_counter:
        ch_table = Table(title="Каналы")
        ch_table.add_column("Каналов", style="cyan")
        ch_table.add_column("Файлов", style="green", justify="right")
        for ch, cnt in sorted(channels_counter.items()):
            label = "Моно" if ch == 1 else ("Стерео" if ch == 2 else str(ch))
            ch_table.add_row(label, str(cnt))
        console.print(ch_table)

    # ==== Частоты дискретизации ====
    if len(sample_rates) > 1:
        sr_table = Table(title="Частоты дискретизации")
        sr_table.add_column("Частота", style="cyan")
        sr_table.add_column("Файлов", style="green", justify="right")
        for sr, cnt in sorted(sample_rates.items(), reverse=True):
            sr_table.add_row(f"{sr // 1000} kHz", str(cnt))
        console.print(sr_table)

    # ==== Рекомендации ====
    if wem_count > 0:
        console.print(
            Panel(
                "[yellow]Найдены WEM-файлы[/yellow] — сконвертируйте:\n"
                "[cyan]py src.main convert --convert-media[/cyan]",
                title="Рекомендация",
            )
        )

    return {
        "total": total,
        "wav": wav_count,
        "wem": wem_count,
        "total_duration": total_duration,
        "total_size": total_size,
        "durations": durations,
    }


def check_all_converted(converted_dir: str = "extracted/converted") -> dict:
    """Проверяет все подпапки в converted/."""
    from src.utils.filesystem import FileSystemManager

    fs = FileSystemManager()
    converted_path = fs.find_project_dir(converted_dir)

    if not converted_path:
        converted_path = Path(converted_dir)
        if not converted_path.exists():
            console.print(f"[red]Папка {converted_dir} не найдена[/red]")
            return {}

    console.print(f"[dim]Проверяю: {converted_path}[/dim]")

    grand_total = 0
    grand_wav = 0
    grand_wem = 0
    grand_duration = 0.0
    grand_size = 0

    for subdir in sorted(converted_path.iterdir()):
        if subdir.is_dir():
            result = check_directory(subdir)
            if result:
                grand_total += result["total"]
                grand_wav += result["wav"]
                grand_wem += result["wem"]
                grand_duration += result["total_duration"]
                grand_size += result["total_size"]

    if grand_total > 0:
        console.print()
        console.print(
            Panel.fit(
                f"[bold]Всего:[/bold] {grand_total} файлов ({grand_wav} WAV + {grand_wem} WEM)\n"
                f"[bold]Размер:[/bold] {format_size(grand_size)}\n"
                f"[bold]Длительность:[/bold] {grand_duration:.0f}с ({grand_duration / 60:.1f} мин)",
                title="Общий итог",
            )
        )

    return {}


def format_size(size_bytes: int) -> str:
    """Форматирует размер в читаемый вид."""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} B"


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        check_directory(sys.argv[1])
    else:
        check_all_converted()
