"""
Унифицированная система логирования с поддержкой уровней и цветов.
"""

import logging
import sys
from pathlib import Path

import click


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветами для консоли."""

    COLORS = {
        "DEBUG": "dim",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red",
    }

    def format(self, record):
        msg = super().format(record)
        color = self.COLORS.get(record.levelname, "white")
        return click.style(msg, fg=color)


class LoggerManager:
    """Управляет логгерами для всех модулей."""

    _instance = None
    _loggers = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_root_logger()
        return cls._instance

    def _setup_root_logger(self):
        """Настраивает корневой логгер."""
        self.root_logger = logging.getLogger("marathon")
        self.root_logger.setLevel(logging.INFO)
        self.root_logger.handlers.clear()

        # Консольный handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # Формат без времени
        formatter = ColoredFormatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(formatter)

        self.root_logger.addHandler(console_handler)

    def get_logger(self, name: str, level: str = "INFO") -> logging.Logger:
        """Возвращает логгер для модуля."""
        if name in self._loggers:
            return self._loggers[name]

        logger = self.root_logger.getChild(name)
        logger.setLevel(getattr(logging, level.upper()))
        self._loggers[name] = logger
        return logger

    def set_level(self, level: str):
        """Устанавливает уровень логирования."""
        level_num = getattr(logging, level.upper())
        self.root_logger.setLevel(level_num)
        for logger in self._loggers.values():
            logger.setLevel(level_num)

    def add_file_handler(self, log_file: Path):
        """Добавляет файловый handler."""
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        self.root_logger.addHandler(file_handler)


# Глобальный менеджер
logger_manager = LoggerManager()


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Удобный доступ к логгеру."""
    return logger_manager.get_logger(name, level)


def set_log_level(level: str):
    """Устанавливает уровень логирования глобально."""
    logger_manager.set_level(level)


def add_file_log(log_file: Path):
    """Добавляет запись лога в файл."""
    logger_manager.add_file_handler(log_file)
