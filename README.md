# Marathon 2026 Package Extractor

[Русский](#русский) | [English](#english)

[Лицензия](#лицензияlicense) | [License](#лицензияlicense)

---

## Русский

Инструмент для извлечения, анализа и конвертации ресурсов из `.pkg` файлов игры **Marathon 2026** (Tiger Engine).

### Возможности

- **Извлечение** — распаковка `.pkg` файлов в отдельные файлы с сохранением структуры
- **Анализ** — определение форматов файлов по сигнатурам (аудио, видео, текстуры, сжатые данные)
- **Конвертация** — на данный момент только преобразование аудио (WEM → WAV) и видео (USM → MP4)
- **Валидация ключей** — проверка AES-GCM ключей для зашифрованных пакетов
- **Авто-установка** — автоматическая загрузка необходимых библиотек (Oodle, vgmstream, ffmpeg)

## Установка
### Требования

- Python 3.12
- Windows (для Oodle DLL и vgmstream)

#### Установка из репозитория

```bash
git clone https://github.com/onyxfireglow/marathon-pkg-extractor.git
cd marathon-pkg-extractor
```

#### Создание виртуального окружения
```bash
python -m venv venv
venv\Scripts\activate  # Windows
```

#### Установка зависимостей
```bash
pip install -e requirements.txt
```

#### Или установка вручную
```bash
pip install click rich tqdm requests pycryptodome
```

#### Автоматическая установка зависимостей
Инструмент сам скачает необходимые библиотеки в папку lib/:

---
|Библиотека | Назначение |
|-----------|------------|
| oo2core_9_win64.dll |	Декомпрессия Oodle (необходима для извлечения)|
| vgmstream-cli.exe | Конвертация аудио (WEM → WAV) |
| ffmpeg.exe | Конвертация видео (USM → MP4) |
---
### Установка всех зависимостей
```bash
python -m src.main install
```
## Использование
### Основные команды

#### Полный пайплайн (извлечение → анализ → конвертация)
```bash
python -m src.main process
```
#### Только извлечение
```bash
python -m src.main extract
```
#### Анализ извлечённых файлов
```bash
python -m src.main analyze
```
#### Конвертация файлов в правильные форматы
```bash
python -m src.main convert --convert-media
```
#### Проверка аудиофайлов
```bash
python -m src.main check
```
## Примеры
#### Без конвертации
```bash
python -m src.main process --no-convert-media
```
#### Параллельное извлечение с 4 воркерами
```bash
python -m src.main extract --workers 4
```
#### Анализ с подробным выводом
```bash
python -m src.main analyze --verbose
```

#### Конвертация в тестовом режиме
```bash
python -m src.main convert --convert-media --dry-run
```
---
### Структура проекта
```text

marathon.pkg.extractor/
├── raw/                    # Поместите сюда .pkg файлы из игры
├── extracted/              # Извлечённые файлы
│   └── <package_name>/
│       └── <id>.bin
├── extracted/converted/    # Сконвертированные файлы
├── lib/                    # Загруженные зависимости
├── src/
│   ├── core/               # Основная логика
│   │   ├── package.py      # Работа с .pkg файлами
│   │   ├── constants.py    # Константы и ключи
│   │   ├── analyze.py      # Анализ форматов
│   │   ├── converter.py    # Конвертация
│   │   └── cryptographer.py # Валидация ключей
│   └── utils/              # Вспомогательные модули
│       ├── downloader.py   # Авто-установка
│       ├── filesystem.py   # Работа с файловой системой
│       ├── logger.py       # Логирование
│       └── oodle.py        # Обёртка Oodle
├── setup.py
└── README.md
```
## Форматы файлов
### Инструмент определяет следующие форматы:

| Расширение | Формат | Описание |
|---|---|---|
|.wem    |	WWise Audio          |  Аудио в контейнере Wwise |
|.ogg    |	Ogg Vorbis           |  Сжатый аудиоформат       |
|.wav    |	WAV                  |  Несжатый аудиоформат     |
|.usm    |  CriWare USM	         |  Видео в контейнере USM   |
|.mp4    |	MP4                  |  Видеоформат              |
|.bnk    |  WWise SoundBank	     |  Звуковой банк            |
|.dds    |  DirectDraw Surface	 |  Текстура                 |
|.png    |  PNG                  |  Изображение              |
|.pkg    |  Tiger Package	     |  Пакет данных игры        |
|.gz, .zz|	GZip / zlib          |  Сжатые данные	         |
---
## Экспериментальные возможности (для разработки)
### Валидация ключей 
#### Для проверки AES-GCM ключей:

```bash
python -m src.main validate --auto-find-pkg
```

### Решение проблем
#### Ошибка "Oodle DLL not found"
Убедитесь, что в папке lib/ есть oo2core_9_win64.dll.

``` bash
python -m src.main install
```
#### Ошибка "No module named 'src'"

Установите пакет в режиме разработки:

``` bash
pip install -e .
```
Или используйте запуск через модуль:

```bash
python -m src.main process
```


#### Файлы не конвертируются

Убедитесь, что установлены необходимые инструменты.

```bash
python -m src.main --with-ffmpeg
```

# Лицензия и условия использования
## Права на код
Данное программное обеспечение распространяется бесплатно в рамках лицензии MIT.

*Автор: Петрушенко Алексей Алексеевич (OnyxFireGlow)*

### Условия использования:

1. Вы можете свободно использовать, копировать, изменять и распространять данный код

2. При распространении обязательно указание авторства с ссылкой на GitHub автора

3. Запрещена продажа данного кода как отдельного продукта

4. Вы не можете выдавать данный код за свой собственный

**Ссылка на автора: https://github.com/onyxfireglow**

### Все сторонние компоненты сохраняют свои оригинальные лицензии и авторские права.

## Отказ от ответственности
Данное ПО предоставляется **"КАК ЕСТЬ"**, без каких-либо гарантий, явных или подразумеваемых, включая, но не ограничиваясь, гарантиями товарной пригодности, соответствия конкретным целям и ненарушения прав интеллектуальной собственности.

Инструмент предназначен исключительно для образовательных и исследовательских целей.

### Пользователь принимает на себя всю ответственность за:

- Соблюдение применимых законов и нормативных актов

- Уважение прав интеллектуальной собственности

- Любые последствия, возникающие при использовании этого инструмента

**Ни при каких обстоятельствах автор не несёт ответственности за любые претензии, убытки или другую ответственность, возникающие в связи с использованием данного ПО.**

---

## English
Tool for extracting, analyzing and converting resources from .pkg files of Marathon 2026 (Tiger Engine).

### Features
---
 - **Extraction** - unpack .pkg files into separate files preserving structure

- **Analysis** - detect file formats by signatures (audio, video, textures, compressed data)

- **Conversion** - convert audio (WEM → WAV) and video (USM → MP4)

- **Key Validation** - verify AES-GCM keys for encrypted packages

- **Auto-Install** - automatic download of required libraries (Oodle, vgmstream, ffmpeg)

## Installation
### Requirements
- Python 3.12

- Windows (for Oodle DLL and vgmstream)

Install from repository
```bash
git clone https://github.com/onyxfireglow/marathon-pkg-extractor.git
cd marathon-pkg-extractor
```
# Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate  # Windows
```

# Install dependencies
```bash
pip install -e requirements.txt
```

# Or manual install
```bash
pip install click rich tqdm requests pycryptodome
```
#### Automatic Dependency Installation
The tool will automatically download required libraries to lib/:

---
| Library | Purpose |
|---|---|
| oo2core_9_win64.dll |	Oodle decompression (required for extraction)|
| vgmstream-cli.exe | Audio conversion (WEM → WAV) |
| ffmpeg.exe | Video conversion (USM → MP4) |
---

### Install all dependencies
```bash
python -m src.main install
```

## Usage
### Basic Commands
#### Full pipeline (extract → analyze → convert)
```bash
python -m src.main process
```

#### Extract only
```bash
python -m src.main extract
```

#### Analyze extracted files
```bash
python -m src.main analyze
```

#### Convert files to proper formats
```bash
python -m src.main convert --convert-media
```

#### Check audio files
```bash
python -m src.main check
```


## Examples
#### Skip conversion
```bash
python -m src.main process --no-convert-media
```

#### Parallel extraction with 4 workers
```bash
python -m src.main extract --workers 4
```

#### Verbose analysis
```bash
python -m src.main analyze --verbose
```

#### Dry-run conversion
```bash
python -m src.main convert --convert-media --dry-run
```
---
### Project Structure
```text
marathon.pkg.extractor/
├── raw/                    # Place .pkg files from the game here
├── extracted/              # Extracted files
│   └── <package_name>/
│       └── <id>.bin
├── extracted/converted/    # Converted files
├── lib/                    # Downloaded dependencies
├── src/
│   ├── core/               # Core logic
│   │   ├── package.py      # .pkg file handling
│   │   ├── constants.py    # Constants and keys
│   │   ├── analyze.py      # Format analysis
│   │   ├── converter.py    # Conversion logic
│   │   └── cryptographer.py # Key validation
│   └── utils/              # Helper modules
│       ├── downloader.py   # Auto-installation
│       ├── filesystem.py   # File system operations
│       ├── logger.py       # Logging
│       └── oodle.py        # Oodle wrapper
├── setup.py
└── README.md
```
## File Formats
### The tool detects the following formats:

| Extension | Format | Description |
|---|---|---|
|.wem    |	WWise Audio          |  Audio in Wwise container |
|.ogg    |	Ogg Vorbis           |  Compressed audio format       |
|.wav    |	WAV                  |  Uncompressed audio format     |
|.usm    |  CriWare USM	         |  Video in USM container   |
|.mp4    |	MP4                  |  Video format             |
|.bnk    |  WWise SoundBank	     |  SoundBank	Sound bank            |
|.dds    |  DirectDraw Surface	 |  Texture               |
|.png    |  PNG                  |  Image             |
|.pkg    |  Tiger Package	     |  Game data package        |
|.gz, .zz|	GZip / zlib          |  Compressed data	         |

### Key Validation
#### To validate AES-GCM keys:

```bash
python -m src.main validate --auto-find-pkg
```

### Troubleshooting
#### Error: "Oodle DLL not found"

Make sure oo2core_9_win64.dll is in the lib/ folder.

``` bash
python -m src.main install
```

#### Error: "No module named 'src'"

Install the package in development mode:
``` bash
pip install -e .
```
Or run via module:
```bash
python -m src.main process
```


#### Files not converting

Make sure required tools are installed:

```bash
python -m src.main --with-ffmpeg
```


# License and Terms of Use
### Code Rights
This software is distributed for free under the MIT License.

**Author: Aleksey Petrushenko (OnyxFireGlow)**

## Terms of Use:

1. You are free to use, copy, modify and distribute this code

2. When distributing, you must provide attribution with a link to the author's GitHub

3. Selling this code as a standalone product is prohibited

4. You may not claim this code as your own

**Author Link: https://github.com/onyxfireglow**

## Third-Party Dependencies
**All third-party components retain their original licenses and copyrights.**

## Disclaimer
THIS SOFTWARE IS PROVIDED "AS IS", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement.

**This tool is intended for educational and research purposes only.**

The user assumes all responsibility for:

- Compliance with applicable laws and regulations

- Respecting intellectual property rights

- Any consequences arising from the use of this tool

**In no event shall the author be liable for any claim, damages or other liability arising from the use of this software.**

## Developers

* [**__OnyxFireGlow__**](https://github.com/OnyxFireGlow)


## Лицензия/License
### MIT License

**Copyright (c) 2026 OnyxFireGlow**

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.