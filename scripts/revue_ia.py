"""Revue de code par IA via la session locale Claude Code (CLI `claude`).

Envoie le diff courant à Claude avec la check-list du projet et affiche les
constats en français. Aucune clé API : c'est la même session locale que l'appli.

Usage (depuis la racine du dépôt) :
    python scripts/revue_ia.py              # diff du travail en cours (sinon dernier commit)
    python scripts/revue_ia.py HEAD~3       # diff depuis un commit donné
Windows : backend\\venv\\Scripts\\python scripts\\revue_ia.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

CHECKLIST = """Check-list spécifique Job Finder (en plus des bugs classiques) :
- Dédoublonnage : toute logique « même offre ? » doit passer par find_twin (services/scan.py), jamais être réécrite.
- Un scan ne ferme, ne supprime ni ne change JAMAIS le statut d'une offre (still_online=False au maximum).
- Heures : toujours local_now() (naïf, Europe/Paris) — jamais datetime.utcnow ni un mélange aware/naïf.
- Scoring : toute modification de score passe par rescore_offer ; les groupes de statuts viennent de models.py (STATUTS_*).
- Connecteurs : fetch() ne lève jamais (erreurs dans result.errors) ; dates via parse_published (connectors/base.py).
- Messages d'erreur API : phrases françaises actionnables (affichées telles quelles dans l'UI).
- Frontend : libellés/statuts/couleurs importés d'api.js (une seule source) ; téléchargements via downloadFile ; échéances via actionDue.
- Toute nouvelle route API doit être simulée dans demoApi.js ou y renvoyer « disponible uniquement dans l'appli locale ».
- Requêtes SQL : pas de requête dans une boucle (N+1) ; ne pas charger les colonnes lourdes (description, lettres) inutilement."""


def _git(*args: str, codes_ok: tuple[int, ...] = (0,)) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    if out.returncode not in codes_ok:
        print(f"git {' '.join(args)} a échoué : {(out.stderr or '').strip()[:200]}")
        return ""
    return out.stdout


def git_diff(depuis: str | None) -> tuple[str, str]:
    """Diff à relire + description de ce qui a été relu (pour l'afficher)."""
    if depuis:
        return _git("diff", f"{depuis}..HEAD").strip(), f"diff {depuis}..HEAD"

    # Travail en cours : fichiers suivis modifiés + fichiers nouveaux (non suivis),
    # que `git diff` ignore complètement.
    morceaux = [_git("diff", "HEAD")]
    nouveaux = [f for f in _git("ls-files", "--others", "--exclude-standard").splitlines() if f]
    for fichier in nouveaux:
        # --no-index renvoie 1 dès qu'il y a des différences : c'est le cas normal ici.
        morceaux.append(_git("diff", "--no-index", "--", os.devnull, fichier, codes_ok=(0, 1)))
    diff = "\n".join(m for m in morceaux if m.strip()).strip()
    if diff:
        detail = "travail en cours"
        if nouveaux:
            detail += f" ({len(nouveaux)} fichier(s) nouveau(x) inclus)"
        return diff, detail

    # Rien en cours : on relit le dernier commit, et on le dit.
    return _git("diff", "HEAD~1..HEAD").strip(), "dernier commit (rien en cours)"


def main() -> int:
    exe = shutil.which("claude")
    if exe is None:
        print("CLI Claude Code introuvable : ouvre un terminal où la commande « claude » fonctionne,")
        print("ou fais la revue à la main avec la check-list de .claude/rules/qualite.md.")
        return 1

    diff, quoi = git_diff(sys.argv[1] if len(sys.argv) > 1 else None)
    if not diff:
        print("Aucun diff à revoir.")
        return 0
    if len(diff) > 150_000:
        diff = diff[:150_000] + "\n[... diff tronqué pour la revue ...]"

    prompt = f"""Tu es relecteur de code pour Job Finder (FastAPI + SQLite + React, application locale mono-utilisateur, tout en français).

{CHECKLIST}

Passe en revue ce diff. Réponds UNIQUEMENT en JSON : une liste d'objets
{{"fichier": "...", "ligne": N, "gravite": "bloquant|important|mineur", "constat": "une phrase en français", "correction": "la piste de correction"}}.
Maximum 10 constats, les plus graves d'abord. Si le diff est propre : [].

DIFF :
{diff}"""

    print(f"Revue de {quoi} via ta session Claude locale…")
    try:
        # Prompt envoyé sur l'entrée standard : en argument, Windows plafonne la
        # ligne de commande à ~32 000 caractères (un diff moyen la dépasse).
        proc = subprocess.run(
            [exe, "-p", "--output-format", "json"],
            input=prompt,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
        )
    except subprocess.TimeoutExpired:
        print("La revue a dépassé 10 minutes — réessaie sur un diff plus petit (ex. HEAD~1).")
        return 1
    except OSError as exc:
        print(f"Impossible de lancer la CLI claude ({exc}). Vérifie que « claude » fonctionne dans un terminal.")
        return 1
    if proc.returncode != 0:
        print("La CLI claude a échoué :", (proc.stderr or "").strip()[:400])
        return 1

    try:
        result = json.loads(proc.stdout).get("result", "")
        start, end = result.find("["), result.rfind("]")
        constats = json.loads(result[start:end + 1]) if start != -1 else []
    except (json.JSONDecodeError, ValueError):
        print("Réponse inattendue de Claude — la voici brute :\n", proc.stdout[:2000])
        return 1

    if not constats:
        print("✔ Aucun constat : le diff respecte la check-list du projet.")
        return 0

    print(f"\n{len(constats)} constat(s) :\n")
    for c in constats:
        print(f"[{c.get('gravite', '?').upper()}] {c.get('fichier', '?')}:{c.get('ligne', '?')}")
        print(f"  {c.get('constat', '')}")
        if c.get("correction"):
            print(f"  → {c['correction']}")
        print()
    bloquants = sum(1 for c in constats if c.get("gravite") == "bloquant")
    return 2 if bloquants else 0


if __name__ == "__main__":
    sys.exit(main())
