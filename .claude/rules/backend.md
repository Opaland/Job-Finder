---
paths:
  - "backend/**"
---

# Règles backend

- **Dédoublonnage** : toute logique « même offre ? » passe par `find_twin()`
  (`services/scan.py`) — ne jamais la réécrire, même partiellement.
- **Scan** : un scan ne ferme, ne supprime ni ne change JAMAIS le statut d'une
  offre. Une disparition à la source = `still_online=False`, rien d'autre.
- **Heures** : uniquement `local_now()` (`models.py`, naïf, Europe/Paris).
  Jamais `datetime.utcnow()`, jamais de mélange aware/naïf.
- **Scoring** : toute modification de score passe par `rescore_offer()` ;
  le pipeline scan→digest→email passe par `run_full_scan()`.
- **Statuts** : utiliser `OFFER_STATUSES`, `STATUS_LABELS` et les groupes
  `STATUTS_NON_TRAITES` / `STATUTS_EN_ATTENTE` / `STATUTS_CLOS` (`models.py`) —
  jamais de listes littérales de statuts.
- **Helpers existants — chercher avant d'écrire** : `parse_iso_dt`,
  `contains_word`, `escape_like`, `fingerprint`, `titles_similar`
  (`services/textutils.py`) ; `parse_published` (`connectors/base.py`) ;
  `offer_to_scoring_dict`, `profile_to_dict` (`services/scan.py`).
- **Connecteurs** : `fetch()` ne lève jamais — les erreurs vont dans
  `result.errors`, en phrases françaises actionnables.
- **SQL** : jamais de requête dans une boucle (précharger un dict) ; ne pas
  charger les colonnes lourdes (description, lettres, fiches) quand la réponse
  ne les renvoie pas (`load_only` ou requête de colonnes).
- **Messages d'erreur API** : phrases françaises actionnables — elles sont
  affichées telles quelles dans l'interface.
