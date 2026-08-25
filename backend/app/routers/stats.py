"""Statistiques de la recherche d'emploi + sauvegarde / restauration de la base."""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import engine, ensure_schema, get_db
from ..models import OFFER_STATUSES, STATUTS_CLOS, STATUTS_EN_ATTENTE, Offer, local_now
from ..services.scan import scan_status
from ..services.textutils import parse_iso_dt

router = APIRouter(prefix="/api", tags=["statistiques"])

# Libellés servis par les connecteurs eux-mêmes : une seule source de vérité.
from ..connectors import ALL_CONNECTORS

SOURCE_LABELS = {c.name: c.label for c in ALL_CONNECTORS} | {"manuelle": "Ajout manuel"}


def _company_stats(db: Session) -> list[dict]:
    """Réactivité par entreprise, calculée depuis l'historique des statuts."""
    now = local_now()
    by_company: dict[str, dict] = {}
    for company, status, status_history in db.query(
        Offer.company, Offer.status, Offer.status_history
    ).all():
        history = status_history or []
        applied = next(
            (parse_iso_dt(h.get("date")) for h in history if h.get("status") == "postulee"),
            None,
        )
        if applied is None:
            continue
        response = None
        for h in history:
            if h.get("status") not in ("entretien", "refusee"):
                continue
            dt = parse_iso_dt(h.get("date"))
            if dt is not None and dt >= applied:
                response = dt
                break
        entry = by_company.setdefault(
            company or "Entreprise non précisée",
            {"applications": 0, "responses": 0, "delays": [], "pending": []},
        )
        entry["applications"] += 1
        if response is not None:
            entry["responses"] += 1
            entry["delays"].append(max(0, (response - applied).days))
        elif status in STATUTS_EN_ATTENTE:
            entry["pending"].append(max(0, (now - applied).days))

    companies = [
        {
            "company": name,
            "applications": e["applications"],
            "responses": e["responses"],
            "avg_response_days": round(sum(e["delays"]) / len(e["delays"])) if e["delays"] else None,
            "pending_days": max(e["pending"]) if e["pending"] else None,
        }
        for name, e in by_company.items()
    ]
    companies.sort(key=lambda c: (-c["applications"], c["company"]))
    return companies[:25]


def _conversion_par_source(db: Session) -> list[dict]:
    """Ce que chaque source rapporte vraiment : candidatures, entretiens, taux."""
    par_source: dict[str, dict] = {}
    for source, statut, historique in db.query(Offer.source, Offer.status, Offer.status_history).all():
        entree = par_source.setdefault(source, {
            "source": source, "label": SOURCE_LABELS.get(source, source),
            "offres": 0, "candidatures": 0, "entretiens": 0,
        })
        entree["offres"] += 1
        statuts = {h.get("status") for h in (historique or [])} | {statut}
        if "postulee" in statuts:
            entree["candidatures"] += 1
        if "entretien" in statuts:
            entree["entretiens"] += 1

    lignes = []
    for entree in par_source.values():
        candidatures = entree["candidatures"]
        lignes.append({
            **entree,
            # Part des candidatures qui ont débouché sur un entretien.
            "taux_entretien": round(100 * entree["entretiens"] / candidatures) if candidatures else None,
        })
    lignes.sort(key=lambda s: (-(s["taux_entretien"] or -1), -s["candidatures"], s["label"]))
    return lignes


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    now = local_now()
    total = db.query(func.count(Offer.id)).scalar() or 0
    new_7d = (
        db.query(func.count(Offer.id))
        .filter(Offer.collected_at >= now - timedelta(days=7))
        .scalar()
        or 0
    )

    status_counts = dict(db.query(Offer.status, func.count(Offer.id)).group_by(Offer.status).all())
    sent = sum(status_counts.get(s, 0) for s in ("postulee", "relancee", "entretien", "refusee"))
    responses = status_counts.get("entretien", 0) + status_counts.get("refusee", 0)

    top20 = [
        s for (s,) in db.query(Offer.final_score)
        .filter(Offer.status.notin_(STATUTS_CLOS))
        .order_by(Offer.final_score.desc())
        .limit(20)
        .all()
    ]

    by_source = [
        {"source": src, "label": SOURCE_LABELS.get(src, src), "count": count}
        for src, count in db.query(Offer.source, func.count(Offer.id))
        .group_by(Offer.source)
        .order_by(func.count(Offer.id).desc())
        .all()
    ]

    bins = [0] * 10
    for (score,) in db.query(Offer.final_score).all():
        bins[min(9, int(score // 10))] += 1
    score_bins = [
        {"label": f"{i * 10}-{i * 10 + 9}" if i < 9 else "90-100", "count": count}
        for i, count in enumerate(bins)
    ]

    per_day = []
    counts_by_day: dict[str, int] = {}
    for (collected,) in db.query(Offer.collected_at).filter(
        Offer.collected_at >= now - timedelta(days=30)
    ).all():
        key = collected.strftime("%Y-%m-%d")
        counts_by_day[key] = counts_by_day.get(key, 0) + 1
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        per_day.append({"date": day, "count": counts_by_day.get(day, 0)})

    return {
        "totals": {
            "offers": total,
            "new_7d": new_7d,
            "sent": sent,
            "interviews": status_counts.get("entretien", 0),
            "response_rate": round(100 * responses / sent) if sent else None,
            "avg_top20": round(sum(top20) / len(top20), 1) if top20 else None,
        },
        "by_status": [
            {"status": s, "count": status_counts.get(s, 0)} for s in OFFER_STATUSES
        ],
        "by_source": by_source,
        "score_bins": score_bins,
        "per_day": per_day,
        "companies": _company_stats(db),
        "conversion_sources": _conversion_par_source(db),
    }


@router.get("/journal")
def journal(limit: int = 100, kind: str | None = None, db: Session = Depends(get_db)):
    """Journal d'activité : les derniers événements de l'application."""
    from ..models import ActivityLog

    query = db.query(ActivityLog)
    if kind:
        query = query.filter(ActivityLog.kind == kind)
    entries = query.order_by(ActivityLog.id.desc()).limit(min(limit, 500)).all()
    return [
        {"id": e.id, "at": e.at.isoformat(), "kind": e.kind, "message": e.message, "offer_id": e.offer_id}
        for e in entries
    ]


@router.get("/backup")
def backup():
    """Télécharge une copie cohérente de la base SQLite (API backup, sûre même en cours d'écriture)."""
    src = sqlite3.connect(settings.db_path)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        dest = sqlite3.connect(tmp_path)
        with dest:
            src.backup(dest)
        dest.close()
        content = Path(tmp_path).read_bytes()
    finally:
        src.close()
        Path(tmp_path).unlink(missing_ok=True)

    stamp = local_now().strftime("%Y-%m-%d_%H%M")
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="jobfinder_sauvegarde_{stamp}.db"'},
    )


@router.post("/restore")
async def restore(file: UploadFile):
    """Remplace la base par une sauvegarde téléversée (copie de sécurité créée avant)."""
    if scan_status().get("running"):
        raise HTTPException(409, "Un scan est en cours : attends qu'il se termine avant de restaurer.")

    content = await file.read()
    if not content.startswith(b"SQLite format 3\x00"):
        raise HTTPException(400, "Ce fichier n'est pas une base SQLite — choisis un fichier .db issu du bouton de sauvegarde.")

    # Validation du contenu avant de toucher à quoi que ce soit.
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        check = sqlite3.connect(tmp_path)
        try:
            tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"offers", "profile"} <= tables:
                raise HTTPException(400, "Cette base n'est pas une sauvegarde Job Finder (tables offres/profil absentes).")
            offer_count = check.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
        except sqlite3.DatabaseError:
            raise HTTPException(400, "Fichier SQLite illisible ou corrompu — restauration annulée.")
        finally:
            check.close()

        # Copie de sécurité de la base actuelle, puis restauration via l'API
        # backup de SQLite : le remplacement se fait page à page sous verrou
        # d'écriture, une requête concurrente voit toujours une base cohérente
        # (jamais un fichier à moitié écrit).
        db_path = Path(settings.db_path)
        safety_name = f"avant_restauration_{local_now().strftime('%Y-%m-%d_%H%M%S')}.db"
        if db_path.exists():
            current = sqlite3.connect(db_path)
            safety = sqlite3.connect(db_path.parent / safety_name)
            try:
                with safety:
                    current.backup(safety)
            finally:
                safety.close()
                current.close()

        src = sqlite3.connect(tmp_path)
        dest = sqlite3.connect(db_path)
        try:
            with dest:
                src.backup(dest)
        finally:
            dest.close()
            src.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Purge les connexions du pool puis migre la base restaurée si elle vient
    # d'une version antérieure de l'application.
    engine.dispose()
    ensure_schema(engine)

    from ..database import SessionLocal
    from ..services.journal import log_event

    session = SessionLocal()
    try:
        log_event(session, "restauration",
                  f"Base restaurée depuis une sauvegarde ({offer_count} offres) — copie de sécurité : {safety_name}.")
    finally:
        session.close()

    return {
        "restored": True,
        "offers": offer_count,
        "safety_copy": safety_name,
    }
