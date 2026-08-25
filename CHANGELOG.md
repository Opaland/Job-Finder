# Changelog

## v3.0 — Décrocher le poste (sprints 21 à 40)

**Entretiens et suivi (EPIC L)**
- Entretiens datés par offre (date, format, interlocuteur) + carte « Prochains
  entretiens » sur le tableau de bord.
- Compte-rendu structuré après l'entretien (déroulé, ressenti, suite annoncée)
  qui planifie directement la relance.
- Checklist de candidature (CV adapté, lettre prête, envoyée, relancée) avec
  avancement visible dans la liste.
- Historique des lettres : 10 versions gardées, comparables et restaurables.

**Comprendre le marché (EPIC M)**
- Nouvel onglet Marché : compétences les plus demandées et lesquelles manquent
  au CV, entreprises qui recrutent, salaires observés (lecture des fourchettes
  dans les annonces), manques récurrents repérés par l'IA, fraîcheur des offres
  et repérage des annonces republiées en boucle.

**Preuves et administratif (EPIC N)**
- Justificatif PDF de recherche d'emploi sur une période (France Travail).
- Import / export CSV du suivi, doublons ignorés à l'import.
- Taux d'entretien par source : ce que chaque site rapporte vraiment.

**Efficacité quotidienne (EPIC O)**
- Recherches sauvegardées, comparateur de deux offres côte à côte,
  raccourcis clavier et palette de commandes (Ctrl+K).
- Rappel par email à 18 h la veille d'un entretien ou d'une action datée,
  signalant une fiche de préparation non générée.

**IA de préparation (EPIC P)**
- Simulation d'entretien : Claude joue le recruteur, commente chaque réponse.
- Reformulation ATS du CV pour une offre donnée, sans rien inventer.
- Bilan hebdomadaire commenté : ce qui avance, ce qui bloque, 3 actions.

**Mobile (EPIC Q)**
- Application installable sur l'écran d'accueil (PWA) et interface repensée
  pour le téléphone.

**Durcissement** — correctif de migration important : les colonnes JSON
ajoutées à une base existante recevaient NULL et l'API renvoyait une erreur au
premier affichage ; elles reçoivent désormais leur valeur vide et les NULL
laissés par une version antérieure sont rattrapés.

## v2.3 — Tourner 24/7 : tâche planifiée et Docker

- `deploiement/installer-linux.sh` : installation en une commande sur
  Raspberry Pi ou vieux PC recyclé (environnement Python, build de l'interface,
  service systemd qui redémarre avec la machine) — sans Docker.
- `installer-tache-quotidienne.bat` : enregistre la tâche Windows du scan
  quotidien avec **réveil du PC en veille** à 07h25 et rattrapage si le PC
  était éteint — le scan et l'email partent sans intervention.

- Image Docker multi-étapes (build de l'interface puis runtime Python) et
  `docker-compose.yml` prêt pour Container Manager : scan quotidien, email et
  interface tournent sur le NAS, PC éteint.
- Base et CV dans un volume `./data` sur le NAS (Hyper Backup), rien de
  personnel dans l'image.
- Fonctions IA en option : sans la CLI Claude Code (défaut), le classement par
  règles et tout le suivi fonctionnent ; avec `AVEC_IA=1`, la CLI est embarquée
  et authentifiée une fois, session conservée entre les redémarrages.
- README §9 : installation pas à pas, rappel « réseau local uniquement »
  (aucune authentification), et règle d'une seule instance par base.

## v2.2 — Qualité : refacto + garde-fous

**Refacto (revue globale)**
- Règle de dédoublonnage unique (`find_twin`) partagée par le scan et l'ajout
  manuel ; pipeline `run_full_scan` unique (bouton Scanner, scan quotidien, CLI).
- Scan sans requête N+1 (index en mémoire) ; liste, Kanban, export Excel et
  digest ne chargent plus les colonnes lourdes inutilement.
- Mutualisation : tronc commun des 4 routes IA, groupes de statuts nommés,
  `parse_iso_dt` / `parse_published` ; côté interface `downloadFile`,
  `actionDue`, `StatusRow`, un seul état d'action longue, statuts dérivés
  d'`api.js` (démo comprise).

**Garde-fous**
- `scripts/verif.sh` / `verif.bat` : syntaxe + tests + build + build démo,
  identique à la CI ; hook Claude Code bloquant sur commit (rapide) et push
  (complet).
- `scripts/revue_ia.py` : revue du diff par la session Claude locale avec la
  check-list du projet ; `scripts/smoke_ui.mjs` : parcours navigateur des
  7 onglets.
- `.claude/` : règles backend/frontend/qualité, agent `revue-jobfinder`,
  skills `/verif` `/revue` `/smoke`, hook d'installation des dépendances pour
  les sessions web.
- Nouveau test : toute route API doit être gérée en mode démo (sinon la démo
  GitHub Pages casse) ; la CI construit désormais aussi la démo.

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
