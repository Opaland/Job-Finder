"""Entretiens prévus dans une fenêtre de dates.

Sprint 49 : la même boucle « offre non close → entretiens → celui qui tombe
dans la fenêtre » existait séparément dans `digest.py` (fenêtre glissante de
plusieurs jours) et `rappels.py` (demain seulement).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session, load_only

from ..models import STATUTS_CLOS, Offer
from .textutils import parse_iso_dt


def offres_avec_interview_dans(
    db: Session, debut: datetime, fin: datetime, *colonnes_en_plus
) -> list[tuple[Offer, dict, datetime]]:
    """(offre, entretien, date) pour chaque entretien prévu dans [debut, fin].

    Une offre refusée ou fermée n'en annonce plus. `colonnes_en_plus` étend le
    chargement partiel (toujours id/status/interviews) aux colonnes dont
    l'appelant a besoin pour mettre en forme son résultat.
    """
    resultat = []
    offres = (
        db.query(Offer)
        .options(load_only(Offer.id, Offer.status, Offer.interviews, *colonnes_en_plus))
        .filter(Offer.status.notin_(STATUTS_CLOS))
        .all()
    )
    for offer in offres:
        for entretien in offer.interviews or []:
            quand = parse_iso_dt(entretien.get("date"))
            if quand is not None and debut <= quand <= fin:
                resultat.append((offer, entretien, quand))
    return resultat
