"""Taxonomie QA hiérarchique (referentiel/taxonomie.json, versionnée).

Règles : un thème n'est jamais supprimé (statut « obsolete » + remplace_par), un nouveau
sous-thème est refusé s'il ressemble trop à un thème existant, et chaque changement est
journalisé."""
import json
import re
from datetime import date

from . import chemins, journal
from .textes import jaccard, recouvrement, signature

STATUTS = ("actif", "obsolete")


def charger() -> dict:
    return json.loads(chemins.taxonomie().read_text(encoding="utf-8"))


def _ecrire(t: dict) -> None:
    # Toujours écrire dans la racine de données (la copie livrée sert de modèle initial).
    p = chemins.racine() / "referentiel" / "taxonomie.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(t, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def themes(inclure_obsoletes: bool = True) -> list[dict]:
    return [t for t in charger()["themes"] if inclure_obsoletes or t["statut"] == "actif"]


def theme(code: str) -> dict:
    for t in charger()["themes"]:
        if t["code"] == code:
            return t
    proches = [t["code"] for t in charger()["themes"] if code.lower() in t["code"] or code.lower() in t["libelle"].lower()]
    raise KeyError(f"Thème inconnu : {code}." + (f" Vouliez-vous : {', '.join(proches)} ?" if proches else
                                                  " Voir `themes`."))


def resoudre(code: str) -> str:
    """Code actif correspondant (suit remplace_par pour un thème obsolète)."""
    t, vus = theme(code), set()
    while t["statut"] == "obsolete" and t.get("remplace_par") and t["code"] not in vus:
        vus.add(t["code"])
        t = theme(t["remplace_par"])
    return t["code"]


def chemin(code: str) -> str:
    """« Test management › Risk-Based Testing »."""
    t, parts = theme(code), []
    while t:
        parts.append(t["libelle"])
        t = theme(t["parent"]) if t.get("parent") else None
    return " › ".join(reversed(parts))


def similaires(libelle: str, mots_cles: list[str] | None = None, seuil: float = 0.5) -> list[tuple[float, dict]]:
    sig = signature(" ".join([libelle, *(mots_cles or [])]))
    sig_lib = signature(libelle)
    out = []
    for t in themes():
        st = signature(" ".join([t["libelle"], *t["mots_cles"]]))
        score = max(jaccard(sig_lib, signature(t["libelle"])), recouvrement(sig_lib, st) * 0.9, jaccard(sig, st))
        if score >= seuil:
            out.append((round(score, 2), t))
    return sorted(out, key=lambda x: -x[0])


def proposer(texte: str, n: int = 3) -> list[tuple[float, str]]:
    """Thèmes les plus proches d'un texte (titre + description d'une idée)."""
    sig = signature(texte)
    scores = []
    for t in themes(inclure_obsoletes=False):
        st = signature(" ".join([t["libelle"], *t["mots_cles"]]))
        commun = len(sig & st)
        if commun:
            scores.append((round(commun / (len(sig) ** 0.5 * len(st) ** 0.5), 3), t["code"]))
    return sorted(scores, reverse=True)[:n]


def ajouter(code: str, libelle: str, parent: str | None, mots_cles: list[str], motif: str,
            forcer: bool = False) -> dict:
    t = charger()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", code):
        raise ValueError("Code de thème invalide : minuscules, chiffres et tirets (ex. « contract-testing »).")
    if any(x["code"] == code for x in t["themes"]):
        raise ValueError(f"Le thème « {code} » existe déjà.")
    if parent:
        theme(parent)
    if not motif:
        raise ValueError("Indiquer le motif (--motif) : pourquoi aucun thème existant ne convient.")
    proches = similaires(libelle, mots_cles)
    if proches and not forcer:
        liste = "; ".join(f"{p['code']} « {p['libelle']} » ({s:.0%})" for s, p in proches[:3])
        raise ValueError(f"Thème redondant probable avec : {liste}. Rattacher l'idée à ce thème, ou relancer "
                         "avec --forcer si la distinction est réelle (le motif sera journalisé).")
    nouveau = {"code": code, "parent": parent, "libelle": libelle, "mots_cles": mots_cles or [libelle],
               "statut": "actif", "cree_le": date.today().isoformat()}
    t["themes"].append(nouveau)
    t["version"] = t.get("version", 1) + 1
    _ecrire(t)
    journal.noter("theme_ajoute", code, {"libelle": libelle, "parent": parent, "forcer": forcer}, motif)
    return nouveau


def rendre_obsolete(code: str, remplace_par: str | None, motif: str) -> dict:
    t = charger()
    cible = next((x for x in t["themes"] if x["code"] == code), None)
    if not cible:
        raise KeyError(f"Thème inconnu : {code}.")
    if remplace_par:
        theme(remplace_par)
    cible.update(statut="obsolete", remplace_par=remplace_par, obsolete_le=date.today().isoformat())
    t["version"] = t.get("version", 1) + 1
    _ecrire(t)
    journal.noter("theme_obsolete", code, {"remplace_par": remplace_par}, motif)
    return cible


def arbre() -> list[tuple[int, dict]]:
    tous = themes()
    enfants: dict = {}
    for t in tous:
        enfants.setdefault(t.get("parent"), []).append(t)
    out = []

    def descendre(parent, niveau):
        for t in enfants.get(parent, []):
            out.append((niveau, t))
            descendre(t["code"], niveau + 1)
    descendre(None, 0)
    return out
