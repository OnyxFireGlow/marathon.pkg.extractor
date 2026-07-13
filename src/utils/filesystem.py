"""Модуль для проверки и подготовки файловой структуры."""

from pathlib import Path
from typing import List, Tuple


class FileSystemManager:
    """Управляет рабочей файловой структурой экстрактора."""

    REQUIRED_DIRS = ["raw", "extracted"]
    SUPPORTED_EXTENSIONS = (".pkg",)

    def __init__(self, base_dir: str = None, quiet: bool = False):
        """
        Инициализация файлового менеджера.

        Args:
            base_dir: Путь к корневой директории проекта.
                      Если None — определяется автоматически.
            quiet: Не выводить информационные сообщения.
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = self._find_project_root()

        if not quiet:
            print(f"[·] Корневая директория проекта: {self.base_dir}")

    @staticmethod
    def _find_project_root() -> Path:
        """
        Находит корень проекта.
        Ищет вверх по дереву директорий, пока не найдёт папку src/.
        Если не находит — используется директория на два уровня выше этого файла.
        """
        # Начинаем с директории, где лежит этот скрипт (utils/)
        current = Path(__file__).resolve().parent  # utils/

        # Поднимаемся на два уровня: utils/ -> src/ -> корень проекта
        project_root = current.parent.parent

        # Проверяем, что это действительно корень (должна быть папка src/)
        if (project_root / "src").is_dir():
            return project_root

        # Fallback: текущая рабочая директория
        cwd = Path.cwd()

        # Если мы в src/ или его поддиректориях — поднимаемся
        if cwd.name == "src" or (cwd / "src").is_dir():
            return cwd if cwd.name != "src" else cwd.parent

        # Ищем src/ вверх по дереву
        for parent in [cwd] + list(cwd.parents):
            if (parent / "src").is_dir():
                return parent

        # Последний fallback
        return cwd

    def validate_environment(self) -> Tuple[bool, List[str]]:
        """
        Проверяет структуру директорий. Создаёт отсутствующие папки.

        Returns:
            (успех_проверки, список_сообщений)
        """
        messages = []

        for dir_name in self.REQUIRED_DIRS:
            dir_path = self.base_dir / dir_name
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                messages.append(f"[✓] Создана папка: {dir_name}/")
            else:
                messages.append(f"[·] Папка существует: {dir_name}/")

        return True, messages

    def check_raw_directory(self) -> Tuple[bool, List[Path], str]:
        """
        Проверяет содержимое папки raw.

        Returns:
            (готовность_к_работе, список_pkg_файлов, сообщение)
        """
        raw_dir = self.base_dir / "raw"

        # Проверяем существование (хотя validate_environment уже должен создать)
        if not raw_dir.exists():
            return False, [], "[!] Папка raw/ не существует"

        # Получаем список всех файлов
        all_files = list(raw_dir.iterdir())

        # Папка пуста
        if not all_files:
            return (
                False,
                [],
                "[!] Папка raw/ пуста. Поместите туда .pkg файлы из игры Marathon 2026",
            )

        # Фильтруем только .pkg файлы
        pkg_files = [f for f in all_files if f.is_file() and f.suffix.lower() == ".pkg"]

        if not pkg_files:
            other_files = [f.name for f in all_files if f.is_file()]
            return (
                False,
                [],
                (
                    f"[!] В папке raw/ нет .pkg файлов.\n"
                    f"    Найдены файлы других типов: {', '.join(other_files[:5])}\n"
                    f"    Поместите .pkg файлы из Marathon 2026"
                ),
            )

        # Формируем информационное сообщение
        total_size = sum(f.stat().st_size for f in pkg_files)

        if total_size < 1024 * 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size / (1024 * 1024):.1f} MB"

        message = (
            f"[✓] Найдено .pkg файлов: {len(pkg_files)}\n"
            f"    Общий размер: {size_str}\n"
            f"    Файлы:\n"
            + "\n".join(f"      • {f.name}" for f in pkg_files)
            + "\n\n    Запустить расшифровку? [Y/n]: "
        )

        return True, pkg_files, message

    def get_extracted_path(self, pkg_name: str, category: str = "") -> Path:
        """
        Возвращает путь для выходных данных с сохранением структуры.

        Args:
            pkg_name: Имя исходного пакета (без расширения)
            category: Подкатегория (например, 'audio', 'textures', 'models')

        Returns:
            Путь вида extracted/<имя_пакета>/<категория>/
        """
        path = self.base_dir / "extracted" / Path(pkg_name).stem

        if category:
            path = path / category

        path.mkdir(parents=True, exist_ok=True)
        return path

    def find_project_dir(self, dirname: str) -> Path | None:
        """
        Ищет директорию dirname относительно корня проекта.

        Args:
            dirname: Имя искомой папки (например, 'extracted', 'raw')

        Returns:
            Path к папке или None
        """
        candidate = self.base_dir / dirname
        if candidate.exists() and candidate.is_dir():
            return candidate
        return None
