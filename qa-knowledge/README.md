# QA Knowledge Agent

Assistant de connaissances QA **utilisé uniquement en conversation dans Claude Code**.
Il cherche dans une bibliothèque locale de syllabus ISTQB (FR et EN, pages et sections
citées), dans une base d'idées QA capitalisées au fil du temps, et sur le Web seulement
quand c'est justifié. Il ne « s'entraîne » pas : il enrichit une mémoire documentaire
persistante, vérifiable et versionnée avec Git.

Pas de serveur, pas d'interface graphique, pas de clé d'API. Python ≥ 3.10 + `pypdf`.

## Installation

```bash
pip install -r qa-knowledge/requirements.txt
python qa-knowledge/qa.py telecharger --tous                 # 26 syllabus officiels (istqb.org), ≈ 2 min
python qa-knowledge/qa.py importer chemin/vers/syllabus-fr/  # vos traductions françaises (PDF)
python qa-knowledge/qa.py inventaire
```

(`python3` sous Linux/macOS.) Ensuite tout se fait en conversation : le skill
`.claude/skills/qa-knowledge/` est chargé automatiquement par Claude Code dès qu'une
question porte sur le test logiciel ou la qualité (ou via `/qa-knowledge`).

## Utilisation

Exemples de demandes, en langage naturel :

- « Quelles techniques ISTQB permettent d'améliorer la couverture des tests ? »
- « Recherche des idées pour intégrer le risk-based testing dans une équipe produit agile. »
- « Comment réduire le coût de maintenance de nos tests Playwright ? »
- « Compare les techniques de priorisation de l'ISTQB avec des retours d'expérience récents. »
- « Retrouve les idées déjà capitalisées sur le shift-left. » · « Classe cette nouvelle idée. »
- « Identifie les thèmes sur lesquels notre base est encore pauvre. »

Voir [docs/exemples-conversations.md](docs/exemples-conversations.md) (sorties réelles).

La CLI reste utilisable directement (`python qa-knowledge/qa.py --help`) :

| Besoin | Commande |
|---|---|
| Chercher dans les syllabus | `chercher <notions> [--doc CTAL-TM] [--theme rbt] [--section 1.3] [--langue fr]` |
| Lire avant de citer | `lire <passage> [--contexte 1]` · `section <doc> <num>` · `page <doc> <p[-q]>` · `plan <doc>` |
| Base d'idées | `idee chercher …` · `idee lister [--theme] [--statut]` · `idee voir QA-0001` |
| Capitaliser | `idee modele` · `idee doublons --fichier f.json` · `idee ajouter --fichier f.json` |
| Faire évoluer | `idee modifier` · `idee statut … --motif` · `idee retour` · `idee lier` · `journal` |
| Taxonomie | `themes` · `theme proposer "<texte>"` · `theme ajouter …` · `theme obsolete …` · `couverture` |
| Bibliothèque | `catalogue [--verifier]` · `telecharger` · `importer` · `actualiser` · `inventaire` · `corriger` · `retirer` |
| Qualité de la recherche | `evaluer --jeu controle` |

## Ce qui est versionné

| Versionné (Git) | Non versionné (reconstructible) |
|---|---|
| `connaissances/connaissances.jsonl` — les idées | `connaissances/base.db` — reconstruite depuis le JSONL |
| `connaissances/journal.jsonl` — l'historique | `bibliotheque/index.db` — reconstruit par `actualiser` |
| `bibliotheque/manifeste.json` — métadonnées des documents | `bibliotheque/sources/*.pdf` — retéléchargés / redéposés |
| `referentiel/` (taxonomie, thésaurus), `catalogue/`, `eval/` | |

Après une session de capitalisation : commiter `qa-knowledge/connaissances/` (et
`referentiel/taxonomie.json` si un thème a été ajouté). Sur un autre poste, un `git pull`
suffit : la base locale se resynchronise toute seule.

## État de la bibliothèque (relevé du 2026-10-21)

- **Catalogue officiel** : 26 syllabus recensés sur istqb.org (Foundation, Advanced,
  Expert, Specialist, dont CT-AI v2.0, CT-GenAI v1.1, CT-QDO, CT-STE) — tous téléchargés,
  extraits et indexés en anglais (`inventaire`).
- **Français** : 14 codes fournis par l'utilisateur (CTAL-TA v4.0 et 2019, CTAL-TM v3.0,
  CTAL-TAE v2.0, CTAL-TTA v4.0, CTAL-ATT, CT-ATLaS + Body of Knowledge, CTEL-ITP, CTFL-AT,
  CT-AcT, CT-MAT, CT-MBT, CT-PT, CT-TAS, CT-UT). Le CTAL-TA 2019 est marqué « remplacé »
  par la v4.0 ; un doublon exact (ATLaS) a été écarté.
- **Absents en français** : notamment CTFL v4.0, CT-AI, CT-GenAI, CT-QDO, CT-SEC/STE, CTEL-TM
  (disponibles en anglais). Les déposer dans `bibliotheque/sources/` puis `actualiser`.
- **Non intégré** : le glossaire ISTQB (application Web sans export officiel).

## Fiabilité : ce que l'outil garantit

- Une référence ISTQB enregistrée pointe vers un document présent, une page qui existe
  et un extrait réellement présent sur ces pages — sinon l'enregistrement est refusé.
- Les versions remplacées sont exclues des recherches par défaut et signalées.
- Aucune idée n'est créée en double sans motif explicite ; aucun statut « validée » sans motif.
- Chaque modification est journalisée. Un seul domaine de téléchargement accepté : istqb.org.

Le skill impose le reste (règles non automatisables) : lire avant de citer, distinguer
ISTQB / Web / base / interprétation, justifier toute recherche Web, ne capitaliser
qu'avec l'accord de l'utilisateur.

## Limites

- Recherche **lexicale** (FTS5 + thésaurus FR/EN) : rappel@5 = 88 % sur des questions de
  contrôle jamais vues. Les requêtes très courtes et génériques réussissent mieux avec le
  terme ISTQB anglais. Pas de recherche sémantique : bénéfice non démontré
  ([docs/architecture.md](docs/architecture.md)).
- Pas d'OCR (PDF scanné = « illisible »). Certains PDF FR produisent des espaces parasites
  dans les mots (« sélecti on ») : la recherche reste correcte dans l'ensemble mais une
  expression exacte peut être manquée sur ces pages.
- La bibliothèque locale n'est pas l'ensemble des connaissances : l'assistant le dit
  quand elle ne couvre pas une question.

## Maintenance

- Actualisation des documents : [docs/actualisation.md](docs/actualisation.md).
- Schéma des données : [docs/schema.md](docs/schema.md).
- Architecture, choix, mesures, critères d'acceptation : [docs/architecture.md](docs/architecture.md).
- Tests : `python -m pytest qa-knowledge/tests -q -rs` (≈ 15 s ; `test_sources_reelles.py`
  appelle vraiment istqb.org et s'ignore, avec la raison, si le site est injoignable).
- Enrichir le thésaurus (`referentiel/thesaurus.json`) quand une notion n'est pas trouvée ;
  ajouter la question au jeu de contrôle `eval/requetes.json` avant de toucher au moteur.

## Droits

Les syllabus sont © ISTQB® ; leur notice autorise la copie, en tout ou partie, si la
source est citée. Ce dépôt ne versionne que leurs métadonnées ; les PDF sont récupérés
depuis istqb.org ou fournis par l'utilisateur.
