"""Justificatif de recherche d'emploi (PDF) — actes de recherche sur une période.

France Travail demande de pouvoir justifier ses démarches. Ce document liste
les candidatures envoyées, les relances et les entretiens tels qu'ils ont été
suivis dans l'application, avec la date de chaque acte.
"""
from __future__ import annotations

import io
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..models import Offer, Profile, local_now
from .textutils import parse_iso_dt

# Libellés des actes, dans l'ordre de priorité d'affichage d'une même journée.
ACTES = {"postulee": "Candidature envoyée", "relancee": "Relance", "entretien": "Entretien"}


def actes_de_recherche(db: Session, depuis: date, jusqu_a: date) -> list[dict]:
    """Liste datée des démarches, la plus récente d'abord."""
    debut = datetime.combine(depuis, datetime.min.time())
    fin = datetime.combine(jusqu_a, datetime.max.time())
    actes: list[dict] = []

    for offer in db.query(Offer).all():
        commun = {
            "entreprise": offer.company or "Entreprise non précisée",
            "poste": offer.title,
            "source": offer.source,
        }
        for entree in offer.status_history or []:
            statut = entree.get("statut") or entree.get("status")
            if statut not in ("postulee", "relancee"):
                continue
            quand = parse_iso_dt(entree.get("date"))
            if quand and debut <= quand <= fin:
                actes.append({**commun, "date": quand, "acte": ACTES[statut]})

        for entretien in offer.interviews or []:
            quand = parse_iso_dt(entretien.get("date"))
            if quand and debut <= quand <= fin:
                detail = entretien.get("format") or ""
                actes.append({
                    **commun, "date": quand,
                    "acte": ACTES["entretien"] + (f" ({detail})" if detail else ""),
                })

    actes.sort(key=lambda a: a["date"], reverse=True)
    return actes


def justificatif_pdf(db: Session, depuis: date, jusqu_a: date) -> bytes:
    """Rend le justificatif en PDF (A4, une ligne par démarche)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    profile = db.get(Profile, 1)
    actes = actes_de_recherche(db, depuis, jusqu_a)
    resume = {libelle: 0 for libelle in ACTES.values()}
    for acte in actes:
        cle = acte["acte"].split(" (")[0]
        resume[cle] = resume.get(cle, 0) + 1

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largeur, hauteur = A4
    marge = 18 * mm
    y = hauteur - marge

    def ligne(texte: str, taille: int = 10, gras: bool = False, saut: float = 5.5 * mm):
        nonlocal y
        if y < marge + 15 * mm:          # page suivante
            pdf.showPage()
            y = hauteur - marge
        pdf.setFont("Helvetica-Bold" if gras else "Helvetica", taille)
        pdf.drawString(marge, y, texte)
        y -= saut

    ligne("Justificatif de recherche d'emploi", 16, gras=True, saut=9 * mm)
    ligne(profile.full_name or "", 11, gras=True)
    if profile.email:
        ligne(profile.email, 9)
    ligne(f"Période du {depuis.strftime('%d/%m/%Y')} au {jusqu_a.strftime('%d/%m/%Y')}", 10)
    ligne(f"Document établi le {local_now().strftime('%d/%m/%Y')} — {len(actes)} démarche(s)", 9,
          saut=8 * mm)

    detail = " · ".join(f"{libelle} : {nombre}" for libelle, nombre in resume.items() if nombre)
    if detail:
        ligne(detail, 10, gras=True, saut=8 * mm)

    if not actes:
        ligne("Aucune démarche enregistrée sur cette période.", 10)
    else:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(marge, y, "Date")
        pdf.drawString(marge + 25 * mm, y, "Démarche")
        pdf.drawString(marge + 68 * mm, y, "Entreprise")
        pdf.drawString(marge + 118 * mm, y, "Poste")
        y -= 2 * mm
        pdf.line(marge, y, largeur - marge, y)
        y -= 5 * mm

        for acte in actes:
            if y < marge + 15 * mm:
                pdf.showPage()
                y = hauteur - marge
            pdf.setFont("Helvetica", 9)
            pdf.drawString(marge, y, acte["date"].strftime("%d/%m/%Y"))
            pdf.drawString(marge + 25 * mm, y, acte["acte"][:26])
            pdf.drawString(marge + 68 * mm, y, acte["entreprise"][:30])
            pdf.drawString(marge + 118 * mm, y, acte["poste"][:38])
            y -= 5 * mm

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(marge, marge - 4 * mm,
                   "Extrait du suivi personnel de recherche d'emploi (application Job Finder).")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
