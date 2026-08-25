@echo off
REM Job Finder — installe la tache planifiee du scan quotidien.
REM Le PC en VEILLE est reveille a 07h25, le scan tourne, l'email part, puis le
REM PC repart en veille. (Un PC completement eteint ne peut pas etre reveille.)
setlocal
cd /d "%~dp0"

set "NOM=Job Finder - scan quotidien"
set "SCAN=%~dp0scan.bat"
set "DOSSIER=%~dp0"
if "%DOSSIER:~-1%"=="\" set "DOSSIER=%DOSSIER:~0,-1%"
set "MODELE=%~dp0tache-quotidienne.xml"
set "TEMPXML=%TEMP%\job-finder-tache.xml"

if not exist "%SCAN%" (
    echo ERREUR : scan.bat est introuvable dans "%~dp0".
    echo Lance ce script depuis le dossier du projet Job-Finder.
    pause
    exit /b 1
)
if not exist "%MODELE%" (
    echo ERREUR : tache-quotidienne.xml est introuvable ^(depot incomplet ?^).
    pause
    exit /b 1
)

echo Preparation de la tache pour :
echo    %SCAN%
echo.

REM Le Planificateur veut de l'UTF-16 : PowerShell ecrit le fichier au bon format.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "(Get-Content -LiteralPath $env:MODELE -Raw) -replace '__CHEMIN_SCAN__', [Security.SecurityElement]::Escape($env:SCAN) -replace '__DOSSIER__', [Security.SecurityElement]::Escape($env:DOSSIER) | Set-Content -LiteralPath $env:TEMPXML -Encoding Unicode"
if errorlevel 1 goto echec

schtasks /create /tn "%NOM%" /xml "%TEMPXML%" /f
if errorlevel 1 goto echec
del "%TEMPXML%" >nul 2>nul

echo.
echo ================================================================
echo  Tache installee : "%NOM%"
echo.
echo  - Scan tous les jours a 07h25, PC reveille depuis la veille.
echo  - Si le PC etait eteint, le scan se lance au demarrage suivant.
echo  - Verifier / modifier : Planificateur de taches ^> Bibliotheque.
echo  - Desinstaller : schtasks /delete /tn "%NOM%" /f
echo.
echo  Pense a autoriser le reveil : Panneau de configuration ^> Options
echo  d'alimentation ^> Parametres du mode ^> Veille ^> "Minuteries de
echo  reveil" = Activer.
echo ================================================================
echo.
pause
exit /b 0

:echec
echo.
echo ECHEC de l'installation de la tache.
echo Astuce : relance ce fichier en tant qu'administrateur ^(clic droit^).
pause
exit /b 1
