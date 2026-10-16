"""POST /api/offers/bulk-reject : seul outil de masse contre la pile d'offres
jamais triées qui grossit sans fin (issue #30).
"""
from app.models import Offer


def _offre(db, source_id, score, status="nouvelle", source="apec"):
    db.add(Offer(fingerprint=f"fp-{source_id}", source=source, source_id=source_id,
                 title="QA", company="ACME", final_score=score, status=status))
    db.commit()


def test_rejette_seulement_les_offres_sous_le_score(client, db):
    _offre(db, "1", 20.0)
    _offre(db, "2", 60.0)
    resp = client.post("/api/offers/bulk-reject", params={"max_score": 45})
    assert resp.status_code == 200
    assert resp.json() == {"rejected": 1}
    assert db.query(Offer).filter_by(source_id="1").one().status == "fermee"
    assert db.query(Offer).filter_by(source_id="2").one().status == "nouvelle"


def test_ne_retouche_jamais_une_offre_deja_close(client, db):
    _offre(db, "3", 10.0, status="refusee")
    resp = client.post("/api/offers/bulk-reject", params={"max_score": 100})
    assert resp.json() == {"rejected": 0}
    assert db.query(Offer).filter_by(source_id="3").one().status == "refusee"


def test_respecte_les_filtres_comme_la_liste(client, db):
    _offre(db, "4", 20.0, source="apec")
    _offre(db, "5", 20.0, source="hellowork")
    resp = client.post("/api/offers/bulk-reject", params={"max_score": 100, "source": "apec"})
    assert resp.json() == {"rejected": 1}
    assert db.query(Offer).filter_by(source_id="4").one().status == "fermee"
    assert db.query(Offer).filter_by(source_id="5").one().status == "nouvelle"


def test_garde_une_trace_dans_l_historique(client, db):
    _offre(db, "6", 10.0)
    client.post("/api/offers/bulk-reject", params={"max_score": 50})
    offre = db.query(Offer).filter_by(source_id="6").one()
    assert offre.status_history[-1]["par"] == "rejet en masse"


def test_max_score_obligatoire(client, db):
    resp = client.post("/api/offers/bulk-reject")
    assert resp.status_code == 422


def test_filtre_still_online(client, db):
    db.add(Offer(fingerprint="fp-7", source="apec", source_id="7", title="QA", company="ACME",
                 final_score=10.0, status="nouvelle", still_online=True))
    db.add(Offer(fingerprint="fp-8", source="apec", source_id="8", title="QA", company="ACME",
                 final_score=10.0, status="nouvelle", still_online=False))
    db.commit()
    resp = client.post("/api/offers/bulk-reject", params={"max_score": 100, "still_online": False})
    assert resp.json() == {"rejected": 1}
    assert db.query(Offer).filter_by(source_id="7").one().status == "nouvelle"
    assert db.query(Offer).filter_by(source_id="8").one().status == "fermee"


def test_liste_filtre_aussi_par_still_online(client, db):
    db.add(Offer(fingerprint="fp-9", source="apec", source_id="9", title="QA", company="ACME",
                 final_score=50.0, still_online=True))
    db.add(Offer(fingerprint="fp-10", source="apec", source_id="10", title="QA", company="ACME",
                 final_score=50.0, still_online=False))
    db.commit()
    resp = client.get("/api/offers", params={"still_online": False})
    assert resp.json()["total"] == 1
