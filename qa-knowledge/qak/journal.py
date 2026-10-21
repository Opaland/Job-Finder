"""Journal append-only des modifications de la base de connaissances et de la taxonomie
(connaissances/journal.jsonl, versionné) : qui a changé quoi, quand et pourquoi."""
import json
from datetime import datetime

from . import chemins


def noter(action: str, cible: str, details: dict | None = None, motif: str | None = None) -> dict:
    entree = {"horodatage": datetime.now().isoformat(timespec="seconds"), "action": action, "cible": cible}
    if motif:
        entree["motif"] = motif
    if details:
        entree["details"] = details
    p = chemins.journal_jsonl()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")
    return entree


def lire(cible: str | None = None, limite: int = 30) -> list[dict]:
    p = chemins.journal_jsonl()
    if not p.exists():
        return []
    lignes = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if cible:
        lignes = [l for l in lignes if l["cible"] == cible or cible in json.dumps(l.get("details", {}))]
    return lignes[-limite:]
