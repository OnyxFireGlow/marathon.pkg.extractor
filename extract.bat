@echo off
chcp 65001 >nul
echo Marathon 2026 Package Extractor - Extract
echo ==========================================

call "%~dp0_venv.bat"

"%~dp0venv\Scripts\python.exe" -m src.cli.main extract %*

pause
