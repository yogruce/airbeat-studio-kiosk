@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title AirBeat Studio Kiosk - Tek Tikla Guncelleme Araci
cd /d "%~dp0"

echo ========================================================
echo   AirBeat Studio (Kiosk Edition) - Otomatik Guncelleyici
echo ========================================================
echo.

:: 1. Eger Git deposu ise git uzerinden guncelle
if exist .git (
    where git >nul 2>&1
    if not errorlevel 1 (
        echo [1/2] Git uzerinden en son guncellemeler aliniyor...
        git fetch origin main
        git reset --hard origin/main
        goto :DONE
    )
)

:: 2. Git yoksa dogrudan GitHub ZIP arsivini indir ve guncelle
echo [1/2] GitHub'dan en guncel surum indiriliyor...
set "ZIP_FILE=%TEMP%\airbeat_kiosk_latest.zip"
set "EXTRACT_DIR=%TEMP%\airbeat_kiosk_extract"

powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/yogruce/airbeat-studio-kiosk/archive/refs/heads/main.zip' -OutFile '%ZIP_FILE%'"
if errorlevel 1 (
    echo [HATA] Guncelleme indirilemedi. Internet baglantinizi kontrol edin.
    pause
    exit /b 1
)

echo [2/2] Dosyalar guncelleniyor...
powershell -NoProfile -Command "if (Test-Path '%EXTRACT_DIR%') { Remove-Item '%EXTRACT_DIR%' -Recurse -Force }; Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force; $src = Get-ChildItem -Path '%EXTRACT_DIR%' -Directory | Select-Object -First 1; Copy-Item -Path ($src.FullName + '\*') -Destination '%~dp0' -Recurse -Force; Remove-Item -Path '%EXTRACT_DIR%' -Recurse -Force; Remove-Item -Path '%ZIP_FILE%' -Force"

:DONE
echo.
echo ========================================================
echo   [BASARILI] AirBeat Studio Kiosk en son surume guncellendi!
echo ========================================================
timeout /t 3 /nobreak >nul
exit /b 0
