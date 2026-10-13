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
- **Panel de relecteurs** (`.claude/agents/`), à lancer en parallèle pour un audit large —
  chacun ne rend que des constats, aucun ne modifie de fichier : `chasseur-de-bugs`
  (défauts de correction), `avocat-de-cedric` (pièges d'usage, chiffres trompeurs),
  `gardien-des-donnees` (intégrité, fuites, dépôt public), `relecteur-de-tests` (ce que
  les tests prouvent vraiment), `architecte-du-code` (structure, code mort, dette),
  `ergonome-de-l-interface` (parcours, états vides, accessibilité, mobile),
  `exploitant-de-la-machine` (démarrage, tâche planifiée, sauvegardes, pannes silencieuses),
  `recruteur-lyonnais` (le seul qui juge la raison d'être : est-ce que ça aide vraiment à
  décrocher le poste ?). **Coûteux** (8 agents en parallèle, ~100k tokens chacun) : réservé à
  un audit explicitement demandé comme global/complet, pas le réflexe par défaut pour vérifier
  un point précis — voir « Discipline de consommation » ci-dessous.
- Les règles détaillées vivent dans `.claude/rules/` (backend, frontend, qualité) : helpers
  partagés à réutiliser, règle absolue du scan, heures locales, simulation démo obligatoire.

## Discipline de consommation (tokens)

Cédric est sur l'abonnement Claude Pro, **sans clé API Anthropic séparée** : les sessions
Claude Code (développement) ET les appels IA de l'application elle-même
(`services/claude_ai.py`, via la CLI locale `claude`) tirent sur le **même quota hebdomadaire**.
Un usage mal réparti épuise ce quota avant la fin de la semaine.

- **Panel de 8 relecteurs** : le lancer en entier coûte ~800k tokens par passe (vérifié :
  deux passes complètes lors de l'audit du 30/09–02/10). Ne le relancer en entier que sur
  demande explicite d'« audit complet » ou équivalent — espacé d'au moins plusieurs semaines.
  Pour vérifier un point précis, un seul agent ciblé (ou une investigation directe au
  Grep/Read/Bash, sans agent) suffit presque toujours.
- **Sessions longues** : proposer `/compact` entre deux sujets sans rapport (ex. fin d'un
  audit avant d'attaquer un sprint) plutôt que de laisser le contexte s'accumuler — chaque
  tour d'une conversation très longue renvoie tout l'historique au modèle.
- **IA de l'application** (`ai_max_offers_per_scan`, `ai_min_rule_score` dans `config.py`) :
  chaque offre affinée au scan quotidien renvoie le CV complet (~1 600 tokens) à Claude.
  Ne pas remonter ces réglages sans mesurer l'effet sur le quota partagé — ils ont été
  resserrés une fois (15→8 offres, seuil 45→55) précisément pour cette raison.
- **Automatisation (hooks/Routines)** : préférer un hook (déterministe, coût nul) à un agent
  pour toute vérification mécanique répétée. Préférer la demande explicite à une Routine
  planifiée récurrente pour les audits larges : une Routine qui se déclenche sans besoin
  réel est justement le genre de dépense qu'on cherche à éviter.

## Architecture

- `backend/app/connectors/` — un fichier par site d'emploi (France Travail, Adzuna, JSearch,
  WTTJ, APEC, HelloWork). **État réel au dernier relevé** : APEC (~181 offres) et HelloWork
  (~57) répondent sans clé ; WTTJ est en panne (403, clé Algolia publique invalide et plus
  exposée par le site) ; les trois autres attendent leurs clés dans `.env`. L'APEC tronque
  ses descriptions à 283 caractères et refuse la page de détail (401) — ce n'est pas un bug
  du connecteur, ne pas « réparer ». Contrat : `fetch(profile) -> ConnectorResult` ; un connecteur ne doit
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
