# Marathon 2026 Package Extractor

Tool for extracting and converting resources from `.pkg` files of the game **Marathon 2026** (Tiger Engine).

## Features

- **Extraction** — unpack `.pkg` files into separate `.bin` files, with AES-GCM decryption and Oodle decompression
- **Conversion** — rename `.bin` files to their original extensions based on file signatures (WEM, OGG, MP4, DDS, PNG, USM, etc.) and optionally transcode audio (WEM → WAV) and video (USM → MP4)

## Quick Start

1. **Install Python 3.12** from [python.org](https://python.org) — make sure to check **"Add to PATH"**
2. Double-click `download.bat` — creates a virtual environment, installs the package, and downloads required libraries
3. Copy your `.pkg` files from Marathon 2026 into the `raw/` folder
4. Double-click `run.bat`

That's it. The batch files automatically manage the Python virtual environment on first run.

### Bat files

| Bat file | What it does |
|----------|-------------|
| `run.bat` | Full pipeline: extract .pkg → convert .bin files |
| `extract.bat` | Extract only: .pkg → .bin |
| `convert.bat` | Convert only: rename .bin to correct extensions |
| `download.bat` | Download required libraries (Oodle, vgmstream, ffmpeg) |
| `help.bat` | Show available commands and examples |

Add arguments after the filename, e.g.: `run.bat --no-convert-media`

| Argument | Effect |
|----------|--------|
| `--convert-media` | Transcode WEM → WAV (audio) and USM → MP4 (video) |
| `--no-convert-media` | Skip transcoding, rename only |
| `--dry-run` | Show what would be done without making changes |
| `--workers N` | Use N parallel threads for extraction |

### Manual console usage (if bats don't work)

```bash
python -m venv venv
venv\Scripts\activate
pip install -e .
python -m src.cli.main process    # full pipeline
python -m src.cli.main extract    # extract only
python -m src.cli.main convert    # convert only
```

## Requirements

- **Python 3.12**
- **Windows** (for Oodle DLL and vgmstream)

### Dependencies (downloaded by `download.bat`)

| Library | Purpose |
|---------|---------|
| `oo2core_9_win64.dll` | Oodle decompression — required for extraction |
| `vgmstream-cli.exe` | Audio transcoding (WEM → WAV) |
| `ffmpeg.exe` | Video transcoding (USM → MP4) |

## Project Structure

```
marathon.pkg.extractor/
├── raw/                    # Place .pkg files here
├── extracted/              # Extracted .bin files
│   └── <package_name>/
│       └── <id>.bin
├── lib/                    # Dependencies (Oodle, vgmstream, ffmpeg)
├── src/
│   ├── core/
│   │   ├── package.py      # .pkg parser and extractor
│   │   ├── converter.py    # .bin format detection and renaming
│   │   ├── signatures.py   # File signature database
│   │   └── constants.py    # Offsets, keys, configuration
│   ├── utils/
│   │   ├── oodle.py        # Oodle decompression wrapper
│   │   ├── downloader.py   # Dependency auto-installer
│   │   ├── filesystem.py   # Directory management
│   │   └── logger.py       # Logging setup
│   └── cli/
│       └── main.py         # Command-line interface
├── tests/
│   └── unit/               # Unit tests
├── venv/                   # Virtual environment (auto-created)
├── run.bat                 # Quick start — full pipeline
├── extract.bat             # Extract only
├── convert.bat             # Convert only
├── download.bat            # Install dependencies
├── _venv.bat               # Internal helper (venv setup)
├── help.bat                # Show available commands
├── pyproject.toml
├── LICENSE
└── README.md
```

## Detected Formats

| Extension | Format | Description |
|-----------|--------|-------------|
| `.wem` | WWise Audio | Audio in Wwise container |
| `.ogg` | Ogg Vorbis | Compressed audio |
| `.usm` | CriWare USM | Video in USM container |
| `.mp4` | MP4 | Video format |
| `.bnk` | WWise SoundBank | Sound bank |
| `.dds` | DirectDraw Surface | Texture |
| `.png` | PNG | Image |
| `.pkg` | Tiger Package | Game data package |
| `.gz` / `.zz` | GZip / zlib | Compressed data |

## Troubleshooting

**Python not found**
Install Python 3.12 from [python.org](https://python.org) with **"Add to PATH"** checked.

**Oodle DLL not found**
Run `download.bat` to install it automatically.

**Files not converting**
Make sure `vgmstream-cli.exe` is in `lib/` (audio) or `ffmpeg.exe` (video). Run `download.bat`.

**Extraction is slow**
Try `extract.bat --workers 4` to parallelize.

## License

MIT License — Copyright (c) 2026 OnyxFireGlow

See [LICENSE](LICENSE) for full terms in English and Russian.

**Author:** [Aleksey Petrushenko (OnyxFireGlow)](https://github.com/OnyxFireGlow)

*This tool is intended for educational and research purposes only.*
