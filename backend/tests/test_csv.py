"""Sprint 30 : import / export CSV du suivi."""
import io

from app.models import Offer


def _offre(db, source_id="c1", titre="Test Manager", entreprise="ACME", statut="postulee"):
    db.add(Offer(fingerprint=f"fp-{source_id}", source="apec", source_id=source_id,
                 title=titre, company=entreprise, location="Lyon", contract_type="CDI",
                 salary_text="50 000 €", remote=True, status=statut, final_score=88.0,
                 notes="Bon contact"))
    db.commit()


def test_export_csv(client, db):
    _offre(db)
    resp = client.get("/api/exports/offres.csv")
    assert resp.status_code == 200
    texte = resp.content.decode("utf-8-sig")
    lignes = texte.strip().splitlines()
    assert lignes[0].startswith("titre;entreprise")
    assert "Test Manager;ACME;Lyon;CDI;50 000 €;oui;Postulée;88" in lignes[1]


def test_import_ajoute_les_offres(client, db):
    csv_texte = (
        "titre;entreprise;lieu;contrat;statut;url\n"
        "QA Lead;Beta Corp;Villeurbanne;CDI;À postuler;https://exemple.fr/1\n"
    )
    resp = client.post("/api/exports/offres.csv",
                       files={"file": ("suivi.csv", csv_texte.encode("utf-8"), "text/csv")})
    assert resp.status_code == 200
    assert resp.json() == {"ajoutees": 1, "doublons": 0, "ignorees": 0}
    offre = db.query(Offer).filter(Offer.title == "QA Lead").one()
    assert offre.status == "a_postuler"      # libellé français reconnu
    assert offre.source == "import"
    assert offre.final_score > 0             # scorée à l'import


def test_import_ignore_les_doublons(client, db):
    _offre(db, titre="Test Manager", entreprise="ACME")
    csv_texte = "titre;entreprise\nTest Manager;ACME\n"
    resp = client.post("/api/exports/offres.csv",
                       files={"file": ("s.csv", csv_texte.encode("utf-8"), "text/csv")})
    assert resp.json()["doublons"] == 1
    assert resp.json()["ajoutees"] == 0


def test_import_lignes_sans_titre_ignorees(client, db):
    csv_texte = "titre;entreprise\n;Sans titre\nQA;ACME\n"
    resp = client.post("/api/exports/offres.csv",
                       files={"file": ("s.csv", csv_texte.encode("utf-8"), "text/csv")})
    assert resp.json() == {"ajoutees": 1, "doublons": 0, "ignorees": 1}


def test_import_separateur_virgule(client, db):
    csv_texte = "titre,entreprise\nQA Engineer,Gamma\n"
    resp = client.post("/api/exports/offres.csv",
                       files={"file": ("s.csv", csv_texte.encode("utf-8"), "text/csv")})
    assert resp.json()["ajoutees"] == 1


def test_import_fichier_invalide(client, db):
    resp = client.post("/api/exports/offres.csv",
                       files={"file": ("x.csv", b"nimporte;quoi\n1;2\n", "text/csv")})
    assert resp.status_code == 400
    assert "titre" in resp.json()["detail"]


def test_import_fichier_vide(client, db):
    resp = client.post("/api/exports/offres.csv", files={"file": ("x.csv", b"  ", "text/csv")})
    assert resp.status_code == 400


def test_doublon_dans_le_meme_fichier(client, db):
    """Deux lignes identiques dans un seul CSV ne doivent créer qu'une offre."""
    csv_texte = "titre;entreprise\nQA Lead;Beta Corp\nQA Lead;Beta Corp\n"
    resp = client.post("/api/exports/offres.csv",
                       files={"file": ("s.csv", csv_texte.encode("utf-8"), "text/csv")})
    assert resp.json() == {"ajoutees": 1, "doublons": 1, "ignorees": 0}
    assert db.query(Offer).filter(Offer.title == "QA Lead").count() == 1


def test_doublon_par_titre_similaire_dans_le_meme_fichier(client, db):
    """Même règle que le scan : « H/F » et la casse ne créent pas un doublon."""
    csv_texte = "titre;entreprise\nTest Manager;ACME\nTest Manager H/F;acme\n"
    resp = client.post("/api/exports/offres.csv",
                       files={"file": ("s.csv", csv_texte.encode("utf-8"), "text/csv")})
    assert resp.json()["ajoutees"] == 1
    assert resp.json()["doublons"] == 1
