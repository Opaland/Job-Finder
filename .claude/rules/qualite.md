# Règles de qualité (tout le dépôt)

- **Avant tout commit** : `bash scripts/verif.sh --rapide` doit être vert.
  **Avant tout push** : `bash scripts/verif.sh` complet (tests + build + build
  démo). Le hook `.claude/hooks/verif-avant-git.sh` le force, mais ne pas
  compter dessus : lancer la vérification soi-même.
- **Réutiliser avant d'écrire** : chercher un helper existant (grep dans
  `services/textutils.py`, `services/scan.py`, `connectors/base.py`,
  `frontend/src/api.js`) avant d'écrire une fonction. Un copier-coller avec
  petite variation = extraire un helper partagé.
- **Revue** : pour un changement de plus de ~50 lignes, lancer `/revue`
  (ou `python scripts/revue_ia.py`) avant de pousser.
- **Comportement intouchable sans demande explicite de l'utilisateur** :
  fermeture/statut des offres, seuils métier (GEM_SCORE 85, relance 7 j,
  hors-ligne 15 j), textes des prompts IA.
- **Données personnelles** (CV, lettre) : ne rien ajouter de nouveau sans
  l'accord de l'utilisateur (dépôt public assumé).
- **Commits** : messages en français, descriptifs ; jamais de push direct si la
  vérification est rouge — pas d'exception « petite modif ».
