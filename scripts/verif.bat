@echo off
REM Vérification complète du projet sous Windows — équivalent de scripts/verif.sh
REM   scripts\verif.bat              tests backend + builds frontend (normal + démo)
REM   scripts\verif.bat rapide       syntaxe + tests backend uniquement
REM   scripts\verif.bat --rapide     idem (même option que la version bash)
setlocal
cd /d "%~dp0.."

REM Chemin ABSOLU : les etapes suivantes font "pushd backend", et un chemin
REM relatif y pointerait vers backend\backend\venv (pytest ne demarrait jamais).
set "RACINE=%CD%"
set "PY=%RACINE%\backend\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo == Verification Job Finder ==

echo -- Syntaxe backend
"%PY%" -m compileall -q backend\app
if errorlevel 1 goto echec

echo -- Tests backend (pytest)
pushd backend
"%PY%" -m pytest tests\ -q
if errorlevel 1 ( popd & goto echec )
popd

if /i "%~1"=="rapide" goto fin_rapide
if /i "%~1"=="--rapide" goto fin_rapide

echo -- Build frontend
pushd frontend
call npm run build --silent
if errorlevel 1 ( popd & goto echec )

echo -- Build demo (GitHub Pages)
REM setlocal isole deja VITE_DEMO : ne rien intercaler entre le build et le test
REM du code retour (une commande set ecraserait errorlevel).
set "VITE_DEMO=1"
call npx vite build --base=/Job-Finder/demo/ --outDir=dist-demo --logLevel=error
if errorlevel 1 ( popd & goto echec )
popd

echo == OK : tests + builds verts, pret a pousser ==
exit /b 0

:fin_rapide
echo == OK ^(rapide^) : syntaxe + tests verts ==
exit /b 0

:echec
echo == ECHEC : corrige avant de commiter / pousser ==
exit /b 1
