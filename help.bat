@echo off
chcp 65001 >nul
echo Available Commands — Marathon 2026 Package Extractor
echo =====================================================

echo.
echo Bat files (easiest — double-click to run):
echo.
echo   run.bat         Full pipeline: extract .pkg + convert .bin files
echo   extract.bat     Extract only: .pkg -^> .bin files
echo   convert.bat     Convert only: rename .bin files to correct extensions
echo   download.bat    Download required libraries (Oodle, vgmstream, ffmpeg)
echo.
echo NOTE: All bats auto-create a virtual environment (venv/) and install
echo the package on first run. You only need Python 3.12 installed.
echo.
echo Arguments (add after the bat name, e.g.: run.bat --no-convert-media):
echo.
echo   --convert-media     Transcode WEM to WAV and USM to MP4
echo   --no-convert-media  Skip media transcoding (rename only)
echo   --dry-run           Show what would be done without making changes
echo   --workers N         Number of parallel workers for extraction
echo.
echo Examples:
echo   run.bat --no-convert-media
echo   convert.bat --dry-run
echo   extract.bat --workers 4
echo.
echo If bats don't work, open a terminal in this folder and run:
echo   python -m venv venv
echo   venv\Scripts\activate
echo   pip install -e .
echo   python -m src.cli.main process
echo.
pause
