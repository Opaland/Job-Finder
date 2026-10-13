from pathlib import Path

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

# Colonnes NOT NULL en base (models.Profile) dont le schéma Pydantic accepte
# pourtant None, pour distinguer "non fourni" (absent de la requête) de "vidé"
# (envoyé à null) via exclude_unset=True. Un null explicite sur l'un de ces
# champs plantait auparavant toute la requête en 500 (IntegrityError SQLite)
# et perdait AVEC elle les autres champs valides de la même requête — la
# transaction entière échouait. `saved_searches`, également NOT NULL, n'a pas
# besoin d'y être : _nettoyer_recherches(None) renvoie déjà [], jamais None.
CHAMPS_OBLIGATOIRES = {
    "full_name", "email", "letter_template", "target_titles", "skills",
    "location_label", "location_keywords", "radius_km", "remote_ok",
    "contracts", "sector_bonus", "excluded_keywords", "scan_hour",
    "sources_enabled", "weekly_goal",
}


@router.get("", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    return db.get(Profile, 1)


# Filtres autorisés dans une recherche sauvegardée : ceux de la liste d'offres.
FILTRES_RECHERCHE = {"status", "source", "min_score", "search", "company", "favorite", "remote", "sort"}
MAX_RECHERCHES = 20


def _nettoyer_recherches(recherches: list | None) -> list:
    """Garde des recherches exploitables : un nom, des filtres connus, pas de doublon."""
    propres, noms_vus = [], set()
    for brute in recherches or []:
        if not isinstance(brute, dict):
            continue
        nom = str(brute.get("nom", "")).strip()[:60]
        if not nom or nom.lower() in noms_vus:
            continue
        filtres = brute.get("filtres") or {}
        if not isinstance(filtres, dict):
            continue
        noms_vus.add(nom.lower())
        propres.append({
            "nom": nom,
            "filtres": {
                cle: str(valeur)[:120]
                for cle, valeur in filtres.items()
                if cle in FILTRES_RECHERCHE and str(valeur).strip()
            },
        })
    return propres[:MAX_RECHERCHES]


@router.put("", response_model=ProfileOut)
def update_profile(update: ProfileUpdate, db: Session = Depends(get_db)):
    profile = db.get(Profile, 1)
    champs = update.model_dump(exclude_unset=True)
    vides = sorted(f for f in CHAMPS_OBLIGATOIRES if f in champs and champs[f] is None)
    if vides:
        raise HTTPException(
            400,
            f"Champ(s) obligatoire(s) envoyé(s) vide(s) : {', '.join(vides)}. "
            "Aucune modification n'a été enregistrée.",
        )
    changed_scoring = False
    scoring_fields = {
        "target_titles", "skills", "location_keywords", "radius_km", "remote_ok",
        "contracts", "sector_bonus", "excluded_keywords", "scoring_weights",
    }
    for field, value in champs.items():
        if field == "saved_searches":
            value = _nettoyer_recherches(value)
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

    # Seul le nom de base est retenu : un fichier nomme « ../jobfinder.db »
    # ecrasait la base, et « dossier/cv.txt » faisait une 500. Les deux
    # separateurs sont neutralises : la meme image Docker tourne sous Linux,
    # ou Path() ne reconnait pas l'antislash de Windows.
    nom = Path((file.filename or "cv.txt").replace("\\", "/")).name or "cv.txt"
    saved = DATA_DIR / "uploads" / nom
    saved.write_bytes(content)

    profile = db.get(Profile, 1)
    profile.cv_filename = nom
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
