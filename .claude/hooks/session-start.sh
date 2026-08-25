#!/bin/bash
# Hook SessionStart (Claude Code sur le web) : installe les dépendances pour que
# pytest et les builds fonctionnent dès le début de session. Idempotent.
set -euo pipefail

# Uniquement dans les sessions web/conteneur — jamais sur le poste local.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

RACINE="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

echo "Job Finder : préparation de l'environnement de session…"

if ! python3 -c "import fastapi, sqlalchemy, pytest" >/dev/null 2>&1; then
  pip install -q --disable-pip-version-check -r "$RACINE/backend/requirements.txt"
fi

if [ ! -d "$RACINE/frontend/node_modules" ]; then
  (cd "$RACINE/frontend" && npm install --no-audit --no-fund --loglevel=error)
fi

echo "Environnement prêt : pytest et les builds frontend sont utilisables."
