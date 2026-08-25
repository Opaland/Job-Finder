from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import DATA_DIR
from ..database import get_db
from ..models import Profile, local_now
from ..schemas import ProfileOut, ProfileUpdate
from ..services import scheduler
from ..services.cv_parser import extract_skills, extract_text
from ..services.journal import log_event
from ..services.scan import rescore_all

router = APIRouter(prefix="/api/profile", tags=["profil"])


@router.get("", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    return db.get(Profile, 1)


@router.put("", response_model=ProfileOut)
def update_profile(update: ProfileUpdate, db: Session = Depends(get_db)):
    profile = db.get(Profile, 1)
    changed_scoring = False
    scoring_fields = {
        "target_titles", "skills", "location_keywords", "radius_km", "remote_ok",
        "contracts", "sector_bonus", "excluded_keywords", "scoring_weights",
    }
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
        if field in scoring_fields:
            changed_scoring = True
        if field == "scan_hour" and value:
            scheduler.reschedule(value)
    db.commit()
    if changed_scoring:
        rescore_all(db)
    return profile


@router.post("/cv", response_model=ProfileOut)
async def upload_cv(file: UploadFile, db: Session = Depends(get_db)):
    """Importe un nouveau CV (PDF, DOCX ou TXT), extrait le texte et les compétences."""
    content = await file.read()
    if not content:
        raise HTTPException(400, "Fichier vide")
    try:
        text = extract_text(file.filename or "cv.txt", content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Impossible de lire ce fichier : {exc}")
    if len(text.strip()) < 100:
        raise HTTPException(400, "Le texte extrait est trop court — le fichier est-il bien ton CV ?")

    saved = DATA_DIR / "uploads" / (file.filename or "cv.txt")
    saved.write_bytes(content)

    profile = db.get(Profile, 1)
    profile.cv_filename = file.filename or "cv.txt"
    profile.cv_text = text
    profile.cv_updated_at = local_now()
    profile.skills = extract_skills(text)
    db.commit()
    rescore_all(db)
    log_event(db, "cv", f"CV importé ({profile.cv_filename}) : {len(profile.skills)} compétences détectées, scores recalculés.")
    return profile


@router.post("/rescore")
def rescore(db: Session = Depends(get_db)):
    """Recalcule le score de toutes les offres avec le profil actuel."""
    count = rescore_all(db)
    return {"rescored": count}


@router.get("/scoring-defaults")
def scoring_defaults():
    """Pondérations par défaut du moteur de score (source unique : services/scoring.py)."""
    from ..services.scoring import DEFAULT_WEIGHTS

    return DEFAULT_WEIGHTS
