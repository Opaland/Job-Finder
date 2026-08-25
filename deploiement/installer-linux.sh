#!/bin/bash
# Installation de Job Finder sur une machine Linux allumée en permanence
# (Raspberry Pi, vieux PC recyclé, mini-PC) — sans Docker.
#
#   bash deploiement/installer-linux.sh
#
# Idempotent : relançable après un « git pull » pour mettre à jour.
# Options : --sans-service (n'installe pas le service systemd, pour tester).
set -euo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
UTILISATEUR="${SUDO_USER:-$(id -un)}"
SANS_SERVICE=0
[ "${1:-}" = "--sans-service" ] && SANS_SERVICE=1

echo "== Installation de Job Finder =="
echo "   dossier     : $RACINE"
echo "   utilisateur : $UTILISATEUR"
echo

# --- 1. Prérequis -----------------------------------------------------------
manque=""
command -v python3 >/dev/null 2>&1 || manque="$manque python3"
python3 -c "import venv" >/dev/null 2>&1 || manque="$manque python3-venv"
command -v npm >/dev/null 2>&1 || manque="$manque nodejs npm"
if [ -n "$manque" ]; then
  echo "Il manque :$manque"
  echo "Installe-les puis relance :   sudo apt install -y$manque"
  exit 1
fi

version_py="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python $version_py détecté : il en faut 3.11 ou plus récent."
  echo "Sur Raspberry Pi OS / Debian 12 et suivants, python3 convient déjà."
  exit 1
fi
echo "-- Python $version_py et Node $(node --version) : OK"

# --- 2. Environnement Python ------------------------------------------------
if [ ! -x "$RACINE/backend/venv/bin/python" ]; then
  echo "-- Création de l'environnement Python"
  python3 -m venv "$RACINE/backend/venv"
fi
echo "-- Dépendances Python"
"$RACINE/backend/venv/bin/python" -m pip install -q --upgrade pip
"$RACINE/backend/venv/bin/python" -m pip install -q -r "$RACINE/backend/requirements.txt"

# --- 3. Interface ------------------------------------------------------------
echo "-- Construction de l'interface (quelques minutes sur un Raspberry Pi)"
cd "$RACINE/frontend"
npm install --no-audit --no-fund --loglevel=error
npm run build --silent
cd "$RACINE"

# --- 4. Configuration --------------------------------------------------------
if [ ! -f "$RACINE/.env" ]; then
  cp "$RACINE/.env.example" "$RACINE/.env"
  echo "-- .env créé depuis .env.example : pense à y mettre tes clés (README §3) et le SMTP (§4)"
fi

# --- 5. Service systemd ------------------------------------------------------
if [ "$SANS_SERVICE" = 1 ]; then
  echo
  echo "== Installation terminée (sans service) =="
  echo "Démarrage manuel :"
  echo "   cd $RACINE/backend && venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
  exit 0
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemd absent : lance l'application à la main (voir ci-dessus) ou utilise Docker."
  exit 0
fi
if [ "$(id -u)" -ne 0 ]; then
  echo
  echo "Le service doit être installé en root. Relance :"
  echo "   sudo bash deploiement/installer-linux.sh"
  exit 1
fi

echo "-- Installation du service systemd"
sed -e "s|__DOSSIER__|$RACINE|g" -e "s|__UTILISATEUR__|$UTILISATEUR|g" \
    "$RACINE/deploiement/job-finder.service" > /etc/systemd/system/job-finder.service
chown -R "$UTILISATEUR" "$RACINE/backend/venv" "$RACINE/frontend" 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now job-finder

echo
echo "================================================================"
echo " Job Finder tourne et redémarrera automatiquement avec la machine."
echo
echo "   Interface : http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000"
echo "   État      : systemctl status job-finder"
echo "   Journal   : journalctl -u job-finder -f"
echo "   Arrêt     : sudo systemctl stop job-finder"
echo
echo " Le scan quotidien (07:30) tourne dans le service : rien à planifier."
echo " Réseau LOCAL uniquement : aucune authentification, ne pas exposer"
echo " sur Internet (pas de redirection de port sur la box)."
echo "================================================================"
