@echo off
REM ============================================================
REM  Job Finder — scan + digest sans interface
REM  A planifier via le Planificateur de taches Windows si tu ne
REM  laisses pas l'application ouverte en permanence (README §5).
REM ============================================================
cd /d "%~dp0backend"
venv\Scripts\python -m app.cli scan
