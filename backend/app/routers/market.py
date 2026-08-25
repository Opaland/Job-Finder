"""Analyse du marché QA à partir des offres collectées (aucune source externe)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.marche import competences_demandees, fraicheur, manques_recurrents, qui_recrute

router = APIRouter(prefix="/api/market", tags=["marché"])


@router.get("/skills")
def skills(limit: int = 25, db: Session = Depends(get_db)):
    """Compétences les plus demandées, et lesquelles manquent au CV."""
    return competences_demandees(db, limite=min(limit, 60))


@router.get("/companies")
def companies(limit: int = 20, db: Session = Depends(get_db)):
    """Entreprises qui recrutent le plus et salaires observés par intitulé."""
    return qui_recrute(db, limite=min(limit, 60))


@router.get("/gaps")
def gaps(db: Session = Depends(get_db)):
    """Manques revenant dans les analyses d'écart générées par l'IA."""
    return manques_recurrents(db)


@router.get("/freshness")
def freshness(db: Session = Depends(get_db)):
    """Ancienneté des offres ouvertes et annonces republiées en boucle."""
    return fraicheur(db)
