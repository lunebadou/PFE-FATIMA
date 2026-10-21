@echo off
chcp 65001 >nul
title TIMDEIZ Incendie - Import de l'ancienne base
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Lancez d'abord start.bat une premiere fois, puis fermez-le et relancez ce fichier.
    pause
    exit /b 1
)

echo Installation du connecteur MySQL...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q mysql-connector-python
if errorlevel 1 (
    echo Echec de l'installation. Verifiez la connexion Internet.
    pause
    exit /b 1
)

echo.
echo ATTENTION : le contenu actuel de la nouvelle application va etre remplace
echo par celui de l'ancienne base MySQL.
choice /c ON /m "Continuer (O = oui, N = non)"
if errorlevel 2 exit /b 0

".venv\Scripts\python.exe" importer_mysql.py
pause
