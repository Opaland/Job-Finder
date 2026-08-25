#!/bin/bash
# Hook PreToolUse (Bash) : bloque un `git commit` si les tests sont rouges, et un
# `git push` si tests OU builds sont rouges — la CI ne doit jamais découvrir un
# problème que ce hook pouvait attraper. Exit 2 = bloquant pour Claude Code.
#
# Ne se déclenche que sur un VRAI verbe git : une commande qui ne fait que
# mentionner « git push » (grep, echo, message de commit) passe sans vérification.
set -u

ENTREE="$(cat)"
RACINE="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# Extraction fiable de la commande (jq si présent, sinon Python — toujours
# disponible ici, c'est un projet Python). Jamais de sed glouton : il avalerait
# les autres champs du JSON.
if command -v jq >/dev/null 2>&1; then
  CMD="$(printf '%s' "$ENTREE" | jq -r '.tool_input.command // empty' 2>/dev/null)"
else
  for PY in python3 python py; do
    command -v "$PY" >/dev/null 2>&1 || continue
    CMD="$(printf '%s' "$ENTREE" | "$PY" -c \
      'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)"
    break
  done
fi
[ -z "${CMD:-}" ] && exit 0

# Le verbe git doit être en début de commande ou après un séparateur de shell.
verbe_git() {
  printf '%s' "$CMD" | grep -Eq "(^|[;&|]|&&|\|\|)[[:space:]]*git[[:space:]]+$1([[:space:]]|$)"
}

if verbe_git push; then
  MODE=complet
elif verbe_git commit; then
  MODE=rapide
else
  exit 0
fi

if [ "$MODE" = rapide ]; then
  bash "$RACINE/scripts/verif.sh" --rapide >/tmp/jf_verif.log 2>&1
else
  bash "$RACINE/scripts/verif.sh" >/tmp/jf_verif.log 2>&1
fi
CODE=$?

if [ $CODE -ne 0 ]; then
  {
    echo "Vérification Job Finder en échec ($MODE) — commit/push bloqué. Dernières lignes :"
    tail -15 /tmp/jf_verif.log
    echo "Corrige puis relance (bash scripts/verif.sh pour le détail complet)."
  } >&2
  exit 2
fi
exit 0
