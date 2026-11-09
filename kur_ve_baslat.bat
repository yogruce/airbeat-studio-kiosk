@echo off
chcp 65001 >nul
title AirBeat Studio (Kiosk Edition) - Otomatik Kurulum Sihirbazi
cd /d "%~dp0"

echo ========================================================
echo   AirBeat Studio (Kiosk Edition) - KURULUM SIHIRBAZI
echo ========================================================
echo.
echo [1/3] Masaustu kisayolu olusturuluyor...

set "TARGET_BAT=%~dp0baslat.bat"
if exist "%~dp0AirBeatStudioKiosk.exe" (
    set "TARGET_BAT=%~dp0AirBeatStudioKiosk.exe"
)

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $desk = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut((Join-Path $desk 'AirBeat Studio Kiosk.lnk')); $s.TargetPath = '%TARGET_BAT%'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'AirBeat Studio (Kiosk Edition)'; $s.Save()"

echo [2/3] Guncellemeler kontrol ediliyor...
call "%~dp0guncelle.bat"

echo [3/3] AirBeat Studio Kiosk baslatiliyor...
call "%~dp0baslat.bat"
exit /b 0
