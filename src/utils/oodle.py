"""Обёртка для работы с Oodle сжатием."""

import os
from ctypes import c_char_p, c_int, cdll, create_string_buffer
from typing import Optional


class OodleManager:
    """
    Управляет загрузкой и использованием Oodle библиотеки.
    Поддерживает версии 8 и 9.
    """

    KNOWN_DLL_NAMES = [
        "oo2core_9_win64.dll",  # Marathon 2026 и актуальные версии Destiny 2
        "oo2core_8_win64.dll",  # Destiny 2 Beyond Light
        "oo2core_7_win64.dll",  # Destiny 2 Shadowkeep (устаревшая)
    ]

    # Возможные пути поиска
    SEARCH_PATHS = [
        ".",
        "./lib/",
        "../lib/",
    ]

    def __init__(self, dll_path: Optional[str] = None):
        """
        Инициализация Oodle менеджера.

        Args:
            dll_path: Прямой путь к DLL. Если None — выполняется автопоиск.
        """
        self.dll_path = None
        self._handle = None

        if dll_path and os.path.exists(dll_path):
            self._load_dll(dll_path)
        return

    def _auto_find_dll(self):
        """Автоматический поиск Oodle DLL в известных местах."""

        for search_path in self.SEARCH_PATHS:
            for dll_name in self.KNOWN_DLL_NAMES:
                full_path = os.path.join(search_path, dll_name)
                if os.path.exists(full_path):
                    self._load_dll(full_path)
                    return

        # Если не нашли — даём понятную инструкцию
        raise FileNotFoundError(
            "Oodle DLL не найдена.\n\n"
            "Пожалуйста, поместите один из следующих файлов в папку lib/:\n"
            + "\n".join(f"  • {dll}" for dll in self.KNOWN_DLL_NAMES)
            + "\n\n"
            "Эту библиотеку можно найти в составе инструментов:\n"
            "  - Destiny 2 Shadowkeep/Beyond Light\n"
            "  - Oodle SDK (https://www.radgametools.com/oodle.htm)\n"
            "  - Репозиторий с инструментами для Tiger Engine"
        )

    def _load_dll(self, path: str):
        """Загружает DLL и проверяет наличие нужных функций."""

        try:
            self._handle = cdll.LoadLibrary(path)
        except OSError as e:
            raise OSError(
                f"Не удалось загрузить Oodle DLL из {path}\n"
                f"Ошибка: {e}\n"
                f"Убедитесь, что у вас 64-битная версия Python и библиотека совместима."
            )

        # Проверяем наличие функции декомпрессии
        try:
            _ = self._handle.OodleLZ_Decompress
        except AttributeError:
            raise RuntimeError(
                f"Библиотека {path} не содержит функцию OodleLZ_Decompress"
            )

        self.dll_path = path
        print(f"[·] Загружена Oodle DLL: {os.path.basename(path)}")

    def decompress(self, data: bytes, output_size: Optional[int] = None) -> bytes:
        """
        Декомпрессия Oodle-сжатых данных.
        Код 0 означает, что данные не сжаты — возвращаем как есть.
        """
        if output_size is None:
            output_size = max(len(data) * 4, 0x40000)

        output_buffer = create_string_buffer(output_size)

        result = self._handle.OodleLZ_Decompress(
            c_char_p(data),
            c_int(len(data)),
            output_buffer,
            c_int(output_size),
            c_int(0),  # fuzz
            c_int(0),  # crc
            c_int(0),  # verbosity
            None,  # dst_base
            None,  # e
            None,  # cb
            None,  # cb_ctx
            None,  # scratch
            None,  # scratch_size
            c_int(3),  # thread_phase
        )

        if result == 0:
            # Данные не сжаты или не Oodle — возвращаем исходные
            return data

        if result < 0:
            raise RuntimeError(f"Oodle декомпрессия вернула код ошибки: {result}")

        return output_buffer.raw[:result]

    @property
    def is_loaded(self) -> bool:
        """Проверяет, загружена ли библиотека."""
        return self._handle is not None
