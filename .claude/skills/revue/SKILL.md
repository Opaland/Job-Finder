---
name: revue
description: Revue de code Job Finder avec la check-list du projet — lance l'agent revue-jobfinder sur le diff courant (ou la cible donnée) puis applique les corrections retenues.
---

Revue de code selon les règles du projet, puis application des correctifs.

1. Détermine la cible : l'argument fourni (plage de commits, fichiers), sinon
   `git diff HEAD` s'il y a du travail en cours, sinon le dernier commit.
2. Lance l'agent `revue-jobfinder` (via l'outil Agent) avec le diff et la
   cible ; en parallèle, tu peux exécuter `python scripts/revue_ia.py` pour un
   second avis via la CLI claude locale quand elle est disponible.
3. Déduplique les constats, écarte les faux positifs (en le notant), applique
   les corrections qui ne changent pas le comportement voulu.
4. Termine par `bash scripts/verif.sh --rapide` pour prouver la non-régression,
   puis résume en français : corrigé / écarté et pourquoi.
