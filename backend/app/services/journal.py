"""Journal d'activité : enregistrement best-effort des événements de l'application."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..models import ActivityLog

logger = logging.getLogger("jobfinder.journal")

# Types d'événements connus (libellés côté frontend).
KINDS = ["scan", "statut", "ia", "ajout", "cv", "restauration"]


def log_event(db: Session, kind: str, message: str, offer_id: int | None = None) -> None:
    """N'échoue jamais et ne touche jamais à la transaction de l'appelant.

    L'entrée est écrite dans une session indépendante (même moteur que `db`) :
    un échec d'écriture du journal ne peut ni annuler ni committer le travail
    en cours de l'action tracée. À appeler de préférence APRÈS le commit de
    l'action, pour ne pas croiser un verrou d'écriture SQLite.
    """
    try:
        with Session(bind=db.get_bind()) as journal_session:
            journal_session.add(ActivityLog(kind=kind, message=message[:500], offer_id=offer_id))
            journal_session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Écriture du journal impossible")
