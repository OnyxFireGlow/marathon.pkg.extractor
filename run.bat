@echo off
chcp 65001 >nul
echo Marathon 2026 Package Extractor
echo ================================

call "%~dp0_venv.bat"

"%~dp0venv\Scripts\python.exe" -m src.cli.main process %*

echo.
pause
