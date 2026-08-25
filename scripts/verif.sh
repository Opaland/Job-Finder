#!/bin/bash
# Vérification complète du projet — la même que la CI, en local.
#   scripts/verif.sh            tests backend + builds frontend (normal + démo)
#   scripts/verif.sh --rapide   syntaxe + tests backend uniquement (pré-commit)
# Sort en erreur (≠ 0) dès qu'une étape échoue. Équivalent Windows : scripts\verif.bat
set -u

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
RAPIDE=0
[ "${1:-}" = "--rapide" ] && RAPIDE=1

# Python : venv du projet en priorité (Windows puis Linux/macOS), sinon le poste.
if [ -x "$RACINE/backend/venv/Scripts/python.exe" ]; then
  PY="$RACINE/backend/venv/Scripts/python.exe"
elif [ -x "$RACINE/backend/venv/bin/python" ]; then
  PY="$RACINE/backend/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

echo "== Vérification Job Finder $( [ $RAPIDE = 1 ] && echo '(rapide)' ) =="

echo "-- Syntaxe backend (compileall)"
"$PY" -m compileall -q "$RACINE/backend/app" || { echo "ÉCHEC : erreur de syntaxe dans backend/app." >&2; exit 1; }

echo "-- Tests backend (pytest)"
(cd "$RACINE/backend" && "$PY" -m pytest tests/ -q) || { echo "ÉCHEC : des tests backend sont rouges." >&2; exit 1; }

if [ $RAPIDE = 1 ]; then
  echo "== OK (rapide) : syntaxe + tests verts =="
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  # Sortir en 0 ici laisserait passer un push avec un frontend cassé : on échoue,
  # sauf demande explicite (JF_SANS_FRONT=1) pour un poste sans Node.
  if [ "${JF_SANS_FRONT:-}" = "1" ]; then
    echo "npm introuvable — builds frontend ignorés (JF_SANS_FRONT=1)." >&2
    echo "== OK (partiel, sans frontend) =="
    exit 0
  fi
  echo "ÉCHEC : npm introuvable — impossible de vérifier les builds frontend." >&2
  echo "Installe Node.js LTS, ou lance JF_SANS_FRONT=1 scripts/verif.sh en connaissance de cause." >&2
  exit 1
fi

echo "-- Build frontend"
(cd "$RACINE/frontend" && npm run build --silent) || { echo "ÉCHEC : le build frontend casse." >&2; exit 1; }

echo "-- Build démo (GitHub Pages)"
(cd "$RACINE/frontend" && VITE_DEMO=1 npx vite build --base=/Job-Finder/demo/ --outDir=dist-demo --logLevel=error) \
  || { echo "ÉCHEC : le build démo casse (demoApi.js doit simuler toute nouvelle route)." >&2; exit 1; }

echo "== OK : tests + builds verts, prêt à pousser =="
