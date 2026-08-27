# Règles de qualité (tout le dépôt)

- **Avant tout commit** : `bash scripts/verif.sh --rapide` doit être vert.
  **Avant tout push** : `bash scripts/verif.sh` complet (tests + build + build
  démo). Le hook `.claude/hooks/verif-avant-git.sh` le force, mais ne pas
  compter dessus : lancer la vérification soi-même.
- **Jamais la vraie base dans les tests** : un garde-fou `autouse` de
  `backend/tests/conftest.py` redirige `settings.db_path`, `database.engine` et
  `database.SessionLocal` vers une base vide. Ne pas le contourner — sans lui,
  un test qui retombe par erreur sur `data/jobfinder.db` passe au vert en local
  (le fichier existe) et casse en CI (`data/` y est vide).
- **Pas de client HTTP bouchonné** : un faux client prouve qu'on envoie ce qu'on
  croit envoyer, jamais que la source l'accepte — les trois défauts de la V1
  étaient précisément de ce genre. Ce qui se vérifie hors réseau passe par une
  fonction pure (`ApecConnector.payloads()`, `HelloWorkConnector.recherches()`)
  ou par une page réelle figée dans `tests/fixtures/` ; le reste passe par
  `tests/test_sources_reelles.py`, qui appelle les vrais sites. Un connecteur
  factice (`FausseSource`, `FakeConnector`) reste légitime : c'est l'ENTRÉE du
  code testé — diagnostic, orchestration du scan — pas un substitut de réseau.
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
