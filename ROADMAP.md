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
- [ ] **Sprint 7** : pépites (score ≥ 85 mises en avant dans l'appli et le
  digest) + objectif hebdomadaire de candidatures avec jauge de progression.

### EPIC F — Personnalisation & finitions

- [ ] **Sprint 8** : requêtes de scan configurables dans le profil (les
  mots-clés de recherche des connecteurs ne sont plus codés en dur).
- [ ] **Sprint 9** : mode sombre complet (tokens CSS + pas sombres validés de
  la palette dataviz).
- [ ] **Sprint 10** : durcissement final — tests supplémentaires, revue de
  code globale, documentation et site à jour, tag v2.0.

### Réserve (non planifié)

- Connecteurs supplémentaires (jobboards spécialisés QA) — nécessite de
  pouvoir tester les accès réseau réels depuis le poste local.
