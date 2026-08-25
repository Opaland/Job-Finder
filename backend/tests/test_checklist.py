"""Sprint 23 : checklist de candidature par offre."""
from app.models import CHECKLIST_ETAPES, Offer


def _offre(db):
    offer = Offer(fingerprint="fp-check", source="manuelle", source_id="c1",
                  title="QA Lead", company="ACME", final_score=80.0)
    db.add(offer)
    db.commit()
    return offer


def test_etapes_exposees_au_frontend(client):
    resp = client.get("/api/offers/meta/checklist")
    assert resp.status_code == 200
    assert list(resp.json()) == list(CHECKLIST_ETAPES)


def test_cocher_une_etape(client, db):
    offer = _offre(db)
    resp = client.patch(f"/api/offers/{offer.id}", json={"checklist": {"cv_adapte": True}})
    assert resp.status_code == 200
    assert resp.json()["checklist"] == {"cv_adapte": True}


def test_etapes_inconnues_ignorees(client, db):
    """La checklist reste comparable d'une offre à l'autre."""
    offer = _offre(db)
    resp = client.patch(f"/api/offers/{offer.id}", json={
        "checklist": {"cv_adapte": True, "invente": True},
    })
    assert "invente" not in resp.json()["checklist"]


def test_valeurs_forcees_en_booleen_et_etapes_conservees(client, db):
    offer = _offre(db)
    client.patch(f"/api/offers/{offer.id}", json={"checklist": {"cv_adapte": True}})
    resp = client.patch(f"/api/offers/{offer.id}", json={"checklist": {"envoyee": "oui"}})
    checklist = resp.json()["checklist"]
    assert checklist["envoyee"] is True          # "oui" -> booléen
    assert checklist["cv_adapte"] is True        # étape déjà cochée conservée


def test_checklist_visible_dans_la_liste(client, db):
    offer = _offre(db)
    client.patch(f"/api/offers/{offer.id}", json={"checklist": {"cv_adapte": True}})
    item = client.get("/api/offers").json()["items"][0]
    assert item["checklist"] == {"cv_adapte": True}
