import io
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OFFER_STATUSES, Offer, Profile, utcnow
from ..schemas import OfferDetail, OfferSummary, OfferUpdate
from ..services.claude_ai import ai_cover_letter, cli_available
from ..services.enrich import fetch_full_description

router = APIRouter(prefix="/api/offers", tags=["offres"])


@router.get("", response_model=dict)
def list_offers(
    status: str | None = None,
    source: str | None = None,
    min_score: float | None = None,
    search: str | None = None,
    favorite: bool | None = None,
    remote: bool | None = None,
    sort: str = "score",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Offer)
    if status:
        statuses = [s for s in status.split(",") if s in OFFER_STATUSES]
        if statuses:
            query = query.filter(Offer.status.in_(statuses))
    if source:
        query = query.filter(Offer.source == source)
    if min_score is not None:
        query = query.filter(Offer.final_score >= min_score)
    if favorite is not None:
        query = query.filter(Offer.favorite.is_(favorite))
    if remote is not None:
        query = query.filter(Offer.remote.is_(remote))
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(Offer.title.ilike(like), Offer.company.ilike(like), Offer.description.ilike(like))
        )

    total = query.count()
    if sort == "date":
        query = query.order_by(Offer.collected_at.desc(), Offer.final_score.desc())
    else:
        query = query.order_by(Offer.final_score.desc(), Offer.collected_at.desc())
    offers = query.offset(offset).limit(min(limit, 500)).all()
    return {
        "total": total,
        "items": [OfferSummary.model_validate(o).model_dump() for o in offers],
    }


@router.get("/export.xlsx")
def export_xlsx(db: Session = Depends(get_db)):
    """Exporte toutes les offres suivies dans un classeur Excel (tri par score)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    status_labels = {
        "nouvelle": "Nouvelle", "vue": "Vue", "a_postuler": "À postuler",
        "postulee": "Postulée", "relancee": "Relancée", "entretien": "Entretien",
        "refusee": "Refusée", "fermee": "Fermée",
    }
    headers = [
        ("Score", 8), ("Titre", 42), ("Entreprise", 24), ("Lieu", 20), ("Contrat", 14),
        ("Salaire", 16), ("Télétravail", 11), ("Statut", 12), ("Favori", 8),
        ("Source", 16), ("Publiée le", 12), ("Collectée le", 12), ("Avis IA", 40),
        ("Notes", 40), ("Lien", 45),
    ]

    wb = Workbook()
    ws = wb.active
    ws.title = "Offres"
    header_fill = PatternFill("solid", fgColor="10192B")
    for col, (label, width) in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"

    offers = db.query(Offer).order_by(Offer.final_score.desc()).all()
    for row, o in enumerate(offers, start=2):
        values = [
            round(o.final_score), o.title, o.company, o.location, o.contract_type,
            o.salary_text, "Oui" if o.remote else "", status_labels.get(o.status, o.status),
            "★" if o.favorite else "",
            o.source, o.published_at.strftime("%d/%m/%Y") if o.published_at else "",
            o.collected_at.strftime("%d/%m/%Y"), o.ai_reason, o.notes, o.url,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(vertical="top", wrap_text=col in (2, 13, 14))
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(len(offers) + 1, 2)}"

    buffer = io.BytesIO()
    wb.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="job_finder_offres.xlsx"'},
    )



@router.get("/{offer_id}", response_model=OfferDetail)
def get_offer(offer_id: int, db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offre introuvable")
    return offer


@router.patch("/{offer_id}", response_model=OfferDetail)
def update_offer(offer_id: int, update: OfferUpdate, db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offre introuvable")

    if update.status is not None:
        if update.status not in OFFER_STATUSES:
            raise HTTPException(400, f"Statut inconnu : {update.status}")
        if update.status != offer.status:
            history = list(offer.status_history or [])
            history.append({"status": update.status, "date": utcnow().isoformat(), "par": "utilisateur"})
            offer.status_history = history
            offer.status = update.status
    if update.notes is not None:
        offer.notes = update.notes
    if update.favorite is not None:
        offer.favorite = update.favorite
    if update.cover_letter is not None:
        offer.cover_letter = update.cover_letter

    db.commit()
    return offer


@router.post("/{offer_id}/letter", response_model=OfferDetail)
def generate_letter(offer_id: int, db: Session = Depends(get_db)):
    """Génère la lettre de motivation adaptée à l'offre via la session locale Claude Code."""
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offre introuvable")
    if not cli_available():
        raise HTTPException(
            503,
            "CLI Claude Code introuvable sur ce poste. Vérifie que la commande « claude » "
            "fonctionne dans un terminal, ou édite la lettre manuellement.",
        )
    profile = db.get(Profile, 1)
    letter = ai_cover_letter(
        {
            "title": offer.title,
            "company": offer.company,
            "location": offer.location,
            "description": offer.description,
        },
        profile.cv_text,
        profile.letter_template,
    )
    if not letter:
        raise HTTPException(502, "La génération a échoué (voir les logs). Réessaie ou édite la lettre manuellement.")
    offer.cover_letter = letter.strip()
    db.commit()
    return offer


@router.post("/{offer_id}/enrich", response_model=OfferDetail)
def enrich_offer(offer_id: int, db: Session = Depends(get_db)):
    """Récupère la description complète depuis la page d'origine de l'offre, puis re-score."""
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offre introuvable")
    text = fetch_full_description(offer.url)
    if not text:
        raise HTTPException(
            502,
            "Impossible de récupérer la description depuis le site d'origine "
            "(page protégée ou indisponible). Ouvre l'offre sur le site via le bouton dédié.",
        )
    if len(text) <= len(offer.description or ""):
        raise HTTPException(409, "La description actuelle est déjà aussi complète que la page d'origine.")

    offer.description = text
    # L'avis IA portait sur l'ancien extrait : on le retire, le prochain scan
    # (ou la prochaine évaluation) le recalculera sur le texte complet.
    offer.ai_score = None
    offer.ai_reason = ""
    from ..services.scan import profile_to_dict, rescore_offer

    profile = db.get(Profile, 1)
    rescore_offer(offer, profile_to_dict(profile))
    db.commit()
    return offer


@router.get("/{offer_id}/letter.docx")
def letter_docx(offer_id: int, db: Session = Depends(get_db)):
    """Exporte la lettre de motivation de l'offre au format Word."""
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offre introuvable")
    if not (offer.cover_letter or "").strip():
        raise HTTPException(400, "Aucune lettre pour cette offre : génère-la ou écris-la d'abord.")

    from docx import Document
    from docx.shared import Pt

    profile = db.get(Profile, 1)
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    header = doc.add_paragraph()
    run = header.add_run(profile.full_name or "")
    run.bold = True
    if profile.email:
        header.add_run(f"\n{profile.email}")

    title = f"Candidature — {offer.title}"
    if offer.company:
        title += f" · {offer.company}"
    doc.add_paragraph(title).runs[0].bold = True
    doc.add_paragraph("")

    for paragraph in offer.cover_letter.split("\n\n"):
        if paragraph.strip():
            doc.add_paragraph(paragraph.strip())

    buffer = io.BytesIO()
    doc.save(buffer)

    safe_company = re.sub(r"[^A-Za-z0-9_-]+", "_", offer.company or "offre").strip("_") or "offre"
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="lettre_{safe_company}_{offer.id}.docx"'},
    )


@router.get("/meta/statuses")
def statuses():
    return OFFER_STATUSES
