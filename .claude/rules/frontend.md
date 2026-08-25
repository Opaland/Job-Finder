---
paths:
  - "frontend/**"
---

# Règles frontend

- **Source unique `api.js`** : `STATUS_LABELS`, `STATUS_COLORS`,
  `SOURCE_LABELS`, `GEM_SCORE`, `scoreColor`, `formatDate`, `actionDue`,
  `downloadFile`. Ne jamais recopier ces tables ou cette logique dans un
  composant ou dans `demoApi.js` — importer. Les colonnes du Kanban se
  dérivent : `Object.keys(STATUS_LABELS)`.
- **Téléchargements** : toujours `downloadFile(path)` (avec garde `DEMO` +
  toast côté appelant) — pas de rituel `createElement('a')` à la main.
- **Actions longues** (IA, enrichissement) : un seul état `busy` par vue et un
  helper commun type `runAction` — pas un `useState` booléen par bouton.
- **Chargement** : un seul `useEffect` par vue pour le chargement initial et le
  rafraîchissement de fin de scan — pas d'effets redondants qui doublent les
  requêtes au montage.
- **Mode démo** : toute nouvelle route API doit être simulée dans `demoApi.js`
  ou y lever la constante `LOCAL_ONLY` (« Disponible uniquement dans
  l'application locale… »). Le test `backend/tests/test_demo_couverture.py`
  échoue tant qu'une route n'est pas gérée ; le build démo est vérifié par
  `scripts/verif.sh` et par la CI.
- **UI en français, tutoiement**, dates via `formatDate`.
