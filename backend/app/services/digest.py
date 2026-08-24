"""Construction du point quotidien (digest) : nouvelles offres classées + état des lieux."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Digest, Offer, ScanRun, utcnow
from .emailer import send_email, smtp_configured

logger = logging.getLogger("jobfinder.digest")

STATUS_LABELS = {
    "nouvelle": "Nouvelles",
    "vue": "Vues",
    "a_postuler": "À postuler",
    "postulee": "Postulées",
    "relancee": "Relancées",
    "entretien": "Entretiens",
    "refusee": "Refusées",
    "fermee": "Fermées",
}


def _offer_brief(offer: Offer) -> dict:
    return {
        "id": offer.id,
        "title": offer.title,
        "company": offer.company,
        "location": offer.location,
        "contract_type": offer.contract_type,
        "source": offer.source,
        "url": offer.url,
        "final_score": offer.final_score,
        "ai_reason": offer.ai_reason,
        "remote": offer.remote,
    }


# Une candidature « postulée » ou « relancée » sans changement depuis ce délai
# est signalée comme à relancer.
RELAUNCH_AFTER_DAYS = 7


def _last_status_change(offer: Offer) -> datetime | None:
    history = offer.status_history or []
    if not history:
        return None
    try:
        return datetime.fromisoformat(history[-1]["date"])
    except (KeyError, ValueError, TypeError):
        return None


def offers_to_relaunch(db: Session) -> list[Offer]:
    """Candidatures envoyées restées sans suite depuis RELAUNCH_AFTER_DAYS jours."""
    cutoff = utcnow() - timedelta(days=RELAUNCH_AFTER_DAYS)
    result = []
    for offer in db.query(Offer).filter(Offer.status.in_(["postulee", "relancee"])).all():
        changed = _last_status_change(offer)
        if changed is not None and changed <= cutoff:
            result.append(offer)
    result.sort(key=lambda o: -o.final_score)
    return result


def build_digest(db: Session, for_date: str | None = None) -> Digest:
    """Construit (ou reconstruit) le digest du jour."""
    date_str = for_date or utcnow().strftime("%Y-%m-%d")
    since = utcnow() - timedelta(hours=26)

    new_offers = (
        db.query(Offer)
        .filter(Offer.collected_at >= since)
        .order_by(Offer.final_score.desc())
        .all()
    )
    top_overall = (
        db.query(Offer)
        .filter(Offer.status.notin_(["refusee", "fermee"]))
        .order_by(Offer.final_score.desc())
        .limit(10)
        .all()
    )
    status_counts = dict(
        db.query(Offer.status, func.count(Offer.id)).group_by(Offer.status).all()
    )
    last_run = db.query(ScanRun).order_by(ScanRun.id.desc()).first()
    to_follow = (
        db.query(Offer)
        .filter(Offer.status.in_(["a_postuler", "postulee", "relancee", "entretien"]))
        .order_by(Offer.final_score.desc())
        .all()
    )

    payload = {
        "date": date_str,
        "new_count": len(new_offers),
        "new_offers": [_offer_brief(o) for o in new_offers[:25]],
        "top_overall": [_offer_brief(o) for o in top_overall],
        "status_counts": {k: status_counts.get(k, 0) for k in STATUS_LABELS},
        "total_offers": db.query(func.count(Offer.id)).scalar() or 0,
        "to_follow": [
            {**_offer_brief(o), "status": o.status} for o in to_follow[:15]
        ],
        "to_relaunch": [
            {**_offer_brief(o), "status": o.status} for o in offers_to_relaunch(db)[:10]
        ],
        "last_scan": {
            "id": last_run.id,
            "finished_at": last_run.finished_at.isoformat() if last_run and last_run.finished_at else None,
            "trigger": last_run.trigger,
            "new_count": last_run.new_count,
            "error_count": last_run.error_count,
            "source_stats": last_run.source_stats,
        } if last_run else None,
    }

    digest = db.query(Digest).filter(Digest.date == date_str).one_or_none()
    if digest:
        digest.payload = payload
        digest.created_at = utcnow()
    else:
        digest = Digest(date=date_str, payload=payload)
        db.add(digest)
    db.commit()
    return digest


def digest_html(payload: dict) -> str:
    """Rendu HTML de l'email quotidien."""
    def rows(offers: list[dict]) -> str:
        if not offers:
            return "<tr><td colspan='4' style='padding:8px;color:#888'>Rien à signaler</td></tr>"
        out = []
        for o in offers:
            badge_color = "#1a7f37" if o["final_score"] >= 70 else ("#9a6700" if o["final_score"] >= 45 else "#57606a")
            remote = " · télétravail" if o.get("remote") else ""
            out.append(
                f"<tr>"
                f"<td style='padding:6px 8px;white-space:nowrap'><b style='color:{badge_color}'>{o['final_score']:.0f}</b></td>"
                f"<td style='padding:6px 8px'><a href='{o['url']}'>{o['title']}</a><br>"
                f"<span style='color:#57606a'>{o['company']} — {o['location']}{remote}</span></td>"
                f"<td style='padding:6px 8px'>{o.get('contract_type') or ''}</td>"
                f"<td style='padding:6px 8px'>{o['source']}</td>"
                f"</tr>"
            )
        return "".join(out)

    counts = payload.get("status_counts", {})
    counts_html = " · ".join(
        f"{STATUS_LABELS.get(k, k)} : <b>{v}</b>" for k, v in counts.items() if v
    ) or "Aucune offre pour l'instant"

    scan = payload.get("last_scan") or {}
    errors = scan.get("error_count", 0)
    scan_line = (
        f"Dernier scan : {scan.get('new_count', 0)} nouvelle(s) offre(s), {errors} erreur(s) de source."
        if scan else "Aucun scan effectué pour l'instant."
    )

    return f"""
<html><body style="font-family:Segoe UI,Arial,sans-serif;color:#1f2328;max-width:760px">
<h2 style="margin-bottom:2px">Job Finder — point du {payload['date']}</h2>
<p style="color:#57606a;margin-top:0">{scan_line}</p>

<h3>Nouvelles offres ({payload['new_count']})</h3>
<table style="border-collapse:collapse;width:100%" border="0">{rows(payload.get('new_offers', []))}</table>

<h3>Top 10 des offres ouvertes</h3>
<table style="border-collapse:collapse;width:100%" border="0">{rows(payload.get('top_overall', []))}</table>

{f'''<h3 style="color:#bc4c00">Candidatures à relancer ({len(payload["to_relaunch"])})</h3>
<p style="color:#57606a;margin-top:0">Postulées ou relancées il y a plus de {RELAUNCH_AFTER_DAYS} jours, sans changement depuis.</p>
<table style="border-collapse:collapse;width:100%" border="0">{rows(payload["to_relaunch"])}</table>''' if payload.get("to_relaunch") else ''}

<h3>État des lieux</h3>
<p>{counts_html}</p>
<p style="color:#57606a">Total : {payload.get('total_offers', 0)} offre(s) suivie(s). Aucune offre n'est jamais fermée automatiquement.</p>

<p style="color:#57606a;font-size:12px">Ouvre l'application pour classer, annoter et générer tes lettres de motivation.</p>
</body></html>
"""


def send_digest_email(db: Session, digest: Digest) -> bool:
    """Envoie le digest par email si le SMTP est configuré. Renvoie True si envoyé."""
    if not smtp_configured():
        return False
    subject = f"Job Finder — {digest.payload.get('new_count', 0)} nouvelle(s) offre(s) le {digest.date}"
    try:
        send_email(subject, digest_html(digest.payload))
        digest.email_sent = True
        db.commit()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Envoi de l'email du digest impossible")
        return False
