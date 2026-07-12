"""
Единый модуль для определения форматов файлов.
"""

from typing import Dict, Tuple

# Сигнатуры: {байтовая_сигнатура: (название, расширение)}
SIGNATURES: Dict[bytes, Tuple[str, str]] = {
    # Аудио
    b"RIFF": ("WAV/WEM (WWise Audio)", ".wem"),
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
    # Bungie Tiger
    b"\x07\x00\x00\x00": ("Tiger Package Header", ".pkg"),
    b"\x09\x00\x00\x00": ("Tiger Package v9", ".pkg"),
    b"\x0a\x00\x00\x00": ("Tiger Package v10", ".pkg"),
}


def detect_format(header: bytes) -> Tuple[str, str]:
    """
    Определяет формат по заголовку.

    Returns:
        (название_формата, расширение)
    """
    for sig, (name, ext) in SIGNATURES.items():
        if header.startswith(sig):
            return name, ext

    hex_sig = header[:4].hex(" ")
    return f"Неизвестный ({hex_sig})", ".bin"


def get_extension(header: bytes) -> str:
    """Возвращает расширение файла."""
    return detect_format(header)[1]


def is_known_format(header: bytes) -> bool:
    """Проверяет, известен ли формат."""
    return not detect_format(header)[0].startswith("Неизвестный")


def get_known_formats() -> Dict[str, str]:
    """Возвращает словарь {расширение: название}."""
    return {ext: name for _, (name, ext) in SIGNATURES.items()}
