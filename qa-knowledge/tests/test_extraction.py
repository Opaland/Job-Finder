from pypdf import PdfWriter

from qak import extraction
from conftest import FIXTURES


def test_pages_entetes_retires_et_sommaires_detectes():
    x = extraction.extraire(FIXTURES / "syllabus_v9.pdf")
    assert x.statut()[0] == "ok"
    assert x.nb_pages == 7
    # L'en-tête « Version 9.9 Page N of 7 date » et le pied de page sont retirés du texte…
    assert all("Page" not in p.texte and "Fictional" not in p.texte for p in x.pages)
    # … mais conservés pour les métadonnées.
    assert "Page 1 of 7" in x.brut_debut[0]
    assert [p.numero for p in x.pages if p.sommaire] == [2, 7]  # table des matières + index


def test_plan_ignore_liste_numerotee_et_objectifs_repetes():
    x = extraction.extraire(FIXTURES / "syllabus_v9.pdf")
    plan = [(t.numero, t.titre, t.page) for t in x.plan]
    assert ("1", "Fundamentals of Testing", 3) in plan
    assert not any(t.startswith("To national boards") for _, t, _ in plan)
    # « 1.1 Test Objectives » figure dans les objectifs p. 3 ET comme vrai titre p. 4 : seul le second compte.
    assert ("1.1", "Test Objectives", 4) in plan and ("1.1", "Test Objectives", 3) not in plan


def test_passages_ne_franchissent_pas_les_pages_et_portent_leur_section():
    x = extraction.extraire(FIXTURES / "syllabus_v9.pdf")
    ps = extraction.passages(x)
    ep = [p for p in ps if "divides data into partitions" in p.texte]
    assert len(ep) == 1 and ep[0].page == 5 and ep[0].section_num == "1.2"
    valides = [p for p in ps if "valid partition;" in p.texte][0]
    assert valides.section_num == "1.2.1" and valides.page == 5
    assert all(p.page in {q.numero for q in x.pages} for p in ps)


def test_page_imprimee_differente_conservee(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("Page 10 de 12\nTexte de la première page assez long pour compter.\f"
                 "Page 11 de 12\nTexte de la seconde page assez long pour compter.", encoding="utf-8")
    x = extraction.extraire(f)
    assert [(p.numero, p.imprimee) for p in x.pages] == [(1, "10"), (2, "11")]


def test_markdown_plan_par_titres(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("# 1 Stratégie\nTexte de stratégie de test suffisamment long.\n## 1.1 Risques\nTexte sur les risques.",
                 encoding="utf-8")
    x = extraction.extraire(f)
    assert [(t.numero, t.titre) for t in x.plan] == [("1", "Stratégie"), ("1.1", "Risques")]
    assert x.plan_source == "markdown"


def test_pdf_sans_texte_signale_illisible(tmp_path):
    w = PdfWriter()
    for _ in range(4):
        w.add_blank_page(width=595, height=842)
    f = tmp_path / "scan.pdf"
    with open(f, "wb") as fh:
        w.write(fh)
    statut, message = extraction.extraire(f).statut()
    assert statut == "illisible" and "OCR" in message


def test_fichier_corrompu_et_format_inconnu(tmp_path):
    casse = tmp_path / "casse.pdf"
    casse.write_bytes(b"%PDF-1.4 pas vraiment un pdf")
    assert extraction.extraire(casse).statut()[0] == "echec"
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"PK")
    assert "format non pris en charge" in extraction.extraire(docx).statut()[1]
