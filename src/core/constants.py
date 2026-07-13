"""
Константы для работы с пакетами Tiger Engine.
"""

from typing import Any, Dict

# ===== Размеры и смещения =====
BLOCK_SIZE = 0x40000  # 256 KB
BLOCK_ENTRY_SIZE = 48  # Размер записи в таблице блоков


# ===== Смещения в заголовке пакета =====
class PkgOffsets:
    """Смещения в заголовке .pkg файла."""

    MAGIC = 0x00
    VERSION = 0x04
    PACKAGE_ID = 0x10
    PATCH_ID = 0x30
    ENTRY_TABLE_OFFSET = 0x44
    ENTRY_TABLE_SIZE = 0x60
    BLOCK_TABLE_OFFSET = 0x6C
    BLOCK_TABLE_SIZE = 0x68

    # Альтернативные смещения для разных версий
    ENTRY_TABLE_OFFSET_ALT = 0x48
    BLOCK_TABLE_OFFSET_ALT = 0x60
    BLOCK_TABLE_SIZE_ALT = 0x64


# ===== Флаги блоков =====
class BlockFlags:
    COMPRESSED = 0x1
    ENCRYPTED = 0x2
    USE_KEY_1 = 0x4


# ===== AES-ключи (подтверждены для Marathon 2026) =====
AES_KEYS = {
    "KEY_0": bytes.fromhex("D62AB2C10CC01BC535DB7B8655C7DC3B"),
    "KEY_1": bytes.fromhex("3A4A5D3673A660587E63E676E40892B5"),
}

# ===== Конфигурация =====
DEFAULT_CONFIG: Dict[str, Any] = {
    "oodle_dll": "oo2core_9_win64.dll",
    "vgmstream_cli": "vgmstream-cli.exe",
    "ffmpeg": "ffmpeg.exe",
    "max_workers": 8,
    "timeout_vgmstream": 30,
    "timeout_ffmpeg": 300,
    "batch_size": 100,  # Для параллельной обработки
}


