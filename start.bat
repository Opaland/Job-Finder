@echo off
REM ============================================================
REM  Job Finder — lancement sous Windows
REM  Premier lancement : installe tout (Python + Node requis)
REM  Lancements suivants : demarre directement le serveur
REM ============================================================
setlocal
title Job Finder
cd /d "%~dp0"

REM --- 1. Trouver Python (lanceur py en priorite, sinon python) ---
set "PY="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python --version >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo.
    echo [ERREUR] Python introuvable ou non fonctionnel.
    echo.
    echo   1. Installe Python 3.11+ depuis https://www.python.org/downloads/
    echo      en cochant "Add python.exe to PATH" au debut de l'installation.
    echo   2. Si Python est deja installe : desactive l'alias du Microsoft Store
    echo      ^(Parametres ^> Applications ^> Parametres avances d'applications
    echo      ^> Alias d'execution d'applications ^> desactiver python.exe^).
    echo   3. Ferme puis rouvre cette fenetre, et relance start.bat
    echo.
    pause
    exit /b 1
)
echo [OK] Python detecte : %PY%

REM --- 2. Fichier .env ---
if not exist ".env" (
    echo [INFO] Fichier .env absent : copie de .env.example vers .env
    copy .env.example .env >nul
    echo        Pense a remplir tes cles API dans .env ^(voir README, section 3^).
)

REM --- 3. Environnement Python ---
if exist "backend\venv\Scripts\python.exe" goto deps
echo [INSTALL] Creation de l'environnement Python...
%PY% -m venv backend\venv
if not exist "backend\venv\Scripts\python.exe" (
    echo.
    echo [ERREUR] La creation de l'environnement Python a echoue ^(voir message ci-dessus^).
    echo          Supprime le dossier backend\venv puis relance start.bat
    pause
    exit /b 1
)

:deps
echo [INSTALL] Verification des dependances Python...
backend\venv\Scripts\python -m pip install -q --disable-pip-version-check -r backend\requirements.txt
if errorlevel 1 (
    echo.
    echo [ERREUR] L'installation des dependances Python a echoue ^(voir message ci-dessus^).
    echo          Verifie ta connexion internet puis relance start.bat
    pause
    exit /b 1
)

REM --- 4. Interface (build une seule fois) ---
if exist "frontend\dist\index.html" goto run
where npm >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERREUR] npm introuvable et l'interface n'est pas encore construite.
    echo          Installe Node.js LTS depuis https://nodejs.org puis ferme et
    echo          rouvre cette fenetre, et relance start.bat
    pause
    exit /b 1
)
echo [INSTALL] Installation des dependances de l'interface...
cd frontend
call npm install --no-audit --no-fund
if errorlevel 1 (
    echo.
    echo [ERREUR] npm install a echoue ^(voir message ci-dessus^).
    cd ..
    pause
    exit /b 1
)
echo [INSTALL] Construction de l'interface...
call npm run build
if errorlevel 1 (
    echo.
    echo [ERREUR] La construction de l'interface a echoue ^(voir message ci-dessus^).
    cd ..
    pause
    exit /b 1
)
cd ..

:run
echo.
echo ============================================================
echo  Job Finder demarre sur http://127.0.0.1:8000
echo  Laisse cette fenetre ouverte ^(scan quotidien automatique^).
echo  Ctrl+C pour arreter.
echo ============================================================
start "" http://127.0.0.1:8000
cd backend
venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo [INFO] Le serveur s'est arrete. Message d'erreur eventuel ci-dessus.
pause
