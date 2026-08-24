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

## V3

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
- [ ] **Sprint 17** : focus du jour — 3 actions suggérées (pépite à traiter,
  relance due, action datée).

### EPIC I — Fiabilité & visibilité

- [x] **Sprint 15** : pagination et tris avancés de la liste des offres
  (tri par date de publication, filtre entreprise).
- [ ] **Sprint 18** : santé des sources — historique d'erreurs sur 14 jours,
  retries HTTP avec backoff dans les connecteurs.
- [ ] **Sprint 19** : journal d'activité (scans, changements de statut,
  générations IA).

### EPIC J — Release

- [ ] **Sprint 20** : durcissement, revue de code globale, doc/site/démo à
  jour, CHANGELOG, v2.1.

### Réserve (non planifié)

- Connecteurs supplémentaires (jobboards spécialisés QA) — nécessite de
  pouvoir tester les accès réseau réels depuis le poste local.
