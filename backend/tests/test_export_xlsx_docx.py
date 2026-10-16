"""Contenu réel des exports xlsx/docx (issue #8) : jusqu'ici seule leur présence
en mode démo était vérifiée (test_demo_couverture.py), jamais ce qu'ils contiennent.
"""
import io

from openpyxl import load_workbook

from app.models import Offer


def _offre(db, **champs):
    base = {"fingerprint": f"fp-{champs.get('source_id', '1')}", "source": "apec",
            "source_id": "1", "title": "Test Manager", "company": "ACME",
            "final_score": 88.0, "status": "nouvelle"}
    base.update(champs)
    db.add(Offer(**base))
    db.commit()


def test_export_xlsx_contenu_et_tri_par_score(client, db):
    _offre(db, source_id="1", title="Moins bonne offre", final_score=40.0)
    _offre(db, source_id="2", title="Meilleure offre", final_score=90.0)

    resp = client.get("/api/offers/export.xlsx")
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active

    entetes = [c.value for c in ws[1]]
    assert entetes[:3] == ["Score", "Titre", "Entreprise"]
    # Triée par score décroissant : la meilleure offre d'abord.
    assert ws.cell(row=2, column=2).value == "Meilleure offre"
    assert ws.cell(row=2, column=1).value == 90
    assert ws.cell(row=3, column=2).value == "Moins bonne offre"


def test_export_xlsx_neutralise_un_titre_qui_ressemble_a_une_formule(client, db):
    """Seule protection anti-injection du classeur Excel : `cell.data_type = "s"`
    force une lecture en texte plutôt qu'en formule à l'ouverture. Sans elle,
    un titre scrapé commençant par « = » s'exécuterait dans Excel."""
    _offre(db, source_id="inj", title="=1+1")
    resp = client.get("/api/offers/export.xlsx")
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    cellule = ws.cell(row=2, column=2)
    assert cellule.value == "=1+1"       # valeur intacte...
    assert cellule.data_type == "s"      # ...mais explicitement du texte, jamais une formule


def test_lettre_docx_404_si_offre_introuvable(client, db):
    assert client.get("/api/offers/999/letter.docx").status_code == 404


def test_lettre_docx_400_si_aucune_lettre(client, db):
    _offre(db, cover_letter="")
    offre = db.query(Offer).one()
    assert client.get(f"/api/offers/{offre.id}/letter.docx").status_code == 400


def test_lettre_docx_contenu_reel(client, db):
    from docx import Document

    _offre(db, title="Test Manager Santé", company="ACME Santé",
           cover_letter="Madame, Monsieur,\n\nPremier paragraphe de la lettre.\n\nCordialement.")
    offre = db.query(Offer).one()

    resp = client.get(f"/api/offers/{offre.id}/letter.docx")
    assert resp.status_code == 200
    assert "ACME_Sant" in resp.headers["content-disposition"]  # nom de fichier assaini

    doc = Document(io.BytesIO(resp.content))
    texte = "\n".join(p.text for p in doc.paragraphs)
    assert "Test Manager Santé" in texte and "ACME Santé" in texte
    assert "Premier paragraphe de la lettre." in texte
    assert "Cordialement." in texte
