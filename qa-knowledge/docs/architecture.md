# Architecture et choix techniques

## Vue d'ensemble

```
Conversation Claude Code
        │  (le skill .claude/skills/qa-knowledge/SKILL.md décrit QUAND et COMMENT)
        ▼
python qa-knowledge/qa.py <commande>          ← une seule CLI, sortie texte FR (ou --json)
        │
        ├── Bibliothèque ISTQB ─────────────────────────────────────────────
        │     catalogue/istqb.json        catalogue officiel (26 syllabus, URL istqb.org)   [versionné]
        │     bibliotheque/sources/       PDF / .txt / .md                                  [non versionné]
        │     bibliotheque/manifeste.json métadonnées par empreinte SHA-256                 [versionné]
        │     bibliotheque/index.db       SQLite : documents, sections, passages + FTS5     [reconstructible]
        │
        ├── Base de connaissances ───────────────────────────────────────────
        │     connaissances/connaissances.jsonl  une idée par ligne (miroir lisible)        [versionné]
        │     connaissances/journal.jsonl        journal append-only des modifications      [versionné]
        │     connaissances/base.db              SQLite + FTS5, reconstruit depuis le JSONL [reconstructible]
        │
        └── Référentiels ────────────────────────────────────────────────────
              referentiel/taxonomie.json   39 thèmes hiérarchiques + mots-clés FR/EN       [versionné]
              referentiel/thesaurus.json   ~130 concepts, ~1000 termes FR↔EN              [versionné]
```

Modules (`qak/`) : `extraction` (PDF → pages, plan, passages) · `bibliotheque` (import,
métadonnées, doublons, versions, index) · `catalogue` (istqb.org) · `recherche` (FTS5 +
thésaurus + reclassement) · `connaissances` (idées, déduplication, références vérifiées) ·
`taxonomie` · `journal` · `evaluation` · `cli`.

Aucun serveur, aucune interface graphique, aucune clé d'API. Dépendance unique : `pypdf`.

## Choix et compromis

| Sujet | Choix | Pourquoi / compromis |
|---|---|---|
| Point d'entrée | **Un skill** + une CLI | Le skill porte la méthode (ordre de recherche, citations, capitalisation) ; la CLI porte les garanties (vérifications, déduplication, journal). Pas de sous-agent : rien ne le justifie aujourd'hui, et il perdrait le contexte de la conversation. |
| Stockage | **SQLite** (stdlib) | Local, sans service, transactionnel, FTS5 intégré. |
| Recherche | **FTS5 BM25 + thésaurus FR/EN + reclassement par couverture** | Les syllabus sont un vocabulaire contrôlé : la recherche lexicale suffit si l'on traduit les concepts (FR → EN). Voir « Mesures ». |
| Recherche sémantique | **Non ajoutée** | Bénéfice non démontré (rappel@5 = 88 % sur des questions jamais vues), coût réel (modèle d'embeddings ~100-400 Mo, dépendances lourdes, index à recalculer). Critère pour la reconsidérer : questions réalistes qui échouent malgré une reformulation avec le terme ISTQB. Le jeu `eval/` sert d'arbitre. |
| Versionnement de la base | **JSONL miroir** + SQLite de travail | Un `.db` binaire se fusionne mal dans Git. Le JSONL (une idée par ligne, trié) donne des diffs lisibles ; après un `git pull`, l'empreinte du JSONL change et la base est reconstruite automatiquement. |
| PDF sources | **Non versionnés** | Les PDF ISTQB se retéléchargent depuis la source officielle ; la notice ISTQB autorise la copie avec citation, mais ce n'est pas nécessaire. Le manifeste versionné garde les métadonnées et retrouve chaque fichier par empreinte. |
| Pages | **Page physique du PDF** + page imprimée si différente | La page physique est non ambiguë (c'est celle qu'ouvre un lecteur PDF) ; la page imprimée (« Page 12 de 80 ») est conservée quand elle diffère. Un passage ne franchit jamais une page. |
| Sections | Signets PDF si numérotés, sinon **plus longue chaîne de titres à numérotation cohérente** | Les syllabus FR n'ont souvent pas de signets. La programmation dynamique écarte les listes numérotées du préambule ; les titres répétés par les objectifs d'apprentissage sont écartés au profit du vrai titre. |
| Taxonomie | Fichier JSON, codes stables, statut `obsolete` + `remplace_par` | Un thème n'est jamais supprimé ; les idées gardent leur classement historique et les requêtes suivent le remplaçant. |
| Déduplication | Signature = concepts du thésaurus + racines | « Partitions d'équivalence » et « Equivalence partitioning » ont la même signature ; seuil 0,6 = doublon probable (bloquant), 0,35 = proche (signalé). |
| Références ISTQB | **Vérifiées à l'écriture** | Document présent, page existante, extrait réellement présent (≥ 70 % des mots) : une citation inventée est refusée par l'outil, pas seulement déconseillée par le skill. |

## Mesures de la recherche (bibliothèque réelle : 42 fichiers, 26 codes EN + 14 FR)

`python qa-knowledge/qa.py evaluer --jeu reglage|controle` — rappel@5 = la réponse attendue
(code + section) figure dans les 5 premiers résultats.

| Version du moteur | Jeu de réglage (36 q.) | Jeu de contrôle (16 q., jamais utilisées pour régler) |
|---|---|---|
| FTS5 + thésaurus, « ET strict puis OU » | 75 % | — |
| + reclassement par couverture, concepts scindés, lexique FR→EN | 94 % | — |
| + rétrogradation annexes / notes de version | 100 % (MRR 0,82) | **88 %** (MRR 0,76) |

Le 100 % du jeu de réglage est optimiste par construction ; le chiffre honnête est celui
du jeu de contrôle. Les deux échecs du contrôle sont des requêtes très courtes faites de
mots omniprésents (« principes du test », « contenu d'un plan de test ») : la même
question avec le terme ISTQB anglais (« testing principles », « purpose and content of a
test plan ») trouve la bonne section en 1re ou 2e position. Le skill demande donc
d'ajouter le terme anglais quand il est connu.

Temps : une recherche ≈ 50 ms ; import initial ≈ 3 s par syllabus (≈ 2-3 min pour 42) ;
actualisation sans changement < 1 s.

## Critères d'acceptation (vérifiables)

| # | Critère | Vérification |
|---|---|---|
| 1 | Import PDF/txt/md, texte extrait, sources conservées | `tests/test_extraction.py`, `test_bibliotheque.py` ; `inventaire` |
| 2 | Métadonnées (titre, code, niveau, domaine, version, langue, date, source, chemin) | `inventaire --json`, `manifeste.json` ; détection testée sur les titres réels FR |
| 3 | Pages et sections préservées, jamais de passage à cheval sur deux pages | `test_passages_ne_franchissent_pas_les_pages…` |
| 4 | Doublons exacts et changements de version détectés | `test_doublon_exact…`, `test_nouvelle_version_remplace…` ; doublon ATLaS réel écarté |
| 5 | Extractions défaillantes signalées (scan, encodage, corrompu, absent) | `test_pdf_sans_texte…`, `test_fichier_corrompu…`, `inventaire` (« À surveiller ») |
| 6 | Indexation incrémentale, réutilisable, reconstructible | `test_actualisation_incrementale…`, `test_index_reconstructible…` |
| 7 | Recherche par mots-clés, concepts/synonymes FR↔EN, thème, section, versions applicables | `tests/test_recherche.py` ; `evaluer` |
| 8 | Retour aux passages d'origine (lecture page / section / contexte) | `lire`, `page`, `section` ; `test_lire_passage…` |
| 9 | Base de connaissances avec tous les champs demandés, identifiant stable | `docs/schema.md`, `test_connaissances.py` |
| 10 | Déduplication avant insertion, mise à jour plutôt que création | `test_doublon_reformule…`, `test_doublon_detecte_entre_francais_et_anglais` |
| 11 | Taxonomie hiérarchique, multi-thèmes, sans redondance, historique conservé | `tests/test_taxonomie.py` |
| 12 | Modifications explicites et traçables | `journal`, `test_regles_de_statut` |
| 13 | Aucune référence ou page inventée | `test_references_istqb_verifiees…` |
| 14 | Recherche Web uniquement justifiée, jamais présentée comme ISTQB | règles du skill (non automatisable : relu en revue) |
| 15 | Fonctionne hors ligne une fois les documents installés | aucune dépendance réseau hors `catalogue`/`telecharger` |
| 16 | Disponibilité des sources officielles vérifiée | `test_sources_reelles.py` (vrai réseau), `catalogue --verifier` |

## Limites connues

- Les traductions françaises (CFTL) ne sont pas téléchargeables automatiquement : elles
  sont fournies par l'utilisateur. 12 codes n'existent localement qu'en anglais.
- CTEL-TM et CTEL-ITP (Expert, 2011) regroupent plusieurs modules dans un PDF : un seul code.
- Pas d'OCR : un PDF scanné est signalé « illisible », pas extrait.
- Le glossaire ISTQB (glossary.istqb.org) est une application Web sans export : non intégré ;
  les définitions se trouvent via les sections « Keywords » des syllabus.
- Les tableaux PDF sont extraits ligne à ligne (lisibles mais sans structure de colonnes).
- La recherche est lexicale : une notion absente du thésaurus et formulée autrement que
  dans le syllabus peut être manquée → ajouter le terme au thésaurus (une ligne JSON).
