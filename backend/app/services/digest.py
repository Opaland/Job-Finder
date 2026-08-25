"""Construction du point quotidien (digest) : nouvelles offres classées + état des lieux."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, load_only

from ..models import (
    STATUS_LABELS,
    STATUTS_CLOS,
    STATUTS_EN_ATTENTE,
    STATUTS_NON_TRAITES,
    Digest,
    Offer,
    Profile,
    ScanRun,
    local_now,
)
from .emailer import send_email, smtp_configured
from .textutils import parse_iso_dt

logger = logging.getLogger("jobfinder.digest")


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

# Une « pépite » : offre ouverte non traitée dont le score atteint ce seuil.
GEM_SCORE = 85


def gems(db: Session) -> list[Offer]:
    """Les meilleures offres pas encore traitées — à regarder en priorité."""
    return (
        db.query(Offer)
        .filter(Offer.final_score >= GEM_SCORE, Offer.status.in_(STATUTS_NON_TRAITES))
        .order_by(Offer.final_score.desc())
        .limit(10)
        .all()
    )


def applications_this_week(db: Session) -> int:
    """Nombre d'offres postulées depuis lundi (d'après l'historique des statuts)."""
    now = local_now()
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    count = 0
    # Seule la colonne d'historique est lue : inutile de matérialiser les offres.
    for (history,) in db.query(Offer.status_history).filter(
        Offer.status.notin_(STATUTS_NON_TRAITES)
    ).all():
        for entry in history or []:
            if entry.get("status") != "postulee":
                continue
            applied = parse_iso_dt(entry.get("date"))
            if applied is not None and applied >= monday:
                count += 1
                break
    return count


def _last_status_change(offer: Offer) -> datetime | None:
    history = offer.status_history or []
    if not history:
        return None
    return parse_iso_dt(history[-1].get("date"))


def offers_to_relaunch(db: Session) -> list[Offer]:
    """Candidatures envoyées restées sans suite depuis RELAUNCH_AFTER_DAYS jours."""
    cutoff = local_now() - timedelta(days=RELAUNCH_AFTER_DAYS)
    candidates = (
        db.query(Offer)
        .options(load_only(
            Offer.id, Offer.title, Offer.company, Offer.location, Offer.contract_type,
            Offer.source, Offer.url, Offer.final_score, Offer.ai_reason, Offer.remote,
            Offer.status, Offer.status_history,
        ))
        .filter(Offer.status.in_(STATUTS_EN_ATTENTE))
        .all()
    )
    result = []
    for offer in candidates:
        changed = _last_status_change(offer)
        if changed is not None and changed <= cutoff:
            result.append(offer)
    result.sort(key=lambda o: -o.final_score)
    return result


def next_interviews(db: Session, jours: int = 21) -> list[dict]:
    """Entretiens à venir (aujourd'hui inclus), le plus proche d'abord."""
    debut = local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    fin = debut + timedelta(days=jours)
    a_venir = []
    for offer in db.query(Offer).all():
        for entretien in offer.interviews or []:
            quand = parse_iso_dt(entretien.get("date"))
            if quand is None or not (debut <= quand <= fin):
                continue
            a_venir.append({
                **_offer_brief(offer),
                "status": offer.status,
                "date": quand.isoformat(),
                "format": entretien.get("format", ""),
                "interlocuteur": entretien.get("interlocuteur", ""),
                "aujourdhui": quand.date() == debut.date(),
            })
    a_venir.sort(key=lambda e: e["date"])
    return a_venir


def actions_due(db: Session) -> list[dict]:
    """Actions datées arrivées à échéance (aujourd'hui inclus), les plus urgentes d'abord."""
    end_of_today = local_now().replace(hour=23, minute=59, second=59, microsecond=0)
    start_of_today = local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    offers = (
        db.query(Offer)
        .filter(Offer.next_action_date.isnot(None), Offer.next_action_date <= end_of_today)
        .order_by(Offer.next_action_date)
        .all()
    )
    return [
        {
            **_offer_brief(o),
            "status": o.status,
            "action_date": o.next_action_date.isoformat(),
            "action_note": o.next_action_note or "",
            "overdue": o.next_action_date < start_of_today,
        }
        for o in offers
    ]


def daily_focus(
    db: Session,
    todo: list[dict] | None = None,
    gem_list: list[Offer] | None = None,
    relaunch: list[Offer] | None = None,
) -> list[dict]:
    """Les 3 actions du jour qui comptent, par priorité décroissante.

    1. L'action datée échue la plus ancienne · 2. La meilleure pépite non
    traitée · 3. La relance due la plus ancienne · 4. À défaut, postuler à la
    meilleure offre en attente. Une même offre n'apparaît qu'une fois.
    Les listes déjà calculées par l'appelant sont réutilisées telles quelles.
    """
    todo = actions_due(db) if todo is None else todo
    gem_list = gems(db) if gem_list is None else gem_list
    relaunch = offers_to_relaunch(db) if relaunch is None else relaunch

    focus: list[dict] = []
    used: set[int] = set()

    def push(kind: str, label: str, brief: dict):
        if brief["id"] in used or len(focus) >= 3:
            return
        used.add(brief["id"])
        focus.append({"type": kind, "label": label, **brief})

    for action in todo:
        note = action["action_note"] or "Action prévue"
        prefix = "En retard : " if action["overdue"] else "Aujourd'hui : "
        push("action", prefix + note, action)
        if len(focus) >= 3:
            return focus

    for gem in gem_list[:1]:
        brief = _offer_brief(gem)
        push("pepite", f"Étudie cette pépite (score {brief['final_score']:.0f})", brief)

    for offer in relaunch[:1]:
        push("relance", "Relance cette candidature restée sans réponse", _offer_brief(offer))

    if len(focus) < 3:
        best_waiting = (
            db.query(Offer)
            .filter(Offer.status.in_(STATUTS_NON_TRAITES))
            .order_by(Offer.final_score.desc())
            .first()
        )
        if best_waiting:
            push("objectif", "Avance vers ton objectif : postule à cette offre", _offer_brief(best_waiting))

    return focus


def build_digest(db: Session, for_date: str | None = None) -> Digest:
    """Construit (ou reconstruit) le digest du jour."""
    date_str = for_date or local_now().strftime("%Y-%m-%d")
    since = local_now() - timedelta(hours=26)

    new_offers = (
        db.query(Offer)
        .filter(Offer.collected_at >= since)
        .order_by(Offer.final_score.desc())
        .all()
    )
    top_overall = (
        db.query(Offer)
        .filter(Offer.status.notin_(STATUTS_CLOS))
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
    # Calculées une seule fois, réutilisées par le payload ET le focus du jour.
    todo = actions_due(db)
    gem_list = gems(db)
    relaunch = offers_to_relaunch(db)

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
            {**_offer_brief(o), "status": o.status} for o in relaunch
        ],
        "gems": [_offer_brief(o) for o in gem_list],
        "todo_today": todo,
        "interviews": next_interviews(db),
        "focus": daily_focus(db, todo=todo, gem_list=gem_list, relaunch=relaunch),
        "weekly": {
            "goal": (db.get(Profile, 1).weekly_goal if db.get(Profile, 1) else 5) or 0,
            "sent": applications_this_week(db),
        },
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
        digest.created_at = local_now()
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

{f'''<h3>🎯 Focus du jour</h3>
<ol style="margin-top:4px">{''.join(
    f"<li style='margin-bottom:6px'><b>{f['label']}</b><br>"
    f"<a href='{f['url']}'>{f['title']}</a> <span style='color:#57606a'>— {f['company']}</span></li>"
    for f in payload["focus"]
)}</ol>''' if payload.get("focus") else ''}

{f'''<h3 style="color:#0969da">🗓️ À faire aujourd'hui ({len(payload["todo_today"])})</h3>
<table style="border-collapse:collapse;width:100%" border="0">{''.join(
    f"<tr><td style='padding:6px 8px;white-space:nowrap'>{'⚠️ en retard' if a['overdue'] else 'aujourd’hui'}</td>"
    f"<td style='padding:6px 8px'><b>{a['action_note'] or 'Action prévue'}</b><br>"
    f"<a href='{a['url']}'>{a['title']}</a> <span style='color:#57606a'>— {a['company']}</span></td></tr>"
    for a in payload["todo_today"]
)}</table>''' if payload.get("todo_today") else ''}

{f'''<h3 style="color:#1a7f37">💎 Pépites à regarder en priorité ({len(payload["gems"])})</h3>
<p style="color:#57606a;margin-top:0">Score ≥ {GEM_SCORE}, pas encore traitées.</p>
<table style="border-collapse:collapse;width:100%" border="0">{rows(payload["gems"])}</table>''' if payload.get("gems") else ''}

{f'''<p><b>Objectif de la semaine :</b> {payload["weekly"]["sent"]} / {payload["weekly"]["goal"]} candidature(s) envoyée(s){' ✅' if payload["weekly"]["sent"] >= payload["weekly"]["goal"] > 0 else ''}</p>''' if payload.get("weekly", {}).get("goal") else ''}

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
