# Job Finder 🎯

Application **locale** de recherche d'emploi construite pour Cédric Moretti (Test Manager / QA Lead, Lyon).
Elle interroge chaque jour plusieurs sites d'emploi, **classe les offres selon leur adéquation avec le CV**
(score 0-100 expliqué critère par critère), produit un **point quotidien** (tableau de bord + email) et
génère des **lettres de motivation adaptées** à chaque offre via la session locale Claude Code.

Règle de conception : **aucune offre n'est jamais fermée automatiquement** — seul toi peux passer une offre
en « Refusée » ou « Fermée ». Une offre disparue de sa source est simplement marquée « Plus en ligne ? ».

🌐 **Site du projet + démo interactive (données d'exemple)** : https://opaland.github.io/Job-Finder/
— la démo montre l'interface dans le navigateur ; l'application complète (scans réels, IA, email)
tourne en local, voir ci-dessous. Le site est déployé automatiquement par GitHub Actions
(`.github/workflows/pages.yml`). Historique des versions : [CHANGELOG.md](CHANGELOG.md).

---

## 1. Démarrage rapide (Windows)

Prérequis (à installer une seule fois) :
- [Python 3.11+](https://www.python.org/downloads/) — coche **« Add python.exe to PATH »** à l'installation
- [Node.js LTS](https://nodejs.org) (uniquement pour construire l'interface au premier lancement)

Ensuite :

```bat
git clone https://github.com/Opaland/Job-Finder.git
cd Job-Finder
start.bat
```

`start.bat` fait tout : environnement Python, dépendances, build de l'interface, copie de `.env.example`
vers `.env`, puis ouvre http://127.0.0.1:8000 dans ton navigateur.

Ton profil est **pré-chargé** : CV (texte + compétences détectées), lettre de motivation type, zone
Lyon + 40 km + full remote, contrats CDI + Freelance, postes cibles Test Manager / QA Lead / Responsable QA.
Tout est modifiable dans l'onglet **Profil & CV**.

> ⚠️ Sans aucune clé, l'application marche déjà : **APEC et HelloWork** répondent sans inscription
> (≈ 240 offres lyonnaises au dernier relevé). Welcome to the Jungle, en revanche, est **actuellement
> en panne** (voir §3.4). Pour la couverture complète, configure les clés gratuites — §3, ≈ 10 minutes.
> `python -m app.cli sources` dit à tout moment ce que chaque source renvoie vraiment.

## 2. Ce que fait l'application

| Fonction | Détail |
|---|---|
| **Scan multi-sites** | France Travail, Adzuna, JSearch (LinkedIn/Indeed via Google for Jobs), Welcome to the Jungle, APEC, HelloWork — état réel de chacune en §3.4 et §10 |
| **Classement 0-100** | Adéquation du titre (40), compétences du CV citées (25), séniorité (10), localisation Lyon/remote (15), contrat (5), secteur connu (5). Postes hors QA plafonnés à 20, juniors/stages à 30 |
| **Affinage IA** | Ta session locale Claude Code donne un avis (0-100 + justification) sur les meilleures offres ; le score final est la moyenne règles/IA |
| **« Pourquoi ce score ? »** | Chaque offre affiche le détail de son score, critère par critère |
| **Dédoublonnage** | Une même offre vue sur deux sites = une seule fiche (les autres sources sont listées dessus) |
| **Statuts** | Nouvelle → Vue → À postuler → Postulée → Relancée → Entretien → Refusée / Fermée — **modifiés uniquement par toi** |
| **Point quotidien** | Scan automatique chaque matin (07:30 par défaut) + tableau de bord + email récapitulatif (pépites, relances, objectif hebdo) |
| **Lettres de motivation** | Génération d'une lettre adaptée à l'offre (Claude local), éditable, copiable, export Word |
| **Préparation d'entretien** | Fiche générée par Claude : pitch, points forts face à l'annonce, questions probables, vigilances, questions à poser |
| **Pipeline Kanban** | Colonnes par statut, cartes en glisser-déposer |
| **Statistiques** | KPI, activité 30 jours, pipeline, sources, distribution des scores, réactivité des entreprises (délais de réponse) |
| **Pépites & objectif** | Offres score ≥ 85 mises en avant partout ; objectif de candidatures hebdomadaire avec jauge. *Le meilleur score observé sur de vraies offres est 82 : la section reste vide tant que le seuil n'est pas abaissé (§10).* |
| **Personnalisation** | Pondérations du score réglables, requêtes de scan configurables, mode sombre |
| **Données** | Enrichissement de description depuis le site d'origine, export Excel du suivi, sauvegarde et restauration de la base en un clic, migration automatique du schéma |
| **Notes & favoris** | Notes libres, favoris ★, historique des statuts par offre |
| **Entretiens** | Entretiens datés par offre, carte « Prochains entretiens », compte-rendu structuré qui planifie la relance |
| **Checklist** | CV adapté / lettre prête / envoyée / relancée, avancement visible dans la liste |
| **Marché** | Compétences les plus demandées (et lesquelles manquent à ton CV), qui recrute, salaires observés, offres fantômes |
| **Justificatifs** | Export PDF des démarches sur une période, pour l'actualisation France Travail |
| **Simulation d'entretien** | Claude joue le recruteur : questions, retours sur tes réponses, ce qu'il attend |
| **Version ATS du CV** | Titre, accroche et puces réécrits avec les mots de l'offre, sans rien inventer |
| **Bilan hebdomadaire** | Chiffres de la semaine + commentaire de Claude : ce qui avance, ce qui bloque, 3 actions |
| **Rappels** | Email à 18 h la veille d'un entretien ou d'une action datée |
| **Confort** | Recherches sauvegardées, comparateur d'offres, raccourcis clavier et palette (Ctrl+K), import/export CSV |
| **Mobile** | Application installable sur l'écran d'accueil (PWA), interface adaptée au téléphone |

## 3. Configurer les sources (clés gratuites)

Toutes les clés vont dans le fichier **`.env`** à la racine (créé automatiquement au premier lancement,
modèle dans `.env.example`). Redémarre l'application après modification.

### 3.1 France Travail (ex Pôle Emploi) — recommandé, 5 min

La source officielle la plus riche pour la France.

1. Va sur **https://francetravail.io** et crée un compte
2. « Créer une application » → donne un nom (ex. *JobFinder*)
3. Dans le catalogue, ajoute l'API **« Offres d'emploi v2 »** à ton application
4. Récupère **l'identifiant client** et la **clé secrète** → colle-les dans `.env` :
   ```
   FT_CLIENT_ID=PAR_xxxxxxxx
   FT_CLIENT_SECRET=xxxxxxxxxxxx
   ```

### 3.2 Adzuna — agrégateur, 3 min

1. **https://developer.adzuna.com** → « Sign up »
2. Les clés `Application ID` et `Application Key` s'affichent dans ton dashboard
3. ```
   ADZUNA_APP_ID=xxxxx
   ADZUNA_APP_KEY=xxxxxxxxxxxx
   ```

### 3.3 JSearch (RapidAPI) — couvre LinkedIn et Indeed, 5 min

LinkedIn et Indeed **interdisent la collecte directe** ; leurs offres sont indexées par Google for Jobs,
que l'API JSearch expose légalement.

1. Crée un compte sur **https://rapidapi.com**
2. Cherche l'API **« JSearch »** (éditeur *letscrape*) → « Subscribe to test » → plan **Basic (gratuit)**
3. Copie la valeur **X-RapidAPI-Key** affichée dans les exemples de code
4. ```
   RAPIDAPI_KEY=xxxxxxxxxxxx
   ```

> Le plan gratuit autorise ~200 requêtes/mois ; le connecteur en consomme 4 par scan, soit ~120/mois
> avec le scan quotidien : ça passe. Si tu lances beaucoup de scans manuels, désactive JSearch entre-temps
> (onglet Sources) ou passe au plan supérieur.

### 3.4 Welcome to the Jungle, APEC, HelloWork — sans clé

Ces trois connecteurs utilisent les services **non officiels** des sites eux-mêmes : ils fonctionnent sans
inscription mais peuvent casser quand les sites évoluent. Les erreurs éventuelles s'affichent dans
l'onglet **Sources & réglages** sans bloquer le reste.

**APEC — opérationnelle** (181 offres au dernier relevé). Rien à configurer. Une limite à connaître :
son service ne renvoie que les **283 premiers caractères** de l'annonce, et la page de détail refuse
la lecture automatique (HTTP 401). Le score et l'avis IA travaillent donc sur un résumé, pas sur
l'annonce entière — le lien de l'offre ouvre bien la page complète dans le navigateur.

**HelloWork — opérationnelle** (57 offres au dernier relevé). Rien à configurer. La page de résultats
ne porte qu'un entrefilet ; la description complète arrive à l'ouverture de l'offre (enrichissement),
et fonctionne bien : ~4 700 caractères sur une annonce typique.

**Welcome to the Jungle — en panne, et pas réparable simplement.** La recherche passe par un index
Algolia dont la clé publique a changé, et le site ne l'expose plus dans ses pages : la méthode
« F12 → Réseau → copier `x-algolia-api-key` » ne donne plus rien. Si tu récupères une clé valide par
un autre moyen, elle se colle dans `.env` (`WTTJ_ALGOLIA_API_KEY=`) et le connecteur repart sans autre
changement. En attendant, la source remonte un échec explicite et n'empêche rien.

En cas de panne durable d'APEC ou HelloWork, demande à Claude Code de mettre à jour le connecteur
(`backend/app/connectors/apec.py` ou `hellowork.py`) : les tests réels (§8) montrent précisément ce
qui a bougé.

### 3.5 Vérifier que les sources répondent vraiment

```bash
cd backend
python -m app.cli sources          # ce que chaque source renvoie réellement
python -m app.cli sources --brut   # + fige les réponses dans data/diagnostic/
```

Le diagnostic distingue trois cas : **OK**, **KO** (la source ne répond pas, avec la raison) et
surtout **SUSPECT** — la source répond mais ce qu'elle renvoie est inexploitable (aucune offre, ou
un champ vide sur *toutes* les offres, signe que le site a changé de format). C'est le cas qui ne
fait pas de bruit : un scan normal se contente d'afficher « 0 nouvelle offre ».

À lancer après avoir rempli les clés, et à relancer le jour où une source semble muette.

La suite de tests fait la même vérification, en plus strict et sans rien à lire :

```bash
cd backend
python -m pytest tests/test_sources_reelles.py -q -rs
```

Ces tests appellent **vraiment** les sites. Une source injoignable fait *ignorer* le test en disant
pourquoi (`SKIPPED France Travail : Clés FT_CLIENT_ID / FT_CLIENT_SECRET absentes du .env`) ; une
source qui répond mal fait **échouer**. C'est le retour immédiat quand on vient de coller une clé.

## 4. Email quotidien

Le digest est envoyé chaque matin après le scan (si le SMTP est configuré). Avec Gmail :

1. Active la **validation en 2 étapes** sur ton compte Google
2. Crée un **mot de passe d'application** : https://myaccount.google.com/apppasswords
3. Dans `.env` :
   ```
   SMTP_USER=ced.moretti@gmail.com
   SMTP_PASSWORD=le mot de passe d'application (16 caractères)
   DIGEST_EMAIL_TO=ced.moretti@gmail.com
   ```
4. Teste depuis l'onglet **Sources & réglages** → « Envoyer un email de test »

## 5. Scan quotidien

- **Application ouverte** : le scan tourne tout seul à l'heure choisie (Profil & CV → « Heure du scan
  quotidien », 07:30 par défaut) puis met à jour le tableau de bord et envoie l'email.
- **Application fermée** : planifie `scan.bat` dans le **Planificateur de tâches Windows**
  (Créer une tâche de base → Quotidien → 07:30 → Démarrer un programme → `C:\...\Job-Finder\scan.bat`).
  Le scan et l'email fonctionnent alors même sans interface ouverte.
- Pour lancer l'application automatiquement au démarrage de Windows : mets un raccourci vers `start.bat`
  dans le dossier `shell:startup`.
- **Les deux à la fois, c'est sans risque** : un verrou de fichier (`data/scan.lock`) empêche
  l'application et la tâche planifiée de scanner en même temps. Le second arrivé s'arrête
  proprement — la tâche planifiée affiche « Scan ignoré », l'interface un message d'attente.

## 6. IA locale (session Claude Code)

L'application n'utilise **aucune clé API Anthropic** : elle appelle la commande `claude` de ta session
locale Claude Code (ton abonnement) pour :
- **affiner le score** des offres les mieux classées à chaque scan (avis 0-100 + justification, encadré
  bleu dans le détail de l'offre) ;
- **générer les lettres de motivation** adaptées (bouton « Générer avec Claude » dans chaque offre).

Vérifie que `claude` fonctionne dans un terminal ; l'onglet Sources indique si l'IA est détectée.
Réglages dans `.env` : `AI_MODE=off` pour désactiver, `AI_MAX_OFFERS_PER_SCAN` et `AI_MIN_RULE_SCORE`
pour doser. Sans IA, le classement par règles fonctionne normalement.

## 7. Architecture

```
Job-Finder/
├── start.bat / scan.bat        Lancement Windows / scan planifié sans interface
├── .env(.example)              Clés API et réglages
├── data/                       Base SQLite + CV importés (créé au 1er lancement, non versionné)
├── backend/
│   ├── app/
│   │   ├── main.py             API FastAPI + sert l'interface buildée
│   │   ├── config.py           Réglages (.env)
│   │   ├── models.py           Offres, profil, scans, digests (SQLite)
│   │   ├── connectors/         Un fichier par site d'emploi
│   │   ├── services/
│   │   │   ├── scoring.py      Moteur de classement expliqué (0-100)
│   │   │   ├── scan.py         Orchestration + dédoublonnage (jamais de fermeture auto)
│   │   │   ├── claude_ai.py    Affinage IA + lettres via la CLI claude locale
│   │   │   ├── digest.py       Point quotidien + email HTML
│   │   │   └── scheduler.py    Scan quotidien (APScheduler)
│   │   └── routers/            Endpoints REST (/api/...)
│   ├── seed/                   Profil initial : CV, lettre type, critères
│   └── tests/                  pytest — dont test_sources_reelles.py (vrais appels
│       └── fixtures/           aux sites) et une page HelloWork réelle figée
├── frontend/                   React + Vite (tableau de bord, offres, profil, sources)
├── scripts/                    Vérification, revue IA, smoke test navigateur
└── .claude/                    Règles, hooks et skills pour Claude Code
```

Lancer les tests : `cd backend && venv\Scripts\python -m pytest tests/ -q`
Mode développement interface : `cd frontend && npm run dev` (proxy vers le backend sur :8000).

## 8. Garde-fous qualité (scripts)

**Les tests parlent aux vrais sites.** `backend/tests/test_sources_reelles.py` appelle réellement
apec.fr, hellowork.com et la CLI `claude` (≈ 25 s sur les ~305 tests). Il n'y a **aucun client HTTP
bouchonné** dans la suite : un faux client prouve qu'on envoie ce qu'on croit envoyer, jamais que la
source l'accepte — les défauts trouvés en validation étaient tous de ce genre (lien d'offre en 404,
filtre géographique ignoré, bandeau de cookies pris pour une description). Ce qui se vérifie sans
réseau passe par des fonctions pures (`ApecConnector.payloads()`, `HelloWorkConnector.recherches()`)
ou par la page réelle figée dans `tests/fixtures/`.

Cinq scripts, utilisables à la main ou par Claude Code :

| Commande | Ce qu'elle fait |
|---|---|
| `scripts\verif.bat` (Windows) · `bash scripts/verif.sh` | Syntaxe + tests backend + build frontend + build démo — exactement ce que vérifie la CI. Ajouter `rapide` / `--rapide` pour un contrôle éclair avant un commit. |
| `python scripts/revue_ia.py [commit]` | Revue du diff par **ta session Claude locale** (aucune clé API), avec la check-list du projet : dédoublonnage, heures locales, statuts centralisés, N+1 SQL, simulation démo. Constats en français, gravité par constat. |
| `node scripts/smoke_ui.mjs [url]` | Parcourt les 7 onglets dans un vrai navigateur (Playwright) et signale toute erreur JS. Backend démarré requis. |
| `python scripts/mutation.py [modules]` | **Test de mutation** : abîme le code une faute à la fois (`<` → `<=`, `and` → `or`, seuil décalé) et vérifie que les tests s'en aperçoivent. Un « survivant » est une ligne qu'on pourrait casser sans que rien ne bronche. Travaille sur une copie jetable — le dépôt n'est jamais modifié. |
| `python scripts/mesures.py [n]` | Chronomètre les opérations coûteuses (index de dédoublonnage, digest, pages Marché) sur `n` offres générées, dans une base jetable. Alerte au-delà d'une seconde. Mesuré à ce jour : tout reste sous 1 s jusqu'à 10 000 offres, le digest étant le plus lent (0,9 s). |

Dans Claude Code, les mêmes contrôles sont accessibles par `/verif`, `/revue` et `/smoke`, et un
hook bloque automatiquement un commit dont les tests sont rouges ou un push dont les builds cassent.

## 9. Scan quotidien sans PC allumé

Le scan de 07:30 et l'email n'ont d'intérêt que s'ils partent tous les jours.
Trois façons d'y arriver, de la plus simple à la plus « installée ».

### 9.1 Réveiller le PC — aucun matériel, 2 minutes

Windows sait sortir le PC de **veille** pour exécuter une tâche. Le PC se
réveille à 07h25, scanne, envoie l'email, et se rendort.

```bat
installer-tache-quotidienne.bat        (clic droit > Executer en tant qu'administrateur)
```

Le script crée la tâche « Job Finder - scan quotidien » (réveil activé,
rattrapage si le PC était éteint). Une condition côté Windows : Panneau de
configuration → Options d'alimentation → Paramètres du mode → Veille →
**Minuteries de réveil = Activer**.

Limite : la veille suffit, un PC **complètement éteint** ne se réveille pas
(le scan se lancera alors au démarrage suivant). Pour désinstaller :
`schtasks /delete /tn "Job Finder - scan quotidien" /f`.

### 9.2 NAS Synology ou mini-PC avec Docker — 24/7 pour de bon

Là, l'application tourne en permanence : scan, email et interface accessibles
depuis le PC comme depuis le téléphone, sans rien allumer.

**Il faut Container Manager**, donc un Synology à processeur **x86 (Intel/AMD)** :
les modèles « + » récents (DS224+, **DS225+**, DS423+, DS723+…). Un Raspberry Pi 4/5
ou n'importe quel mini-PC sous Linux conviennent aussi — l'image se construit en
ARM64 comme en x86-64.

1. Copier le dépôt dans un dossier partagé, ex. `/volume1/docker/job-finder`
   (File Station, ou en SSH : `git clone https://github.com/Opaland/Job-Finder.git`).
2. Créer le fichier de configuration — obligatoire, même vide :
   ```bash
   cd /volume1/docker/job-finder
   cp .env.example .env      # puis les clés (§3) et le SMTP (§4)
   ```
3. Construire et démarrer :
   ```bash
   docker compose up -d --build
   ```
   Depuis DSM : Container Manager → Projet → Créer → choisir le dossier, le
   `docker-compose.yml` est détecté automatiquement.
4. Ouvrir **`http://<ip-du-nas>:8000`**.

Le conteneur embarque l'API, l'interface **et le planificateur** : rien à
programmer dans le Planificateur de tâches DSM. La base et les CV vivent dans
`./data` sur le NAS (à inclure dans Hyper Backup) ; l'image ne contient aucune
donnée personnelle.

**⚠️ Réseau local uniquement.** L'application n'a aucune authentification (choix
assumé, §10) : ne pas l'exposer via QuickConnect, un reverse proxy DSM ou une
redirection de port sur la box. Pour ne l'ouvrir qu'au NAS lui-même, remplacer
`"8000:8000"` par `"127.0.0.1:8000:8000"` dans `docker-compose.yml`.

**Fonctions IA : deux options**

- *Par défaut* — pas de CLI Claude Code dans le conteneur. Le scan, le
  classement 0-100 expliqué, le digest, l'email, le Kanban et les statistiques
  fonctionnent normalement (le score par règles est déterministe et complet).
  Les boutons IA affichent un message clair indiquant que la CLI est absente.
- *Avec l'IA sur le NAS* — construire avec `AVEC_IA=1`, puis authentifier une
  seule fois la session :
  ```bash
  # dans docker-compose.yml : décommenter le volume ./claude:/root/.claude
  AVEC_IA=1 docker compose up -d --build
  docker exec -it job-finder claude          # suivre le lien de connexion affiché
  ```
  L'authentification est conservée dans `./claude` entre les redémarrages.

**Sur un Raspberry Pi ou un vieux PC recyclé — sans Docker**

Plus léger que Docker sur une petite machine, et c'est une commande :

```bash
git clone https://github.com/Opaland/Job-Finder.git
cd Job-Finder
sudo bash deploiement/installer-linux.sh
```

Le script installe l'environnement Python, construit l'interface, crée `.env`
et enregistre un service systemd : l'application redémarre avec la machine et
le scan de 07:30 tourne dedans. Ensuite :

| | |
|---|---|
| État du service | `systemctl status job-finder` |
| Journal en direct | `journalctl -u job-finder -f` |
| Mise à jour | `git pull && sudo bash deploiement/installer-linux.sh` |
| Arrêt | `sudo systemctl stop job-finder` |

Prérequis : Python 3.11+ et Node (Raspberry Pi OS Bookworm 64 bits et Debian 12
les ont déjà : `sudo apt install -y python3-venv nodejs npm`). Sur un Pi,
préférer un SSD USB à une carte micro-SD : la base est écrite tous les jours et
les cartes s'usent vite.

Une même base ne doit être utilisée que par **une seule instance** : soit le NAS,
soit `start.bat` sur le PC — jamais les deux en même temps sur un dossier
partagé (SQLite ne supporte pas l'accès concurrent via SMB). Pour passer du PC
au NAS, copier `data/jobfinder.db`, ou utiliser Sauvegarde / Restauration dans
l'onglet Sources & réglages.

### 9.3 Les NAS ARM ne peuvent pas héberger l'application

Container Manager (Docker) n'existe **que sur les Synology x86**. Les modèles ARM
— dont le **DS214** (Marvell Armada XP 32 bits, 512 Mo) et les séries « j » /
« play » — ne le proposent pas dans le Centre de paquets, et aucun contournement
fiable n'existe en ARM 32 bits.

Installer Python à la main dessus (Entware) est théoriquement possible mais
déconseillé : 512 Mo de RAM, dépendances compilées introuvables pour cette
architecture, et une maintenance sans fin pour un gain nul par rapport à
l'option 9.1.

En revanche, un tel NAS reste **parfait comme destination de sauvegarde** :
copier `data\jobfinder.db` (ou le fichier produit par le bouton Sauvegarde) vers
un dossier partagé du NAS, manuellement ou via une tâche planifiée.

## 10. Limites connues (assumées)

Relevées en interrogeant les vraies sources, pas déduites du code.

- **Welcome to the Jungle est en panne.** Clé Algolia publique invalide et plus exposée par le site :
  la source remonte un HTTP 403 explicite à chaque scan. Détail et contournement en §3.4.
- **Les descriptions APEC sont tronquées à 283 caractères.** C'est ce que renvoie son service ; la page
  de détail refuse la lecture automatique (401). Le score et l'avis IA lisent donc un résumé. Vérifié sur
  30 offres : la troncature est systématique, ce n'est pas un défaut du connecteur.
- **La section « Pépites » reste vide en pratique.** Le seuil est à 85 et le meilleur score observé sur
  de vraies offres lyonnaises est **82**. Rien n'est cassé — le seuil est simplement plus haut que ce que
  le marché QA lyonnais produit. À arbitrer : abaisser le seuil, ou l'assumer comme une exigence.
- **Un contrat « non précisé » rapporte plus qu'un contrat identifié comme différent** (3/5 contre 2/5).
  Une source qui cache le type de contrat est donc mieux notée qu'une source honnête. Deux codes APEC
  restent d'ailleurs sans libellé faute d'échantillon parlant (10 offres sur ~600).
- **LinkedIn / Indeed** : pas d'accès direct (interdit par leurs CGU et bloqué techniquement) — couverts
  indirectement via JSearch et Adzuna.
- **APEC / HelloWork** : connecteurs best-effort sur les services non officiels des sites ; ils peuvent
  casser sans préavis. Les tests réels (§8) et `python -m app.cli sources` le disent tout de suite.
- Application **mono-utilisateur, 100 % locale**, sans authentification — ne pas l'exposer sur Internet
  en l'état.
