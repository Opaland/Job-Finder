---
name: verif
description: Vérification complète du projet Job Finder (syntaxe, tests backend, build frontend, build démo) via scripts/verif.sh — à lancer avant tout commit/push ou quand l'utilisateur demande « vérifie ».
---

Lance la vérification complète du projet et rends compte en français.

1. Exécute `bash scripts/verif.sh` depuis la racine du dépôt (sous Windows :
   `scripts\verif.bat`). Ajoute `--rapide` uniquement si l'utilisateur veut un
   contrôle éclair (syntaxe + tests, sans les builds).
2. Si tout est vert : dis-le en une phrase, avec le nombre de tests passés.
3. Si une étape échoue : montre les lignes d'erreur utiles, identifie la cause
   dans le code (pas seulement le symptôme), corrige, puis RELANCE le script
   jusqu'au vert. Ne jamais conclure sur un état rouge sans explication et
   proposition de correction.
4. Ne pousse rien : cette skill vérifie, elle ne publie pas.
