@echo off
REM ============================================================
REM  Job Finder — lancement sous Windows
REM  Premier lancement : installe tout (Python + Node requis)
REM  Lancements suivants : démarre directement le serveur
REM ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Python introuvable. Installe Python 3.11+ depuis https://www.python.org/downloads/
    echo          en cochant "Add python.exe to PATH", puis relance ce script.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [INFO] Fichier .env absent : copie de .env.example vers .env
    copy .env.example .env >nul
    echo        Pense a remplir tes cles API dans .env ^(voir README, section 3^).
)

if not exist "backend\venv" (
    echo [INSTALL] Creation de l'environnement Python...
    python -m venv backend\venv
)
echo [INSTALL] Mise a jour des dependances Python...
backend\venv\Scripts\pip install -q -r backend\requirements.txt

if not exist "frontend\dist" (
    where npm >nul 2>nul
    if errorlevel 1 (
        echo [ERREUR] npm introuvable et l'interface n'est pas encore construite.
        echo          Installe Node.js depuis https://nodejs.org puis relance ce script.
        pause
        exit /b 1
    )
    echo [INSTALL] Construction de l'interface ^(une seule fois^)...
    cd frontend
    call npm install --no-audit --no-fund
    call npm run build
    cd ..
)

echo.
echo ============================================================
echo  Job Finder demarre sur http://127.0.0.1:8000
echo  Laisse cette fenetre ouverte ^(scan quotidien automatique^).
echo  Ctrl+C pour arreter.
echo ============================================================
start "" http://127.0.0.1:8000
cd backend
venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
