# Changelog

## v2.1 — Sprints 11 à 20 (EPICs G/H/I/J)

**Capture & candidature**
- Ajout manuel d'offres : coller une annonce (LinkedIn, Indeed, cooptation…) —
  parsing heuristique, scoring immédiat, dédoublonnage.
- Emails de candidature et de relance générés par l'IA locale (mailto pré-rempli,
  adressé au contact connu de l'entreprise).
- Analyse d'écart CV ↔ offre : couvert / manquant / adaptations ATS / verdict.

**Organisation quotidienne**
- Prochaines actions datées par offre + « À faire aujourd'hui » (tableau de bord
  et email, retards signalés, chips ⏰).
- Contacts recruteurs par entreprise (mini-CRM rattaché aux offres).
- Focus du jour : les 3 actions qui comptent, priorisées automatiquement.

**Fiabilité & visibilité**
- Pagination réelle et tris avancés des offres (date de publication, entreprise).
- Santé des sources : historique d'erreurs sur 14 jours + retries réseau.
- Journal d'activité (scans, statuts, générations IA, ajouts, CV, restaurations).

**Durcissement** : revue de code globale (journal isolé de la transaction
appelante, validation des contacts, états d'erreur UI, fenêtre 14 jours réelle,
requêtes dédupliquées du digest).

## v2.0 — Sprints 1 à 10 (EPICs A à F)

Statistiques (KPI, activité, pipeline, sources, distribution, réactivité des
entreprises), Kanban drag & drop, préparation d'entretien IA, pondérations du
scoring réglables, migration automatique du schéma, restauration de sauvegarde,
doublons par similarité de titre, pépites + objectif hebdomadaire, requêtes de
scan configurables, mode sombre.

## v1.0

Agrégation 6 sources (France Travail, Adzuna, JSearch, WTTJ, APEC, HelloWork),
scoring 0-100 expliqué calibré CV, affinage IA et lettres via la session Claude
Code locale, digest quotidien + email, relances à J+7, enrichissement de
description, exports Word et Excel, site GitHub Pages (accueil + démo), CI,
scripts Windows.
