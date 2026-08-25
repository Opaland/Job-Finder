# Job Finder — image pour NAS Synology (Container Manager) ou tout hôte Docker.
#
# Étape 1 : construction de l'interface React.
# Étape 2 : image finale Python qui sert l'API ET l'interface, et exécute le
#           scan quotidien (APScheduler tourne dans le processus uvicorn).
#
# Construction avec l'IA locale embarquée (facultatif, voir README §9) :
#   AVEC_IA=1 docker compose build      (même commande que le README §9)

FROM node:22-alpine AS interface
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim

# 0 (défaut) : score par règles uniquement, aucune dépendance IA.
# 1 : embarque la CLI Claude Code pour les lettres, fiches d'entretien et
#     l'affinage IA — nécessite une authentification unique (README §9).
ARG AVEC_IA=0

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Paris

WORKDIR /app

# Dépendances Python d'abord : cette couche est réutilisée tant que
# requirements.txt ne change pas (reconstructions rapides).
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

RUN if [ "$AVEC_IA" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends nodejs npm ca-certificates && \
      npm install -g @anthropic-ai/claude-code && \
      apt-get clean && rm -rf /var/lib/apt/lists/*; \
    fi

# Le code garde la même arborescence qu'en local : config.py déduit la racine
# du projet depuis backend/app/, et y cherche data/, .env et frontend/dist.
COPY backend/ backend/
COPY --from=interface /build/dist frontend/dist

# Base SQLite et CV importés : volume monté sur le NAS (jamais dans l'image).
VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
