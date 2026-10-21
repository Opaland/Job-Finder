"""Génère les PDF de test (contenu fictif, aucun texte ISTQB) : `python tests/fixtures/generer.py`.

Les PDF produits sont versionnés ; ce script documente comment ils ont été faits et
permet de les régénérer (reportlab requis, uniquement pour cette génération).
Ils reproduisent les pièges rencontrés dans les vrais syllabus : en-tête répété avec
« Page N of M », table des matières à pointillés, liste numérotée dans le préambule,
objectifs d'apprentissage qui répètent les titres, index final."""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ICI = Path(__file__).parent


def page(c, n, total, version, date, lignes):
    c.setFont("Helvetica", 9)
    c.drawString(50, 810, f"Version {version}   Page {n} of {total}   {date}")
    c.drawString(50, 30, "© Fictional Testing Board")
    c.setFont("Helvetica", 11)
    y = 770
    for l in lignes:
        c.drawString(50, y, l)
        y -= 16
    c.showPage()


def generer(nom, version, date, variante=""):
    pages = [
        ["Certified Tester", "Foundation Level Syllabus", f"Version {version}"],
        ["Table of Contents"] + [f"{t} {'.' * 40} {p}" for t, p in
                                 (("0 Introduction", 3), ("1 Fundamentals of Testing", 3), ("1.1 Test Objectives", 4),
                                  ("1.2 Equivalence Partitioning", 5), ("2 Risk Management", 6))],
        ["0 Introduction", "0.1 Purpose of this Document", "This document is provided as follows:",
         "1. To national boards, to translate into their local language", "2. To exam boards, to derive questions",
         "3. To training providers, to produce courseware", "1 Fundamentals of Testing", "Learning objectives:",
         "1.1 Test Objectives", "1.2 Equivalence Partitioning"],
        ["1.1 Test Objectives", "Typical test objectives are evaluating work products, triggering failures",
         "and finding defects, ensuring required coverage of a test object." + variante,
         "Testing also reduces the level of risk of inadequate software quality."],
        ["1.2 Equivalence Partitioning", "Equivalence partitioning divides data into partitions such that all",
         "elements of a given partition are expected to be processed in the same way.",
         "1.2.1 Valid and Invalid Partitions", "A partition containing valid values is called a valid partition;",
         "boundary value analysis is often combined with this technique."],
        ["2 Risk Management", "2.1 Product Risk Analysis", "Risk level is determined by risk likelihood and risk impact.",
         "The results of product risk analysis are used for the prioritization of tests",
         "and to decide the thoroughness of testing."],
        ["Index"] + [f"{t} {p}" for t, p in (("boundary value analysis", 5), ("coverage", 4), ("defect", 4),
                                             ("equivalence partitioning", "5, 6"), ("failure", 4), ("partition", 5),
                                             ("product risk", 6), ("prioritization", 6), ("risk impact", 6),
                                             ("risk level", 6), ("risk likelihood", 6), ("test objective", 4),
                                             ("thoroughness", 6), ("valid partition", 5))],
    ]
    c = canvas.Canvas(str(ICI / nom), pagesize=A4)
    c.setTitle("Microsoft Word - fixture.docx")
    for i, lignes in enumerate(pages, 1):
        page(c, i, len(pages), version, date, lignes)
    c.save()


if __name__ == "__main__":
    generer("syllabus_v9.pdf", "9.9", "12/03/2030")
    generer("syllabus_v10.pdf", "10.0", "05/09/2031", variante=" Revised.")
