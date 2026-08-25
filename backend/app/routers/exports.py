"""Exports : justificatif de recherche d'emploi, échanges CSV."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import local_now
from ..services.justificatif import justificatif_pdf

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/justificatif.pdf")
def justificatif(
    depuis: date | None = None,
    jusqu_a: date | None = None,
    db: Session = Depends(get_db),
):
    """Justificatif PDF des démarches (par défaut : les 30 derniers jours)."""
    fin = jusqu_a or local_now().date()
    debut = depuis or (fin - timedelta(days=30))
    if debut > fin:
        raise HTTPException(400, "La date de début doit précéder la date de fin.")

    contenu = justificatif_pdf(db, debut, fin)
    nom = f"justificatif_recherche_{debut:%Y-%m-%d}_{fin:%Y-%m-%d}.pdf"
    return Response(
        content=contenu,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )
