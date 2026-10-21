"""Évaluation de la recherche locale sur un jeu de questions annotées (eval/requetes.json).

Chaque question indique le document et la section (ou la page) où se trouve la réponse.
Le rappel@k mesure si ce passage figure dans les k premiers résultats. C'est le critère
qui décidera d'ajouter (ou non) une recherche sémantique : elle ne se justifie que si
des questions réalistes échouent malgré le thésaurus."""
import json

from . import bibliotheque, chemins, recherche


def _dans_section(trouvee: str | None, attendue: str) -> bool:
    """« 4.2.1 » est dans « 4.2 » ; « 4.20 » ne l'est pas ; section vide = tout le document."""
    return not attendue or trouvee == attendue or (trouvee or "").startswith(attendue + ".")


def evaluer(k: int = 5, controle: bool | None = None) -> dict:
    """controle=None : tout le jeu ; True : seulement les questions de contrôle (jamais
    utilisées pour régler le moteur) ; False : seulement le jeu de réglage."""
    cas = json.loads((chemins.CODE / "eval" / "requetes.json").read_text(encoding="utf-8"))["cas"]
    cx = bibliotheque.connecter()
    details, trouves, rr, ignorees = [], 0, 0.0, 0
    try:
        codes = {r["code"] for r in cx.execute("SELECT DISTINCT code FROM documents WHERE statut_version='courant'")}
        for c in cas:
            if controle is not None and bool(c.get("controle")) != controle:
                continue
            attendus = [a for a in c["attendus"] if a["code"] in codes]
            if not attendus:
                ignorees += 1
                continue
            res = recherche.chercher(c["requete"], n=k, cx=cx, **c.get("filtres", {}))["resultats"]
            rang = next((i for i, r in enumerate(res, 1) if any(
                r["code"] == a["code"] and _dans_section(r["section_num"], a.get("section", ""))
                for a in attendus)), None)
            trouves += rang is not None
            rr += 1 / rang if rang else 0
            details.append({"requete": c["requete"],
                            "attendu": " ou ".join(f"{a['code']} §{a.get('section') or '*'}" for a in attendus),
                            "trouve": rang is not None, "rang": rang})
    finally:
        cx.close()
    total = len(details)
    return {"details": details, "trouves": trouves, "total": total, "ignorees": ignorees,
            "rappel": trouves / total if total else 0.0, "mrr": rr / total if total else 0.0}
