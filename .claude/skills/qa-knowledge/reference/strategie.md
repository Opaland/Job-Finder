# Stratégie de recherche et formats de réponse

## Comprendre l'intention

| Demande | Cas | Ce qu'on fait |
|---|---|---|
| « Qu'est-ce que… », « Que dit l'ISTQB sur… » | A — simple | base + syllabus, lecture, réponse courte citée |
| « Recherche des idées pour… », « Compare… » | B — approfondie | A + lacunes/contradictions + Web ciblé + comparaison + recommandations |
| « Classe / enregistre cette idée » | C — capitalisation | doublons → thème → ajout tracé |
| « Idées sur le thème X », « Où notre base est-elle pauvre ? » | D — exploration | `idee lister --theme`, `chercher --theme`, `couverture`, regroupement par sous-thème |

## Formuler les requêtes locales

- Découper la question en 2-4 notions et lancer une requête par angle :
  `chercher "risk-based testing" agile`, puis `chercher priorisation risques --doc CTAL-TM`.
- Ajouter le terme ISTQB anglais quand il est connu : les syllabus EN sont plus complets
  (26 codes) que les traductions FR. Les deux langues sont indexées.
- `--theme <code>` restreint aux passages qui évoquent le thème (mots-clés de la taxonomie).
- Un résultat « PARTIEL » ne couvre qu'une partie des notions : le lire avant de l'utiliser.
- Un passage dans `§ 0.x` ou une annexe (« Business Outcomes », « Release Notes ») est
  rarement la réponse : préférer le chapitre de fond.
- Si rien ne sort : reformuler (synonymes, terme anglais), élargir (`--toutes-versions`),
  puis seulement envisager le Web.

## Lire et recouper

- `lire <id> --contexte 1` donne le passage et ses voisins ; `section <doc> 4.2` toute une
  section. Lire au moins les 2-3 meilleurs passages, de documents différents si possible.
- Noter la version et la date du syllabus ; si deux syllabus divergent (ex. CTFL vs
  CTAL-TM), le dire et expliquer (niveau, date, angle).

## Formats de réponse (proportionnés)

**Question simple** : réponse directe (2-5 phrases) · explication · référence(s).

**Techniques / idées** — pour chacune : idée ou technique · problème traité · principe ·
conditions d'application · bénéfices et limites · références (ISTQB / Web / base).

**Amélioration de processus** : diagnostic · options possibles · recommandation ·
mise en œuvre (étapes) · indicateurs de validation · sources et limites.

Terminer, si pertinent, par : « À capitaliser ? » avec 0-3 propositions concrètes.

## Marquage de la provenance

- `[ISTQB CTAL-TA v4.0 FR, §3.1.1, p. 31]` — passage lu.
- `[Web — titre, domaine, consulté le AAAA-MM-JJ]`.
- `[Base QA-0007, statut à évaluer]`.
- « Interprétation : … » / « Hypothèse : … » pour ce qui vient du raisonnement.

## Quand dire « je ne sais pas »

Aucune source locale ni Web fiable, sources contradictoires sans arbitrage possible,
extraction défaillante du document utile (voir `inventaire`) : le dire, indiquer ce qui
manque (document à importer, version, terme à préciser).
