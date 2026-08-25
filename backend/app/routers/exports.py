"""Exports : justificatif de recherche d'emploi, échanges CSV."""
import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OFFER_STATUSES, STATUS_LABELS, Offer, Profile, local_now
from ..services.justificatif import justificatif_pdf
from ..services.journal import log_event
from ..services.scan import find_twin, profile_to_dict, rescore_offer
from ..services.textutils import fingerprint

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


# Colonnes du CSV, dans l'ordre. Ce sont aussi celles acceptées à l'import.
CSV_COLONNES = [
    "titre", "entreprise", "lieu", "contrat", "salaire", "teletravail",
    "statut", "score", "source", "publiee_le", "url", "notes",
]


@router.get("/offres.csv")
def export_csv(db: Session = Depends(get_db)):
    """Export CSV du suivi (séparateur « ; », UTF-8 avec BOM pour Excel FR)."""
    tampon = io.StringIO()
    writer = csv.writer(tampon, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLONNES)
    for o in db.query(
        Offer.title, Offer.company, Offer.location, Offer.contract_type, Offer.salary_text,
        Offer.remote, Offer.status, Offer.final_score, Offer.source, Offer.published_at,
        Offer.url, Offer.notes,
    ).order_by(Offer.final_score.desc()).all():
        writer.writerow([
            o.title, o.company, o.location, o.contract_type, o.salary_text,
            "oui" if o.remote else "non", STATUS_LABELS.get(o.status, o.status),
            round(o.final_score), o.source,
            o.published_at.strftime("%d/%m/%Y") if o.published_at else "",
            o.url, o.notes,
        ])
    return Response(
        content="\ufeff" + tampon.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="job_finder_offres.csv"'},
    )


@router.post("/offres.csv")
async def import_csv(file: UploadFile, db: Session = Depends(get_db)):
    """Importe un suivi tenu ailleurs. Les doublons connus sont ignorés, pas écrasés."""
    contenu = (await file.read()).decode("utf-8-sig", errors="replace")
    if not contenu.strip():
        raise HTTPException(400, "Fichier vide : exporte d'abord un CSV pour voir le format attendu.")

    dialecte = ";" if contenu.count(";") >= contenu.count(",") else ","
    lignes = list(csv.DictReader(io.StringIO(contenu), delimiter=dialecte))
    if not lignes or "titre" not in {c.lower() for c in (lignes[0] or {})}:
        raise HTTPException(
            400,
            "Colonnes attendues introuvables. La première ligne doit contenir au moins "
            "« titre » (voir le CSV exporté par l'application).",
        )

    profile = db.get(Profile, 1)
    profile_dict = profile_to_dict(profile)
    libelle_vers_statut = {v.lower(): k for k, v in STATUS_LABELS.items()}

    ajoutees, doublons, ignorees = 0, 0, 0
    for ligne in lignes:
        valeurs = {(cle or "").strip().lower(): (valeur or "").strip() for cle, valeur in ligne.items()}
        titre = valeurs.get("titre", "")
        if not titre:
            ignorees += 1
            continue
        entreprise = valeurs.get("entreprise", "")
        if find_twin(db, titre, entreprise):
            doublons += 1
            continue

        statut_brut = valeurs.get("statut", "").lower()
        statut = statut_brut if statut_brut in OFFER_STATUSES else libelle_vers_statut.get(statut_brut, "nouvelle")
        offer = Offer(
            fingerprint=fingerprint(titre, entreprise),
            source="import",
            source_id=f"import-{local_now().strftime('%Y%m%d%H%M%S%f')}-{ajoutees}",
            title=titre[:300],
            company=entreprise[:200],
            location=valeurs.get("lieu", "")[:200],
            contract_type=valeurs.get("contrat", "")[:60],
            salary_text=valeurs.get("salaire", "")[:200],
            remote=valeurs.get("teletravail", "").lower() in ("oui", "true", "1", "yes"),
            url=valeurs.get("url", ""),
            notes=valeurs.get("notes", ""),
            description=valeurs.get("description", ""),
            status=statut,
            status_history=[{"status": statut, "date": local_now().isoformat(), "par": "import CSV"}],
        )
        rescore_offer(offer, profile_dict)
        db.add(offer)
        ajoutees += 1

    db.commit()
    log_event(db, "import", f"Import CSV : {ajoutees} offre(s) ajoutée(s), "
                            f"{doublons} doublon(s) ignoré(s), {ignorees} ligne(s) sans titre.")
    return {"ajoutees": ajoutees, "doublons": doublons, "ignorees": ignorees}
