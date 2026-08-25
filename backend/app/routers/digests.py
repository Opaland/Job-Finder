from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Digest
from ..schemas import DigestOut
from ..services.digest import build_digest, digest_html, send_digest_email
from ..services.emailer import send_email, smtp_configured

router = APIRouter(prefix="/api/digests", tags=["digest"])


@router.get("/today", response_model=DigestOut)
def today(db: Session = Depends(get_db)):
    """Le point du jour (construit à la volée s'il n'existe pas encore)."""
    return build_digest(db)


@router.get("", response_model=list[DigestOut])
def history(limit: int = 14, db: Session = Depends(get_db)):
    return db.query(Digest).order_by(Digest.id.desc()).limit(min(limit, 60)).all()


@router.post("/send-email")
def send_now(db: Session = Depends(get_db)):
    """Reconstruit le digest du jour et l'envoie par email immédiatement."""
    if not smtp_configured():
        raise HTTPException(400, "SMTP non configuré : renseigne SMTP_USER, SMTP_PASSWORD et DIGEST_EMAIL_TO dans .env")
    digest = build_digest(db)
    if not send_digest_email(db, digest):
        raise HTTPException(502, "L'envoi a échoué — vérifie tes identifiants SMTP (voir logs)")
    return {"sent": True}


@router.post("/test-email")
def test_email():
    """Envoie un email de test pour valider la configuration SMTP."""
    if not smtp_configured():
        raise HTTPException(400, "SMTP non configuré : renseigne SMTP_USER, SMTP_PASSWORD et DIGEST_EMAIL_TO dans .env")
    try:
        send_email(
            "Job Finder — email de test",
            "<p>La configuration email de Job Finder fonctionne ✔</p>",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Échec de l'envoi : {exc}")
    return {"sent": True}


@router.post("/reminder")
def send_reminder(db: Session = Depends(get_db)):
    """Envoie tout de suite le rappel des échéances de demain (test manuel)."""
    from ..services.rappels import echeances_de_demain, envoyer_rappel

    echeances = echeances_de_demain(db)
    envoye = envoyer_rappel(db)
    return {"envoye": envoye, **echeances}


@router.post("/weekly-review")
def weekly_review(db: Session = Depends(get_db)):
    """Bilan de la semaine commenté par l'IA locale (chiffres + conseils)."""
    from ..models import Profile
    from ..services.claude_ai import ai_bilan_hebdo, cli_available
    from ..services.digest import resume_semaine

    resume = resume_semaine(db)
    if not cli_available():
        raise HTTPException(
            503,
            "CLI Claude Code introuvable sur ce poste : les chiffres de la semaine sont "
            "affichés, mais le commentaire nécessite la commande « claude ».",
        )
    profile = db.get(Profile, 1)
    texte = ai_bilan_hebdo(resume, profile.cv_text if profile else "")
    if not texte:
        raise HTTPException(502, "La génération a échoué (voir les logs). Réessaie dans un instant.")
    return {"resume": resume, "bilan": texte}


@router.get("/weekly-summary")
def weekly_summary(db: Session = Depends(get_db)):
    """Chiffres de la semaine, sans IA."""
    from ..services.digest import resume_semaine

    return resume_semaine(db)
