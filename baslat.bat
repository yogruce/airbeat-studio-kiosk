@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
title AirBeat Studio - Kiosk Edition Baslatici
cd /d "%~dp0"

echo ========================================================
echo   AirBeat Studio (Kiosk Edition)
echo   Otomatik Guncelleme ve Baslatma Araci
echo ========================================================
echo.

:: 1. Eger hazir derlenmis EXE varsa once guncellemeyi kontrol et ve EXE'yi calistir
if exist "AirBeatStudioKiosk.exe" (
    goto :RUN_EXE
)

:: 2. Python Sanal Ortami Kontrolu (Ilk Kurulum - Python 3.12 / 3.11 oncelikli)
if not exist .venv\Scripts\python.exe (
    echo [BILGI] Ilk kullanim algilandi, sanal ortam hazirlaniyor...
    py -3.12 -m venv .venv >nul 2>&1
    if errorlevel 1 (
        py -3.11 -m venv .venv >nul 2>&1
    )
    if errorlevel 1 (
        python -m venv .venv >nul 2>&1
    )
    if not exist .venv\Scripts\python.exe (
        echo [BILGI] Python 3.12 bulunamadi, winget ile otomatik kuruluyor...
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        py -3.12 -m venv .venv
    )
)

:: 3. Gerekli kutuphaneler kurulu mu?
.venv\Scripts\python.exe -c "import cv2, mediapipe, pygame, sounddevice, scipy" >nul 2>&1
if errorlevel 1 (
    echo [BILGI] Gerekli ses ve goruntu kutuphaneleri yukleniyor, lutfen bekleyin...
    .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
)

:: 4. Acilista GitHub'dan otomatik guncelleme kontrolu
echo [GUNCELLEME] GitHub uzerinden en son surum kontrol ediliyor...
if exist .git (
    where git >nul 2>&1
    if not errorlevel 1 (
        git fetch origin main >nul 2>&1
        git reset --hard origin/main >nul 2>&1
    )
) else (
    .venv\Scripts\python.exe -c "from core.updater import AutoUpdater; u = AutoUpdater(); info = u.check_for_updates(); u.apply_update() if info.get('has_update') else None" >nul 2>&1
)

:RUN_PYTHON
echo [BASLATILIYOR] AirBeat Studio Kiosk aciliyor...
.venv\Scripts\python.exe main.py
if "%ERRORLEVEL%"=="42" (
    echo [YENIDEN BASLATMA] Yeni guncelleme uygulandi, tekrar baslatiliyor...
    timeout /t 1 /nobreak >nul
    goto :RUN_PYTHON
)
exit /b 0

:RUN_EXE
echo [BASLATILIYOR] AirBeatStudioKiosk.exe aciliyor...
start "" "AirBeatStudioKiosk.exe"
exit /b 0
