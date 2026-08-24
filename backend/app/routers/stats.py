"""Statistiques de la recherche d'emploi + sauvegarde de la base."""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import OFFER_STATUSES, Offer, utcnow

router = APIRouter(prefix="/api", tags=["statistiques"])

SOURCE_LABELS = {
    "france_travail": "France Travail",
    "adzuna": "Adzuna",
    "jsearch": "LinkedIn / Indeed",
    "wttj": "Welcome to the Jungle",
    "apec": "APEC",
    "hellowork": "HelloWork",
}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    now = utcnow()
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
        .filter(Offer.status.notin_(["refusee", "fermee"]))
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
    }


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

    stamp = utcnow().strftime("%Y-%m-%d_%H%M")
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="jobfinder_sauvegarde_{stamp}.db"'},
    )
