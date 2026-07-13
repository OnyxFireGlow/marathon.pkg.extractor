@echo off
chcp 65001 >nul
REM ==========================================
REM  Internal: set up venv + install package
REM ==========================================

set VENV_DIR=venv
set VENV_PYTHON=%~dp0%VENV_DIR%\Scripts\python.exe

set PYTHONWARNINGS=ignore::RuntimeWarning

if not exist "%VENV_PYTHON%" (
    echo [SETUP] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Install Python 3.12 from https://python.org
        pause
        exit /b 1
    )
)

"%VENV_PYTHON%" -c "import click, tqdm, rich, Crypto" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing package dependencies...
    "%VENV_PYTHON%" -m pip install -e "%~dp0."
    if errorlevel 1 (
        echo [ERROR] Failed to install package.
        pause
        exit /b 1
    )
)
