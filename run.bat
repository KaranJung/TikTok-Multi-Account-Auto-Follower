@echo off
title TikTok Multi-Account Auto-Follower by @hydra_X001
setlocal enabledelayedexpansion

:: Force Windows console and Python I/O to UTF-8
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8
set PYTHONLEGACYWINDOWSSTDIO=0

:: Set comfortable standard console window size (100 cols, 32 rows)
mode con: cols=100 lines=32 >nul 2>&1

:: Navigate to script directory
cd /d "%~dp0"

:: 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [-] Python is not installed or not in your system PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Fast check for required dependencies
python -c "import playwright, playwright_stealth, rich, curl_cffi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] First-time setup: Installing required dependencies...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [-] Failed to install required dependencies.
        pause
        exit /b 1
    )
)

:: 3. Check Playwright Chromium browser
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] First-time setup: Installing Playwright Chromium browser...
    python -m playwright install chromium
    if %errorlevel% neq 0 (
        echo [-] Failed to install Playwright Chromium.
        pause
        exit /b 1
    )
)

:: 4. Run main.py (animated Rich interface handles all displays and interactions)
python main.py %*

if %errorlevel% neq 0 (
    echo.
    echo [!] Bot finished with exit code %errorlevel%.
)

echo.
echo Press any key to exit...
pause >nul
