"""
Marathon 2026 Package Extractor
Точка входа в программу.
"""

import sys
from pathlib import Path

# Добавляем src в путь (если запускаем из корня проекта)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.package import TigerPackage
from src.utils.filesystem import FileSystemManager
from src.utils.oodle import OodleManager


def main():
    """Основная функция."""

    print("╔══════════════════════════════════════╗")
    print("║  Marathon 2026 Package Extractor    ║")
    print("║  Tiger Engine .pkg tool            ║")
    print("╚══════════════════════════════════════╝")
    print()

    # Шаг 1: Проверка окружения
    fs = FileSystemManager()

    success, messages = fs.validate_environment()
    for msg in messages:
        print(msg)

    if not success:
        print("[!] Критическая ошибка при проверке окружения")
        return 1

    # Шаг 2: Проверка папки raw
    ready, pkg_files, message = fs.check_raw_directory()
    print()
    print(message)

    if not ready:
        return 1

    # Шаг 3: Пробуем загрузить Oodle
    print("[·] Поиск Oodle библиотеки...")
    try:
        oodle = OodleManager()
    except FileNotFoundError as e:
        print(f"\n[!] {e}")
        return 1
    except Exception as e:
        print(f"\n[!] Ошибка загрузки Oodle: {e}")
        return 1

    print("[✓] Oodle готов к работе\n")

    # Шаг 4: Запрос подтверждения
    try:
        response = input(">>> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n[·] Отмена операции")
        return 0

    if response not in ("y", "yes", "да", ""):
        print("[·] Операция отменена пользователем")
        return 0

    # Шаг 5: Обработка пакетов
    print("\n" + "=" * 50)
    print("Начинаю расшифровку...")
    print("=" * 50)

    for pkg_file in pkg_files:
        try:
            print(f"\n{'─' * 50}")
            print(f"Обработка: {pkg_file.name}")
            print(f"{'─' * 50}")

            # Загружаем и парсим пакет
            package = TigerPackage(str(pkg_file), oodle)
            package.load()

            # Создаём выходную директорию
            output_dir = fs.get_extracted_path(pkg_file.stem)

            # Извлекаем все файлы
            extracted = package.extract_all_parallel(max_workers=8)

            # Сохраняем файлы
            print(f"\n[·] Сохранение файлов в {output_dir}")

            for name, data in extracted.items():
                file_path = output_dir / f"{name}.bin"
                with open(file_path, "wb") as f:
                    f.write(data)

            print(f"[✓] Извлечено {len(extracted)} файлов")

        except Exception as e:
            print(f"\n[!] Ошибка при обработке {pkg_file.name}:")
            print(f"    {e}")
            import traceback

            traceback.print_exc()
            continue

    print("\n" + "=" * 50)
    print("[✓] Расшифровка завершена!")
    print("[✓] Файлы сохранены в папку extracted/")
    print("=" * 50)

    print("\n" + "=" * 50)
    print("📁 Содержимое extracted/:")
    print("=" * 50)

    extracted_dir = fs.base_dir / "extracted"
    for pkg_dir in sorted(extracted_dir.iterdir()):
        if pkg_dir.is_dir():
            files = list(pkg_dir.glob("*.bin"))
            total_size = sum(f.stat().st_size for f in files)
            print(f"\n  {pkg_dir.name}/")
            print(f"  Файлов: {len(files)} | Размер: {total_size:,} байт")

            # Показываем первые 5 файлов
            for f in sorted(files)[:5]:
                size = f.stat().st_size
                # Читаем первые 16 байт для сигнатуры
                with open(f, "rb") as fh:
                    sig = fh.read(16)
                sig_hex = sig.hex(" ")[:47]
                sig_ascii = "".join(chr(b) if 32 <= b < 127 else "." for b in sig[:16])
                print(f"    {f.name}: {size:>8,} B  [{sig_hex}] {sig_ascii}")

            if len(files) > 5:
                print(f"    ... и ещё {len(files) - 5} файлов")

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
