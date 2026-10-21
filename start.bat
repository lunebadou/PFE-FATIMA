@echo off
chcp 65001 >nul
title TIMDEIZ Incendie
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python n'est pas installe. Installez-le depuis https://www.python.org/downloads/
    echo en cochant "Add python.exe to PATH", puis relancez ce fichier.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Premiere installation : creation de l'environnement Python...
    python -m venv .venv
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

echo Verification des dependances...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo Echec de l'installation des dependances. Verifiez la connexion Internet.
    pause
    exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul

rem Ouvre le navigateur 4 secondes apres, le temps que le serveur demarre
start "" /min cmd /c "timeout /t 4 >nul & start http://localhost:5000"

".venv\Scripts\python.exe" main.py
pause
