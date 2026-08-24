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

> ⚠️ Sans clés API, seules les sources « sans clé » (Welcome to the Jungle, APEC, HelloWork) sont
> interrogées. Pour une couverture complète, configure les clés gratuites — voir section 3 (≈ 10 minutes).

## 2. Ce que fait l'application

| Fonction | Détail |
|---|---|
| **Scan multi-sites** | France Travail, Adzuna, JSearch (LinkedIn/Indeed via Google for Jobs), Welcome to the Jungle, APEC, HelloWork |
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
| **Pépites & objectif** | Offres score ≥ 85 mises en avant partout ; objectif de candidatures hebdomadaire avec jauge |
| **Personnalisation** | Pondérations du score réglables, requêtes de scan configurables, mode sombre |
| **Données** | Enrichissement de description depuis le site d'origine, export Excel du suivi, sauvegarde et restauration de la base en un clic, migration automatique du schéma |
| **Notes & favoris** | Notes libres, favoris ★, historique des statuts par offre |

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

- **WTTJ** : si la source tombe en erreur 4xx, la clé publique du site a changé. Ouvre
  welcometothejungle.com → F12 → onglet Réseau → cherche une requête « algolia » → copie l'en-tête
  `x-algolia-api-key` → colle-la dans `.env` (`WTTJ_ALGOLIA_API_KEY=`).
- **APEC / HelloWork** : rien à configurer. En cas de panne durable, demande à Claude Code de mettre à
  jour le connecteur (`backend/app/connectors/apec.py` ou `hellowork.py`).

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
│   └── tests/                  pytest (scoring, dédoublonnage, statuts)
└── frontend/                   React + Vite (tableau de bord, offres, profil, sources)
```

Lancer les tests : `cd backend && venv\Scripts\python -m pytest tests/ -q`
Mode développement interface : `cd frontend && npm run dev` (proxy vers le backend sur :8000).

## 8. Limites connues (assumées)

- **LinkedIn / Indeed** : pas d'accès direct (interdit par leurs CGU et bloqué techniquement) — couverts
  indirectement via JSearch et Adzuna.
- **WTTJ / APEC / HelloWork** : connecteurs best-effort sur les services non officiels des sites ; ils
  peuvent casser sans préavis (l'erreur est alors visible dans Sources & réglages).
- Application **mono-utilisateur, 100 % locale**, sans authentification — ne pas l'exposer sur Internet
  en l'état.
