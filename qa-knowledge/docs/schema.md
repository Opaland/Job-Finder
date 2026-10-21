# Schéma des données

## Base de connaissances (`connaissances/`)

Une idée = une ligne de `connaissances.jsonl` (source versionnée) et une ligne de la table
`idees` de `base.db` (copie de travail reconstruite automatiquement si le JSONL change).

| Champ | Obligatoire | Contenu |
|---|---|---|
| `id` | auto | `QA-0001`, `QA-0002`… stable, jamais réattribué |
| `titre` | oui | titre court et explicite |
| `resume` | oui | description synthétique |
| `probleme` | oui | problème ou situation traités |
| `principe` | oui | principe, technique, mode opératoire |
| `theme_principal` | oui | code de la taxonomie (un thème obsolète est résolu vers son remplaçant) |
| `themes_secondaires` | | liste de codes |
| `domaine_application` | | contexte d'application |
| `prerequis` | | conditions nécessaires |
| `benefices` | | bénéfices attendus |
| `limites` | | limites et risques |
| `maturite` | défaut `hypothese` | `hypothese` · `documentee` · `pratiquee` · `eprouvee` |
| `statut` | défaut `a_explorer` | `a_explorer` · `a_evaluer` · `validee` · `experimentee` · `abandonnee` |
| `provenance` | | d'où vient l'idée (recherche du …, saisie utilisateur) |
| `references` | | liste, voir ci-dessous (références documentaires, URLs, pages et sections) |
| `relations` | | liste `{cible, type, note, cree_le}` ; types : `complementaire`, `contradictoire`, `variante`, `prerequis`, `remplace` |
| `retours` | | retours d'expérience `{date, contexte, resultat, enseignement}` |
| `cree_le`, `maj_le` | auto | horodatages ISO |

### Référence

| Champ | Usage |
|---|---|
| `type` | `istqb`, `norme`, `web`, `livre`, `article`, `interne`, `conversation` |
| `doc_id` | (istqb) identifiant ou code du document ; complété avec la version et le titre de l'index |
| `pages` | « 31 » ou « 31-33 » (pages physiques du PDF) — vérifiées |
| `section` | « 3.1.1 » |
| `extrait` | quelques mots copiés du passage lu — vérifiés sur les pages citées |
| `url`, `titre`, `consulte_le`, `note` | (web/article) URL obligatoire, date ajoutée automatiquement |

### Règles d'intégrité appliquées par l'outil

- création refusée si un doublon probable existe (similarité ≥ 0,6), sauf `--forcer --motif` ;
- `validee` / `experimentee` impossibles à la création ; `validee`, `abandonnee`,
  `experimentee` exigent un motif ; `experimentee` exige un retour d'expérience ;
- `idee modifier` ajoute aux listes (références, thèmes) au lieu de les remplacer ;
- référence ISTQB : document connu, page existante, extrait présent, version remplacée signalée ;
- chaque écriture ajoute une ligne à `journal.jsonl` (horodatage, action, cible, détails avant/après, motif).

### Tables SQLite (`base.db`)

`idees` (champs scalaires) · `idee_themes(idee_id, theme, principal)` · `refs` ·
`relations(source, cible, type, note, cree_le)` · `retours` · `idees_fts` (FTS5 sur titre +
contenu) · `meta(cle, valeur)` (empreinte du JSONL synchronisé).

## Bibliothèque (`bibliotheque/`)

### `manifeste.json` (versionné)

Clé = SHA-256 du fichier. Valeur : `doc_id`, `fichier`, `titre`, `code`, `type`
(`syllabus`, `bok`, `glossaire`, `notes`, `examen`, `document`), `niveau` (`fondation`,
`avance`, `expert`, `specialiste`), `domaine` (code de thème), `version`, `langue`,
`date_publication`, `source_officielle`, `page_officielle`, `origine`, `importe_le`,
`champs_forces` (corrigés à la main, jamais écrasés par la détection).

### `index.db` (reconstructible)

| Table | Contenu |
|---|---|
| `documents` | métadonnées + `statut_version` (`courant`, `remplace`, `absent`), `remplace_par`, `nb_pages`, `pages_vides`, `statut_extraction` (`ok`, `partiel`, `illisible`, `echec`, `absent`), `message_extraction`, `plan_source`, `version_extracteur` |
| `sections` | plan : `numero`, `titre`, `page` |
| `passages` | ≈ 1 400 caractères, jamais à cheval sur deux pages : `page`, `page_imprimee`, `section_num`, `section_titre`, `texte`, `sommaire` (table des matières / index) |
| `passages_fts` | FTS5 (`porter unicode61 remove_diacritics 2`) sur `texte` et `section_titre` |

## Référentiels (`referentiel/`)

- `taxonomie.json` : `{code, parent, libelle, mots_cles[], statut, remplace_par?, cree_le}`.
  Les mots-clés FR/EN servent au filtre `--theme` et au calcul de `couverture`.
- `thesaurus.json` : `{id, termes[]}` ; un terme n'appartient qu'à un concept. Les concepts
  `lex-*` sont un petit lexique FR→EN de mots courants (poids 1 dans le classement).

## Évolution du schéma

Ajouter une colonne = l'ajouter à `SCHEMA` (connaissances.py) et à `_inserer` ; le JSONL
étant la source, une base ancienne se reconstruit d'elle-même. Ne changer le schéma que
pour un besoin réel constaté.
