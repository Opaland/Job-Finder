# Changelog

## v3.1 — Validation sur les vraies sources

Jusqu'ici l'application n'avait jamais parlé aux vrais sites : tout était vérifié
sur des données fabriquées. Cette version confronte les six connecteurs au réel,
et corrige ce que ça a révélé.

**Défauts trouvés en interrogeant les vrais sites**
- Les six sources répondaient 403 derrière un proxy : le client HTTP ne lisait
  pas la configuration réseau de la machine. Un `HTTPS_PROXY` sans schéma faisait
  même *lever* le scan, et les exclusions `no_proxy` étaient ignorées.
- Chaque offre APEC portait un **lien mort** (404) : une forme au pluriel dans
  l'URL de détail.
- Une recherche « Lyon » sur l'APEC renvoyait Nantes, Saran et Annemasse — 1 offre
  sur 20 dans le Rhône. Le filtre se fait par département, pas par rayon.
- L'enrichissement d'une offre APEC remplaçait la vraie description par le
  **bandeau de cookies** de la page (417 caractères contre 283) et remettait
  l'avis IA à zéro au passage.
- HelloWork ne ramenait **jamais** d'offre en télétravail : deux recherches sur
  cinq interrogeaient un lieu nommé « Télétravail », qui n'existe pas.
- Les champs HelloWork étaient devinés à leur position dans la carte ; ils sont
  maintenant lus dans l'`aria-label`, qui les donne en clair.
- Les dates des API étaient dépouillées de leur fuseau sans conversion : deux
  heures d'écart, et un changement de jour pour toute offre publiée après 22 h.
- « moins d'une heure » et « plus de 1 mois » n'étaient pas reconnus : les offres
  les plus fraîches comme les plus anciennes perdaient leur date.
- Le salaire affiché par HelloWork était jeté ; il est conservé (27 offres sur 55).

**Les tests parlent aux vrais sites**
- Plus aucun client HTTP bouchonné dans la suite. Ce qui se vérifie sans réseau
  passe par des fonctions pures ou par une page réelle figée ; le reste appelle
  vraiment apec.fr, hellowork.com et la CLI `claude`.
- Une source injoignable fait *ignorer* le test en disant pourquoi ; une source
  qui répond mal le fait **échouer**. Une source qui répond sans erreur et sans
  offre échoue aussi : c'est le « succès à vide » que le diagnostic traque.
- Un scan complet de bout en bout sur les vraies sources, avec la règle absolue
  vérifiée pour de vrai : aucun statut touché, aucune offre supprimée.
- La CI faisait tourner 292 tests en ignorant les 7 tests de traversée de chemin,
  sans le dire. Elle les exécute désormais, et affiche la raison de chaque test
  ignoré.
- 305 tests, ≈ 25 s. 18 fautes plausibles injectées une à une : les 18 sont
  attrapées.

**Sécurité**
- Correction d'une traversée de chemin : `/../../data/jobfinder.db` servait la
  base de données entière. Et d'une écriture arbitraire à l'import de CV, où un
  nom de fichier piégé écrasait la base.
- Le CV ne transite plus par la ligne de commande de la CLI `claude` (il était
  lisible dans la liste des processus).

**Limites documentées** (§10 du README) : Welcome to the Jungle en panne côté
site, descriptions APEC tronquées à 283 caractères, seuil des pépites (85)
au-dessus du meilleur score réel observé (82).

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
