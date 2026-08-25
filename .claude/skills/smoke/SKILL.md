---
name: smoke
description: Smoke test de l'interface Job Finder dans un vrai navigateur — build, démarrage du backend, parcours des 7 onglets via Playwright (scripts/smoke_ui.mjs), rapport des erreurs JS.
---

Vérifie que l'application réelle fonctionne de bout en bout.

1. Assure-toi que `frontend/dist` est à jour (`npm run build` dans frontend/).
2. Démarre le backend : `python -m uvicorn app.main:app --port 8000` depuis
   backend/ (en arrière-plan), attends `/api/health`.
3. Lance `node scripts/smoke_ui.mjs`. Si Playwright n'est pas installé,
   installe-le d'abord (`npm i -D playwright` dans le dossier adapté ; dans le
   conteneur web, Chromium est déjà sous /opt/pw-browsers — passe
   `PW_CHROMIUM=/opt/pw-browsers/chromium`).
4. Arrête proprement le serveur (`pkill -f "[u]vicorn app.main"` dans une
   commande séparée — jamais dans la même commande que le motif).
5. Rapporte en français : onglets OK, erreurs JS éventuelles avec leur cause
   probable. Si un onglet casse, corrige puis relance le smoke test.
