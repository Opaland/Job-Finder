# Roadmap Job Finder

Organisation en EPICs et sprints. Un sprint n'est terminé que livré : tests verts,
build OK, poussé sur la branche, CI verte, démo/documentation à jour.

## V1 — livrée ✅

Agrégation 6 sources (France Travail, Adzuna, JSearch, WTTJ, APEC, HelloWork),
scoring 0-100 expliqué et calibré CV, affinage IA + lettres via la session Claude
Code locale, digest quotidien + email, relances à J+7, enrichissement de
description, export Word des lettres, export Excel du suivi, site GitHub Pages
(accueil + démo), CI, scripts Windows.

## V2

### EPIC A — Pilotage & visibilité

- [x] **Sprint 1** : page Statistiques (KPI, activité 30 jours, pipeline par
  statut, offres par source, distribution des scores — méthode dataviz, palette
  validée) + sauvegarde de la base en un clic (API backup SQLite).

### EPIC B — Candidature augmentée

- [x] **Sprint 2** : tableau Kanban du pipeline — colonnes par statut, cartes
  glissées-déposées (le statut reste modifié uniquement par l'utilisateur),
  disponible aussi dans la démo.
- [x] **Sprint 3 (part. 1)** : préparation d'entretien par l'IA locale — fiche
  générée par Claude pour une offre (points forts du CV face à l'annonce,
  questions probables du recruteur, questions à poser, pièges), stockée sur
  l'offre et exportable.

### EPIC C — Matching intelligent

- [x] **Sprint 3 (part. 2)** : pondérations du scoring réglables dans l'UI
  (titre / compétences / séniorité / localisation / contrat / secteur) avec
  re-scoring immédiat ; migration automatique de la base (les données existantes
  sont préservées).

### EPIC D — Fiabilité des données

- [x] **Sprint 4** : restauration de sauvegarde depuis l'UI (validation du
  fichier, copie de sécurité automatique, migration de la sauvegarde).
- [x] **Sprint 5** : détection de doublons par similarité de titre (fusion au
  scan des offres de même entreprise aux titres quasi identiques).

### EPIC E — Pilotage avancé

- [x] **Sprint 6** : réactivité des entreprises — candidatures, réponses,
  délai moyen et attentes en cours, par entreprise (page Statistiques).
- [x] **Sprint 7** : pépites (score ≥ 85 mises en avant dans l'appli et le
  digest) + objectif hebdomadaire de candidatures avec jauge de progression.

### EPIC F — Personnalisation & finitions

- [x] **Sprint 8** : requêtes de scan configurables dans le profil (les
  mots-clés de recherche des connecteurs ne sont plus codés en dur).
- [x] **Sprint 9** : mode sombre complet (tokens CSS + pas sombres validés de
  la palette dataviz).
- [x] **Sprint 10** : durcissement final — tests supplémentaires, revue de
  code globale, documentation et site à jour, tag v2.0.

## V2.1 — Sprints 11 à 20

### EPIC G — Capture & candidature

- [x] **Sprint 11** : ajout manuel d'offres — coller une annonce (LinkedIn,
  Indeed, cooptation…) : parsing heuristique, scoring immédiat, dédoublonnage.
- [x] **Sprint 13** : emails de candidature et de relance générés par l'IA
  locale (mailto pré-rempli + copie).
- [x] **Sprint 14** : analyse d'écart CV ↔ offre par l'IA (compétences
  manquantes, conseils ATS), stockée sur l'offre.

### EPIC H — Organisation quotidienne

- [x] **Sprint 12** : prochaines actions datées par offre (relance, entretien…)
  + section « À faire aujourd'hui » (tableau de bord et email).
- [x] **Sprint 16** : contacts recruteurs par entreprise (nom, email,
  téléphone, notes), rattachés aux offres.
- [x] **Sprint 17** : focus du jour — 3 actions suggérées (pépite à traiter,
  relance due, action datée).

### EPIC I — Fiabilité & visibilité

- [x] **Sprint 15** : pagination et tris avancés de la liste des offres
  (tri par date de publication, filtre entreprise).
- [x] **Sprint 18** : santé des sources — historique d'erreurs sur 14 jours,
  retries HTTP avec backoff dans les connecteurs.
- [x] **Sprint 19** : journal d'activité (scans, changements de statut,
  générations IA).

### EPIC J — Release

- [x] **Sprint 20** : durcissement, revue de code globale, doc/site/démo à
  jour, CHANGELOG, v2.1.

### EPIC K — Qualité durable

- [x] **Revue globale + refacto** : dédoublonnage et pipeline de scan
  mutualisés, requêtes allégées, duplications front/back supprimées.
- [x] **Garde-fous** : `scripts/verif.sh|.bat`, revue IA locale
  (`scripts/revue_ia.py`), smoke test navigateur (`scripts/smoke_ui.mjs`),
  règles et hooks Claude Code (`.claude/`), test de couverture du mode démo,
  build démo ajouté à la CI.

## V3 — Décrocher le poste

Cap : passer de « collecter des offres » à « piloter une recherche d'emploi »,
avec ce qui compte quand on cherche vraiment — préparer et suivre les entretiens,
comprendre le marché QA lyonnais, prouver ses démarches, et gagner du temps
chaque jour.

### EPIC L — Entretiens et suivi de candidature

- [x] **Sprint 21** : entretiens datés par offre (date, format, interlocuteur),
  carte « Prochains entretiens » sur le tableau de bord.
- [x] **Sprint 22** : compte-rendu d'entretien structuré (déroulé, ressenti,
  suite annoncée) et relance calée sur la suite annoncée.
- [x] **Sprint 23** : checklist de candidature par offre (CV adapté, lettre
  prête, envoyée, relancée) avec avancement visible dans la liste.
- [x] **Sprint 24** : historique des lettres générées — comparer et restaurer
  une version précédente.

### EPIC M — Comprendre le marché

- [x] **Sprint 25** : compétences les plus demandées dans les offres collectées
  (classement, et lesquelles manquent au CV).
- [x] **Sprint 26** : entreprises qui recrutent le plus + fourchettes de salaire
  observées par intitulé de poste.
- [x] **Sprint 27** : synthèse des analyses d'écart IA — les manques qui
  reviennent, pour orienter formation et CV.
- [x] **Sprint 28** : fraîcheur des offres et repérage des annonces fantômes
  (republiées en boucle depuis des mois).

### EPIC N — Preuves et administratif

- [x] **Sprint 29** : export PDF « justificatif de recherche d'emploi » —
  candidatures, relances et entretiens sur une période (France Travail).
- [x] **Sprint 30** : import / export CSV des offres (reprise d'un suivi tenu
  ailleurs, ou sauvegarde lisible).
- [x] **Sprint 31** : taux de conversion par source — quelle source donne
  réellement des entretiens.

### EPIC O — Efficacité quotidienne

- [ ] **Sprint 32** : recherches sauvegardées (filtres nommés, rappelés en un clic).
- [ ] **Sprint 33** : comparateur de deux offres côte à côte.
- [ ] **Sprint 34** : raccourcis clavier et palette de commandes.
- [ ] **Sprint 35** : email de rappel la veille d'un entretien ou d'une action datée.

### EPIC P — IA au service de la préparation

- [ ] **Sprint 36** : simulation d'entretien — Claude pose les questions, tu
  réponds, il commente.
- [ ] **Sprint 37** : reformulation ATS des expériences du CV pour une offre donnée.
- [ ] **Sprint 38** : bilan hebdomadaire commenté par l'IA (ce qui avance, ce
  qui bloque, quoi faire la semaine prochaine).

### EPIC Q — Mobile et release

- [ ] **Sprint 39** : application installable (PWA) et interface soignée sur
  téléphone.
- [ ] **Sprint 40** : durcissement, revue globale, documentation et démo à jour,
  release v3.0.

### Réserve (non planifié)

- Connecteurs supplémentaires (jobboards spécialisés QA) — nécessite de
  pouvoir tester les accès réseau réels depuis le poste local.
