@echo off
REM ============================================================
REM  Job Finder - scan + digest sans interface
REM  A planifier via le Planificateur de taches Windows si tu ne
REM  laisses pas l'application ouverte en permanence (README 5).
REM ============================================================
setlocal

REM Le journal est mis en place AVANT toute verification : une tache planifiee
REM qui echoue a 07h25 ne laisse sinon qu'un code de sortie dans le
REM Planificateur, y compris quand la cause est triviale.
set "JOURNAL=%~dp0data\scan-quotidien.log"
if not exist "%~dp0data" mkdir "%~dp0data"
echo. >> "%JOURNAL%"
echo ===== %DATE% %TIME% ===== >> "%JOURNAL%"

cd /d "%~dp0backend"

if not exist "venv\Scripts\python.exe" (
    echo [ERREUR] Environnement Python absent : lance start.bat une fois. >> "%JOURNAL%"
    echo [ERREUR] Environnement Python absent : lance start.bat une fois.
    exit /b 1
)

venv\Scripts\python -m app.cli scan >> "%JOURNAL%" 2>&1
set "CODE=%ERRORLEVEL%"
echo [code de sortie : %CODE%] >> "%JOURNAL%"
exit /b %CODE%
