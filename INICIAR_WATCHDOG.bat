@echo off
title any-FLOW Printer Watchdog
color 0A
echo.
echo  ========================================
echo   Monitor Impresora any-FLOW - Watchdog
echo  ========================================
echo.
echo  Este programa se ejecutara en segundo plano.
echo  NO cierres esta ventana.
echo  Para detenerlo, presiona Ctrl+C
echo.
cd /d "%~dp0"
python watchdog.py
pause
