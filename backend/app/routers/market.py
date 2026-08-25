"""Analyse du marché QA à partir des offres collectées (aucune source externe)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.marche import competences_demandees

router = APIRouter(prefix="/api/market", tags=["marché"])


@router.get("/skills")
def skills(limit: int = 25, db: Session = Depends(get_db)):
    """Compétences les plus demandées, et lesquelles manquent au CV."""
    return competences_demandees(db, limite=min(limit, 60))
