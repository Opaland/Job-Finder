# Exemples de conversations

Les commandes et extraits ci-dessous proviennent d'exécutions réelles sur la bibliothèque
du dépôt (42 fichiers, octobre 2026). Les numéros de passage (`#13411`) changent à chaque
réindexation : ils servent à lire, jamais à citer. On cite document, version, section, page.

---

## 1. Recherche simple (cas A) — pas de Web

> **Utilisateur** : Comment l'ISTQB propose-t-il d'intégrer le risk-based testing dans une équipe agile ?

L'assistant (skill `qa-knowledge`) :

```text
$ python qa-knowledge/qa.py idee chercher risk-based agile
Aucune idée capitalisée ne correspond.

$ python qa-knowledge/qa.py chercher '"risk-based testing" agile équipe' -n 4
Notions : risque, agile, lex-equipe
[1] CTAL-TA-4.0-en · … v4.0 (2025-05-02)  p. 25 · §2.1 Risk Analysis · passage #8488
[2] CTAL-TA-4.0-fr · … v4.0 (2025-05-01)  p. 28 · §2.2 Contrôle des risques · passage #8680
[3] CTFL-AT-2014-fr · … v2014 (2014-05-31) p. 34 · §3.2.1 Evaluer les risques de qualité sur les Projets Agile · passage #13411
…
$ python qa-knowledge/qa.py lire 13411 --contexte 1
$ python qa-knowledge/qa.py lire 8488
```

> **Assistant** : Rien n'est encore capitalisé sur ce sujet ; deux syllabus le traitent.
>
> - **Évaluer les risques qualité à chaque itération** : dans les projets agiles, l'analyse
>   des risques qualité intervient lors de la planification de release puis de chaque
>   itération ; le niveau de risque combine probabilité et impact
>   [ISTQB CTFL-AT 2014 FR, §3.2.1, p. 34].
> - **Suivi continu** : les risques et leurs niveaux évoluent ; en cycle itératif, le suivi
>   des risques se fait à une fréquence fixée par l'équipe, vraisemblablement à chaque
>   itération [ISTQB CTAL-TA v4.0 FR, §2.2, p. 28 ; EN §2.1, p. 25].
>
> Interprétation : intégrer un court atelier risques au refinement plutôt qu'un
> document de stratégie séparé. Limite : le syllabus CTFL-AT date de 2014.
> Pas de recherche Web : les syllabus couvrent la question.
>
> À capitaliser ? « Atelier risques par itération » (thème `rbt`, secondaire `agile`).

---

## 2. Recherche approfondie avec Web justifié (cas B)

> **Utilisateur** : Comment réduire le coût de maintenance de nos tests Playwright ?

```text
$ python qa-knowledge/qa.py chercher maintenabilité solution automatisation --doc CTAL-TAE
[1] CTAL-TAE-2.0-en … p. 32 · §4.3 Test Automation Solution Maintainability
$ python qa-knowledge/qa.py section CTAL-TAE-2.0-fr 4.3
$ python qa-knowledge/qa.py section CTAL-TAE-2.0-fr 3.1.5      # principes et canevas de conception
$ python qa-knowledge/qa.py chercher playwright
⚠ Aucun passage trouvé dans la bibliothèque locale : reformuler (termes anglais des syllabus),
  élargir les filtres, ou justifier une recherche Web.
```

> **Assistant** : Les syllabus donnent les principes (maintenabilité de la solution
> d'automatisation, conception en couches, canevas de conception) [ISTQB CTAL-TAE v2.0 FR,
> §4.3 et §3.1.5 — pages lues]. Ils ne parlent pas de Playwright : **recherche Web
> nécessaire** pour les pratiques propres à l'outil (sélecteurs, auto-wait, fixtures).
>
> *(WebSearch / WebFetch sur la documentation officielle Playwright)*
>
> **Diagnostic** · **Options** (1. sélecteurs orientés utilisateur — Web : doc Playwright ;
> 2. Page Object / couches — ISTQB CTAL-TAE §3.1.5 ; 3. quarantaine et suivi des tests
> instables — Web ; …) · **Recommandation** · **Mise en œuvre** · **Indicateurs** (taux de
> tests instables, temps de correction après changement d'UI) · **Sources et limites**
> (ISTQB = principes génériques ; Web = documentation d'outil, consultée le …).
>
> À capitaliser ? 2 idées : « Sélecteurs orientés utilisateur » (`maintenance-automatisation`,
> source Web) et « Architecture en couches des tests E2E » (source ISTQB + Web).

---

## 3. Capitalisation contrôlée (cas C)

> **Utilisateur** : Oui, enregistre l'idée sur la matrice probabilité × impact.

```text
$ python qa-knowledge/qa.py section CTAL-TM-3.0-fr 1.3.3        # relu avant de citer
$ python qa-knowledge/qa.py theme proposer "prioriser les tests selon probabilité et impact des risques"
  rbt   Test management › Risk-Based Testing
$ python qa-knowledge/qa.py idee doublons --fichier idee.json
Aucune idée similaire.
$ python qa-knowledge/qa.py idee ajouter --fichier idee.json
Idée créée : QA-0001
```

avec `idee.json` :

```json
{"titre": "Matrice probabilité × impact pour prioriser les tests",
 "resume": "Évaluer chaque risque qualité selon sa probabilité et son impact, puis en dériver l'effort et l'ordre de test.",
 "probleme": "Effort de test réparti uniformément alors que les risques produit sont inégaux.",
 "principe": "Lister les risques qualité, noter probabilité et impact, calculer le niveau de risque, allouer profondeur et ordre de test.",
 "theme_principal": "rbt", "themes_secondaires": ["priorisation"], "maturite": "documentee",
 "provenance": "Recherche du 2026-10-21 : intégrer le RBT en agile",
 "references": [{"type": "istqb", "doc_id": "CTAL-TM-3.0-fr", "pages": "30", "section": "1.3.3",
                 "extrait": "pour chaque élément de risque, de la probabilité du risque et de l'impact du risque"}]}
```

Ce que l'outil refuse (essais réels) :

```text
référence vers la page 300            → Erreur : Page 300 inexistante dans CTAL-TM-3.0-fr (95 pages).
extrait qui n'est pas dans le texte    → Erreur : L'extrait cité n'apparaît pas aux pages 30 de CTAL-TM-3.0-fr (6/10 mots retrouvés).
même idée reformulée                   → REFUSÉ — Doublon probable : compléter l'idée existante (`idee modifier`)…
                                          DOUBLON PROBABLE QA-0001 « Matrice probabilité × impact… » (similarité 0.69)
statut validée sans motif              → Erreur : Le statut « validee » exige un motif (--motif)…
expérimentée sans retour d'expérience  → Erreur : « expérimentée » exige au moins un retour d'expérience
```

---

## 4. Retrouver et faire évoluer (cas C/D)

> **Utilisateur** : Retrouve les idées que nous avons déjà capitalisées sur le shift-left.

```text
$ python qa-knowledge/qa.py idee chercher shift-left
$ python qa-knowledge/qa.py idee lister --theme shift          # inclut shift-left et shift-right
```

> **Utilisateur** : On l'a testée sur la release 3.2, ça a marché.

```text
$ python qa-knowledge/qa.py idee retour QA-0001 --contexte "Release 3.2, équipe paiement" \
      --resultat "2 défauts critiques trouvés avant la recette" --enseignement "atelier d'1 h suffisant"
$ python qa-knowledge/qa.py idee statut QA-0001 experimentee --motif "appliquée sur la release 3.2"
QA-0001 : a_explorer → experimentee
```

---

## 5. Exploration d'un thème et lacunes (cas D)

> **Utilisateur** : Identifie les thèmes QA sur lesquels notre base est encore pauvre.

```text
$ python qa-knowledge/qa.py couverture
thème                                    idées passages  état
Test management                              0      773  vide
  Risk-Based Testing                         1      367  pauvre
…
Thèmes pauvres en idées mais documentés dans les syllabus (pistes d'exploration) : …
```

> **Assistant** : propose 2-3 thèmes à explorer en priorité (beaucoup de matière ISTQB,
> aucune idée capitalisée), et pour chacun lance `chercher --theme <code>` pour en extraire
> les pistes les plus exploitables, regroupées par sous-thème.

---

## 6. Comparaison ISTQB / Web (cas B)

> **Utilisateur** : Compare les techniques de priorisation de l'ISTQB avec les retours d'expérience récents.

1. `chercher priorisation des cas de test` → CTFL v4.0.1 §5.1.5 (*Test Case Prioritization*),
   CTAL-TM §1.3.5 (*Techniques pour le test basé sur les risques*) ; lecture des sections.
2. Lacune identifiée : pas de données terrain récentes → Web justifié (retours
   d'expérience sur la sélection de tests de régression en CI).
3. Tableau comparatif : technique · source (ISTQB §/p. ou URL + date) · conditions ·
   limites ; les éléments Web ne sont jamais présentés comme ISTQB.
4. Proposition de capitalisation : une comparaison (`priorisation`) liée aux idées
   existantes par `idee lier … --type complementaire|contradictoire`.
