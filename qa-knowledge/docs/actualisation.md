# Import initial et actualisation de la bibliothèque

Toutes les commandes se lancent depuis la racine du dépôt (`python3` sous Linux/macOS).

## Import initial (une fois, ≈ 3 minutes)

```bash
pip install -r qa-knowledge/requirements.txt         # pypdf (+ pytest pour les tests)
python qa-knowledge/qa.py catalogue                  # 26 syllabus officiels recensés
python qa-knowledge/qa.py telecharger --tous         # depuis istqb.org uniquement
python qa-knowledge/qa.py importer ~/Documents/syllabus-fr/   # traductions françaises (CFTL…)
python qa-knowledge/qa.py inventaire                 # contrôle : extraction, versions, absents
```

`telecharger --niveau avance` ou `telecharger CTFL CTAL-TM` pour une sélection.

Après un clone sur un autre poste : les PDF ne sont pas dans Git. Relancer
`telecharger --tous`, redéposer les PDF fournis à la main dans
`qa-knowledge/bibliotheque/sources/`, puis `actualiser` : le manifeste versionné retrouve
leurs métadonnées (et corrections manuelles) par empreinte SHA-256.

## Actualisation (périodique, par ex. trimestrielle)

```bash
python qa-knowledge/qa.py catalogue --verifier   # ⚠ NOUVEAU FICHIER = nouvelle version publiée
python qa-knowledge/qa.py telecharger CTFL       # récupère la nouvelle version
python qa-knowledge/qa.py actualiser             # incrémental : seuls les fichiers nouveaux/modifiés
python qa-knowledge/qa.py idee verifier-refs     # références des idées vers une version remplacée ?
```

- La nouvelle version devient « courante » ; l'ancienne reste consultable
  (`chercher --toutes-versions`) et apparaît « remplacé par … » dans `inventaire`.
- Un fichier de même nom mais de contenu différent n'écrase jamais l'ancien
  (suffixe de date).
- Si le catalogue change (nouvelle certification, page renommée), mettre à jour
  `qa-knowledge/catalogue/istqb.json` (URL `sdm_process_download`, `motifs` de détection,
  `verifie_le`). Seul le domaine `istqb.org` est accepté.

## Cas particuliers

| Situation | Action |
|---|---|
| Métadonnée mal détectée (code, version, langue…) | `corriger <doc_id> --version 4.0 --date 2025-05-01` — le champ devient « forcé » et survit aux réindexations |
| Document « illisible » (scan) | passer le PDF dans un OCR, réimporter le PDF texte |
| Document « partiel » | `inventaire` liste les pages vides ; vérifier le PDF |
| Aucune section détectée | la recherche fonctionne, mais sans § : citer la page uniquement |
| Document à retirer | `retirer <doc_id>` puis déplacer le fichier hors de `sources/` |
| Amélioration de l'extracteur | incrémenter `VERSION_EXTRACTEUR` (qak/extraction.py) : `actualiser` réextrait tout |
| Index corrompu ou supprimé | `actualiser` le reconstruit depuis `sources/` + manifeste |

## Mesurer la recherche après un changement

```bash
python qa-knowledge/qa.py evaluer --jeu controle   # questions jamais utilisées pour régler
python qa-knowledge/qa.py evaluer --jeu reglage
```

Ajouter au jeu de contrôle (`qa-knowledge/eval/requetes.json`, `"controle": true`) les
questions réelles qui ont mal fonctionné, AVANT de modifier le moteur.
