@echo off
chcp 65001 >nul
echo Install Dependencies for Marathon 2026 Package Extractor
echo =========================================================

call "%~dp0_venv.bat"

"%~dp0venv\Scripts\python.exe" -m src.cli.main install

echo.
echo Проверка / Checking:
if exist "%~dp0lib\oo2core_9_win64.dll" (
    echo [OK] oo2core_9_win64.dll
) else (
    echo [WARN] oo2core_9_win64.dll not found
)
if exist "%~dp0lib\vgmstream-cli.exe" (
    echo [OK] vgmstream-cli.exe
) else (
    echo [WARN] vgmstream-cli.exe not found
)
if exist "%~dp0lib\ffmpeg.exe" (
    echo [OK] ffmpeg.exe
) else (
    echo [WARN] ffmpeg.exe not found
)

pause
