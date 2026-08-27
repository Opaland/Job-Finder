# Job Finder — guide pour Claude Code

Application **locale et mono-utilisateur** de recherche d'emploi QA pour Cédric Moretti
(Test Manager / QA Lead, Lyon). Backend FastAPI + SQLite, frontend React/Vite, français partout
(UI, messages, commits, commentaires).

## Commandes

```bash
# Backend (depuis backend/) — Windows : remplacer par venv\Scripts\python
python -m pytest tests/ -q              # tests (obligatoire avant tout push)
python -m uvicorn app.main:app --port 8000
python -m app.cli scan                  # scan + digest sans interface
python -m app.cli sources               # diagnostic des sources (OK / SUSPECT / KO)
python -m app.cli sources --brut        # + fige les réponses dans data/diagnostic/

# Frontend (depuis frontend/)
npm run dev                             # dev avec proxy /api -> :8000
npm run build                           # build servi par FastAPI (frontend/dist)
VITE_DEMO=1 npx vite build --base=/Job-Finder/demo/ --outDir=dist-demo   # build démo Pages
```

`start.bat` (racine) fait l'installation complète sous Windows ; `scan.bat` est fait pour le
Planificateur de tâches ; `installer-tache-quotidienne.bat` enregistre la tâche quotidienne
(modèle `tache-quotidienne.xml`, réveil du PC en veille à 07h25).

`deploiement/installer-linux.sh` + `job-finder.service` : installation sans Docker sur Raspberry Pi / vieux PC (venv, build, service systemd). `Dockerfile` + `docker-compose.yml` : déploiement NAS Synology x86 (README §9). L'image reproduit
l'arborescence du dépôt (`/app/backend`, `/app/frontend/dist`, `/app/data` en volume) — `config.py`
déduit la racine depuis `backend/app/`, ne pas casser cette hiérarchie. Sans la CLI `claude` dans
l'image (défaut), les routes IA renvoient leur 503 français et le scan saute l'affinage.

## Garde-fous qualité

- `bash scripts/verif.sh` (Windows : `scripts\verif.bat`) = syntaxe + tests + build + build
  démo, la même chose que la CI. `--rapide` : syntaxe + tests seulement. Un hook
  (`.claude/hooks/verif-avant-git.sh`) la lance automatiquement et **bloque** commit (rapide)
  et push (complet) si elle est rouge.
- `backend/tests/test_sources_reelles.py` appelle **vraiment** apec.fr, hellowork.com et la
  CLI `claude` (~25 s). Aucun client HTTP bouchonné dans toute la suite : ce qui se vérifie
  sans réseau passe par les fonctions pures `ApecConnector.payloads()` /
  `HelloWorkConnector.recherches()` et par la page réelle figée dans `tests/fixtures/`.
  Une source injoignable fait **ignorer** le test (avec la raison) ; une source qui répond
  mal le fait **échouer**.
- `python scripts/revue_ia.py` — revue du diff par la session Claude locale (check-list du
  projet, sortie JSON en français). `node scripts/smoke_ui.mjs` — parcours navigateur des
  7 onglets (Playwright). `python scripts/mesures.py [n]` — chronomètre les opérations
  coûteuses sur n offres générées (alerte au-delà d'une seconde).
  `python scripts/mutation.py [modules]` — test de mutation : injecte des fautes
  plausibles et vérifie que la suite les attrape. Repères actuels : scoring 76 %,
  textutils 58 %, diagnostic 42 %. Un survivant = une ligne cassable sans que
  rien ne le signale.
- Skills projet : `/verif` (vérification + correction jusqu'au vert), `/revue` (agent
  `revue-jobfinder` + revue IA, applique les correctifs), `/smoke` (test navigateur réel).
- Les règles détaillées vivent dans `.claude/rules/` (backend, frontend, qualité) : helpers
  partagés à réutiliser, règle absolue du scan, heures locales, simulation démo obligatoire.

## Architecture

- `backend/app/connectors/` — un fichier par site d'emploi (France Travail, Adzuna, JSearch,
  WTTJ, APEC, HelloWork). Contrat : `fetch(profile) -> ConnectorResult` ; un connecteur ne doit
  JAMAIS lever au-delà de son résultat (les erreurs vont dans `result.errors`, formatées avec
  `resume_erreur()` — jamais `str(exc)` brut, illisible dans l'UI). `capture_reponses()`
  (connectors/base.py) fige les réponses réelles pour en faire des fixtures.
- `backend/app/services/diagnostic.py` — « que renvoie vraiment chaque source ? ». Détecte la
  source qui *réussit à vide* (champ manquant sur toutes les offres), invisible pendant un scan.
- `backend/app/services/scoring.py` — score 0-100 déterministe et expliqué (breakdown en
  français). Toute modification doit passer par `rescore_offer()` (services/scan.py), utilisé par
  le scan, le recalcul global et l'enrichissement.
- `backend/app/services/claude_ai.py` — IA via la CLI locale `claude` (session Claude Code de
  l'utilisateur, AUCUNE clé API Anthropic). Toujours prévoir le fallback CLI absente.
- `backend/app/services/scan.py` — orchestration. Règle absolue : **un scan ne ferme, ne
  supprime ni ne change jamais le statut d'une offre** ; disparition à la source =
  `still_online=False` seulement.
- `backend/seed/` — profil initial (CV, lettre type) chargé au premier démarrage.
- `frontend/src/demoApi.js` + `demoData.json` — mode démo GitHub Pages (`VITE_DEMO=1`), API
  simulée en mémoire ; toute nouvelle route API doit y être simulée ou renvoyer le message
  « disponible uniquement dans l'appli locale ».
- `data/` — SQLite + uploads, jamais versionné.

## Déploiement / CI

- `.github/workflows/ci.yml` — pytest + build frontend à chaque push.
- `.github/workflows/pages.yml` — construit accueil (`site/`) + démo et pousse sur la branche
  `gh-pages` (ne pas utiliser actions/deploy-pages : le token n'a pas les droits d'activation).
  Site : https://opaland.github.io/Job-Finder/

## Conventions

- Pas d'authentification ni de durcissement sécurité : app strictement locale (choix assumé de
  l'utilisateur) — ne pas exposer sur Internet.
- Statuts d'offre : voir `OFFER_STATUSES` (models.py) ; seul l'utilisateur change un statut.
- Les messages d'erreur API sont des phrases françaises actionnables (affichées telles quelles
  dans l'UI).
- Données personnelles (CV, lettre) : elles font partie du projet, dépôt public assumé par
  l'utilisateur — ne pas en ajouter de nouvelles sans son accord.
