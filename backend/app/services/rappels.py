"""Rappels de la veille : entretien ou action datée prévus demain.

Le digest du matin dit ce qu'il y a à faire aujourd'hui ; ce rappel-ci part la
veille, pour laisser le temps de préparer un entretien.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session, load_only

from ..models import STATUTS_CLOS, Offer, local_now
from .emailer import send_email, smtp_configured
from .textutils import parse_iso_dt

logger = logging.getLogger("jobfinder.rappels")


def echeances_de_demain(db: Session) -> dict:
    """Entretiens et actions datées prévus demain."""
    demain = (local_now() + timedelta(days=1)).date()
    entretiens, actions = [], []

    # Une offre refusée ou fermée ne mérite plus de rappel.
    for offer in db.query(Offer).options(load_only(
        Offer.id, Offer.title, Offer.company, Offer.url, Offer.interview_prep,
        Offer.interviews, Offer.next_action_date, Offer.next_action_note,
    )).filter(Offer.status.notin_(STATUTS_CLOS)).all():
        for entretien in offer.interviews or []:
            quand = parse_iso_dt(entretien.get("date"))
            if quand and quand.date() == demain:
                entretiens.append({
                    "titre": offer.title,
                    "entreprise": offer.company or "Entreprise non précisée",
                    "url": offer.url,
                    "heure": quand.strftime("%H:%M"),
                    "format": entretien.get("format", ""),
                    "interlocuteur": entretien.get("interlocuteur", ""),
                    "fiche_prete": bool((offer.interview_prep or "").strip()),
                })
        if offer.next_action_date and offer.next_action_date.date() == demain:
            actions.append({
                "titre": offer.title,
                "entreprise": offer.company or "Entreprise non précisée",
                "url": offer.url,
                "note": offer.next_action_note or "Action prévue",
            })

    entretiens.sort(key=lambda e: e["heure"])
    return {"date": demain.isoformat(), "entretiens": entretiens, "actions": actions}


def rappel_html(echeances: dict) -> str:
    """Email court : ce qui attend demain, et ce qui n'est pas encore prêt."""
    def bloc_entretien(e: dict) -> str:
        alerte = "" if e["fiche_prete"] else (
            " <span style='color:#bc4c00'>— fiche de préparation non générée</span>"
        )
        details = " · ".join(x for x in (e["format"], e["interlocuteur"]) if x)
        return (
            f"<li style='margin-bottom:8px'><b>{e['heure']}</b> — "
            f"<a href='{e['url']}'>{e['titre']}</a> chez <b>{e['entreprise']}</b>"
            f"{f' ({details})' if details else ''}{alerte}</li>"
        )

    parties = ["<html><body style=\"font-family:Segoe UI,Arial,sans-serif;color:#1f2328;max-width:640px\">",
               "<h2>Demain dans ta recherche</h2>"]
    if echeances["entretiens"]:
        parties.append(f"<h3 style='color:#1a7f37'>🗣️ Entretien(s) ({len(echeances['entretiens'])})</h3><ul>")
        parties.extend(bloc_entretien(e) for e in echeances["entretiens"])
        parties.append("</ul>")
    if echeances["actions"]:
        parties.append(f"<h3 style='color:#0969da'>🗓️ Action(s) prévue(s) ({len(echeances['actions'])})</h3><ul>")
        parties.extend(
            f"<li><b>{a['note']}</b> — <a href='{a['url']}'>{a['titre']}</a> ({a['entreprise']})</li>"
            for a in echeances["actions"]
        )
        parties.append("</ul>")
    parties.append("<p style='color:#57606a;font-size:12px'>Rappel envoyé la veille par Job Finder.</p>")
    parties.append("</body></html>")
    return "".join(parties)


def envoyer_rappel(db: Session, echeances: dict | None = None) -> bool:
    """Envoie le rappel s'il y a quelque chose demain ET que le SMTP est configuré.

    `echeances` évite de reparcourir les offres quand l'appelant les a déjà.
    """
    echeances = echeances_de_demain(db) if echeances is None else echeances
    if not echeances["entretiens"] and not echeances["actions"]:
        return False
    if not smtp_configured():
        logger.info("Rappel de la veille : SMTP non configuré, envoi ignoré.")
        return False

    nombre = len(echeances["entretiens"]) + len(echeances["actions"])
    sujet = "Job Finder — demain : "
    if echeances["entretiens"]:
        sujet += f"{len(echeances['entretiens'])} entretien(s)"
        if echeances["actions"]:
            sujet += f" et {len(echeances['actions'])} action(s)"
    else:
        sujet += f"{nombre} action(s) prévue(s)"

    try:
        send_email(sujet, rappel_html(echeances))
        return True
    except Exception:  # noqa: BLE001 — un rappel raté ne casse rien
        logger.exception("Envoi du rappel de la veille impossible")
        return False
