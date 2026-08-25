"""Initialisation de la base : crée le profil de Cédric au premier lancement."""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from ..config import SEED_DIR
from ..models import Profile, local_now
from .cv_parser import extract_skills

logger = logging.getLogger("jobfinder.seed")


def ensure_profile(db: Session) -> Profile:
    profile = db.get(Profile, 1)
    if profile:
        return profile

    seed_path = SEED_DIR / "profile_seed.json"
    letter_path = SEED_DIR / "lettre_type.txt"
    data: dict = {}
    if seed_path.exists():
        data = json.loads(seed_path.read_text(encoding="utf-8"))

    cv_text = data.get("cv_text", "")
    profile = Profile(
        id=1,
        full_name=data.get("full_name", ""),
        email=data.get("email", ""),
        cv_filename=data.get("cv_filename", ""),
        cv_text=cv_text,
        cv_updated_at=local_now() if cv_text else None,
        letter_template=letter_path.read_text(encoding="utf-8") if letter_path.exists() else "",
        target_titles=data.get("target_titles", []),
        skills=extract_skills(cv_text) if cv_text else [],
        location_label=data.get("location_label", "Lyon et alentours"),
        location_keywords=data.get("location_keywords", []),
        radius_km=data.get("radius_km", 40),
        remote_ok=data.get("remote_ok", True),
        contracts=data.get("contracts", ["CDI"]),
        min_salary=data.get("min_salary"),
        sector_bonus=data.get("sector_bonus", []),
        excluded_keywords=data.get("excluded_keywords", []),
        scan_hour=data.get("scan_hour", "07:30"),
        sources_enabled=data.get("sources_enabled", {}),
        search_queries=data.get("search_queries"),
    )
    db.add(profile)
    db.commit()
    logger.info("Profil initialisé depuis le seed (%s)", profile.full_name)
    return profile
