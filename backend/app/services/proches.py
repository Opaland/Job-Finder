"""Offres très proches : une même mission republiée par plusieurs intermédiaires.

Issue #43 : certaines missions (ESN, cabinets de recrutement) sont relayées
mot pour mot par plusieurs sources, parfois avec le nom de l'agrégateur en
guise d'entreprise. Ce n'est pas un défaut de dédoublonnage à corriger
aveuglément (candidater via plusieurs cabinets pour la même mission est
parfois une vraie stratégie) — juste un signal que l'app ne donnait nulle
part. `find_twin()` (services/scan.py) reste le seul mécanisme de fusion ;
ce module ne fusionne, ne ferme et ne modifie jamais rien.
"""
from __future__ import annotations

import difflib

from sqlalchemy.orm import Session, load_only

from ..models import STATUTS_CLOS, Offer

SEUIL_SIMILARITE = 0.85
# Sous ce seuil de caractères, la comparaison n'est pas fiable (même logique
# que _DESCRIPTION_TROP_COURTE, services/scoring.py) : deux descriptions
# HelloWork de 18 caractères ("CDI · Lyon - 69") se ressembleraient toujours.
DESCRIPTION_MIN = 50


def _normalise(texte: str | None) -> str:
    return " ".join((texte or "").lower().split())


def offres_proches(db: Session, offer: Offer) -> list[dict]:
    """Autres offres ouvertes dont la description est quasi identique à celle-ci."""
    description = _normalise(offer.description)
    if len(description) < DESCRIPTION_MIN:
        return []

    autres = (
        db.query(Offer)
        .options(load_only(Offer.id, Offer.title, Offer.company, Offer.source, Offer.url, Offer.status, Offer.description))
        .filter(Offer.id != offer.id, Offer.status.notin_(STATUTS_CLOS))
        .all()
    )

    proches = []
    for autre in autres:
        autre_desc = _normalise(autre.description)
        if len(autre_desc) < DESCRIPTION_MIN:
            continue
        ratio = difflib.SequenceMatcher(None, description, autre_desc).ratio()
        if ratio >= SEUIL_SIMILARITE:
            proches.append({
                "id": autre.id,
                "title": autre.title,
                "company": autre.company,
                "source": autre.source,
                "url": autre.url,
                "ratio": round(ratio, 2),
            })
    proches.sort(key=lambda p: -p["ratio"])
    return proches
