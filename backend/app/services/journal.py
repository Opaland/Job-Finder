"""Journal d'activité : enregistrement best-effort des événements de l'application."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..models import ActivityLog

logger = logging.getLogger("jobfinder.journal")

# Types d'événements connus (libellés côté frontend).
KINDS = ["scan", "statut", "ia", "ajout", "cv", "restauration"]


def log_event(db: Session, kind: str, message: str, offer_id: int | None = None) -> None:
    """N'échoue jamais : le journal ne doit pas casser l'action qu'il trace."""
    try:
        db.add(ActivityLog(kind=kind, message=message[:500], offer_id=offer_id))
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Écriture du journal impossible")
        db.rollback()
